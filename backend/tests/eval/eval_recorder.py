"""Numeric/boolean/static-identifier results only; never serialize test exceptions."""

import json
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
    records = json.loads(RESULTS.read_text()) if RESULTS.exists() else []
    records.append(record)
    temporary = RESULTS.with_suffix(".tmp")
    temporary.write_text(json.dumps(records, indent=2) + "\n")
    temporary.replace(RESULTS)
