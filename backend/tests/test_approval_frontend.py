import asyncio
from pathlib import Path

import pytest
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright, expect

from tests.test_approval_api import application
from tests.test_preview_browser_ws import serve

FRONTEND = Path(__file__).resolve().parents[2] / "front end"


@pytest.mark.parametrize("decision", ["Approve", "Deny", "Stop run"])
async def test_real_react_approval_dialog_round_trip(decision: str) -> None:
    frontend = FRONTEND
    if not await asyncio.to_thread((frontend / "dist/index.html").is_file):
        build = await asyncio.create_subprocess_exec(
            "npm",
            "run",
            "build",
            cwd=frontend,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert await build.wait() == 0, (
            "Frontend build must succeed for the approval integration test."
        )
    app = application()
    app.mount("/", StaticFiles(directory=frontend / "dist", html=True))
    async with serve(app) as host:
        origin = f"http://{host}"
        app.state.service.settings.frontend_origin = origin
        async with async_playwright() as manager:
            browser = await manager.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(origin + "/")
                        else route.abort()
                    ),
                )
                await page.goto(origin, wait_until="domcontentloaded")
                await page.get_by_role("button", name="CLEVIS COMMAND", exact=True).click()
                await page.get_by_placeholder("Let Clevis handle the workflow.").fill(
                    "Submit the demo"
                )
                await page.get_by_role("button", name="Run Task", exact=True).click()
                dialog = page.get_by_role("dialog", name="Approval required")
                await expect(dialog).to_be_visible()
                await expect(dialog.get_by_text("medium risk")).to_be_visible()
                tasks = list(app.state.service.tasks.values())
                assert tasks
                await dialog.get_by_role("button", name=decision, exact=True).click()
                await expect(dialog).not_to_be_visible()
                await asyncio.wait_for(asyncio.gather(*tasks), 3)
                runs = list(app.state.service.machines)
                assert len(runs) == 1
                record = await app.state.service.store.get(runs[0])
                assert record.status == ("stopped" if decision == "Stop run" else "finished")
                storage = await page.evaluate("JSON.stringify(localStorage)")
                assert not any(
                    token in storage for token in app.state.service.approval_tokens.values()
                )
            finally:
                await browser.close()
