import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.browser.network import NavigationMonitor
from app.browser.playwright_driver import PlaywrightDriver
from app.interfaces.browser import BrowserFailure
from tests.settings import PolicySettings


async def test_http_redirect_cannot_contact_private_target() -> None:
    contacts: list[bool] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/source":
                self.send_response(302)
                self.send_header("Location", "/private")
                self.end_headers()
            else:
                contacts.append(True)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Private target must not be contacted")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    driver = PlaywrightDriver(PolicySettings())
    ready = asyncio.Event()
    monitor = NavigationMonitor(PolicySettings())
    original = monitor.warning

    async def warning(url: str, *, fresh: bool = False) -> str | None:
        return None if url == base + "/source" else await original(url, fresh=fresh)

    async def blocked(domain: str, message: str) -> None:
        ready.set()

    async def policy(url: str, navigation: bool) -> None:
        pass

    monitor.warning = warning  # type: ignore[method-assign]
    await driver.start("headless")
    try:
        driver.configure_navigation_monitor(monitor, blocked)
        await driver.install_navigation_guard(policy)
        try:
            await driver.navigate(base + "/source")
        except BrowserFailure:
            pass
        await asyncio.wait_for(ready.wait(), 2)
        assert not contacts
        assert driver.get_active_page().url == "about:blank"
    finally:
        await driver.close()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=1)
