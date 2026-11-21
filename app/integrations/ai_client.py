"""Cliente de la IA (``POST {AI_SERVICE_URL}/api/v1/detect``, contrato ``ia_contract`` 1.0.0).

Traduce en el borde cada fallo de la IA a un ``AppError`` del catálogo del back y nunca inventa
un resultado (DD-4). Solo reintenta una vez ``500 IA_INTERNAL``; los reintentos con espera
(``IA_BUSY``, timeouts, caídas) son del worker (HU-11).
"""

import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import DependencyError
from app.integrations.ia_contract.contract import DetectEnvelope, DetectResult

logger = logging.getLogger(__name__)

# (HTTP, código IA) -> código del back. El HTTP importa: 400 y 415 comparten IA_INVALID_FORMAT.
_ERROR_MAP: dict[tuple[int, str], str] = {
    (
        400,
        "IA_INVALID_FORMAT",
    ): "AI_BAD_RESPONSE",  # faltó file/file_name: bug nuestro, no del usuario
    (401, "IA_UNAUTHORIZED"): "AI_UNAVAILABLE",
    (413, "IA_FILE_TOO_LARGE"): "MEDIA_TOO_LARGE",
    (415, "IA_INVALID_FORMAT"): "MEDIA_UNSUPPORTED_FORMAT",
    (422, "IA_DECODE_FAILED"): "MEDIA_DECODE_FAILED",
    (500, "IA_INTERNAL"): "AI_BAD_RESPONSE",
    (503, "IA_MODEL_NOT_READY"): "AI_NOT_READY",
    (503, "IA_BUSY"): "AI_UNAVAILABLE",
    (504, "IA_PROCESSING_TIMEOUT"): "AI_TIMEOUT",
}


# Código del back -> (HTTP que responde el back, nivel de log, mensaje para la persona).
_BACK_ERRORS: dict[str, tuple[int, int, str]] = {
    "AI_UNAVAILABLE": (
        502,
        logging.ERROR,
        "El servicio de clasificación no está disponible. Intenta más tarde.",
    ),
    "AI_TIMEOUT": (504, logging.ERROR, "La clasificación tardó demasiado. Intenta de nuevo."),
    "AI_NOT_READY": (
        503,
        logging.WARNING,
        "El servicio de clasificación se está iniciando. Intenta en unos minutos.",
    ),
    "AI_BAD_RESPONSE": (
        502,
        logging.ERROR,
        "El servicio de clasificación respondió de forma inesperada.",
    ),
    "MEDIA_TOO_LARGE": (
        413,
        logging.INFO,
        "El archivo supera el tamaño o resolución máxima permitida (300 MB / 100 MP).",
    ),
    "MEDIA_UNSUPPORTED_FORMAT": (415, logging.INFO, "Formato de archivo no soportado."),
    "MEDIA_DECODE_FAILED": (422, logging.INFO, "No se pudo leer el archivo; puede estar dañado."),
}


class AiClientError(DependencyError):
    """Fallo de la IA ya traducido al catálogo del back; el handler global lo responde (HU-01)."""

    def __init__(
        self,
        code: str,
        ia_http_status: int | None = None,
        ia_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        http_status, log_level, message = _BACK_ERRORS[code]
        super().__init__(code, message, context=context)
        self.http_status = http_status
        self.log_level = log_level
        self.ia_http_status = ia_http_status
        self.ia_code = ia_code


async def detect_media(
    file_path: Path,
    request_id: str | None = None,
    flow: str = "FL-08",
    client: httpx.AsyncClient | None = None,
    file_name: str | None = None,
) -> DetectResult:
    """Clasifica un archivo en la IA y devuelve ``data`` validado contra el contrato.

    ``file_name`` es el nombre original (el worker envía el temporal ``<uuid>.ext``).
    """
    base_url = settings.AI_SERVICE_URL.rstrip("/")
    if not base_url or not settings.AI_API_KEY:
        logger.critical("config.invalid: falta AI_SERVICE_URL o AI_API_KEY; no se llama a la IA")
        raise AiClientError("AI_UNAVAILABLE")

    url = f"{base_url}/api/v1/detect"
    headers = {
        "X-API-Key": settings.AI_API_KEY,
        "X-Request-ID": request_id or uuid.uuid4().hex[:12],
        "X-Flow": flow,
    }
    name = file_name or file_path.name
    if client is not None:
        return await _detect_with_retry(client, url, headers, file_path, name)
    # Sin cliente compartido (CLI, scripts) se abre uno para esta llamada; el worker pasa el suyo.
    async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as own_client:
        return await _detect_with_retry(own_client, url, headers, file_path, name)


async def _detect_with_retry(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], file_path: Path, name: str
) -> DetectResult:
    try:
        return await _detect_once(client, url, headers, file_path, name)
    except AiClientError as exc:
        if exc.ia_code != "IA_INTERNAL":
            raise
        logger.warning(
            "ai.detect.retried: IA_INTERNAL, un reintento (request_id=%s)", headers["X-Request-ID"]
        )
        return await _detect_once(client, url, headers, file_path, name)


