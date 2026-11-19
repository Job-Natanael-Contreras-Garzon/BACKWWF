from typing import Any, Literal
from pydantic import BaseModel


class MediaInfo(BaseModel):
    file_name: str
    media_type: str
    sha256: str
    size_bytes: int
    duration_seconds: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None


class CaptureInfo(BaseModel):
    captured_at: str | None = None
    source: str | None = None


class DetectionResult(BaseModel):
    category: Literal["animal", "person", "vehicle", "blank"]
    taxonomy: dict[str, Any] | None = None
    confidence: float
    alternatives: list[dict[str, Any]] = []


class EvidenceInfo(BaseModel):
    frame_index: int | None = None
    timestamp_seconds: float | None = None
    bbox: list[float] | None = None
    image_base64: str
    width: int | None = None
    height: int | None = None


class DetectResponse(BaseModel):
    media: MediaInfo
    capture: CaptureInfo
    result: DetectionResult
    evidence: EvidenceInfo | None = None
    analysis: dict[str, Any] = {}
    model: dict[str, Any] = {}
