"""Conservative text redaction shared by prompt and public-event projections."""

import re


def redact(text: str, api_key: str = "") -> str:
    if api_key:
        text = text.replace(api_key, "[redacted]")
    # TODO Phase 3: injection guard layers. Defensive secret filtering is a separate concern.
    text = re.sub(
        r"(?i)\b(?:bearer\s+|(?:token|secret|api[_-]?key|password)\s*[:=]\s*)[^\s\"<>]+",
        "[redacted]",
        text,
    )
    # Long mixed random-looking identifiers, including common API token formats.
    text = re.sub(
        r"\b(?=[A-Za-z0-9_/-]{32,}\b)(?=[A-Za-z0-9_/-]*[0-9])"
        r"(?=[A-Za-z0-9_/-]*[A-Za-z])[A-Za-z0-9_/-]{32,}\b",
        "[redacted]",
        text,
    )
    return text

