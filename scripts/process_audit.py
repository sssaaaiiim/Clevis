"""Linux process ownership helpers; never inspect arguments/environments or kill unrelated PIDs."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    name: str
    started: int


def processes() -> dict[int, Process]:
    result = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            text = (path / "stat").read_text()
            name = text.split("(", 1)[1].rsplit(")", 1)[0]
            fields = text.rsplit(")", 1)[1].split()
            pid = int(path.name)
            result[pid] = Process(pid, int(fields[1]), name, int(fields[19]))
        except (OSError, ValueError, IndexError):
            continue
    return result


def owned_browsers() -> set[Process]:
    table = processes()
    descendants = {os.getpid()}
    while True:
        new = {p.pid for p in table.values() if p.parent in descendants} - descendants
        if not new:
            break
        descendants.update(new)
    return {
        p
        for pid, p in table.items()
        if pid in descendants
        and any(s in p.name.lower() for s in ("chrome", "chromium", "pinchtab"))
    }


def still_alive(owned: set[Process]) -> set[Process]:
    current = processes()
    return {
        p for p in owned if p.pid in current and current[p.pid].started == p.started
    }


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def loopback_listeners(port: int) -> bool:
    """Reject wildcard/nonloopback binds on an experimental debugging/control port."""
    import ipaddress

    found = False
    for file in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in Path(file).read_text().splitlines()[1:]:
            fields = line.split()
            address, raw_port = fields[1].split(":")
            if int(raw_port, 16) != port or fields[3] != "0A":
                continue
            raw = bytes.fromhex(address)
            raw = b"".join(raw[i : i + 4][::-1] for i in range(0, len(raw), 4))
            if not ipaddress.ip_address(raw).is_loopback:
                return False
            found = True
    return found
