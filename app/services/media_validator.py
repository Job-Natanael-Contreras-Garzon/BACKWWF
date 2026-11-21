"""Validación de un archivo subido, antes de encolarlo (FL-08, CB-56..CB-59).

Se escribe al temporal por partes mientras se calcula el sha256, así un archivo de 300 MB nunca
está entero en memoria. Lo bloqueante (Pillow, disco) corre en hilos; ``ffprobe`` es un
subproceso con lista de argumentos, sin shell.
"""

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.enums import CaptureSource, MediaType
from app.core.logging import logger
from app.integrations.ia_contract import formats

HEAD_BYTES = formats.HEAD_BYTES
# Misma tolerancia que la IA (sampling.DURATION_TOLERANCE_SECONDS): por encima, trunca a 15 s.
DURATION_TOLERANCE_SECONDS = 0.5
_EXIF_IFD = 0x8769
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306
_FILENAME_DATE = re.compile(
    r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_T ]?(\d{2})[-_:.]?(\d{2})[-_:.]?(\d{2})"
)


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class MediaRejected(Exception):
    """El archivo no entra en la cola. El lote sigue: el ítem responde 200 con este error."""

    def __init__(self, code: str, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.context = context or {}


@dataclass(slots=True)
class StoredUpload:
    path: Path
    tmp_key: str
    size_bytes: int
    sha256: str
    head: bytes


@dataclass(slots=True)
class MediaInfo:
    media_type: MediaType
    duration_seconds: float | None
    captured_at: datetime
    captured_at_source: CaptureSource
    warnings: list[dict[str, Any]] = field(default_factory=list)


def too_large(limit_mb: int) -> MediaRejected:
    return MediaRejected(
        "MEDIA_TOO_LARGE",
        f"El archivo supera el máximo permitido ({limit_mb} MB o 100 MP).",
        {"max_file_mb": limit_mb},
    )


def _open_for_write(path: Path) -> BinaryIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("xb")


async def store_upload(upload: AsyncReadable, file_name: str) -> StoredUpload:
    """Guarda el archivo en ``TMP_UPLOAD_PATH`` con un nombre del servidor (S7)."""
    suffix = Path(file_name).suffix.lower()[:10]
    tmp_key = f"{uuid.uuid4().hex}{suffix}"
    path = Path(settings.TMP_UPLOAD_PATH) / tmp_key
    limit = settings.MAX_FILE_MB * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    head = b""
    handle = await asyncio.to_thread(_open_for_write, path)
    try:
        while chunk := await upload.read(settings.UPLOAD_CHUNK_BYTES):
            size += len(chunk)
            if size > limit:
                raise too_large(settings.MAX_FILE_MB)
            if len(head) < HEAD_BYTES:
                head += chunk[: HEAD_BYTES - len(head)]
            digest.update(chunk)
            await asyncio.to_thread(handle.write, chunk)
    except BaseException:
        await asyncio.to_thread(handle.close)
        await discard(path)
        raise
    await asyncio.to_thread(handle.close)
    return StoredUpload(path, tmp_key, size, digest.hexdigest(), head)


async def discard(path: Path) -> None:
    await asyncio.to_thread(path.unlink, True)


def _parse_exif_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw.strip()[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _inspect_image(path: Path) -> datetime | None:
    """Rechaza imágenes de más de MAX_IMAGE_PIXELS y corruptas; devuelve la fecha EXIF."""
    try:
        with Image.open(path) as img:
            width, height = img.size
            if width * height > settings.MAX_IMAGE_PIXELS:
                raise too_large(settings.MAX_FILE_MB)
            img.verify()  # recorre el archivo: detecta truncados (CB-58)
        with Image.open(path) as img:  # verify() invalida la imagen: se reabre para el EXIF
            exif = img.getexif()
            taken = _parse_exif_datetime(exif.get_ifd(_EXIF_IFD).get(_EXIF_DATETIME_ORIGINAL))
            taken = taken or _parse_exif_datetime(exif.get(_EXIF_DATETIME))
    except Image.DecompressionBombError as exc:  # CB-59
        raise too_large(settings.MAX_FILE_MB) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise MediaRejected("MEDIA_DECODE_FAILED", "La imagen está dañada o incompleta.") from exc
    return taken


async def _probe_video(path: Path) -> tuple[float | None, datetime | None]:
    """Duración y fecha del contenedor con ffprobe. Si ffprobe falla, el video está dañado."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:format_tags=creation_time",
            "-of",
            "json",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.warning("ffprobe no está instalado", extra={"event": "media.ffprobe.missing"})
        return None, None
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(), timeout=settings.FFPROBE_TIMEOUT_SECONDS
        )
    except TimeoutError as exc:
        process.kill()
        raise MediaRejected("MEDIA_DECODE_FAILED", "No se pudo leer el video.") from exc
    if process.returncode != 0:
        raise MediaRejected("MEDIA_DECODE_FAILED", "El video está dañado o incompleto.")
    data = json.loads(stdout or b"{}").get("format", {})
    duration = float(data["duration"]) if data.get("duration") not in (None, "N/A") else None
    created = data.get("tags", {}).get("creation_time")
    container_dt: datetime | None = None
    if isinstance(created, str):
        try:
            container_dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
        except ValueError:
            container_dt = None
    return duration, container_dt


def _from_filename(file_name: str) -> datetime | None:
    match = _FILENAME_DATE.search(Path(file_name).stem)
    if match is None:
        return None
    try:
        year, month, day, hour, minute, second = (int(part) for part in match.groups())
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


async def inspect_media(
    stored: StoredUpload, file_name: str, client_mtime: datetime | None
) -> MediaInfo:
    """Formato (extensión + firma), píxeles o duración, y la mejor fecha de captura."""
    ok, reason = formats.check(file_name, stored.head)
    if not ok:  # CB-57, CB-57b, CB-57c
        raise MediaRejected(
            "MEDIA_UNSUPPORTED_FORMAT",
            "Este formato no se admite.",
            {
                "reason": reason,
                "accepted": [ext.lstrip(".") for ext in formats.ACCEPTED_EXTENSIONS],
            },
        )
    is_image = Path(file_name).suffix.lower() in formats.IMAGE_EXTENSIONS
    warnings: list[dict[str, Any]] = []
    duration: float | None = None
    embedded: datetime | None
    if is_image:
        embedded = await asyncio.to_thread(_inspect_image, stored.path)
        source = CaptureSource.EXIF
    else:
        duration, embedded = await _probe_video(stored.path)
        source = CaptureSource.CONTAINER
        if (
            duration is not None
            and duration > settings.MAX_VIDEO_SECONDS + DURATION_TOLERANCE_SECONDS
        ):
            warnings.append(  # F1-D10, CB-56: no se rechaza, la IA analiza los primeros 15 s
                {
                    "code": "VIDEO_TRUNCATED",
                    "message": (
                        f"El video dura {duration:.1f} s; se analizarán los primeros "
                        f"{settings.MAX_VIDEO_SECONDS} s."
                    ),
                    "context": {"duration_seconds": round(duration, 2)},
                }
            )

    captured_at, captured_source = embedded, source
    if captured_at is None and (from_name := _from_filename(file_name)) is not None:
        captured_at, captured_source = from_name, CaptureSource.FILENAME
    if captured_at is None and client_mtime is not None:
        captured_at, captured_source = _naive_utc(client_mtime), CaptureSource.CLIENT_MTIME
    if captured_at is None:
        captured_at, captured_source = (
            datetime.now(UTC).replace(tzinfo=None),
            CaptureSource.UPLOAD_TIME,
        )
    return MediaInfo(
        media_type=MediaType.IMAGE if is_image else MediaType.VIDEO,
        duration_seconds=duration,
        captured_at=captured_at,
        captured_at_source=captured_source,
        warnings=warnings,
    )
