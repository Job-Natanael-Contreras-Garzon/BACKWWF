"""SPIKE-01 · UT-1: la copia del contrato acepta las respuestas reales y nada más (CA-3)."""

import base64
import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from app.integrations.ia_contract.contract import CONTRACT_VERSION, DetectEnvelope

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "ai"
CONTRACT_DIR = ROOT / "app" / "integrations" / "ia_contract"

# sha256 (finales de línea LF) de ia-clasificacion-fauna@cdf3292. Si cambia: re-copiar, no editar.
EXPECTED_SHA256 = {
    "contract.py": "5ec33f7467e01e4860ce59e1bb08019f71ae10c59faaf149a1e81c49a6b5daa3",
    "enums.py": "d5887b5b26ccb269db767697512cd3c6db16165f8782ef850dd15388c180bc82",
}

SUCCESS_FIXTURES = [
    "animal_image",
    "animal_species_video",
    "animal_genus_video",
    "animal_video_truncated",
    "blank_image",
    "person_video",
    "vehicle_image",
]


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", SUCCESS_FIXTURES)
def test_official_success_fixture_validates(name: str) -> None:
    envelope = DetectEnvelope.model_validate(_load(name))
    assert envelope.status == "success"
    assert envelope.data is not None


def test_truncated_video_exposes_new_analysis_fields() -> None:
    analysis = DetectEnvelope.model_validate(_load("animal_video_truncated")).data.analysis
    assert analysis.truncated_at_seconds == 15.0
    assert set(analysis.frames_discarded) == {"duplicate", "blurry", "cap"}
    assert isinstance(analysis.low_evidence, bool)


def test_model_with_geofence_is_rejected() -> None:
    payload = _load("animal_species_video")
    payload["data"]["model"]["geofence"] = "BOL"
    with pytest.raises(ValidationError, match="geofence"):
        DetectEnvelope.model_validate(payload)


def test_evidence_base64_is_a_valid_jpeg() -> None:
    evidence = DetectEnvelope.model_validate(_load("animal_species_video")).data.evidence
    with Image.open(io.BytesIO(base64.b64decode(evidence.image_base64))) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 960


def test_contract_version_is_1_0_0() -> None:
    assert CONTRACT_VERSION == "1.0.0"


@pytest.mark.parametrize("file_name", sorted(EXPECTED_SHA256))
def test_contract_copy_is_unedited(file_name: str) -> None:
    content = (CONTRACT_DIR / file_name).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(content).hexdigest() == EXPECTED_SHA256[file_name], (
        f"{file_name} difiere de ia-clasificacion-fauna@cdf3292: re-copiar, no editar a mano"
    )
