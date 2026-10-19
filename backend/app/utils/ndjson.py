"""Helpers for newline-delimited JSON streaming."""

import json
from typing import Any


def ndjson(obj: dict[str, Any]) -> str:
    """Serialize an object to a single NDJSON line."""
    return json.dumps(obj, ensure_ascii=False) + "\n"
