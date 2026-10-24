import json
import logging
from pathlib import Path

import httpx
import pytest

from app.browser.factory import create_browser_driver
from app.browser.pinchtab_api import (
    PINCHTAB_TESTED_VERSION,
    PinchtabAPI,
    error_code,
    loopback_origin,
    parse_snapshot,
)
from app.browser.pinchtab_driver import PinchtabDriver, reconcile
from app.browser.playwright_driver import PlaywrightDriver
from app.interfaces.browser import BrowserFailure, Element, Observation
from tests.settings import IsolatedSettings

FIXTURE = Path(__file__).with_name("fixtures") / "pinchtab-0.15.2-form.json"


def test_mapping_visibility_caps_redaction_and_ambiguous_nodes() -> None:
    snapshot = parse_snapshot(json.loads(FIXTURE.read_text()))
    # Raw PinchTab content/values must not replace the default driver's safe content.
    baseline = Observation(
        generation=2,
        text_excerpt="Safe visible content",
        elements=[
            Element(
                ref="e30",
                role="textbox",
                name="Name",
                tag="input",
                type="password",
                value="[redacted]",
            ),
            Element(ref="e31", role="textbox", name="Email", tag="input"),
            Element(ref="e32", role="button", name="Hidden", tag="button"),
        ],
    )
    mapped, refs = reconcile(snapshot, baseline)
    assert refs == {"e30": "e2", "e31": "e3"}
    assert mapped.elements[0].value == "[redacted]" and mapped.generation == 2
    assert mapped.text_excerpt == "Safe visible content"
    snapshot.nodes.append(snapshot.nodes[0])
    assert "e30" not in reconcile(snapshot, baseline)[1]
    with pytest.raises(BrowserFailure, match="Unsupported"):
        parse_snapshot({})


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:9867",
        "http://192.168.1.2:9867",
        "https://127.0.0.1:9867",
        "http://localhost:9867",
        "http://user:private@127.0.0.1:9867",
        "http://127.0.0.1:9867/?token=x",
    ],
)
def test_loopback_only(url: str) -> None:
    with pytest.raises(BrowserFailure):
        loopback_origin(url)


async def test_http_failure_does_not_echo_secret_and_version_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "CANARY-PASSWORD-9137"
    settings = IsolatedSettings(pinchtab_token=secret, pinchtab_url="http://127.0.0.1:9867")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer " + secret
        if request.url.path == "/health":
            return httpx.Response(200, json={"version": "0.99.0"})
        return httpx.Response(500, json={"error": "stale reference " + secret, "code": "stale_ref"})

    api = PinchtabAPI(settings, httpx.MockTransport(handler))
    try:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(BrowserFailure, match="version mismatch"):
                await api.health("test-run")
        assert secret not in caplog.text
        with pytest.raises(BrowserFailure) as error:
            await api.snapshot("owned")
        assert error.value.code == "STALE_REF" and secret not in str(error.value)
    finally:
        await api.close()
    assert error_code(httpx.Response(503, json={"error": secret})) == "BROWSER_ERROR"
    assert PINCHTAB_TESTED_VERSION == "0.15.2"


def test_optional_flag_preserves_default_factory() -> None:
    assert isinstance(
        create_browser_driver(IsolatedSettings(browser_driver="playwright")), PlaywrightDriver
    )
    assert isinstance(
        create_browser_driver(IsolatedSettings(agent_driver="pinchtab")), PinchtabDriver
    )


@pytest.mark.parametrize("protected,anonymous", [(200, 401), (401, 401), (200, 200)])
async def test_startup_requires_authenticated_server(protected: int, anonymous: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"version": PINCHTAB_TESTED_VERSION})
        status = protected if request.headers.get("Authorization") else anonymous
        return httpx.Response(status, json=[])

    api = PinchtabAPI(
        IsolatedSettings(pinchtab_token="fake-test-token", pinchtab_url="http://127.0.0.1:9867"),
        httpx.MockTransport(handler),
    )
    try:
        if (protected, anonymous) == (200, 401):
            await api.health()
        else:
            with pytest.raises(BrowserFailure):
                await api.health()
    finally:
        await api.close()


def test_production_default_is_pinchtab(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    monkeypatch.delenv("AGENT_DRIVER", raising=False)
    settings = Settings(_env_file=None)
    assert settings.agent_driver == "pinchtab"
    assert type(create_browser_driver(settings)) is PinchtabDriver


@pytest.mark.parametrize("code,expected", [
    ("navigation_changed", "STALE_REF"),
    ("tab_paused_handoff", "BROWSER_ERROR"),
    ("unauthorized", "BROWSER_ERROR"),
])
async def test_navigation_conflict_reobserves_without_retrying_click(
    code: str, expected: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(409, json={
            "code": code, "error": "CANARY-PASSWORD-9137", "details": {"url": "private"},
        })

    api = PinchtabAPI(
        IsolatedSettings(pinchtab_token="fake-token", pinchtab_url="http://127.0.0.1:9867"),
        httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(BrowserFailure) as error:
            await api.action("fake", "click", "e1")
        assert error.value.code == expected
        assert "CANARY" not in str(error.value) and "private" not in str(error.value)
        assert calls == 1
    finally:
        await api.close()


async def test_attached_runs_have_unique_instance_names() -> None:
    names: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        names.append(json.loads(request.content)["name"])
        return httpx.Response(201, json={
            "attached": True, "url": "http://127.0.0.1:9868", "id": "fake-instance",
        })

    api = PinchtabAPI(
        IsolatedSettings(pinchtab_token="fake-token", pinchtab_url="http://127.0.0.1:9867"),
        httpx.MockTransport(handler),
    )
    try:
        await api.attach(12345)
        await api.attach(12346)
        assert len(set(names)) == 2
    finally:
        await api.close()


@pytest.mark.parametrize("kind", ["navigate", "action", "snapshot"])
async def test_request_deadlines_match_browser_operation(kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["read"] == {
            "navigate": 22, "action": 10, "snapshot": 8,
        }[kind]
        return httpx.Response(200, json={})

    api = PinchtabAPI(
        IsolatedSettings(pinchtab_token="fake-token", pinchtab_url="http://127.0.0.1:9867"),
        httpx.MockTransport(handler),
    )
    try:
        await api.request("POST", "/tabs/test/" + kind)
    finally:
        await api.close()


@pytest.mark.parametrize("failure,expected", [
    (httpx.ReadTimeout, "TIMEOUT"),
    (httpx.ConnectError, "BROWSER_ERROR"),
    (httpx.RemoteProtocolError, "BROWSER_ERROR"),
])
async def test_transport_errors_are_distinct_and_sanitized(
    failure: type[httpx.HTTPError], expected: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure("CANARY-PASSWORD-9137")

    api = PinchtabAPI(
        IsolatedSettings(pinchtab_token="fake-token", pinchtab_url="http://127.0.0.1:9867"),
        httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(BrowserFailure) as error:
            await api.request("POST", "/tabs/test/navigate")
        assert error.value.code == expected
        assert "CANARY" not in str(error.value)
        if expected == "TIMEOUT":
            assert "Start local" not in str(error.value)
    finally:
        await api.close()
