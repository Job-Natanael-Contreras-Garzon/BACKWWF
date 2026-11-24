"""Catálogo único de códigos de error y aviso del back (ESTANDARES §6.1 + los agregados).

Fuente para ``GET /api/v1/meta/error-codes`` (solo en desarrollo, FE-51) y para el test que
exige que todo código que lanza el back esté acá con el HTTP correcto. Si agregas un código:
agrégalo acá, en ``utils/errorMessages.js`` del front y avisa a Miguel.

``kind``: ``error`` (respuesta con ``status: "error"``), ``item`` (en un ítem de un lote o una
línea de importación, la respuesta es 200) y ``warning`` (aviso dentro de una respuesta exitosa).
"""

from dataclasses import dataclass
from typing import Literal

ErrorKind = Literal["error", "item", "warning"]


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    code: str
    http_status: int | None  # None: no es el HTTP de la respuesta (ítem o aviso)
    kind: ErrorKind
    message: str  # resumen para la persona; el back puede dar uno más específico
    also_http: tuple[int, ...] = ()  # otro HTTP que el contrato fija para otra ruta


CATALOG: tuple[ErrorSpec, ...] = (
    # --- ESTANDARES §6.1 ---
    ErrorSpec("VALIDATION_ERROR", 422, "error", "Hay datos inválidos en el formulario"),
    ErrorSpec("ROUTE_NOT_FOUND", 404, "error", "Recurso no encontrado"),
    ErrorSpec("RATE_LIMITED", 429, "error", "Demasiadas solicitudes; espera un momento"),
    ErrorSpec("INTERNAL_ERROR", 500, "error", "Error inesperado (con el código de referencia)"),
    ErrorSpec("DATABASE_ERROR", 500, "error", "Error inesperado"),
    ErrorSpec("AUTH_INVALID_CREDENTIALS", 401, "error", "Correo o contraseña incorrectos"),
    ErrorSpec("AUTH_TOKEN_EXPIRED", 401, "error", "Tu sesión expiró"),
    ErrorSpec("AUTH_TOKEN_INVALID", 401, "error", "Sesión inválida; vuelve a iniciar sesión"),
    ErrorSpec("AUTH_REQUIRED", 401, "error", "Debes iniciar sesión para esta acción"),
    ErrorSpec("AUTH_EMAIL_TAKEN", 409, "error", "Ese correo ya está registrado"),
    ErrorSpec("FORBIDDEN", 403, "error", "No tienes permiso sobre este recurso"),
    ErrorSpec(
        "ANON_SESSION_EXPIRED",
        401,
        "error",
        "Tu sesión sin cuenta expiró; sus datos ya no están disponibles",
    ),
    ErrorSpec(
        "ANON_SESSION_ALREADY_CLAIMED", 409, "error", "Estos datos ya se asociaron a otra cuenta"
    ),
    ErrorSpec(
        "ANON_LIMIT_REACHED",
        422,
        "error",
        "Alcanzaste el límite sin cuenta; regístrate para continuar",
    ),
    ErrorSpec("ANON_PUBLIC_NOT_ALLOWED", 422, "error", "Sin cuenta no se puede publicar contenido"),
    ErrorSpec("CAMERA_NOT_FOUND", 404, "error", "La cámara no existe"),
    ErrorSpec("CAMERA_CODE_TAKEN", 409, "error", "Ya tienes una cámara con ese código"),
    ErrorSpec(
        "CAMERA_INVALID_DATES", 422, "error", "La fecha de retiro es anterior a la de colocación"
    ),
    ErrorSpec("CAMERA_NOT_OWNED", 403, "error", "Solo puedes usar tus propias cámaras"),
    ErrorSpec("PROJECT_NOT_FOUND", 404, "error", "El proyecto no existe"),
    ErrorSpec("ALREADY_ASSOCIATED", 409, "error", "La cámara ya está en el proyecto"),
    ErrorSpec(
        "MEDIA_UNSUPPORTED_FORMAT", 415, "error", "Formato no soportado (se listan los válidos)"
    ),
    ErrorSpec("MEDIA_TOO_LARGE", 413, "error", "El archivo supera X MB"),
    ErrorSpec(
        "VIDEO_TRUNCATED",
        None,
        "warning",
        "El video supera 15 s; se analizaron los primeros 15.0 s (F1-D10)",
    ),
    ErrorSpec(
        "MEDIA_DECODE_FAILED", 422, "error", "No se pudo leer el archivo (puede estar dañado)"
    ),
    ErrorSpec("DUPLICATE_FILE", 409, "item", "Este archivo ya fue clasificado en esta cámara"),
    ErrorSpec("AI_UNAVAILABLE", 502, "error", "El servicio de clasificación no está disponible"),
    ErrorSpec("AI_TIMEOUT", 504, "error", "La clasificación tardó demasiado"),
    ErrorSpec(
        "AI_BAD_RESPONSE",
        502,
        "error",
        "El servicio de clasificación respondió de forma inesperada",
    ),
    ErrorSpec("AI_NOT_READY", 503, "error", "El modelo se está cargando; intenta en un minuto"),
    ErrorSpec(
        "PROCESSING_INTERRUPTED",
        None,
        "item",
        "El procesamiento se interrumpió; vuelve a subir el archivo",
    ),
    ErrorSpec("STORAGE_WRITE_FAILED", 500, "error", "No se pudo guardar el fotograma"),
    ErrorSpec("CLASSIFICATION_NOT_FOUND", 404, "error", "La clasificación no existe"),
    ErrorSpec(
        "CATALOG_TAXON_NOT_FOUND",
        422,
        "error",
        "La especie no está en el catálogo de SpeciesNet",
        also_http=(404,),  # API §9.2: GET /catalog/species/{label_id}
    ),
    ErrorSpec("REPORT_EMPTY", 404, "error", "No hay datos con esos filtros"),
    ErrorSpec("IMPORT_INVALID_PACKAGE", 422, "error", "El paquete no es válido"),
    ErrorSpec(
        "IMPORT_UNSUPPORTED_VERSION",
        422,
        "error",
        "Versión de paquete no soportada; actualiza la app",
    ),
    ErrorSpec("IMPORT_TOO_LARGE", 413, "error", "El paquete es demasiado grande"),
    ErrorSpec("IMPORT_CHECKSUM_MISMATCH", 422, "error", "El paquete está dañado o fue modificado"),
    ErrorSpec("IMPORT_ALREADY_IMPORTED", 409, "error", "Este paquete ya fue importado"),
    ErrorSpec(
        "IMPORT_PREVIEW_EXPIRED", 410, "error", "La vista previa expiró; vuelve a subir el paquete"
    ),
    ErrorSpec("IMPORT_NOT_FOUND", 404, "error", "La importación no existe"),
    ErrorSpec("EVIDENCE_INVALID", None, "item", "El fotograma del paquete no es una imagen válida"),
    ErrorSpec(
        "CAPTURE_OUTSIDE_DEPLOYMENT",
        None,
        "warning",
        "La fecha de captura está fuera del periodo de la cámara",
    ),
    ErrorSpec(
        "AUTH_WEAK_PASSWORD",
        422,
        "error",
        "La contraseña debe tener al menos 8 caracteres, con letras y números",
    ),
    ErrorSpec("CAMERA_REQUIRED", 422, "error", "Elige la cámara a la que pertenecen los archivos"),
    ErrorSpec("BATCH_NOT_FOUND", 404, "error", "El lote de subida no existe"),
    ErrorSpec("BATCH_CLOSED", 409, "error", "El lote ya se cerró; inicia una nueva subida"),
    ErrorSpec(
        "QUEUE_USER_LIMIT",
        429,
        "error",
        "Tienes muchos archivos en espera; continuaremos cuando avancen",
    ),
    ErrorSpec(
        "QUEUE_FULL", 503, "error", "El servidor está muy ocupado; reintenta en unos minutos"
    ),
    ErrorSpec("QUEUE_UNAVAILABLE", 503, "error", "La cola de procesamiento no está disponible"),
    ErrorSpec("ITEM_NOT_CANCELLABLE", 409, "error", "El archivo ya se está analizando"),
    ErrorSpec(
        "RETRY_FILE_UNAVAILABLE", 410, "error", "Vuelve a seleccionar el archivo para reintentar"
    ),
    ErrorSpec("PROCESSING_EXPIRED", None, "item", "El archivo estuvo demasiado tiempo en espera"),
    ErrorSpec("CANCELLED_BY_USER", None, "item", "Cancelado"),
    ErrorSpec("CAMERA_DELETED", None, "item", "La cámara fue eliminada"),
    ErrorSpec(
        "DUPLICATE_FILE_OTHER_CAMERA",
        409,
        "item",
        "Este archivo ya está clasificado en otra de tus cámaras",
    ),
    ErrorSpec("CLASSIFICATION_NOT_DONE", 409, "error", "La clasificación todavía no terminó"),
    ErrorSpec(
        "REPEAT_KEEP_REQUIRED", 422, "error", "Debes conservar al menos un registro del grupo"
    ),
    ErrorSpec(
        "REPEAT_MIXED_CAMERAS",
        422,
        "error",
        "Los registros de una ráfaga deben ser de la misma cámara",
    ),
    ErrorSpec("CONFLICT_STALE", 409, "error", "Se modificó en otra ventana; recarga"),
    ErrorSpec("AUTH_RESET_TOKEN_INVALID", 400, "error", "El enlace venció o ya se usó"),
    ErrorSpec(
        "EMAIL_TEMPORARILY_UNAVAILABLE", 503, "error", "No podemos enviar correos en este momento"
    ),
    ErrorSpec(
        "CAMERA_COORDS_SUSPECT", None, "warning", "Coordenadas 0,0 o posiblemente invertidas"
    ),
    ErrorSpec("CAMERA_MOVED_WITH_DATA", None, "warning", "Mover una cámara con datos"),
    ErrorSpec("ADMIN_REQUIRED", 403, "error", "Esta sección es solo para administradores"),
    ErrorSpec("DELETE_REASON_REQUIRED", 422, "error", "Indica el motivo del borrado"),
    ErrorSpec("ENTITY_ALREADY_DELETED", 409, "error", "El registro ya estaba borrado"),
    ErrorSpec(
        "ENTITY_NOT_DELETED", 409, "error", "El registro no está borrado; no hay nada que restaurar"
    ),
    ErrorSpec("CANNOT_DEACTIVATE_SELF", 409, "error", "No puedes desactivar tu propia cuenta"),
    ErrorSpec("SETTING_INVALID", 422, "error", "Valor de configuración no válido"),
    ErrorSpec(
        "ACCOUNT_DISABLED", 403, "error", "Tu cuenta está desactivada; contacta al administrador"
    ),
    ErrorSpec(
        "PASSWORD_CHANGE_REQUIRED", 403, "error", "Debes cambiar tu contraseña antes de continuar"
    ),
    # --- Usados por el back y no listados en §6.1 (21–24/11/2026) ---
    ErrorSpec(
        "SERVICE_UNAVAILABLE",
        503,
        "error",
        "Un servicio necesario no responde; intenta en unos minutos",
    ),
    ErrorSpec("NOT_FOUND", 404, "error", "El recurso no existe"),
    ErrorSpec("METHOD_NOT_ALLOWED", 405, "error", "Método no permitido para esta ruta"),
    ErrorSpec("USER_NOT_FOUND", 404, "error", "El usuario no existe"),
    ErrorSpec("ANON_SESSION_NOT_FOUND", 404, "error", "La sesión sin cuenta no existe"),
    ErrorSpec("LINE_INVALID", None, "item", "La línea del paquete no cumple el formato"),
    ErrorSpec("EVIDENCE_MISSING", None, "item", "Falta el fotograma de una detección de fauna"),
)

BY_CODE: dict[str, ErrorSpec] = {spec.code: spec for spec in CATALOG}
