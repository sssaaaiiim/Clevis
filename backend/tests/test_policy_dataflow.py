import json

import pytest

from app.agent.policy.dataflow import DataFlowLimit, DataFlowTracker, content_hash
from app.agent.state import AgentState


def test_hash_only_cross_domain_and_same_domain() -> None:
    value = "A long fictional confidential sentence for unit tests."
    state = AgentState(goal="Test")
    tracker = DataFlowTracker(state.data_flow)
    tracker.record_extraction("source.example", content_hash(value), len(value.encode()))
    assert tracker.check_type_action("source.example", value) == "ALLOW"
    assert tracker.check_type_action("other.example", value) == "FLAG"
    assert tracker.check_type_action("other.example", "short") == "ALLOW"
    assert tracker.check_type_action("other.example", "1234567890123456789012345") == "ALLOW"
    tracker.auto_allow_same_domain = False
    assert tracker.check_type_action("source.example", value) == "WARN"
    serialized = state.model_dump_json()
    assert value not in serialized
    assert json.loads(serialized)["data_flow"][content_hash(value)]["byte_len"] == len(value)
    assert AgentState.model_validate_json(serialized).data_flow == state.data_flow


def test_limits_are_atomic_and_multiple_sources_remain_flagged() -> None:
    tracker = DataFlowTracker(max_bytes=40)
    value = "A sufficiently long example"
    digest = content_hash(value)
    tracker.record_extraction("a.example", digest, 30)
    tracker.record_extraction("b.example", digest, 30)
    assert tracker.check_type_action("a.example", value) == "FLAG"
    with pytest.raises(DataFlowLimit, match="MAX_DATA_FLOW_BYTES"):
        tracker.record_extraction("c.example", content_hash("another example"), 11)
    assert len(tracker.state) == 1
    with pytest.raises(ValueError):
        tracker.record_extraction("a.example", "not a hash", 1)
    assert content_hash("x" * 500 + "a") == content_hash("x" * 500 + "b")
