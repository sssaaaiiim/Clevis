"""Numeric/boolean/static-identifier results only; never serialize test exceptions."""

import fcntl
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parents[3] / "docs" / "eval-results.json"


def append_result(data: dict[str, Any], passed: bool) -> None:
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "scenario": data["scenario"],
        "status": "pass" if passed else "fail",
        "events_matched": bool(data.get("events_matched", False)),
        "assertions_passed": data.get("assertions_passed", []),
        "steps": int(data.get("steps", 0)),
        "tokens": int(data.get("tokens", 0)),
        "cost_usd": float(data.get("cost_usd", 0)),
        "failure_reason": ""
        if passed
        else "Scenario assertion or execution failed; inspect pytest locally.",
    }
    lock_path = Path(tempfile.gettempdir()) / (
        "clevis-eval-" + hashlib.sha256(str(RESULTS).encode()).hexdigest()[:16] + ".lock"
    )
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        records = json.loads(RESULTS.read_text()) if RESULTS.exists() else []
        records.append(record)
        with tempfile.NamedTemporaryFile(mode="w", dir=RESULTS.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(records, output, indent=2)
            output.write("\n")
        try:
            temporary.replace(RESULTS)
        finally:
            temporary.unlink(missing_ok=True)
