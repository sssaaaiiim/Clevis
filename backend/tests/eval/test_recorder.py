import json
from pathlib import Path

from pytest import MonkeyPatch

from tests.eval import eval_recorder


def test_recorder_excludes_capabilities_and_content(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    target = tmp_path / "results.json"
    monkeypatch.setattr(eval_recorder, "RESULTS", target)
    canary = "PRIVATE-INPUT-CANARY-9137"
    eval_recorder.append_result(
        {
            "scenario": "RecorderPrivacy",
            "events_matched": True,
            "assertions_passed": [True],
            "approvalToken": canary,
            "controlToken": canary,
            "value": canary,
            "failure_reason": canary,
        },
        False,
    )
    assert canary not in target.read_text()
    record = json.loads(target.read_text())[0]
    assert record["status"] == "fail" and record["failure_reason"]
    assert set(record) == {
        "ts",
        "scenario",
        "status",
        "events_matched",
        "assertions_passed",
        "steps",
        "tokens",
        "cost_usd",
        "failure_reason",
    }
