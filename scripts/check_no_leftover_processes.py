"""Ten real-Chromium runs plus three concurrent isolated runs, with fake LLMs and RAM-only frames.

From root with backend dependencies installed: python scripts/check_no_leftover_processes.py.
No external requests or credentials are needed. Reports only states/counts/RSS, never page data.
"""

from __future__ import annotations

import asyncio
import gc
import io
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.browser.playwright_driver import PlaywrightDriver
from app.config import Settings
from app.core.events import Action, Mode
from app.fakes.fake_llm import FakeLLMClient
from app.preview.framing import Frame
from app.runtime import RunService
from PIL import Image
from process_audit import Process, owned_browsers, still_alive


def rss_mib() -> float:
    pages = int(Path("/proc/self/statm").read_text().split()[1])
    return round(pages * os.sysconf("SC_PAGE_SIZE") / 1024**2, 2)


class IsolatedDriver(PlaywrightDriver):
    def __init__(self, settings: Settings, number: int) -> None:
        super().__init__(settings)
        self.number = number
        self.color = (
            40 + number * 20 % 180,
            50 + number * 37 % 180,
            60 + number * 53 % 180,
        )

    async def start(self, mode: Mode) -> None:
        await super().start(mode)
        await self.get_context().add_cookies(
            [
                {
                    "name": "phase1-isolation",
                    "value": str(self.number),
                    "url": "http://127.0.0.1",
                }
            ]
        )

    async def navigate(self, url: str) -> None:
        await super().navigate(url)
        if url == "about:blank":
            await self.get_active_page().set_content(
                "<style>html{background:rgb("
                + ",".join(map(str, self.color))
                + ")}</style>"
                "<p>Fake isolation test page</p>"
            )


async def await_event(service: RunService, run_id: str, kind: str) -> None:
    async with asyncio.timeout(15):
        async with service.emitter.subscribe(run_id) as subscription:
            while (await subscription.queue.get()).type != kind:
                pass


async def no_processes(owned: set[Process]) -> None:
    for _ in range(40):
        if not await asyncio.to_thread(still_alive, owned):
            return
        await asyncio.sleep(0.05)
    raise RuntimeError("Owned Chromium or PinchTab process remains after cleanup.")


async def main() -> int:
    logging.disable(logging.CRITICAL)
    settings = Settings(
        _env_file=None,
        browser_driver="playwright",
        llm_provider="fake",
        preview_retain_after_end_s=0,
        takeover_max_seconds=0.08,
        input_idle_timeout_s=0.08,
    )
    drivers: list[IsolatedDriver] = []
    current_script: list[Action] = []

    def factory() -> IsolatedDriver:
        driver = IsolatedDriver(settings, len(drivers) + 1)
        drivers.append(driver)
        return driver

    service = RunService(
        settings, factory, lambda: FakeLLMClient(actions=current_script, delay=0.01)
    )
    before = await asyncio.to_thread(rss_mib)
    samples = []
    owned = set()
    outcomes = [
        "finished",
        "failed",
        "stopped",
        "timeout",
        "finished",
        "failed",
        "stopped",
        "timeout",
        "finished",
        "finished",
    ]
    try:
        for index, outcome in enumerate(outcomes, 1):
            if outcome == "failed":
                current_script = [
                    Action(
                        action="navigate",
                        value="file:///blocked",
                        rationale="Test scheme rejection.",
                    )
                ]
            elif outcome == "timeout":
                current_script = [
                    Action(
                        action="handoff",
                        value="Local timeout check",
                        rationale="Request control.",
                    )
                ]
            else:
                current_script = [
                    Action(
                        action="wait",
                        value=".5" if outcome == "finished" else "10",
                        rationale="Local cleanup check.",
                    ),
                    Action(
                        action="done", value="Complete", rationale="Finish local check."
                    ),
                ]
            run = await service.create("Local lifecycle check", "headless")
            task = service.tasks[run.runId]
            await await_event(service, run.runId, "run.started")
            if outcome == "stopped":
                await await_event(service, run.runId, "step.proposed")
                owned |= await asyncio.to_thread(owned_browsers)
                await asyncio.wait_for(service.stop(run.runId), 2)
            else:
                await await_event(service, run.runId, "plan.created")
                owned |= await asyncio.to_thread(owned_browsers)
            await asyncio.wait_for(task, 15)
            expected = "failed" if outcome in {"failed", "timeout"} else outcome
            record = await service.store.get(run.runId)
            if record.status != expected:
                raise RuntimeError("Unexpected lifecycle result.")
            await no_processes(owned)
            await asyncio.sleep(0.02)
            assert service.preview_hubs[run.runId].latest is None
            assert not service.tasks and not service.control_watchers
            gc.collect()
            sample = await asyncio.to_thread(rss_mib)
            samples.append(sample)
            print(f"PASS short run {index}: {outcome}; RSS MiB={sample}", flush=True)

        current_script = [
            Action(
                action="wait",
                value="1",
                rationale="Check isolated concurrent contexts.",
            ),
            Action(
                action="done", value="Complete", rationale="Finish isolation check."
            ),
        ]
        runs = [
            await service.create("Concurrent isolation " + str(i), "headless")
            for i in range(3)
        ]
        tasks = [service.tasks[run.runId] for run in runs]

        async def verify(run_id: str, driver: IsolatedDriver) -> None:
            nonlocal owned
            await await_event(service, run_id, "plan.created")
            owned |= await asyncio.to_thread(owned_browsers)
            cookies = await driver.get_context().cookies("http://127.0.0.1")
            assert [c["value"] for c in cookies if c["name"] == "phase1-isolation"] == [
                str(driver.number)
            ]
            async with asyncio.timeout(3):
                async with service.preview_hubs[run_id].subscribe() as queue:
                    while True:
                        frame = service.preview_hubs[run_id].latest
                        if frame is not None:
                            with Image.open(io.BytesIO(frame.image)) as img:
                                pixel = img.convert("RGB").getpixel((0, 0))
                            assert isinstance(pixel, tuple)
                            if all(
                                abs(pixel[i] - driver.color[i]) < 10 for i in range(3)
                            ):
                                break
                        message = await queue.get()
                        if isinstance(message, Frame):
                            assert message.metadata.tabId
            await asyncio.wait_for(service.tasks[run_id], 10)
            events = await service.store.list_events(run_id)
            assert all(e.runId == run_id for e in events)
            assert [e.seq for e in events] == list(range(1, len(events) + 1))
            assert events[-1].type == "run.finished"

        owned |= await asyncio.to_thread(owned_browsers)
        await asyncio.gather(
            *(verify(r.runId, d) for r, d in zip(runs, drivers[-3:], strict=True))
        )
        await asyncio.gather(*tasks)
        owned |= await asyncio.to_thread(owned_browsers)
        await no_processes(owned)
        after = await asyncio.to_thread(rss_mib)
        assert after - before < 64 and max(samples[-5:]) - min(samples[-5:]) < 16
        print(
            "PASS three concurrent runs: isolated events, native frame colors and cookies",
            flush=True,
        )
        print(
            f"RSS MiB start={before} end={after} delta={round(after - before, 2)}",
            flush=True,
        )
        print(
            "PASS: 10 lifecycle runs, 3 concurrent runs, no owned Chromium/PinchTab processes",
            flush=True,
        )
        return 0
    finally:
        await service.shutdown()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception:
        print(
            "FAIL: lifecycle/isolation/leak assertion failed (no private error details).",
            flush=True,
        )
        raise SystemExit(1) from None
