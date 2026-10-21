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


async def test_http_failure_does_not_echo_secret_and_version_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "CANARY-PASSWORD-9137"
    settings = IsolatedSettings(pinchtab_token=secret)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer " + secret
        if request.url.path == "/health":
            return httpx.Response(200, json={"version": "0.99.0"})
        return httpx.Response(500, json={"error": "stale reference " + secret, "code": "stale_ref"})

    api = PinchtabAPI(settings, httpx.MockTransport(handler))
    try:
        with caplog.at_level(logging.WARNING):
            await api.health("test-run")
        assert "0.99.0" in caplog.text and secret not in caplog.text
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
