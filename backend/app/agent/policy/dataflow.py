"""Only hashes, lengths and source hosts are retained; never extracted text."""

import hashlib
import re
from enum import StrEnum

from pydantic import Field

from app.core.events import Model


class DataFlowLimit(ValueError):
    pass


class DataFlowVerdict(StrEnum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    FLAG = "FLAG"


class FlowEntry(Model):
    domains: list[str] = Field(default_factory=list)
    byte_len: int = Field(ge=0)


def content_hash(value: str) -> str:
    return hashlib.sha256(value[:500].encode()).hexdigest()


class DataFlowTracker:
    def __init__(
        self,
        state: dict[str, FlowEntry] | None = None,
        *,
        max_bytes: int = 10_000,
        auto_allow_same_domain: bool = True,
    ) -> None:
        self.state = state if state is not None else {}
        self.max_bytes = max_bytes
        self.auto_allow_same_domain = auto_allow_same_domain

    def record_extraction(self, domain: str, content_hash: str, byte_len: int) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash) or byte_len < 0:
            raise ValueError("Invalid extraction fingerprint.")
        previous = self.state.get(content_hash)
        increment = max(0, byte_len - (previous.byte_len if previous else 0))
        if sum(entry.byte_len for entry in self.state.values()) + increment > self.max_bytes:
            raise DataFlowLimit("MAX_DATA_FLOW_BYTES exceeded.")
        domains = sorted(set(previous.domains if previous else []) | {domain.lower()})
        self.state[content_hash] = FlowEntry(
            domains=domains,
            byte_len=max(byte_len, previous.byte_len if previous else 0),
        )

    def check_type_action(self, target_domain: str, value: str) -> DataFlowVerdict:
        if (
            len(value) < 20
            or value.isnumeric()
            or value.strip().lower()
            in {
                "hello",
                "thank you",
                "search",
                "yes",
                "no",
            }
        ):
            return DataFlowVerdict.ALLOW
        entry = self.state.get(content_hash(value))
        if not entry:
            return DataFlowVerdict.ALLOW
        if any(source != target_domain.lower() for source in entry.domains):
            return DataFlowVerdict.FLAG
        return DataFlowVerdict.ALLOW if self.auto_allow_same_domain else DataFlowVerdict.WARN