async def _detect_once(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], file_path: Path, name: str
) -> DetectResult:
    try:
        # shortcut: httpx lee el archivo por bloques mientras lo envía (lecturas de disco cortas);
        # si se mide bloqueo del event loop con archivos de 300 MB, pasar a un stream asíncrono.
        with file_path.open("rb") as file:  # noqa: ASYNC230
            response = await client.post(
                url,
                headers=headers,
                files={"file": (name, file)},
                data={"file_name": name},
            )
    except httpx.TimeoutException as exc:
        logger.warning(
            "ai.detect.failed: timeout esperando a la IA (request_id=%s)", headers["X-Request-ID"]
        )
        raise AiClientError("AI_TIMEOUT") from exc
    except httpx.TransportError as exc:
        logger.error("ai.detect.failed: IA inalcanzable (request_id=%s)", headers["X-Request-ID"])
        raise AiClientError("AI_UNAVAILABLE") from exc

    if response.status_code == 200:
        return _parse_success(response)
    raise _translate_error(response)


def _parse_success(response: httpx.Response) -> DetectResult:
    try:
        body = response.json()
        envelope = DetectEnvelope.model_validate(body)
    except ValueError as exc:  # JSON inválido o fuera de contrato (ValidationError es ValueError)
        received = _received_keys(body) if isinstance(exc, ValidationError) else "no es JSON"
        # Se registran solo las claves: los valores pueden traer image_base64.
        logger.error("ai.response.invalid: respuesta 200 fuera de contrato; claves=%s", received)
        raise AiClientError("AI_BAD_RESPONSE", ia_http_status=200) from None
    if envelope.data is None:
        logger.error("ai.response.invalid: respuesta 200 sin data (status=%s)", envelope.status)
        raise AiClientError("AI_BAD_RESPONSE", ia_http_status=200)
    return envelope.data


def _translate_error(response: httpx.Response) -> AiClientError:
    ia_code, context = _read_error(response)
    status = response.status_code
    code = _ERROR_MAP.get((status, ia_code or ""), "AI_BAD_RESPONSE")
    if code == "MEDIA_DECODE_FAILED" and context.get("reason") == "too_many_pixels":
        code = "MEDIA_TOO_LARGE"

    if status == 401:
        logger.critical(
            "ai.unauthorized: la IA rechazó X-API-Key; revisar AI_API_KEY en ambos servicios"
        )
    elif status == 400 or (status, ia_code or "") not in _ERROR_MAP:
        logger.error(
            "ai.request.rejected: HTTP %s %s -> %s (campos=%s)",
            status,
            ia_code,
            code,
            context.get("errors"),
        )
    else:
        logger.warning("ai.detect.failed: HTTP %s %s -> %s", status, ia_code, code)
    return AiClientError(code, ia_http_status=status, ia_code=ia_code, context=context)


def _read_error(response: httpx.Response) -> tuple[str | None, dict[str, Any]]:
    """Lee ``error.code`` y ``details[0].context`` sin el schema estricto.

    Así un campo nuevo en el error de la IA no tapa el error real con un AI_BAD_RESPONSE.
    """
    try:
        error = response.json().get("error") or {}
        details = error.get("details") or [{}]
        return error.get("code"), details[0].get("context") or {}
    except (ValueError, AttributeError, IndexError, TypeError):
        return None, {}


def _received_keys(body: Any) -> dict[str, list[str]]:
    if not isinstance(body, dict):
        return {"body": [type(body).__name__]}
    data = body.get("data")
    return {"body": sorted(body), "data": sorted(data) if isinstance(data, dict) else []}
