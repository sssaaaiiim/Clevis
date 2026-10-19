import asyncio
import os
from pathlib import Path
from time import monotonic, sleep

import pytest

from app.browser.playwright_driver import PlaywrightDriver
from app.core.events import Action
from tests.settings import IsolatedSettings


def browser_descendants() -> set[int]:
    """Track only this test process's browser children, never an operator's browser."""
    processes: dict[int, tuple[int, str]] = {}
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            raw = (directory / "stat").read_text()
            name = raw.split("(", 1)[1].rsplit(")", 1)[0]
            fields = raw.rsplit(")", 1)[1].split()
            processes[int(directory.name)] = (int(fields[1]), name)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    descendants = {os.getpid()}
    while True:
        found = {pid for pid, (parent, _) in processes.items() if parent in descendants}
        new = found - descendants
        if not new:
            break
        descendants.update(new)
    return {
        pid
        for pid in descendants
        if pid in processes
        and any(part in processes[pid][1].lower() for part in ("chrome", "chromium"))
    }


@pytest.mark.skipif(
    not Path("/proc").exists(), reason="Process-level cleanup audit uses Linux /proc."
)
async def test_cancel_reaps_own_chromium_processes() -> None:
    before = await asyncio.to_thread(browser_descendants)
    driver = PlaywrightDriver(IsolatedSettings())
    await driver.start("headless")
    owned = await asyncio.to_thread(browser_descendants)
    owned -= before
    assert owned, "The test must observe real Chromium child processes."
    try:
        task = asyncio.create_task(driver.act(Action(action="wait", value="10", rationale="Wait.")))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(wait_for_exit, owned)
    finally:
        await driver.close()


def wait_for_exit(pids: set[int]) -> bool:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        if not any(Path(f"/proc/{pid}").exists() for pid in pids):
            return True
        sleep(0.02)
    return False
