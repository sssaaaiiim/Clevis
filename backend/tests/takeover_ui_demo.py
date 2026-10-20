"""Opt-in real frontend check; requires npm ci, ports 5173/8000 and a local display for headed.

Run: python -m tests.takeover_ui_demo. Uses only the public fake local credentials.
Never records screenshots, traces, videos or input payloads.
"""

import asyncio
import contextlib
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import cast

import httpx
from playwright.async_api import async_playwright

from app.browser.playwright_driver import PlaywrightDriver
from app.browser.safety import display_available
from app.core.events import Mode
from app.core.state import RunStatus
from app.main import create_app
from app.runtime import RunService
from tests.conftest import QuietHandler
from tests.settings import IsolatedSettings
from tests.test_preview_browser_ws import serve
from tests.test_takeover_browser import BrowserLLM
from tests.test_takeover_state import wait_status


async def run_mode(testsite: str, mode: Mode, scale: int) -> None:
    settings = IsolatedSettings(device_scale_factor=scale)
    driver = PlaywrightDriver(settings)
    llm = BrowserLLM(testsite + "/login.html")
    app = create_app(settings, driver_factory=lambda: driver, llm_factory=lambda: llm)
    service = cast(RunService, app.state.service)
    async with serve(app, 8000):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, channel="chromium")
            try:
                page = await browser.new_page(
                    viewport={"width": 1900, "height": 1200}, device_scale_factor=scale
                )
                await page.goto("http://localhost:5173", wait_until="networkidle")
                await page.get_by_role("button", name="CLEVIS COMMAND", exact=True).click()
                await page.get_by_placeholder("Let Clevis handle the workflow.").fill(
                    "Log in and report the welcome message"
                )
                if mode == "headed":
                    await page.get_by_role("button", name="Parameters", exact=True).click()
                    await page.get_by_role("button", name="Headless ON", exact=True).click()
                await page.get_by_role("button", name="Run Task", exact=True).click()
                await page.get_by_text(
                    "You are in control. The agent is paused", exact=True
                ).wait_for(timeout=10000)
                await page.get_by_role("button", name="CLEVIS COMMAND", exact=True).click()
                await page.wait_for_function("document.querySelector('canvas')?.width > 0")
                await page.get_by_text("Browser is not accepting input", exact=True).wait_for(
                    state="hidden"
                )
                source = driver.get_active_page()

                async def click_source(selector: str) -> None:
                    box = await source.locator(selector).bounding_box()
                    rect = await page.locator("canvas").bounding_box()
                    assert box and rect
                    await page.mouse.click(
                        rect["x"] + (box["x"] + box["width"] / 2) * rect["width"] / 1280,
                        rect["y"] + (box["y"] + box["height"] / 2) * rect["height"] / 720,
                    )

                await click_source("#username")
                await page.keyboard.insert_text("demo-user")
                await click_source("#password")
                await page.keyboard.type("demo-pass-only", delay=20)
                # Input protocol ordering is preserved; wait for the page value before submit.
                await source.wait_for_function(
                    "document.querySelector('#password').value.length === 14"
                )
                await click_source("button")
                await source.get_by_text("Welcome, demo-user", exact=True).wait_for()
                await page.get_by_role("button", name="CLEVIS COMMAND", exact=True).click()
                await page.get_by_role("button", name="Resume agent", exact=True).click()
                await page.get_by_text(
                    "You are in control. The agent is paused", exact=True
                ).wait_for(state="hidden")
                await page.get_by_text("Run ended", exact=True).wait_for()
                run_id = next(iter(service.machines))
                await wait_status(service, run_id, RunStatus.FINISHED)
                record = await service.store.get(run_id)
                assert record.status == "finished"
                assert record.result == "Welcome, [redacted]-[redacted]"
                print(f"PASS frontend login/resume: {mode}, DSF={scale}")
            finally:
                await browser.close()


ROOT = Path(__file__).resolve().parents[2]


async def main() -> None:
    root = ROOT
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(root / "testsite"))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    vite = await asyncio.create_subprocess_exec(
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        "localhost",
        "--strictPort",
        cwd=root / "front end",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        async with httpx.AsyncClient(trust_env=False) as http:
            for _ in range(100):
                try:
                    if (await http.get("http://localhost:5173", timeout=0.2)).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError("Frontend dev server did not start.")
        url = f"http://127.0.0.1:{server.server_port}"
        await run_mode(url, "headless", 2)
        if display_available():
            await run_mode(url, "headed", 1)
        else:
            print("SKIP headed frontend smoke: no display available")
    finally:
        import os
        import signal

        with contextlib.suppress(ProcessLookupError):
            os.killpg(vite.pid, signal.SIGTERM)
        await vite.wait()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    asyncio.run(main())
