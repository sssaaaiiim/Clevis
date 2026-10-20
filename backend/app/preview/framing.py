"""Wire frames are length-prefixed metadata followed by untouched encoded image bytes."""

import json
import struct
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import Field

from app.core.events import Model


class FrameMetadata(Model):
    format: Literal["jpeg", "png"]
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    deviceScaleFactor: float = Field(gt=0)
    viewportWidth: int = Field(ge=1)
    viewportHeight: int = Field(ge=1)
    pageScaleFactor: float = 1
    scrollOffsetX: float = 0
    scrollOffsetY: float = 0
    offsetTop: float = 0
    seq: int = Field(ge=1)
    ts: str
    tabId: str


def encode_frame(metadata: dict[str, Any], image: bytes) -> bytes:
    header = json.dumps(metadata, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return struct.pack("!I", len(header)) + header + image


def decode_frame(packet: bytes) -> tuple[dict[str, Any], bytes]:
    if len(packet) < 4:
        raise ValueError("Missing frame header.")
    size = struct.unpack("!I", packet[:4])[0]
    if size > 64 * 1024 or len(packet) < 4 + size:
        raise ValueError("Invalid metadata length.")
    metadata = json.loads(packet[4 : 4 + size])
    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be an object.")
    return metadata, packet[4 + size :]


@dataclass(frozen=True, repr=False)
class Frame:
    image: bytes = field(repr=False)
    metadata: FrameMetadata

    def packet(self) -> bytes:
        return encode_frame(self.metadata.model_dump(), self.image)
