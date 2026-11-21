"""Fotograma de evidencia (DD-3): el back no guarda el JPEG de la IA tal cual.

Lo decodifica con Pillow, lo limita a ``EVIDENCE_MAX_PX`` del lado mayor y lo vuelve a
codificar como JPEG **sin EXIF** (sin metadatos de la cámara ni del pipeline).
"""

import base64
import binascii
import io
import uuid
from datetime import datetime

from PIL import Image, UnidentifiedImageError

from app.core.config import settings


class EvidenceInvalid(ValueError):
    """El fotograma que mandó la IA no es una imagen válida."""


def reencode(image_base64: str) -> tuple[bytes, int, int]:
    """Devuelve (jpeg, ancho, alto). Corre en un hilo: Pillow bloquea."""
    try:
        raw = base64.b64decode(image_base64, validate=True)
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            rgb = img.convert("RGB")
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as exc:
        raise EvidenceInvalid(str(exc)) from exc
    rgb.thumbnail((settings.EVIDENCE_MAX_PX, settings.EVIDENCE_MAX_PX))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=settings.EVIDENCE_JPEG_QUALITY, optimize=True)
    return out.getvalue(), rgb.width, rgb.height


def evidence_key(classification_id: uuid.UUID, when: datetime) -> str:
    """La BD guarda solo esta clave, nunca rutas ni URLs (DD-3)."""
    return f"evidence/{when:%Y}/{when:%m}/{classification_id}.jpg"
