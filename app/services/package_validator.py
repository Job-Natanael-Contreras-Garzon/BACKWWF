"""Validación del paquete ``.wwm.zip`` de escritorio (HU-10, PAQUETE_ESCRITORIO §5, CB-82..84).

Código propio: el ``package_validator.py`` de la IA es AGPL-3.0 solamente (no está en la lista MIT
del contrato), así que acá solo se reusan los **modelos** MIT de ``ia_contract/package.py``.

Orden de los controles (el primero que falla rechaza todo el paquete, sin escribir en la BD):
tamaño → rutas (Zip Slip, symlinks) → manifest → versión → checksum. Después, cada línea se valida
por separado y sus problemas van a ``issues`` (la línea se salta, el paquete sigue).
"""

import hashlib
import io
import json
import re
import stat
import zipfile
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import AppError, BusinessRuleError
from app.integrations.ia_contract.package import (
    JSONL_NAME,
    MANIFEST_NAME,
    PACKAGE_FORMAT,
    SUPPORTED_MAJOR,
    Manifest,
    PackageLine,
)

MAX_ENTRIES = 20_000
_EVIDENCE_NAME = re.compile(r"^evidence/[0-9a-f]{64}\.jpg$")
_MAX_EVIDENCE_BYTES = 5 * 1024 * 1024  # un fotograma de ≤ 960 px pesa ~100 KB


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


def _check_entries(infos: list[zipfile.ZipInfo]) -> None:
    limit = settings.IMPORT_MAX_MB * 1024 * 1024
    if len(infos) > MAX_ENTRIES:
        raise PackageTooLarge(
            "IMPORT_TOO_LARGE", f"El paquete tiene más de {MAX_ENTRIES} archivos."
        )
    if sum(i.file_size for i in infos) > 3 * limit:  # zip bomb (CB-84)
        raise PackageTooLarge("IMPORT_TOO_LARGE", "Descomprimido es demasiado grande.")
    seen: set[str] = set()
    for info in infos:
        name = info.filename
        if stat.S_ISLNK(info.external_attr >> 16):
            raise invalid("El paquete contiene enlaces simbólicos.")
        if info.is_dir() and name == "evidence/":
            continue
        if name not in (MANIFEST_NAME, JSONL_NAME) and not _EVIDENCE_NAME.match(name):
            raise invalid("El paquete tiene archivos fuera de la estructura permitida.")
        if name in seen:
            raise invalid("El paquete tiene archivos repetidos.")
        seen.add(name)
    for required in (MANIFEST_NAME, JSONL_NAME):
        if required not in seen:
            raise invalid(f"Falta {required} en el paquete.")


def _manifest(raw: bytes) -> Manifest:
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise invalid("manifest.json no es JSON válido.") from exc
    if not isinstance(data, dict):
        raise invalid("manifest.json no tiene la forma esperada.")
    version = str(data.get("format_version", ""))
    if data.get("format") != PACKAGE_FORMAT or not re.match(rf"^{SUPPORTED_MAJOR}\.\d+$", version):
        newer = version.split(".")[0].isdigit() and int(version.split(".")[0]) > SUPPORTED_MAJOR
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


def _evidence_ok(zf: zipfile.ZipFile, name: str, names: set[str]) -> str | None:
    """Devuelve el código del problema, o None si el JPEG abre bien."""
    if name not in names:
        return "EVIDENCE_MISSING"
    info = zf.getinfo(name)
    if info.file_size > _MAX_EVIDENCE_BYTES:
        return "EVIDENCE_INVALID"
    try:
        with Image.open(io.BytesIO(zf.read(name))) as img:
            if img.format != "JPEG":
                return "EVIDENCE_INVALID"
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        return "EVIDENCE_INVALID"
    return None


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
        expected = manifest.checksums[JSONL_NAME].removeprefix("sha256:")
        if hashlib.sha256(jsonl).hexdigest() != expected:
            raise BusinessRuleError(
                "IMPORT_CHECKSUM_MISMATCH", "El paquete está dañado (checksum distinto)."
            )
        raw_lines = [ln for ln in jsonl.decode("utf-8", "replace").splitlines() if ln.strip()]
        if len(raw_lines) != manifest.counts.lines:
            raise invalid("La cantidad de líneas no coincide con el manifest.")
        lines = [_parse_line(n, raw, zf, names, catalog_ids) for n, raw in enumerate(raw_lines, 1)]
    return ParsedPackage(sha256=digest.hexdigest(), manifest=manifest, lines=lines)


def _parse_line(
    number: int,
    raw: str,
    zf: zipfile.ZipFile,
    names: set[str],
    catalog_ids: Collection[str],
) -> ParsedLine:
    def issue(code: str, file_name: str | None) -> ParsedLine:
        return ParsedLine(number, None, [Issue(number, file_name, "error", code, _MESSAGES[code])])

    try:
        data = json.loads(raw)
    except ValueError:
        return issue("LINE_INVALID", None)
    name = data.get("file_name") if isinstance(data, dict) else None
    try:
        line = PackageLine.model_validate(data)
    except ValidationError:
        return issue("LINE_INVALID", name if isinstance(name, str) else None)
    if line.taxonomy is not None and line.taxonomy.label_id not in catalog_ids:
        return issue("CATALOG_TAXON_NOT_FOUND", line.file_name)
    if line.evidence is not None:
        problem = _evidence_ok(zf, line.evidence.file, names)
        if problem:
            return issue(problem, line.file_name)
    return ParsedLine(number, line)
