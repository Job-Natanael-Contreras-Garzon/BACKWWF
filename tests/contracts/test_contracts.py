"""HU-16 · Contratos compartidos con ``ia-clasificacion-fauna``.

- Paridad byte a byte (LF) de cada archivo copiado cuando el repo de la IA está al lado
  (``IA_REPO_PATH`` o ``../ia-clasificacion-fauna``); sin él, el sha256 fijo de
  ``test_spike01_ai_contract.py`` cubre lo mismo contra ``cdf3292``.
- Todo código de error que la IA declara tiene traducción en el back (ninguno cae por descuido
  en ``AI_BAD_RESPONSE``) y cada código del back tiene HTTP y mensaje.
- Recordatorio D2: cuando ``package_validator.py`` figure como MIT, este test falla para que se
  copie sin editar y se borre la réplica.
"""

import os
from pathlib import Path

import pytest

from app.core import enums as back_enums
from app.integrations import ai_client
from app.integrations.ia_contract import enums as ia_enums
from app.integrations.ia_contract.contract import IA_ERROR_HTTP

ROOT = Path(__file__).resolve().parents[2]
IA_REPO = Path(os.environ.get("IA_REPO_PATH", ROOT.parent / "ia-clasificacion-fauna"))
needs_ia_repo = pytest.mark.skipif(
    not (IA_REPO / "wwm_pipeline").is_dir(), reason="repo de la IA no disponible al lado"
)

COPIES = {
    "app/integrations/ia_contract/contract.py": "wwm_pipeline/contract.py",
    "app/integrations/ia_contract/enums.py": "wwm_pipeline/enums.py",
    "app/integrations/ia_contract/package.py": "wwm_pipeline/package.py",
    "app/integrations/ia_contract/formats.py": "wwm_pipeline/formats.py",
    "app/integrations/ia_contract/LICENSE-CONTRATO-MIT.txt": "LICENSE-CONTRATO-MIT.txt",
    "app/data/speciesnet_catalog.json": "catalog/speciesnet_catalog.json",
}
# Caen en AI_BAD_RESPONSE a propósito: un 500 de la IA, y IA_DURATION_EXCEEDED, que es un resto
# anterior a F1-D10 (ningún video se rechaza por duración; doc 10 §diferencias). Si la IA lo
# retira de IA_ERROR_HTTP, sacarlo de acá.
INTENTIONAL_BAD_RESPONSE = {"IA_INTERNAL", "IA_DURATION_EXCEEDED"}


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


@needs_ia_repo
@pytest.mark.parametrize("ours,theirs", sorted(COPIES.items()))
def test_copied_contract_files_match_ia_repo(ours: str, theirs: str) -> None:
    assert _lf(ROOT / ours) == _lf(IA_REPO / theirs), f"{ours} difiere de la IA: re-copiar"


@needs_ia_repo
def test_package_fixtures_match_ia_repo() -> None:
    ours = {p.name: p.read_bytes() for p in (ROOT / "tests/fixtures/package").glob("*.wwm.zip")}
    theirs = {p.name: p.read_bytes() for p in (IA_REPO / "tests/fixtures/package").glob("*.zip")}
    assert ours and ours == theirs


@needs_ia_repo
def test_d2_reminder_copy_package_validator_once_it_is_mit() -> None:
    mit = (IA_REPO / "LICENSE-CONTRATO-MIT.txt").read_text(encoding="utf-8")
    assert "package_validator" not in mit, (
        "package_validator.py ya es MIT: copiarlo sin editar a ia_contract/ y borrar la réplica "
        "app/services/package_validator.py (D2)"
    )


def test_every_ia_error_code_is_translated() -> None:
    mapped = {code for (_status, code) in ai_client._ERROR_MAP}
    missing = set(IA_ERROR_HTTP) - mapped - INTENTIONAL_BAD_RESPONSE
    assert not missing, f"Códigos de la IA sin traducción en ai_client: {sorted(missing)}"
    for code, status in IA_ERROR_HTTP.items():
        back = ai_client._ERROR_MAP.get((status, code), "AI_BAD_RESPONSE")
        assert back in ai_client._BACK_ERRORS, f"{back} sin HTTP ni mensaje"
        if back == "AI_BAD_RESPONSE":
            assert code in INTENTIONAL_BAD_RESPONSE, f"{code} cae en AI_BAD_RESPONSE"


def test_ia_enums_are_the_ones_the_back_stores() -> None:
    for name in ("Category", "Rank", "MediaType"):
        assert getattr(back_enums, name) is getattr(ia_enums, name)
    # "none" de la IA se guarda como upload_time (import_service); el resto coincide.
    ia_sources = {s.value for s in ia_enums.CaptureSource} - {"none"}
    assert ia_sources <= {s.value for s in back_enums.CaptureSource}
