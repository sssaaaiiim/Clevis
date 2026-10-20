from collections.abc import AsyncIterator, Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from app.browser.playwright_driver import PlaywrightDriver
from tests.settings import IsolatedSettings


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def testsite() -> Iterator[str]:
    directory = Path(__file__).resolve().parents[2] / "testsite"
    handler = partial(QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
async def driver() -> AsyncIterator[PlaywrightDriver]:
    instance = PlaywrightDriver(IsolatedSettings())
    await instance.start("headless")
    browser = instance.get_context().browser
    try:
        yield instance
    finally:
        await instance.close()
        assert browser is not None and not browser.is_connected()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # A key in the operator's environment must not make normal test runs billable.
    if "live" not in config.option.markexpr:
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(pytest.mark.skip(reason="Opt in explicitly with pytest -m live."))
