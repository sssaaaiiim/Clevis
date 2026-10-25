"""Independent browser-side destination checks, including uncached post-load DNS."""

import ipaddress

from app.agent.policy.domains import (
    Resolver,
    hostname,
    is_allowed_domain,
    is_private_address,
    parse_domains,
)
from app.agent.policy.resolver import CachedResolver
from app.config import Settings


class NavigationMonitor:
    def __init__(
        self,
        settings: Settings,
        resolver: Resolver | None = None,
        approved_hosts: set[str] | None = None,
    ) -> None:
        self.settings = settings
        self.cache = CachedResolver()
        self.resolver = resolver or self.cache
        self.allowed = parse_domains(settings.allowed_domains)
        self.blocked = parse_domains(settings.blocked_domains)
        self.approved_hosts = approved_hosts if approved_hosts is not None else set()

    async def warning(self, url: str, *, fresh: bool = False) -> str | None:
        if url == "about:blank":
            return None
        host = hostname(url)
        if self.settings.block_private_network:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                if self.resolver is self.cache and host not in {
                    "localhost",
                    "metadata.google.internal",
                    "metadata.azure.com",
                }:
                    if fresh:
                        self.cache.addresses.pop(host, None)
                    try:
                        await self.cache.resolve(host)
                    except (ValueError, OSError):
                        return "SSRF redirect blocked"
            try:
                if is_private_address(url, self.resolver):
                    return "SSRF redirect blocked"
            except (ValueError, OSError):
                return "SSRF redirect blocked"
        if not is_allowed_domain(url, self.allowed, self.blocked):
            if host in self.blocked or "*" in self.blocked or host not in self.approved_hosts:
                return "Disallowed redirect blocked"
        return None
