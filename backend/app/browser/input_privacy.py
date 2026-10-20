"""Ephemeral keyed fingerprints, never a plaintext input history.

Tokens/prefixes cover paste, IME and text split across keystrokes. Echoed tokens are removed
from observations and public feedback; all editable values are hidden after human control.
This cannot undo data deliberately sent by a website to its own servers.
"""

import hashlib
import hmac
import re
import secrets
from typing import Any

from app.interfaces.browser import Observation

_TOKEN = re.compile(r"\w+|[^\w\s]+", re.UNICODE)


class InputPrivacy:
    def __init__(self) -> None:
        self.active = False
        self._salt = secrets.token_bytes(32)
        self._digests: set[bytes] = set()
        self._current = hmac.new(self._salt, digestmod=hashlib.sha256)
        self._kind = ""
        self._length = 0
        self._saturated = False

    def boundary(self) -> None:
        self._current = hmac.new(self._salt, digestmod=hashlib.sha256)
        self._kind = ""
        self._length = 0

    def remember(self, text: str) -> None:
        self.active = True
        for char in text.casefold():
            kind = (
                "space" if char.isspace() else "word" if char.isalnum() or char == "_" else "punct"
            )
            if kind == "space":
                self.boundary()
                continue
            if self._kind != kind:
                self.boundary()
                self._kind = kind
            self._length += 1
            if len(self._digests) >= 50_000 or self._length > 4000:
                self._saturated = True  # Fail closed instead of growing without bound.
                return
            self._current.update(char.encode())
            self._digests.add(self._current.copy().digest())

    def scrub(self, text: str) -> str:
        if not self.active:
            return text
        if self._saturated:
            return "[private content]"
        return _TOKEN.sub(
            lambda m: (
                "[redacted]"
                if hmac.digest(self._salt, m.group().casefold().encode(), "sha256") in self._digests
                else m.group()
            ),
            text,
        )

    def observation(self, observation: Observation) -> Observation:
        if not self.active:
            return observation

        def clean(value: Any) -> Any:
            if isinstance(value, str):
                return self.scrub(value)
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            return value

        data = clean(observation.model_dump())
        # Keep structural refs/roles intact; content strings alone are untrusted/private.
        for original, element in zip(observation.elements, data["elements"], strict=True):
            element["ref"], element["role"], element["tag"] = (
                original.ref,
                original.role,
                original.tag,
            )
            element["type"] = original.type
            element["name"] = element["name"][:80]
            if original.value is not None:
                element["value"] = "[redacted]" if original.value else ""
        return Observation.model_validate(data)
