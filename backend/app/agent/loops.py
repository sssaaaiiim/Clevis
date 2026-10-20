import hashlib
import json

from app.interfaces.browser import Observation


def fingerprint(observation: Observation) -> str:
    # Refs/generation are fresh every observe; exclude them to measure actual page changes.
    elements = [e.model_dump(exclude={"ref"}) for e in observation.elements]
    return hashlib.sha256(json.dumps(elements, sort_keys=True).encode()).hexdigest()


class NoProgress:
    def __init__(self) -> None:
        self.previous: tuple[str, str] | None = None
        self.count = 0

    def record(self, observation: Observation, successful: bool) -> bool:
        current = (observation.url, fingerprint(observation))
        self.count = (self.count + 1 if current == self.previous else 1) if successful else 0
        self.previous = current
        return self.count >= 5
