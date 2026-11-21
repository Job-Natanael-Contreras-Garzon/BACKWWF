"""Validación del paquete ``.wwm.zip`` de escritorio (HU-10, PAQUETE_ESCRITORIO §5, CB-82..84).

Sigue paso a paso al validador de referencia de la IA (``wwm_pipeline/package_validator.py``, D2):
mismos controles, mismo orden y mismos códigos. Se reescribió en vez de copiarse porque hoy ese
archivo es AGPL-3.0 (no está en ``LICENSE-CONTRATO-MIT.txt``); cuando se publique como MIT se
puede reemplazar por la copia sin editar. Acá solo se usan los modelos MIT de ``package.py``.

Orden: tamaño → entradas (cantidad, descomprimido) → rutas (Zip Slip, symlinks, nombres) →
archivos obligatorios → versión → manifest → checksum → líneas → conteos del manifest.
Los primeros rechazan el paquete entero; cada línea suma sus problemas a ``issues``.
"""

import hashlib
import io
import json
import re
import stat
import zipfile
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from PIL import Image
from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import AppError, BusinessRuleError
from app.integrations.ia_contract.package import (
    JSONL_NAME,
    MANIFEST_NAME,
    SUPPORTED_MAJOR,
    Manifest,
    PackageLine,
    count_lines,
)

MAX_ENTRIES = 20_000
_EVIDENCE_NAME = re.compile(r"^evidence/[0-9a-f]{64}\.jpg$")


class PackageTooLarge(AppError):
    http_status = 413
    default_message = "El paquete supera el tamaño permitido."


def invalid(message: str) -> BusinessRuleError:
    return BusinessRuleError("IMPORT_INVALID_PACKAGE", message)


@dataclass
class Issue:
    line: int
    file_name: str | None
    severity: str  # error | warning
    code: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "line": self.line,
            "file_name": self.file_name,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ParsedLine:
    number: int  # 1-based, como lo ve el usuario
    line: PackageLine | None
    issues: list[Issue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.line is not None and not any(i.severity == "error" for i in self.issues)


@dataclass
class ParsedPackage:
    sha256: str
    manifest: Manifest
    lines: list[ParsedLine]


def _safe_member(info: zipfile.ZipInfo) -> bool:
    path = PurePosixPath(info.filename)
    is_symlink = stat.S_ISLNK(info.external_attr >> 16)
    return not (path.is_absolute() or ".." in path.parts or "\\" in info.filename or is_symlink)


def _allowed_name(name: str) -> bool:
    return name in (MANIFEST_NAME, JSONL_NAME) or bool(_EVIDENCE_NAME.match(name))


def _check_entries(infos: list[zipfile.ZipInfo]) -> None:
    limit = settings.IMPORT_MAX_MB * 1024 * 1024
    if len(infos) > MAX_ENTRIES:
        raise PackageTooLarge("IMPORT_TOO_LARGE", f"Tiene más de {MAX_ENTRIES} archivos.")
    if sum(i.file_size for i in infos) > 3 * limit:  # zip bomb (CB-84)
        raise PackageTooLarge("IMPORT_TOO_LARGE", "Descomprimido es demasiado grande.")
    for info in infos:
        if not _safe_member(info) or not _allowed_name(info.filename):
            raise invalid("El paquete tiene archivos fuera de la estructura permitida.")
    names = {i.filename for i in infos}
    if MANIFEST_NAME not in names or JSONL_NAME not in names:
        raise invalid("Faltan manifest.json o classifications.jsonl.")


def _manifest(raw: bytes) -> Manifest:
    """Primero la versión, después el schema completo (como la referencia)."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise invalid("manifest.json no es JSON válido.") from exc
    if not isinstance(data, dict):
        raise invalid("manifest.json no tiene la forma esperada.")
    version = str(data.get("format_version", ""))
    if not re.match(r"^\d+\.\d+$", version) or int(version.split(".")[0]) != SUPPORTED_MAJOR:
        newer = bool(re.match(r"^\d+", version)) and int(version.split(".")[0]) > SUPPORTED_MAJOR
        raise BusinessRuleError(
            "IMPORT_UNSUPPORTED_VERSION",
            "El paquete es de una versión más nueva: actualiza la plataforma."
            if newer
            else "El formato del paquete no es compatible: actualiza la app de escritorio.",
        )
    try:
        return Manifest.model_validate(data)
    except ValidationError as exc:
        raise invalid("manifest.json no cumple el formato.") from exc


def _valid_jpeg(data: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != "JPEG":
                return False
            img.verify()
    except Exception:  # noqa: BLE001 - cualquier fallo de Pillow = fotograma inválido
        return False
    return True


_MESSAGES = {
    "LINE_INVALID": "La línea no cumple el formato del paquete.",
    "CATALOG_TAXON_NOT_FOUND": "El taxón no está en el catálogo de la plataforma.",
    "EVIDENCE_MISSING": "Falta el fotograma de esta línea.",
    "EVIDENCE_INVALID": "El fotograma está dañado o no es un JPEG.",
}


def parse(path: Path, catalog_ids: Collection[str]) -> ParsedPackage:
    """Valida el zip en disco. Corre en un hilo: lee y verifica imágenes."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise invalid("El archivo no es un .zip válido.") from exc
    with zf:
        infos = zf.infolist()
        _check_entries(infos)
        names = {i.filename for i in infos}
        manifest = _manifest(zf.read(MANIFEST_NAME))
        jsonl = zf.read(JSONL_NAME)
        if manifest.checksums.get(JSONL_NAME) != "sha256:" + hashlib.sha256(jsonl).hexdigest():
            raise BusinessRuleError(
                "IMPORT_CHECKSUM_MISMATCH", "El paquete está dañado (checksum distinto)."
            )
        try:
            text = jsonl.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise invalid("classifications.jsonl no es UTF-8.") from exc
        lines = [
            _parse_line(number, raw, zf, names, catalog_ids)
            for number, raw in enumerate(text.splitlines(), start=1)
            if raw.strip()
        ]
        parsed = [p.line for p in lines if p.line is not None]
        all_parsed = not any(i.code == "LINE_INVALID" for p in lines for i in p.issues)
        if all_parsed and count_lines(parsed) != manifest.counts:
            raise invalid("Los conteos del manifest no coinciden con las líneas.")
    return ParsedPackage(sha256=digest.hexdigest(), manifest=manifest, lines=lines)


def _parse_line(
    number: int,
    raw: str,
    zf: zipfile.ZipFile,
    names: set[str],
    catalog_ids: Collection[str],
) -> ParsedLine:
    """Una línea puede sumar más de un problema (taxón y fotograma), como en la referencia."""
    try:
        line = PackageLine.model_validate_json(raw)
    except ValidationError:
        return ParsedLine(number, None, [_issue(number, None, "LINE_INVALID")])
    result = ParsedLine(number, line)
    if line.taxonomy is not None and line.taxonomy.label_id not in catalog_ids:
        result.issues.append(_issue(number, line.file_name, "CATALOG_TAXON_NOT_FOUND"))
    if line.evidence is not None:
        if line.evidence.file not in names:
            result.issues.append(_issue(number, line.file_name, "EVIDENCE_MISSING"))
        elif not _valid_jpeg(zf.read(line.evidence.file)):
            result.issues.append(_issue(number, line.file_name, "EVIDENCE_INVALID"))
    return result


def _issue(number: int, file_name: str | None, code: str) -> Issue:
    return Issue(number, file_name, "error", code, _MESSAGES[code])
