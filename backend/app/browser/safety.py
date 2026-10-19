import os
import re
import sys
from urllib.parse import urlsplit

from app.interfaces.browser import ErrorCode

SECRET_PATTERN = re.compile(r"password|otp|one[-_ ]?time|token|secret|cvv|cvc|card|ssn", re.I)


class BrowserFailure(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_url(url: str) -> str:
    # TODO Phase 2: domain allowlist and private-network/SSRF policy via ActionValidator
    if url == "about:blank":
        return url
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            _ = parsed.port
            if not any(ord(c) < 32 for c in url):
                return url
    except ValueError:
        pass
    raise BrowserFailure("BLOCKED_URL", "Only HTTP(S) URLs and about:blank are allowed.")


def redact_value(value: str, input_type: str, *attributes: str) -> str:
    if input_type.lower() == "password" or SECRET_PATTERN.search(" ".join(attributes)):
        return "[redacted]" if value else ""
    return value[:100]


def display_available() -> bool:
    return sys.platform != "linux" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
