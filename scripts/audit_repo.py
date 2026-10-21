"""Read-only branch/worktree credential and config audit. Prints paths/counts, never values."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    rb"\bsk-or-v1-[a-fA-F0-9]{32,}\b",
    rb"\bsk-[A-Za-z0-9_-]{30,}\b",
    rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    rb"\bAKIA[0-9A-Z]{16}\b",
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{32,}",
]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.DEVNULL)


def main() -> int:
    private = []
    local = ROOT / "backend/.env"
    if local.exists():
        for line in local.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                value = value.strip().strip("\"'")
                if ("KEY" in key.upper() or "TOKEN" in key.upper()) and len(value) > 24:
                    private.append(value.encode())
    patterns = [re.compile(p) for p in PATTERNS]

    def sensitive(data: bytes) -> bool:
        return any(p.search(data) for p in patterns) or any(v in data for v in private)

    findings = []
    blobs = 0
    for line in git("rev-list", "--objects", "HEAD").decode().splitlines():
        oid, _, path = line.partition(" ")
        if git("cat-file", "-t", oid).strip() != b"blob":
            continue
        blobs += 1
        if sensitive(git("cat-file", "blob", oid)):
            findings.append({"scope": "history", "object": oid[:12], "path": path})
    files = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
    for name in files:
        file = ROOT / name
        if name and file.is_file() and sensitive(file.read_bytes()):
            findings.append({"scope": "working tree", "path": name})
    module = ast.parse((ROOT / "backend/app/config.py").read_text())
    fields = []
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            fields = [
                n.target.id.upper()
                for n in node.body
                if isinstance(n, ast.AnnAssign)
                and isinstance(n.target, ast.Name)
                and n.target.id != "model_config"
            ]
    example = [
        line.split("=", 1)[0]
        for line in (ROOT / "backend/.env.example").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    ]
    missing = sorted(set(fields) - set(example))
    extra = sorted(set(example) - set(fields))
    ignored = (
        subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "--quiet", "backend/.env"]
        ).returncode
        == 0
    )
    tracked_env = [
        p for p in git("ls-files", "-z").decode().split("\0") if p.endswith("/.env") or p == ".env"
    ]
    result = {
        "history_blobs_scanned": blobs,
        "working_files_scanned": len(files) - 1,
        "credential_findings": findings,
        "local_env_ignored": ignored,
        "tracked_env_files": tracked_env,
        "settings_count": len(fields),
        "example_missing": missing,
        "example_extra": extra,
    }
    print(json.dumps(result, indent=2))
    return int(bool(findings or missing or extra or tracked_env or not ignored))


if __name__ == "__main__":
    raise SystemExit(main())
