"""Best-effort size and token estimates for browser page layouts."""

import json
import math
from typing import Any


def _json_layout(value: Any) -> str:
    if isinstance(value, bytes | bytearray | memoryview):
        raise TypeError("Binary page data cannot be tokenized.")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def compare_layout_sizes(raw_html: str, snapshot: Any) -> dict[str, int | float]:
    """Compare raw HTML with the compact JSON accessibility layout."""
    if not isinstance(raw_html, str):
        raise TypeError("Raw HTML must be text.")

    snapshot_json = _json_layout(snapshot)
    html_bytes = len(raw_html.encode("utf-8"))
    snapshot_bytes = len(snapshot_json.encode("utf-8"))
    bytes_saved = html_bytes - snapshot_bytes
    reduction_percent = (bytes_saved / html_bytes * 100) if html_bytes else 0.0

    html_token_input = _json_layout({"html": raw_html})
    snapshot_token_input = _json_layout({"snapshot": snapshot})
    html_tokens_estimate = math.ceil(len(html_token_input.encode("utf-8")) / 4)
    snapshot_tokens_estimate = math.ceil(len(snapshot_token_input.encode("utf-8")) / 4)

    return {
        "html_bytes": html_bytes,
        "snapshot_bytes": snapshot_bytes,
        "bytes_saved": bytes_saved,
        "reduction_percent": round(reduction_percent, 2),
        "html_tokens_estimate": html_tokens_estimate,
        "snapshot_tokens_estimate": snapshot_tokens_estimate,
        "tokens_saved_estimate": html_tokens_estimate - snapshot_tokens_estimate,
    }
