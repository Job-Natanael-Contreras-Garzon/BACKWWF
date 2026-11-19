import pytest
from pydantic import ValidationError

from app.integrations.ai_contract import DetectResponse
from app.integrations.ai_client import detect_media


def test_detect_response_validates_contract_schema() -> None:
    """SPIKE-01 (CA-2 / CB-37): DetectResponse valida el contrato oficial de API_IA_BACK.md."""
    payload = {
        "media": {
            "file_name": "clip.mp4",
            "media_type": "video",
            "sha256": "a" * 64,
            "size_bytes": 1024,
            "duration_seconds": 5.0,
            "fps": 30.0,
            "width": 1920,
            "height": 1080,
        },
        "capture": {"captured_at": "2026-11-17T00:00:00Z", "source": "exif"},
        "result": {
            "category": "animal",
            "taxonomy": {"label_id": "panthera_onca", "scientific_name": "Panthera onca"},
            "confidence": 0.94,
            "alternatives": [],
        },
        "evidence": {
            "frame_index": 12,
            "timestamp_seconds": 1.5,
            "bbox": [0.1, 0.2, 0.5, 0.6],
            "image_base64": "ZmFrZQ==",
            "width": 640,
            "height": 480,
        },
        "analysis": {"frames_sampled": 5},
        "model": {
            "detector": "megadetector",
            "classifier": "speciesnet",
            "geofence": "latam",
            "sampling": "uniform",
            "pipeline_version": "1.0.0",
        },
    }

    parsed = DetectResponse.model_validate(payload)
    assert parsed.result.category == "animal"
    assert parsed.evidence is not None
    assert parsed.evidence.image_base64 == "ZmFrZQ=="

    with pytest.raises(ValidationError):
        DetectResponse.model_validate({"media": {}})


def test_ai_client_exposes_async_detect_media() -> None:
    """SPIKE-01 (CA-1): ai_client expone detect_media asíncrono."""
    import inspect

    assert inspect.iscoroutinefunction(detect_media)
