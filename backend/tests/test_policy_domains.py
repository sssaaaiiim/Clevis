import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.policy.domains import (
    is_allowed_domain,
    is_private_address,
    parse_domains,
)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.99.1.1",
        "10.1.1.1",
        "172.16.0.1",
        "172.31.255.254",
        "192.168.1.1",
        "169.254.1.1",
        "169.254.169.254",
        "[::1]",
        "[fc00::1]",
        "[fd00:ec2::254]",
        "[fe80::1]",
        "[::ffff:127.0.0.1]",
        "metadata.google.internal",
        "metadata.azure.com",
        "localhost",
        "sub.localhost",
        "0.0.0.0",
    ],
)
def test_private_and_metadata(host: str) -> None:
    assert is_private_address("http://" + host, lambda _: ["8.8.8.8"])


def test_injected_dns_all_answers_checked() -> None:
    assert is_private_address("https://public.example", lambda _: ["8.8.8.8", "10.0.0.1"])
    assert not is_private_address("https://public.example", lambda _: ["8.8.8.8", "1.1.1.1"])
    assert not is_private_address("https://8.8.8.8", lambda _: [])
    with pytest.raises(ValueError, match="Cannot verify"):
        is_private_address("https://unresolved.example", lambda _: [])


def test_exact_domain_policy_and_blocked_override() -> None:
    url = "https://example.com/path?secret=hidden"
    assert is_allowed_domain(url)
    assert is_allowed_domain(url, parse_domains("*"))
    assert is_allowed_domain(url, parse_domains(" EXAMPLE.COM. "))
    assert not is_allowed_domain(url, parse_domains("other.example"))
    assert not is_allowed_domain(url, parse_domains("*"), parse_domains("example.com"))
    assert not is_allowed_domain(url, blocked=parse_domains("*"))
    assert not is_allowed_domain("https://example.com.evil.test", parse_domains("example.com"))
    assert not is_allowed_domain("https://sub.example.com", parse_domains("example.com"))


async def test_dns_resolution_is_once_per_hostname_per_run_without_network() -> None:
    from app.agent.policy.resolver import CachedResolver

    resolver = CachedResolver()
    lookup = AsyncMock(return_value=[(2, 1, 6, "", ("8.8.8.8", 0))])
    with patch.object(asyncio.get_running_loop(), "getaddrinfo", lookup):
        await asyncio.gather(resolver.resolve("example.com"), resolver.resolve("example.com"))
        await resolver.resolve("example.com")
    assert lookup.await_count == 1 and resolver("example.com") == ["8.8.8.8"]
