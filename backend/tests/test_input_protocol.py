import json

import pytest

from app.preview.input_protocol import RateLimit, Text, parse_input
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    "message",
    [
        {"type": "unknown"},
        {"type": "mouse", "action": "down", "x": float("nan"), "y": 0},
        {"type": "key", "action": "down", "key": "Enter", "code": "Enter", "modifiers": 16},
        {"type": "text", "value": "a" * 2001},
        {"type": "ping", "extra": "secret"},
        {"type": "mouse", "action": "down", "x": "12", "y": 0},
    ],
)
def test_invalid(message: dict[str, object]) -> None:
    assert parse_input(json.dumps(message), IsolatedSettings()) is None


def test_size_and_private_repr() -> None:
    s = IsolatedSettings(input_max_message_bytes=128, input_max_text_length=10)
    assert parse_input('{"type":"text","value":"' + "a" * 129 + '"}', s) is None
    assert parse_input('{"type":"text","value":"你好你好你好你好你好你好"}', s) is None
    assert parse_input(b"{}", s) is None
    assert parse_input("{", s) is None
    value = parse_input('{"type":"text","value":"CANARY"}', s)
    assert isinstance(value, Text)
    assert "CANARY" not in repr(value) + str(value)


def test_rate_limit() -> None:
    rate = RateLimit(2)
    now = rate.started
    assert rate.allow(now) and rate.allow(now)
    assert not rate.allow(now)
    assert rate.allow(now + 1)
