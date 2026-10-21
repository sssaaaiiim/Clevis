"""Time-boxed PinchTab 0.15.2 attach experiment. Prints statuses/numbers, never payloads.

Run with backend/.venv active: python scripts/spike_pinchtab_attach.py.
PINCHTAB_URL/TOKEN select an existing loopback orchestrator; otherwise own a disposable one.
PINCHTAB_BIN optionally selects its CLI. Only attach is enabled; all state is temporary.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import signal
import sys
import tempfile
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from app.browser.playwright_driver import PlaywrightDriver
from app.config import Settings
from app.core.events import Mode
from app.preview.cdp import CdpScreencastChannel
from app.preview.hub import PreviewHub
from app.preview.input_protocol import Mouse, Text
from app.preview.input_relay import CdpInputRelay
from process_audit import free_port, loopback_listeners, owned_browsers, still_alive
from serve_testsite import QuietHandler

ROOT = Path(__file__).resolve().parents[1]
TESTED_VERSION = "0.15.2"


class CheckFailed(Exception):
    pass


def check(ok: bool, number: int, message: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'} {number}: {message}", flush=True)
    if not ok:
        raise CheckFailed


class DebugDriver(PlaywrightDriver):
    """Spike-only launch flags; production driver/factory/config remain untouched."""

    async def start(self, mode: Mode) -> None:
        self.debug_port = free_port()
        self._manager_started = True
        self._playwright = await self._manager.start()
        self._browser = await self._playwright.chromium.launch(
            channel="chromium",
            timeout=6000,
            headless=True,
            args=[
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self.debug_port}",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            accept_downloads=False,
            permissions=[],
        )
        self._context.on("page", self._on_page)
        self._page = await self._context.new_page()


async def main() -> int:
    # No private developer .env or verbose third-party HTTP/CDP diagnostics.
    logging.disable(logging.CRITICAL)
    binary = os.environ.get("PINCHTAB_BIN") or shutil.which("pinchtab")
    if not binary:
        print(
            "FAIL 1: PinchTab executable unavailable; install optional v0.15.2.\nOVERALL FAIL"
        )
        return 1
    version_process = await asyncio.create_subprocess_exec(
        binary,
        "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await version_process.communicate()
    match = re.search(rb"\b(\d+\.\d+\.\d+)\b", out)
    version = match.group(1).decode() if match else "unknown"
    print("PinchTab version:", version, flush=True)
    if version != TESTED_VERSION:
        print("FAIL 1: Unsupported version; review release docs.\nOVERALL FAIL")
        return 1
    own_url = not bool(os.environ.get("PINCHTAB_URL"))
    token = os.environ.get("PINCHTAB_TOKEN", "")
    if not token and not own_url:
        print(
            "FAIL 1: PINCHTAB_TOKEN is required for an external server.\nOVERALL FAIL"
        )
        return 1
    token = token or secrets.token_urlsafe(32)
    url = os.environ.get("PINCHTAB_URL") or f"http://127.0.0.1:{free_port()}"
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        print(
            "FAIL 1: PINCHTAB_URL must be a bare literal loopback HTTP origin.\nOVERALL FAIL"
        )
        return 1
    settings = Settings(_env_file=None, preview_retain_after_end_s=0)
    driver = DebugDriver(settings)
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(driver, hub, settings)
    relay: CdpInputRelay | None = None
    child: asyncio.subprocess.Process | None = None
    instance: str | None = None
    owned = set()
    success = False
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "testsite"))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with tempfile.TemporaryDirectory(prefix="wto-pinchtab-") as temporary:
            if own_url:
                config = {
                    "configVersion": "0.8.0",
                    "server": {
                        "bind": "127.0.0.1",
                        "port": str(parsed.port),
                        "stateDir": temporary,
                        "logLevel": "error",
                        "networkBufferSize": 0,
                        "retainNetworkBodies": False,
                    },
                    "browser": {"extensionPaths": []},
                    "multiInstance": {"strategy": "explicit"},
                    "security": {
                        "allowEvaluate": False,
                        "allowMacro": False,
                        "allowScreencast": False,
                        "allowDownload": False,
                        "allowCookies": False,
                        "allowUpload": False,
                        "allowClipboard": False,
                        "allowFileScheme": False,
                        "allowedDomains": ["127.0.0.1", "localhost", "::1"],
                        "attach": {
                            "enabled": True,
                            "allowHosts": ["127.0.0.1"],
                            "allowSchemes": ["http", "ws"],
                            "forwardProxyAuth": False,
                        },
                    },
                    "observability": {"activity": {"enabled": False}},
                    "autoSolver": {"enabled": False},
                }
                path = Path(temporary) / "config.json"
                await asyncio.to_thread(path.write_text, json.dumps(config))
                env = {
                    **os.environ,
                    "PINCHTAB_CONFIG": str(path),
                    "PINCHTAB_TOKEN": token,
                }
                child = await asyncio.create_subprocess_exec(
                    binary,
                    "server",
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(parsed.port),
                    "--log-level",
                    "error",
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
            async with httpx.AsyncClient(
                base_url=url,
                headers={"Authorization": "Bearer " + token},
                trust_env=False,
                timeout=12,
                follow_redirects=False,
            ) as client:
                for _ in range(60):
                    try:
                        health = await client.get("/health")
                        if health.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    check(False, 1, "server did not become healthy within six seconds")
                async with httpx.AsyncClient(
                    base_url=url, trust_env=False, timeout=3
                ) as anonymous:
                    rejected = await anonymous.get("/instances")
                allowed = await client.get("/instances")
                check(
                    rejected.status_code in {401, 403}
                    and allowed.status_code == 200
                    and await asyncio.to_thread(loopback_listeners, parsed.port or 80),
                    1,
                    f"/instances anonymous={rejected.status_code}, auth={allowed.status_code}",
                )
                reported = health.json().get("version")
                check(
                    reported == TESTED_VERSION, 1, "server and installed version agree"
                )
                await driver.start("headless")
                print("PASS 2: dual-control launch returned", flush=True)
                page = driver.get_active_page()
                port = driver.debug_port
                async with httpx.AsyncClient(trust_env=False, timeout=3) as debugger:
                    endpoint = await debugger.get(
                        f"http://127.0.0.1:{port}/json/version"
                    )
                check(
                    endpoint.status_code == 200
                    and await asyncio.to_thread(loopback_listeners, port),
                    2,
                    "Playwright pipe and loopback remote-debugging HTTP endpoint coexist",
                )
                attach = await client.post(
                    "/instances/attach",
                    json={
                        "name": "phase1-spike",
                        "cdpUrl": f"http://127.0.0.1:{port}",
                        "provider": "chrome",
                    },
                )
                check(
                    attach.status_code in {200, 201},
                    2,
                    f"POST /instances/attach HTTP {attach.status_code}",
                )
                payload = attach.json()
                instance = payload["id"]
                check(
                    bool(payload.get("attached")),
                    2,
                    "external Chromium registered as attached",
                )

                async def tabs() -> list[dict[str, Any]]:
                    response = await client.get(f"/instances/{instance}/tabs")
                    response.raise_for_status()
                    return list(response.json())

                async def tab_id() -> str:
                    response = await driver.get_context().new_cdp_session(
                        driver.get_active_page()
                    )
                    target = (await response.send("Target.getTargetInfo"))[
                        "targetInfo"
                    ]["targetId"]
                    await response.detach()
                    candidates = await tabs()
                    exact = [t for t in candidates if t["id"] == target]
                    if not exact:
                        exact = [
                            t
                            for t in candidates
                            if t["url"] == driver.get_active_page().url
                        ]
                    check(
                        len(exact) == 1,
                        3,
                        "unique PinchTab tab maps to Playwright active target/URL",
                    )
                    return str(exact[0]["id"])

                await driver.navigate(base + "/form.html")
                tab = await tab_id()
                snap = await client.get(
                    f"/tabs/{tab}/snapshot", params={"filter": "interactive"}
                )
                check(
                    snap.status_code == 200, 3, f"JSON snapshot HTTP {snap.status_code}"
                )
                data = snap.json()
                # v0.15.2 snapshot JSON uses nodes with ref/role/name.
                nodes = data["nodes"]

                def ref(name: str) -> str:
                    return str(next(n["ref"] for n in nodes if n.get("name") == name))

                check(
                    all(
                        any(n.get("name") == name and n.get("ref") for n in nodes)
                        for name in ["Name", "Email", "Project", "Submit form"]
                    ),
                    3,
                    "form controls have refs",
                )
                old_ref = ref("Name")
                durations = []
                for kind, element, text in [
                    ("fill", ref("Name"), "Demo Person"),
                    ("fill", ref("Email"), "demo@example.invalid"),
                    ("click", ref("Submit form"), None),
                ]:
                    started = monotonic()
                    body = {"kind": kind, "ref": element}
                    if text is not None:
                        body["text"] = text
                    response = await client.post(f"/tabs/{tab}/action", json=body)
                    durations.append(round((monotonic() - started) * 1000, 2))
                    check(
                        response.status_code == 200,
                        4,
                        f"action {kind} HTTP {response.status_code}",
                    )
                check(
                    (await page.locator("#confirmation").inner_text())
                    == "Form submitted successfully.",
                    4,
                    "Playwright confirms form submission",
                )
                print("ACTION_LATENCY_MS", json.dumps(durations), flush=True)

                async def ignore(frame: bytes) -> None:
                    pass

                await channel.start_stream(ignore)
                await page.evaluate(
                    "window.spikePaint=setInterval(()=>document.body.style.backgroundColor=Date.now()%2?'white':'#fefefe',50)"
                )
                async with asyncio.timeout(3):
                    async with hub.subscribe() as queue:
                        while hub.latest is None:
                            await queue.get()
                relay = CdpInputRelay(driver)
                box = await page.locator("#name").bounding_box()
                assert box
                before_input = await page.locator("#name").input_value()
                for action in ["down", "up"]:
                    check(
                        await relay.send(
                            Mouse.model_validate(
                                {
                                    "type": "mouse",
                                    "action": action,
                                    "x": box["x"] + 5,
                                    "y": box["y"] + 5,
                                }
                            )
                        ),
                        5,
                        "CDP input acknowledged",
                    )
                check(
                    await relay.send(Text(type="text", value="X")),
                    5,
                    "CDP text acknowledged",
                )
                check(
                    (await page.locator("#name").input_value()).replace("X", "")
                    == before_input
                    and (await page.locator("#name").input_value()) != before_input,
                    5,
                    "CDP clicks land in the expected field",
                )
                first = channel.seq
                await asyncio.sleep(0.4)
                check(
                    channel.seq > first and channel.acked > 0,
                    5,
                    "preview frames keep flowing alongside PinchTab and input",
                )
                await relay.close()
                relay = None

                print(
                    "MEASUREMENTS page pinch_chars est_tokens ms playwright_chars est_tokens ms",
                    flush=True,
                )
                for filename in ["index.html", "form.html", "table.html"]:
                    await driver.navigate(base + "/" + filename)
                    tab = await tab_id()
                    started = monotonic()
                    compact = await client.get(
                        f"/tabs/{tab}/snapshot",
                        params={"filter": "interactive", "format": "compact"},
                    )
                    pt_ms = (monotonic() - started) * 1000
                    check(compact.status_code == 200, 3, "compact snapshot succeeds")
                    started = monotonic()
                    observation = await driver.observe()
                    pw_ms = (monotonic() - started) * 1000
                    size = len(observation.to_prompt_text())
                    print(
                        filename,
                        len(compact.text),
                        (len(compact.text) + 3) // 4,
                        round(pt_ms, 2),
                        size,
                        (size + 3) // 4,
                        round(pw_ms, 2),
                        flush=True,
                    )
                await driver.navigate(base + "/popup.html")
                async with page.expect_popup():
                    await page.locator("#new-tab").click()
                await driver.get_active_page().wait_for_load_state("domcontentloaded")
                check(
                    await tab_id() != tab,
                    6,
                    "new popup maps to a distinct PinchTab tab and active Playwright page",
                )
                await driver.navigate(base + "/form.html")
                tab = await tab_id()
                fresh = await client.get(
                    f"/tabs/{tab}/snapshot", params={"filter": "interactive"}
                )
                old_ref = str(
                    next(
                        n["ref"]
                        for n in fresh.json()["nodes"]
                        if n.get("name") == "Name"
                    )
                )
                await driver.navigate(base + "/index.html")
                response = await client.post(
                    f"/tabs/{tab}/action",
                    json={"kind": "fill", "ref": old_ref, "text": "stale-demo"},
                )
                error = response.json()
                print(
                    "STALE_ERROR_SHAPE",
                    response.status_code,
                    sorted(error.keys()),
                    flush=True,
                )
                check(
                    response.status_code >= 400,
                    7,
                    "old reference fails cleanly after navigation",
                )
                success = True
                owned |= await asyncio.to_thread(owned_browsers)
    except CheckFailed:
        pass
    except Exception as exc:
        print("ERROR_CLASS", type(exc).__name__, flush=True)
        # Never echo third-party errors: they may contain tokens, URLs, page text or typed values.
        print(
            "FAIL: sanitized experiment error; check failed stage against versioned docs.",
            flush=True,
        )
    finally:
        owned |= await asyncio.to_thread(owned_browsers)
        if relay:
            await relay.close()
        if instance:
            try:
                async with httpx.AsyncClient(
                    base_url=url,
                    headers={"Authorization": "Bearer " + token},
                    trust_env=False,
                    timeout=5,
                ) as cleanup:
                    await cleanup.post(f"/instances/{instance}/stop")
            except httpx.HTTPError:
                success = False
        await channel.stop_stream()
        await hub.close()
        await driver.close()
        if child:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                await asyncio.wait_for(child.wait(), 3)
            except (ProcessLookupError, TimeoutError):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await child.wait()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)
        for _ in range(30):
            if not await asyncio.to_thread(still_alive, owned):
                break
            await asyncio.sleep(0.1)
        clean = not await asyncio.to_thread(still_alive, owned)
        print(
            f"{'PASS' if clean else 'FAIL'} 8: owned browser/PinchTab processes cleaned up",
            flush=True,
        )
        success = success and clean
    print("OVERALL " + ("PASS" if success else "FAIL"), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    try:

        async def bounded() -> int:
            async with asyncio.timeout(180):
                return await main()

        raise SystemExit(asyncio.run(bounded()))
    except (TimeoutError, KeyboardInterrupt):
        print("OVERALL FAIL: time-box reached or interrupted; cleanup attempted.")
        raise SystemExit(1) from None
