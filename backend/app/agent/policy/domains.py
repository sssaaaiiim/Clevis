"""Exact-host domain policy and pure address classification with an injected resolver."""

import ipaddress
import re
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

Resolver = Callable[[str], Sequence[str]]
METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.azure.com",
        "fd00:ec2::254",
    }
)


def parse_domains(value: str) -> frozenset[str]:
    entries = frozenset(
        part.strip().lower().rstrip(".") for part in value.split(",") if part.strip()
    )
    for entry in entries:
        if entry == "*":
            continue
        try:
            ipaddress.ip_address(entry)
            continue
        except ValueError:
            pass
        if len(entry) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in entry.split(".")
        ):
            raise ValueError("Domain lists require exact hostnames, IP addresses, or *.")
    return entries


def hostname(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def is_blocked_domain(url: str, blocked: frozenset[str]) -> bool:
    return "*" in blocked or hostname(url) in blocked


def is_allowed_domain(
    url: str,
    allowed: frozenset[str] = frozenset(),
    blocked: frozenset[str] = frozenset(),
) -> bool:
    host = hostname(url)
    return (
        bool(host)
        and not is_blocked_domain(url, blocked)
        and (not allowed or "*" in allowed or host in allowed)
    )


def is_private_address(url: str, resolver: Resolver) -> bool:
    host = hostname(url)
    if not host or host in METADATA_HOSTS or host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = list(resolver(host))
    if not addresses:
        raise ValueError("Cannot verify destination address.")
    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
            parsed = parsed.ipv4_mapped
        if not parsed.is_global:
            return True
    return False
