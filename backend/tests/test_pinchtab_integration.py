"""Opt in: PINCHTAB_URL=managed pytest -m pinchtab, or supply a configured local server/token."""

import asyncio
import json
import os
import secrets
import shutil
import signal
import socket
import tempfile
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import cast

import httpx
import pytest

from app.browser.factory import create_browser_driver
from app.browser.pinchtab_driver import PinchtabDriver
from app.config import Settings
from app.core.events import Action, Target
from app.interfaces.llm import LLMResponse, Message, T
from app.main import create_app
from app.runtime import RunService
from tests.scripted_browser_llm import ObservedScriptLLM, form_script
from tests.settings import IsolatedSettings

pytestmark = [
    pytest.mark.pinchtab,
    pytest.mark.skipif(
        not os.environ.get("PINCHTAB_URL"),
        reason="Opt in with PINCHTAB_URL=managed or a configured loopback server.",
    ),
]


@pytest.fixture
async def pinch_settings() -> AsyncIterator[IsolatedSettings]:
    url = os.environ["PINCHTAB_URL"]
    if url != "managed":
        yield IsolatedSettings(agent_driver="pinchtab")
        return
    binary = shutil.which("pinchtab")
    if not binary:
        pytest.fail("Install optional PinchTab 0.15.2 to run the explicit integration gate.")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="phase1-pinch-tests-") as temporary:
        path = Path(temporary) / "config.json"
        config = {
            "configVersion": "0.8.0",
            "server": {
                "bind": "127.0.0.1",
                "port": str(port),
                "stateDir": temporary,
                "logLevel": "error",
                "networkBufferSize": 0,
                "retainNetworkBodies": False,
            },
            "multiInstance": {"strategy": "explicit"},
            "browser": {"extensionPaths": []},
            "observability": {"activity": {"enabled": False}},
            "security": {
                "attach": {
                    "enabled": True,
                    "allowHosts": ["127.0.0.1"],
                    "allowSchemes": ["http", "ws"],
                    "forwardProxyAuth": False,
                }
            },
        }
        await asyncio.to_thread(path.write_text, json.dumps(config))
        child = await asyncio.create_subprocess_exec(
            binary,
            "server",
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            env={**os.environ, "PINCHTAB_CONFIG": str(path), "PINCHTAB_TOKEN": token},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        settings = IsolatedSettings(
            agent_driver="pinchtab",
            pinchtab_url=f"http://127.0.0.1:{port}",
            pinchtab_token=token,
            max_seconds=45,
            preview_retain_after_end_s=0,
        )
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
                for _ in range(60):
                    try:
                        if (
                            await client.get(
                                settings.pinchtab_url + "/health",
                                headers={"Authorization": "Bearer " + token},
                            )
                        ).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Disposable PinchTab server did not start.")
            yield settings
        finally:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(child.wait(), 3)
            except TimeoutError:
                os.killpg(child.pid, signal.SIGKILL)
                await child.wait()


def action(kind: str, description: str | None = None, value: str | None = None) -> Action:
    return Action.model_validate(
        {
            "action": kind,
            "target": {"description": description},
            "value": value,
            "rationale": "Execute the scripted local demo.",
        }
    )


def script(case: str, base: str) -> tuple[list[Action], str]:
    if case == "form":
        actions = form_script(base)
        actions[-1] = action("done", value="Form submitted successfully.")
        return actions, "Form submitted successfully."
    if case == "search":
        return [
            action("navigate", value=base + "/index.html"),
            action("type", "Search products", "Mug"),
            action("click", "Search"),
            action("extract"),
            action("done", value="Travel Mug $12.00"),
        ], "Travel Mug"
    if case == "table":
        return [
            action("navigate", value=base + "/table.html"),
            action("extract"),
            action("done", value="Notebook $5.00"),
        ], "Notebook"
    if case == "load-more":
        return [
            action("navigate", value=base + "/index.html"),
            action("click", "Long page"),
            action("scroll", value="bottom"),
            action("click", "Load more"),
            action("extract"),
            action("done", value="Loaded more fake content."),
        ], "Loaded more fake content."
    return [
        action("navigate", value=base + "/login.html"),
        action("type", "Username", "demo-user"),
        action("type", "Password", "demo-pass-only"),
        action("click", "Sign in"),
        action("extract"),
        action("done", value="Welcome, demo-user"),
    ], "Welcome, demo-user"


@pytest.mark.parametrize("agent", ["default", "playwright"])
@pytest.mark.parametrize("case", ["search", "form", "table", "load-more", "login"])
async def test_pinchtab_five_smoke_goals(
    testsite: str, pinch_settings: IsolatedSettings, case: str, agent: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions, expected = script(case, testsite)

    class VerifiedScript(ObservedScriptLLM):
        async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
            response = await super().propose(messages, schema)
            if isinstance(response.parsed, Action) and response.parsed.action == "done":
                assert expected in messages[-1].content, "Expected page result was not observed."
                if case == "search":
                    assert "Desk Lamp" not in messages[-1].content
            return response

    monkeypatch.delenv("AGENT_DRIVER", raising=False)
    values = pinch_settings.model_dump(exclude={"agent_driver"})
    values["browser_driver"] = "playwright"
    if agent == "playwright":
        values["agent_driver"] = "playwright"
    settings = Settings(_env_file=None, **values)
    driver = create_browser_driver(settings)
    application = create_app(
        settings,
        driver_factory=lambda: driver,
        llm_factory=lambda: VerifiedScript(actions=actions, delay=0),
    )
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        run = await service.create("Complete the fake " + case + " task", "headless")
        task = service.tasks[run.runId]
        await asyncio.wait_for(task, 45)
        record = await service.store.get(run.runId)
        assert record.status == "finished", record.error
        assert record.result and expected in record.result
        events = await service.store.list_events(run.runId)
        assert events[-1].type == "run.finished"
        assert [e.seq for e in events] == list(range(1, len(events) + 1))
        assert "demo-pass-only" not in str(events)


@pytest.mark.parametrize("agent", ["pinchtab", "playwright"])
async def test_invalid_wait_recovers_on_real_driver(
    pinch_settings: IsolatedSettings, testsite: str, agent: str
) -> None:
    settings = pinch_settings.model_copy(update={
        "agent_driver": agent, "browser_driver": "playwright",
    })
    actions = [
        action("navigate", value=testsite + "/table.html"),
        action("wait", value="until ready"),
        action("extract"),
        action("done", value="Table loaded"),
    ]
    application = create_app(
        settings, llm_factory=lambda: ObservedScriptLLM(actions=actions, delay=0)
    )
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        run = await service.create("Read the fake product table", "headless")
        await asyncio.wait_for(service.tasks[run.runId], 45)
        record = await service.store.get(run.runId)
        events = await service.store.list_events(run.runId)
        assert record.status == "finished", record.error
        executed = [e.model_dump()["data"]["ok"] for e in events if e.type == "step.executed"]
        assert executed == [True, False, True, True]
        assert sum(e.type == "observation.summary" for e in events) == 4


async def test_slow_navigation_uses_navigation_deadline(pinch_settings: IsolatedSettings) -> None:
    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            await asyncio.sleep(0.4)
            body = b"<html><title>Delayed fake page</title><p>Ready</p></html>"
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n"
                + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            )
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    driver = PinchtabDriver(pinch_settings)
    try:
        await driver.start("headless")
        assert driver.api is not None
        driver.api.request_timeout = 0.1
        result = await driver.act(action("navigate", value=f"http://127.0.0.1:{port}"))
        assert result.ok, result.summary
        driver.api.request_timeout = pinch_settings.pinchtab_timeout_s
        observation = await driver.observe()
        # Attached PinchTab 0.15.2 prefixes the tab title with its local bridge port.
        assert observation.title.endswith("Delayed fake page")
        assert observation.url.rstrip("/") == f"http://127.0.0.1:{port}"
    finally:
        await driver.close()
        server.close()
        await server.wait_closed()


async def test_pinchtab_canary_stale_pause_and_outage(
    testsite: str, pinch_settings: IsolatedSettings
) -> None:
    driver = PinchtabDriver(pinch_settings)
    await driver.start("headless")
    try:
        await driver.navigate(testsite + "/login.html")
        await driver.pause_actions()
        assert (await driver.act(action("click", "Sign in"))).error_code == "PAUSED"
        driver.input_privacy.remember("CANARY-PASSWORD-9137")
        await driver.get_active_page().locator("#password").fill("CANARY-PASSWORD-9137")
        await driver.resume_actions()
        observation = await driver.observe()
        assert "CANARY-PASSWORD-9137" not in observation.model_dump_json()
        old = next(e.ref for e in observation.elements if e.name == "Username")
        await driver.navigate(testsite + "/index.html")
        result = await driver.act(
            Action(action="click", target=Target(ref=old), rationale="Reject old ref.")
        )
        assert result.error_code == "STALE_REF"
        assert driver.api
        await driver.api.close()
        assert (await driver.act(action("scroll", value="down"))).error_code == "BROWSER_ERROR"
    finally:
        await driver.close()
