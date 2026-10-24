"""Per-run asynchronous DNS cache; pure policy helpers receive the resulting lookup."""

import asyncio
import socket


class CachedResolver:
    def __init__(self) -> None:
        self.addresses: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()

    async def resolve(self, host: str) -> None:
        async with self._lock:
            if host not in self.addresses:
                try:
                    answers = await asyncio.wait_for(
                        asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM),
                        timeout=2,
                    )
                except (OSError, TimeoutError):
                    self.addresses[host] = []
                    raise ValueError("Cannot verify destination address.") from None
                self.addresses[host] = sorted({str(answer[4][0]) for answer in answers})

    def __call__(self, host: str) -> list[str]:
        return self.addresses.get(host, [])
