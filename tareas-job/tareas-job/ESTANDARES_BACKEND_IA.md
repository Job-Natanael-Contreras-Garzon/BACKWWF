# Estándares de arquitectura, respuestas, errores y logs

> Documento interno · CETERIS404 · v1 — 07/11/2026
> **Aplica a:** `BACKWWF` (Job), `ia-deteccion`, que incluye la API y la app de escritorio (Diego), y a la parte del front que consume la API (Miguel).
> **Objetivo:** que los tres repos respondan, fallen y registren de la misma forma, para que cualquier error se pueda rastrear de punta a punta (front → back → IA) y saber **en qué flujo y en qué paso** ocurrió. Se acepta refactorizar todo lo necesario.
> Los IDs de flujo (`FL-xx`) están en [FLUJOS_SISTEMA.md](FLUJOS_SISTEMA.md). **El proceso para implementar cada tarea** (HU, unidades de trabajo, pruebas, patrones, seguridad, revisión) está en [GUIA_DESARROLLO.md](GUIA_DESARROLLO.md).

---

## Índice

1. [Principios](#1-principios)
2. [Arquitectura por capas](#2-arquitectura-por-capas)
3. [Convenciones de API](#3-convenciones-de-api)
4. [Formato de respuesta estándar](#4-formato-de-respuesta-estándar)
5. [Manejo de errores](#5-manejo-de-errores)
6. [Catálogo de códigos de error](#6-catálogo-de-códigos-de-error)
7. [Logs](#7-logs)
8. [Configuración](#8-configuración)
9. [Almacenamiento de fotogramas](#9-almacenamiento-de-fotogramas)
10. [Clean code y herramientas](#10-clean-code-y-herramientas)
11. [Pruebas](#11-pruebas)
12. [Flujo de trabajo en Git](#12-flujo-de-trabajo-en-git)
13. [Definición de terminado](#13-definición-de-terminado)
14. [Estado actual frente al estándar](#14-estado-actual-frente-al-estándar)

---

## 1. Principios

1. **Una sola forma de responder** en los dos servicios, tanto en el éxito como en el error.
2. **Errores con código estable** (`MEDIA_TOO_LARGE`, `MEDIA_UNSUPPORTED_FORMAT`), no solo con texto. El front decide qué mostrar según el código; el texto es para la persona.
3. **Todo request tiene un `request_id`** que viaja del front al back y a la IA, aparece en cada línea de log y se muestra al usuario cuando algo falla ("Código de referencia: 7f3a…").
4. **Todo log dice en qué flujo y en qué paso está** (`flow=FL-08`, `step=ai.call`).
5. **Capas con responsabilidades claras:** los routers no tienen lógica de negocio, los servicios no conocen HTTP y los repositorios no hacen *commit*.
6. **Dependencias externas detrás de una interfaz** (IA, *storage*, reloj, catálogo), para poder cambiarlas (por ejemplo, de disco local a S3) y simularlas en los tests.
7. **Nada de datos inventados ni errores silenciosos** (DD-4): si algo falla, se registra con su código y se informa.
8. **La configuración solo llega por variables de entorno**, validadas al arrancar.

---

## 2. Arquitectura por capas

### 2.1 Backend (`BACKWWF/app/`)

```
app/
├── main.py                  # crea la app: middlewares, handlers, routers, lifespan
├── core/
│   ├── config.py            # Settings (pydantic-settings), validación al arrancar
│   ├── errors.py            # AppError y subclases + catálogo de códigos
│   ├── logging.py           # configuración JSON, contexto (request_id, flow, step)
│   ├── middleware.py        # RequestContext, AccessLog, SecurityHeaders
│   ├── security.py          # JWT, hash de contraseñas, hash de tokens anónimos
│   └── responses.py         # ApiResponse[T], ok(), paginated()
├── api/
│   ├── deps.py              # get_db, get_owner (usuario o sesión anónima), get_current_user
│   └── v1/
│       ├── router.py        # APIRouter(prefix="/api/v1") que incluye los demás
│       ├── auth.py  anon_sessions.py  camera_stations.py  projects.py
│       ├── classifications.py  batches.py  catalog.py  stats.py
│       ├── reports.py  imports.py  health.py
├── schemas/                 # Pydantic: XxxCreate, XxxUpdate, XxxRead por recurso
├── services/                # casos de uso (uno por flujo o recurso); lanzan AppError
├── repositories/            # acceso a datos (hoy crud/); sin commit
├── models/                  # SQLAlchemy
├── integrations/
│   ├── ai_client.py         # cliente HTTP de la IA (httpx), mapea errores
│   ├── storage/             # StorageBackend: local.py, s3.py (futuro)
│   ├── queue.py             # cliente Redis/arq: encolar, posición, contadores
│   └── email/               # EmailProvider: resend.py, smtp.py (futuro), plantillas
├── reports/                 # excel.py, pdf.py (generadores)
├── worker/                  # arq: WorkerSettings, classify_file_job, send_email_job, import_job, cron FL-30/31/33
│   └── dispatcher.py        # cola justa por dueño (QUEUE_PER_OWNER_INFLIGHT, round-robin)
└── db/                      # engine, session, unit of work
```

**Reglas por capa:**

| Capa | Hace | No hace |
|---|---|---|
| `api/v1/*` (router) | Declara la ruta, los schemas de entrada y salida, las dependencias y el flujo (`flow="FL-08"`); llama a **un** servicio; envuelve con `ok()`. | Consultas a la BD, `if` de negocio, `try/except` genéricos, `HTTPException` con texto libre. |
| `services/*` | Reglas de negocio, autorización por dueño y visibilidad, orquestación (IA, *storage*, repositorios) y transacción (`async with uow:`). | Importar `fastapi`, `Request` o `HTTPException`; devolver `JSONResponse`. |
| `repositories/*` | Consultas SQLAlchemy tipadas (`get`, `list_by_owner`, `stats_by_taxon`…). | `commit()`, reglas de negocio, llamadas HTTP. |
| `integrations/*` | Hablar con sistemas externos y **traducir sus errores** a `AppError` (`AI_TIMEOUT`, `STORAGE_WRITE_FAILED`). | Conocer los modelos de la BD. |
| `schemas/*` | Validación de entrada y forma de salida; un schema distinto para crear, actualizar y leer. | Lógica. |

**Ejemplo de router:**
```python
@router.post("/classifications", status_code=200, response_model=ApiResponse[BatchRead])
async def classify(
    files: list[UploadFile],
    camera_station_id: UUID | None = Form(None),
    owner: Owner = Depends(get_owner),             # usuario o sesión anónima
    service: ClassificationService = Depends(),
    _flow: None = Depends(flow("FL-08")),
):
    batch = await service.classify(owner, files, camera_station_id)
    return ok(batch, message="Clasificación terminada")
```

### 2.2 IA (`ia-deteccion/`)

La API y la app de escritorio comparten **el mismo paquete de pipeline**. No debe haber lógica de clasificación duplicada.

```
ia-deteccion/
├── wwm_pipeline/            # paquete puro de Python, sin FastAPI ni Tkinter
│   ├── config.py            # PipelineConfig (muestreo, umbrales, modo web/escritorio)
│   ├── sampling.py          # extracción de fotogramas (IA-11)
│   ├── detection.py         # MegaDetector
│   ├── classification.py    # SpeciesNet (sin geofence; 3538 taxones)
│   ├── aggregation.py       # votación por archivo (IA-13)
│   ├── taxonomy.py          # etiqueta → taxonomía completa (IA-14)
│   ├── evidence.py          # fotograma con recuadro, JPEG, timestamp (IA-15)
│   ├── metadata.py          # sha256, duración, fecha de captura
│   ├── errors.py            # PipelineError y subclases con código
│   └── pipeline.py          # classify_file(path, config) -> FileResult
├── api/                     # FastAPI: main.py, routes.py, errors.py, logging.py, security.py
├── desktop/                 # Tkinter: app.py, folder_job.py, exporter.py (FL-22), logging.py
├── catalog/                 # speciesnet_catalog.json (IA-19)
├── eval/                    # eval.py, set de validación (IA-10)
└── tests/
```

**Reglas:**
- `wwm_pipeline` **no** sabe si lo llama la API o el escritorio: recibe un `PipelineConfig` y devuelve un `FileResult` (dataclass o Pydantic).
- Los errores del pipeline son `PipelineError(code=...)`. La API los traduce a HTTP y el escritorio a un mensaje en pantalla.
- La inferencia, que usa la CPU de forma intensiva, se ejecuta fuera del *event loop* de la API, con **un solo** *worker* de modelo (cola), para que la RAM se mantenga estable.

### 2.3 Front (`Front-WWF/src/`)
- `services/apiClient.js` es el **único** cliente HTTP:
  - agrega `Authorization` o `X-Anon-Token` y `X-Request-ID`;
  - desempaqueta `data`;
  - convierte cualquier error en un `ApiError {code, message, requestId, details, httpStatus}`.
- Los componentes nunca leen `error.response.data` directamente: usan `ApiError`.
- `utils/errorMessages.js` tiene un mapa `code → texto amigable o acción` (por ejemplo, `AUTH_TOKEN_EXPIRED` lleva al login). Si no hay entrada para el código, se muestra `message` del back.
- Los errores se muestran con un componente único (*toast* o *banner*) que incluye "Código de referencia: `<request_id>`".

---

## 3. Convenciones de API

| Tema | Regla |
|---|---|
| **Prefijo** | Back: `/api/v1/...`. IA: `/api/v1/...` (interna). El proxy publica solo `/api/` del back; la IA no se publica. |
| **Versionado** | Un cambio incompatible crea `/api/v2`; `v1` se mantiene hasta que el front migre. |
| **Rutas** | Sustantivos en plural, en `kebab-case`: `/camera-stations/{id}`, `/classification-batches/{id}`. Las acciones que no son CRUD van como subrecurso: `/anon-sessions/claim`, `/classifications/{id}/validation`. |
| **JSON** | `snake_case` en las claves; los IDs son UUID en texto. |
| **Fechas** | ISO 8601. Las del servidor van en UTC con `Z` (`2026-03-15T04:22:10Z`). Para `captured_at` se guarda la hora local de la cámara sin zona y se documenta así, porque las cámaras trampa no registran la zona. |
| **Duraciones y tiempos dentro del video** | Segundos en `float` (`evidence_timestamp_seconds: 7.07`). El front lo muestra como `mm:ss`. |
| **Paginación** | `?page=1&page_size=50` (máximo 200) → `meta.pagination {page, page_size, total, total_pages}`. |
| **Filtros y orden** | Query params explícitos (`?camera_station_id=&from=&to=&validation_status=`); orden con `?sort=-captured_at`. |
| **Códigos HTTP** | `200` OK (incluye lotes con errores parciales) · `201` creado · `202` aceptado en segundo plano · `204` sin contenido (borrados) · `400` petición mal formada · `401` sin autenticación o token inválido · `403` sin permiso · `404` no existe **o no es visible** (no revelar la existencia de recursos privados ajenos) · `409` conflicto · `413` muy grande · `415` formato no soportado · `422` validación de negocio o de datos · `429` *rate limit* · `500` error interno · `502` dependencia caída (IA) · `503` no está listo (modelo cargando) · `504` dependencia lenta. |
| **Headers** | Entrada: `Authorization`, `X-Anon-Token`, `X-Request-ID` (opcional; si no llega, el back lo genera). Salida: `X-Request-ID` siempre. Back → IA: `X-API-Key`, `X-Request-ID`, `X-Flow`. |
| **Descargas** | Excel y PDF responden con el binario directo (sin envoltura) y `Content-Disposition`. Los errores sí llevan la envoltura JSON. |

---

## 4. Formato de respuesta estándar

Es compatible con el `StandardResponse {status, data, message}` actual, así el interceptor del front no se rompe: se **agregan** `error` y `meta`.

### 4.1 Éxito
```json
{
  "status": "success",
  "data": { "id": "…", "code": "CAM01", "name": "Quebrada norte" },
  "message": "Cámara registrada",
  "error": null,
  "meta": { "request_id": "7f3a9c2e1b", "timestamp": "2026-11-07T15:04:05Z" }
}
```

### 4.2 Lista paginada
```json
{
  "status": "success",
  "data": [ { "…": "…" } ],
  "message": "OK",
  "error": null,
  "meta": {
    "request_id": "7f3a9c2e1b",
    "timestamp": "2026-11-07T15:04:05Z",
    "pagination": { "page": 1, "page_size": 50, "total": 123, "total_pages": 3 }
  }
}
```

### 4.3 Error
```json
{
  "status": "error",
  "data": null,
  "message": "El archivo supera el tamaño máximo permitido de 300 MB.",
  "error": {
    "code": "MEDIA_TOO_LARGE",
    "flow": "FL-08",
    "details": [ { "field": "files[3]", "code": "MEDIA_TOO_LARGE", "message": "…", "context": { "size_mb": 340.5, "max_mb": 300 } } ]
  },
  "meta": { "request_id": "7f3a9c2e1b", "timestamp": "2026-11-07T15:04:05Z" }
}
```
- `message` es para la persona, en español y sin detalles técnicos.
- `error.code` es estable y está en el catálogo (§6). **Nunca se cambia el significado de un código existente.**
- `error.details` contiene errores por campo o por archivo (validación de Pydantic, archivos de un lote).
- En producción **nunca** se envían el *stack trace*, el SQL, rutas del servidor ni mensajes de librerías.

### 4.4 Resultado por ítem (lotes)
Las operaciones por ítem responden **200** y cada ítem lleva su estado y su error, si lo tiene:
- la subida de un archivo responde un `BatchItem`;
- `GET /classification-batches/{id}` y la validación en lote responden la lista de ítems.

El contrato exacto está en [API §1.9 y §7](contratos/API_BACK_FRONT.md#7-clasificación-lotes-y-archivos). Ejemplo de un lote:
```json
{
  "status": "success",
  "data": {
    "batch_id": "…", "status": "completed_with_errors", "total": 3, "done": 2, "failed": 1,
    "items": [
      { "file_name": "A.mp4", "status": "done", "classification": { "…": "…" }, "error": null },
      { "file_name": "B.mp4", "status": "error", "classification": null,
        "error": { "code": "AI_TIMEOUT", "message": "La clasificación tardó demasiado. Intenta de nuevo." } }
    ]
  },
  "message": "2 de 3 archivos clasificados",
  "error": null,
  "meta": { "request_id": "…" }
}
```

### 4.5 IA
La IA usa **la misma envoltura**. El contrato de [API_IA_BACK.md](contratos/API_IA_BACK.md) va dentro de `data`, y sus errores usan los códigos `IA_*` (§6.2).

### 4.6 Implementación (back e IA)
```python
# core/responses.py
class ErrorBody(BaseModel):
    code: str
    flow: str | None = None
    details: list[ErrorDetail] = []

class Meta(BaseModel):
    request_id: str
    timestamp: datetime
    pagination: Pagination | None = None
    warnings: list[Warning] = []   # {code, message, context}: avisos que no impiden la operación

class ApiResponse(BaseModel, Generic[T]):
    status: Literal["success", "error"]
    data: T | None = None
    message: str = "OK"
    error: ErrorBody | None = None
    meta: Meta

def ok(data: T, message: str = "OK", pagination: Pagination | None = None) -> ApiResponse[T]: ...
```
El `meta` lo llena una función que lee `request_id` del contexto (§7.3); el router no lo arma a mano.

---

## 5. Manejo de errores

### 5.1 Jerarquía
```python
# core/errors.py
class AppError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "Ocurrió un error inesperado."
    log_level: int = logging.ERROR

    def __init__(self, message: str | None = None, *, details=None, context: dict | None = None):
        self.message = message or self.message
        self.details = details or []
        self.context = context or {}      # va al log, NO a la respuesta

class NotFoundError(AppError):       http_status = 404; log_level = logging.INFO
class ForbiddenError(AppError):      http_status = 403; log_level = logging.WARNING
class ConflictError(AppError):       http_status = 409; log_level = logging.INFO
class BusinessRuleError(AppError):   http_status = 422; log_level = logging.INFO
class DependencyError(AppError):     http_status = 502; log_level = logging.ERROR

# Si supera 15s, no lanza error; la IA trunca a 15.0s y el back emite warning VIDEO_TRUNCATED (F1-D10).
class MediaTooLargeError(BusinessRuleError):
    code = "MEDIA_TOO_LARGE"
    message = "El archivo supera el tamaño o resolución máxima permitida (300 MB / 100 MP)."
```

### 5.2 Handlers globales (en `main.py`, un solo lugar)

| Excepción | Respuesta | Log |
|---|---|---|
| `AppError` | `http_status` + envoltura con `code`, `message` y `details` | Con el nivel `log_level` de la clase, más `context` |
| `RequestValidationError` (Pydantic) | 422 `VALIDATION_ERROR` con `details` por campo | `INFO` |
| `StarletteHTTPException` (404 de ruta, 405) | `ROUTE_NOT_FOUND` / `METHOD_NOT_ALLOWED` | `INFO` |
| `SQLAlchemyError` | 500 `DATABASE_ERROR`, con un mensaje genérico | `ERROR` con *stack* |
| `Exception` (cualquier otra) | 500 `INTERNAL_ERROR`, con un mensaje genérico | `ERROR` con *stack* + `request_id` |

### 5.3 Reglas
- **No `except Exception: pass`.** Si se captura, se registra y se re-lanza como `AppError` con contexto.
- **No `HTTPException(detail="…")`** en servicios ni en routers; siempre `AppError`.
- Los errores esperados (validación, 404, 409) van con nivel `INFO` o `WARNING`, no `ERROR`. `ERROR` queda para lo que requiere atención.
- Las integraciones traducen errores **en el borde**: `httpx.TimeoutException` → `AiTimeoutError`, `httpx.ConnectError` → `AiUnavailableError`, una respuesta 422 de la IA con `IA_DECODE_FAILED` → `MediaDecodeFailed`.
- El mismo error se registra **una sola vez**, en el handler global o donde se decide no re-lanzarlo (por ejemplo, el error de un ítem de un lote).

---

## 6. Catálogo de códigos de error

> Se mantiene en `core/errors.py` (back) y `wwm_pipeline/errors.py` (IA). El front tiene su espejo en `utils/errorMessages.js`. **Agregar un código = actualizar las tres listas y esta tabla.**

### 6.1 Back

| Código | HTTP | Mensaje al usuario (resumen) | Flujos |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | Hay datos inválidos en el formulario | Todos |
| `ROUTE_NOT_FOUND` | 404 | Recurso no encontrado | — |
| `RATE_LIMITED` | 429 | Demasiadas solicitudes; espera un momento | FL-01, 02, 03, 08 |
| `INTERNAL_ERROR` | 500 | Error inesperado (con el código de referencia) | Todos |
| `DATABASE_ERROR` | 500 | Error inesperado | Todos |
| `AUTH_INVALID_CREDENTIALS` | 401 | Correo o contraseña incorrectos | FL-02 |
| `AUTH_TOKEN_EXPIRED` | 401 | Tu sesión expiró | FL-02 |
| `AUTH_TOKEN_INVALID` | 401 | Sesión inválida; vuelve a iniciar sesión | FL-02 |
| `AUTH_REQUIRED` | 401 | Debes iniciar sesión para esta acción | FL-10, 12, 23 |
| `AUTH_EMAIL_TAKEN` | 409 | Ese correo ya está registrado | FL-01 |
| `FORBIDDEN` | 403 | No tienes permiso sobre este recurso | Todos |
| `ANON_SESSION_EXPIRED` | 401 | Tu sesión sin cuenta expiró; sus datos ya no están disponibles | FL-03, 04 |
| `ANON_SESSION_ALREADY_CLAIMED` | 409 | Estos datos ya se asociaron a otra cuenta | FL-04 |
| `ANON_LIMIT_REACHED` | 422 | Alcanzaste el límite sin cuenta; regístrate para continuar | FL-03, 05, 08 |
| `ANON_PUBLIC_NOT_ALLOWED` | 422 | Sin cuenta no se puede publicar contenido | FL-05, 07 |
| `CAMERA_NOT_FOUND` | 404 | La cámara no existe | FL-05, 06, 08 |
| `CAMERA_CODE_TAKEN` | 409 | Ya tienes una cámara con ese código | FL-05 |
| `CAMERA_INVALID_DATES` | 422 | La fecha de retiro es anterior a la de colocación | FL-05, 06 |
| `CAMERA_NOT_OWNED` | 403 | Solo puedes usar tus propias cámaras | FL-07, 23 |
| `PROJECT_NOT_FOUND` | 404 | El proyecto no existe | FL-07 |
| `ALREADY_ASSOCIATED` | 409 | La cámara ya está en el proyecto | FL-07 |
| `MEDIA_UNSUPPORTED_FORMAT` | 415 | Formato no soportado (se listan los válidos) | FL-08 |
| `MEDIA_TOO_LARGE` | 413 | El archivo supera X MB | FL-08 |
| `VIDEO_TRUNCATED` *(warning 200)* | 200 | El video supera 15 s; se analizaron los primeros 15.0 s (`F1-D10`) | FL-08 |
| `MEDIA_DECODE_FAILED` | 422 | No se pudo leer el archivo (puede estar dañado) | FL-08 |
| `DUPLICATE_FILE` | 409 (por ítem) | Este archivo ya fue clasificado en esta cámara | FL-08, 23 |
| `AI_UNAVAILABLE` | 502 | El servicio de clasificación no está disponible | FL-08 |
| `AI_TIMEOUT` | 504 | La clasificación tardó demasiado | FL-08 |
| `AI_BAD_RESPONSE` | 502 | El servicio de clasificación respondió de forma inesperada | FL-08 |
| `AI_NOT_READY` | 503 | El modelo se está cargando; intenta en un minuto | FL-08 |
| `PROCESSING_INTERRUPTED` | — (por ítem) | El procesamiento se interrumpió; vuelve a subir el archivo | FL-09 |
| `STORAGE_WRITE_FAILED` | 500 | No se pudo guardar el fotograma | FL-08, 23 |
| `CLASSIFICATION_NOT_FOUND` | 404 | La clasificación no existe | FL-10 |
| `CATALOG_TAXON_NOT_FOUND` | 422 | La especie no está en el catálogo de SpeciesNet | FL-10, 23 |
| `REPORT_EMPTY` | 404 | No hay datos con esos filtros | FL-12 |
| `IMPORT_INVALID_PACKAGE` | 422 | El paquete no es válido | FL-23 |
| `IMPORT_UNSUPPORTED_VERSION` | 422 | Versión de paquete no soportada; actualiza la app | FL-23 |
| `IMPORT_TOO_LARGE` | 413 | El paquete es demasiado grande | FL-23 |
| `IMPORT_CHECKSUM_MISMATCH` | 422 | El paquete está dañado o fue modificado | FL-23 |
| `IMPORT_ALREADY_IMPORTED` | 409 | Este paquete ya fue importado | FL-23 |
| `IMPORT_PREVIEW_EXPIRED` | 410 | La vista previa expiró; vuelve a subir el paquete | FL-23 |
| `IMPORT_NOT_FOUND` | 404 | La importación no existe | FL-23 |
| `EVIDENCE_INVALID` | — (*issue* por línea) | El fotograma del paquete no es una imagen válida | FL-23 |
| `CAPTURE_OUTSIDE_DEPLOYMENT` | — (advertencia) | La fecha de captura está fuera del periodo de la cámara | FL-23 |
| `AUTH_WEAK_PASSWORD` | 422 | La contraseña debe tener al menos 8 caracteres, con letras y números | FL-01, 02 |
| `CAMERA_REQUIRED` | 422 | Elige la cámara a la que pertenecen los archivos | FL-08 |
| `BATCH_NOT_FOUND` | 404 | El lote de subida no existe | FL-08 |
| `BATCH_CLOSED` | 409 | El lote ya se cerró; inicia una nueva subida | FL-08 |
| `NETWORK_ERROR` | — (solo en el front) | No hay conexión con el servidor | Todos |
| `QUEUE_USER_LIMIT` | 429 | Tienes muchos archivos en espera; continuaremos cuando avancen | FL-08 |
| `QUEUE_FULL` | 503 | El servidor está muy ocupado; reintenta en unos minutos | FL-08 |
| `QUEUE_UNAVAILABLE` | 503 | La cola de procesamiento no está disponible | FL-08 |
| `ITEM_NOT_CANCELLABLE` | 409 | El archivo ya se está analizando | FL-09 |
| `RETRY_FILE_UNAVAILABLE` | 410 | Vuelve a seleccionar el archivo para reintentar | FL-09 |
| `PROCESSING_EXPIRED` | — (por ítem) | El archivo estuvo demasiado tiempo en espera | FL-09 |
| `CANCELLED_BY_USER` / `CAMERA_DELETED` | — (por ítem) | Cancelado / la cámara fue eliminada | FL-09 |
| `DUPLICATE_FILE_OTHER_CAMERA` | 409 (por ítem) | Este archivo ya está clasificado en otra de tus cámaras | FL-08 |
| `CLASSIFICATION_NOT_DONE` | 409 | La clasificación todavía no terminó | FL-10 |
| `REPEAT_KEEP_REQUIRED` | 422 | Debes conservar al menos un registro del grupo | FL-16 |
| `REPEAT_MIXED_CAMERAS` | 422 | Los registros de una ráfaga deben ser de la misma cámara | FL-16 |
| `CONFLICT_STALE` | 409 | Se modificó en otra ventana; recarga | FL-06, 07 |
| `AUTH_RESET_TOKEN_INVALID` | 400 | El enlace venció o ya se usó | FL-14 |
| `EMAIL_TEMPORARILY_UNAVAILABLE` | 503 | No podemos enviar correos en este momento | FL-14 |
| `CAMERA_COORDS_SUSPECT` / `CAMERA_MOVED_WITH_DATA` | — (advertencia) | Coordenadas `0,0` o posiblemente invertidas / mover una cámara con datos | FL-05, 06 |
| `ADMIN_REQUIRED` | 403 | Esta sección es solo para administradores | FL-40…43 |
| `DELETE_REASON_REQUIRED` | 422 | Indica el motivo del borrado | FL-42, 43 |
| `ENTITY_ALREADY_DELETED` | 409 | El registro ya estaba borrado | FL-06, 42 |
| `ENTITY_NOT_DELETED` | 409 | El registro no está borrado; no hay nada que restaurar | FL-42 |
| `CANNOT_DEACTIVATE_SELF` | 409 | No puedes desactivar tu propia cuenta | FL-43 |
| `SETTING_INVALID` | 422 | Valor de configuración no válido | FL-44 |
| `ACCOUNT_DISABLED` | 403 | Tu cuenta está desactivada; contacta al administrador | FL-02 |
| `PASSWORD_CHANGE_REQUIRED` | 403 | Debes cambiar tu contraseña antes de continuar | FL-02 |

### 6.2 IA (interna, la consume solo el back)

| Código IA | HTTP | Cuándo | El back lo traduce a |
|---|---|---|---|
| `IA_UNAUTHORIZED` | 401 | Falta la `X-API-Key` o es incorrecta | `AI_UNAVAILABLE` (502) + log `CRITICAL`, porque es un error de configuración |
| `IA_INVALID_FORMAT` | 415 | La extensión o la firma no son soportadas | `MEDIA_UNSUPPORTED_FORMAT` |
| `IA_FILE_TOO_LARGE` | 413 | Supera `MAX_FILE_MB` | `MEDIA_TOO_LARGE` |
| `IA_DECODE_FAILED` | 422 | OpenCV o PIL no pueden leer el archivo | `MEDIA_DECODE_FAILED` |
| `IA_INVALID_FORMAT` | 400 | Request multipart malformado o campo `file`/`file_name` faltante | `AI_BAD_REQUEST` / `400` |
| `IA_UNSUPPORTED_FORMAT` / `IA_DECODE_FAILED` (`too_many_pixels`) | 422 | Extensión no soportada o imagen > 100 MP | `MEDIA_UNSUPPORTED_FORMAT` / `MEDIA_TOO_LARGE` / `MEDIA_DECODE_FAILED` |
| `IA_MODEL_NOT_READY` | 503 | Los modelos aún se están cargando | `AI_NOT_READY` |
| `IA_BUSY` | 503 | La cola de inferencia está llena | `AI_UNAVAILABLE` (con reintento en el back) |
| `IA_PROCESSING_TIMEOUT` | 504 | El archivo superó `PROCESS_TIMEOUT_SECONDS` | `AI_TIMEOUT` |
| `IA_INTERNAL` | 500 | Excepción no controlada en el pipeline | `AI_BAD_RESPONSE` (1 reintento en back antes de marcar error) |
| (sin respuesta) | — | Conexión rechazada o DNS | `AI_UNAVAILABLE` |
| (respuesta fuera de contrato) | — | Falla la validación Pydantic del contrato | `AI_BAD_RESPONSE` + log `ERROR` con las claves recibidas, sin el base64 |

### 6.3 Escritorio
Usa los mismos códigos del pipeline (`IA_DECODE_FAILED`…), más:
- `NETWORK_UNAVAILABLE`;
- `DOWNLOAD_INTEGRITY_FAILED`;
- `DISK_SPACE_LOW`;
- `FILE_MOVE_VERIFY_FAILED`;
- `DESTINATION_NOT_WRITABLE`.

Cada código tiene su mensaje en español en `desktop/messages.py`.

---

## 7. Logs

### 7.1 Formato: JSON en una línea

Back e IA usan logs estructurados en JSON a `stdout` (Docker los recoge). Se recomienda `structlog`; la alternativa es `logging` estándar con `python-json-logger`.

```json
{
  "ts": "2026-11-07T15:04:05.123Z",
  "level": "ERROR",
  "service": "backend",
  "env": "production",
  "version": "1.0.3",
  "request_id": "7f3a9c2e1b",
  "flow": "FL-08",
  "step": "ai.call",
  "event": "classification.ai_call.failed",
  "error_code": "AI_TIMEOUT",
  "user_id": "3e1…",
  "anon_session": "a91f",
  "camera_station_id": "c77…",
  "batch_id": "b12…",
  "file_name": "CAM01_20260315_042210.mp4",
  "duration_ms": 180012,
  "message": "Timeout esperando a la IA",
  "exc_info": "Traceback (…)"
}
```

**Campos obligatorios en cada línea:** `ts`, `level`, `service`, `env`, `version`, `request_id`, `event`, `message`.
**Campos de contexto, cuando aplican:** `flow`, `step`, `user_id`, `anon_session` (los primeros 4 caracteres del hash, nunca el token), `camera_station_id`, `project_id`, `batch_id`, `classification_id`, `file_name`, `duration_ms`, `error_code`.

### 7.2 Nombres de eventos
Formato `<dominio>.<acción>.<resultado>`, en inglés y en `snake_case`. Ejemplos:
- `auth.login.succeeded` / `auth.login.failed`
- `anon_session.created` / `anon_session.claimed` / `anon_session.expired`
- `media.validation.failed`
- `classification.ai_call.started` / `.succeeded` / `.failed`
- `classification.stored`
- `storage.evidence.written` / `.failed`
- `import.preview.completed` / `import.confirmed` / `import.rejected`
- `job.anon_expire.completed`
- `admin.soft_delete.completed` / `admin.restore.completed` / `admin.user_deactivated` / `admin.setting.updated`
- `job.anon_purge.completed` (solo datos con `anon_retain = false`)
- `queue.item.enqueued` / `queue.item.started` / `queue.item.completed` / `queue.item.failed` / `queue.item.requeued` (con `queue_wait_ms` y `processing_ms`)
- `queue.reaper.completed` / `queue.full`
- `email.password_reset.queued` / `.sent` / `.failed` / `.skipped_limit` (sin el correo en claro)

Así se puede filtrar, por ejemplo con `jq 'select(.event=="classification.ai_call.failed")'` o en un visor de logs.

### 7.3 Correlación de punta a punta

```
Front  ── X-Request-ID: 7f3a… ──▶  Back  ── X-Request-ID: 7f3a…, X-Flow: FL-08 ──▶  IA
  ▲                                  │ contextvar request_id / flow / step            │ contextvar
  └──── meta.request_id + header ◀───┘                                                └─ logs con el mismo id
```

1. **Front:** genera un `X-Request-ID` (UUID corto) por petición en el interceptor.
2. **Back:**
   1. el `RequestContextMiddleware` lo toma, o genera uno si no llega, y lo guarda en un `contextvar` junto con `user_id` y `anon_session`;
   2. la dependencia `flow("FL-08")` fija `flow`;
   3. dentro del servicio, `with log_step("ai.call"):` fija `step` y mide `duration_ms`.
3. **IA:** su middleware lee `X-Request-ID` y `X-Flow` y los incluye en sus logs. Así, buscando un solo id, se ve el recorrido completo en los dos servicios.
4. **Usuario:** el `request_id` se muestra en el mensaje de error y va en el pie de los PDF exportados.
5. **Escritorio:** genera un `job_id` por cada carpeta procesada y lo usa como `request_id` en su log local.

```python
# core/logging.py (extracto)
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
flow_var: ContextVar[str | None] = ContextVar("flow", default=None)

@contextmanager
def log_step(step: str, **ctx):
    token = step_var.set(step); t0 = perf_counter()
    try:
        yield
        log.info(f"{step}.succeeded", duration_ms=_ms(t0), **ctx)
    except AppError as e:
        log.log(e.log_level, f"{step}.failed", error_code=e.code, duration_ms=_ms(t0), **{**ctx, **e.context})
        raise
    finally:
        step_var.reset(token)
```

### 7.4 Niveles

| Nivel | Uso | Ejemplo |
|---|---|---|
| `DEBUG` | Solo en desarrollo (`LOG_LEVEL=DEBUG`) | Frames muestreados, puntajes por frame |
| `INFO` | Eventos de negocio normales y errores esperados del usuario | `classification.stored`, `media.validation.failed` |
| `WARNING` | Algo raro pero manejado | La IA tardó más de 60 s, `captured_at` fuera del rango de la cámara, 403 repetidos |
| `ERROR` | Fallo que requiere atención | `AI_UNAVAILABLE`, `STORAGE_WRITE_FAILED`, excepción no controlada |
| `CRITICAL` | El servicio no puede funcionar | Falta configuración al arrancar, `IA_UNAUTHORIZED` (claves desalineadas), la BD es inalcanzable |

### 7.5 Lo que **nunca** se registra
- Contraseñas, JWT, *refresh tokens*, `X-Anon-Token`, `AI_API_KEY`, `DATABASE_URL` completa.
- El contenido base64 de fotogramas ni las respuestas completas de la IA: se registran solo las claves y los tamaños. Hoy `videos.py` imprime el JSON completo de la IA y hay que quitarlo.
- Correos completos: se enmascaran como `d***@gmail.com`.
- Cuerpos de peticiones con archivos.
- La IP completa del anónimo: si hace falta para el *rate limit*, se usa en memoria y en los logs va un hash truncado.

**Acciones del administrador:** además del log normal (`event=admin.<acción>.completed`, con `admin_user_id`, `entity_type`, `entity_id` y `reason`), cada una se escribe en la tabla `admin_audit_log`. El log es para diagnóstico y rota; la tabla es la auditoría permanente.

### 7.6 *Access log*
Una línea por petición, del middleware: `event=http.request`, `method`, `route` (la plantilla, `/api/v1/camera-stations/{id}`, no la ruta con IDs), `status`, `duration_ms`, `request_id`, `user_id`. Se desactiva el *access log* propio de uvicorn para no duplicar.

### 7.7 Destino y retención
- **Servidor:** `stdout` → Docker `json-file` con `max-size: 20m`, `max-file: 5`. Opcionalmente se agrega luego un visor (Dozzle, Loki y Grafana) sin cambiar el código.
- **Escritorio:** `%LOCALAPPDATA%\WWM\logs\wwm.log`, rotativo (5 × 5 MB), en JSON. Botón **"Exportar diagnóstico"**, que genera un zip con los logs y la versión, sin rutas personales completas, para enviarlo a soporte.
- **Front:** sin `console.log` en producción (regla de ESLint `no-console`). Los errores inesperados del cliente se muestran con el *error boundary* y su `request_id`.

---

## 8. Configuración

- **Back:** un solo `Settings` (pydantic-settings) con tipos y validación. Si falta una variable obligatoria o es débil (por ejemplo, `SECRET_KEY` de menos de 32 bytes), el servicio **no arranca** y registra `CRITICAL config.invalid`.
- **IA:** lo mismo, con un `Settings` propio; el `PipelineConfig` se construye a partir de él.
- **`.env.example`** en cada repo, con todas las variables, sin valores reales y con un comentario por cada una.
- **Prohibido** leer `os.environ` fuera de `config.py`, y tener URLs, claves o IPs escritas en el código.
- **Dos tipos de configuración:**
  - **de infraestructura** (`.env`): secretos, URLs, límites técnicos. Se cambia con un despliegue;
  - **de negocio** (tabla `system_settings`): la cambia el administrador en caliente desde el panel, queda auditada y se lee con `SettingsService` (caché corta). Hoy la única clave es `anon_data_retention` (por defecto `true`).

  Una opción nunca se define en los dos lugares.

Variables nuevas que introducen estos estándares y los flujos:

| Variable | Servicio | Por defecto |
|---|---|---|
| `ENVIRONMENT` | back, IA | `development` |
| `LOG_LEVEL` | back, IA | `INFO` |
| `LOG_FORMAT` | back, IA | `json` (`console` en desarrollo) |
| `APP_VERSION` | back, IA | lo inyecta el build |
| `ANON_SESSION_TTL_HOURS` | back | `24` |
| `ANON_MAX_FILES` / `ANON_MAX_CAMERAS` | back | `50` / `5` |
| `AI_BASE_URL` / `AI_SERVICE_URL` / `AI_API_KEY` / `AI_TIMEOUT_SECONDS` | back | `http://ia:8001/api/v1` (o base `:8001` en `AI_SERVICE_URL` legado `:8081`) / obligatorio en `production` (`dev-key` en `development`) / `180` |
| `UPLOAD_MAX_PARALLEL_FILES` | back (lo expone `/config/public`) | `2` |
| `BATCH_IDLE_CLOSE_MINUTES` | back | `60` |
| `STORAGE_BACKEND` | back | `local` |
| `STORAGE_LOCAL_PATH` | back | `/data/evidence` |
| `EVIDENCE_MAX_PX` / `EVIDENCE_JPEG_QUALITY` | back, IA | `960` / `80` |
| `IMPORT_MAX_MB` | back | `200` |
| `MAX_FILE_MB` / `MAX_VIDEO_SECONDS` / `MAX_IMAGE_PIXELS` | back, IA | `300` / `15` / `100000000` |
| `ACCEPTED_IMAGE_EXT` / `ACCEPTED_VIDEO_EXT` | back, IA | alineados a `wwm_pipeline/formats.py` (`jpg,jpeg,png,bmp,webp,tiff` / `mp4,avi,mov,mkv,wmv,flv,webm`; `heic/heif` y otros diferidos a `IA-16`) |
| `PUBLIC_COORD_DECIMALS` | back | `2` (~1 km, DD-17) |
| `API_KEY` / `PROCESS_TIMEOUT_SECONDS` / `INFERENCE_QUEUE_SIZE` | IA | — / `150` / `2` |
| `REDIS_URL` | back, worker | `redis://:<pass>@redis:6379/0` |
| `TMP_UPLOAD_PATH` / `TMP_UPLOAD_TTL_HOURS` / `TMP_DISK_MAX_PCT` | back, worker | `/data/tmp-uploads` / `24` / `85` |
| `QUEUE_PER_OWNER_INFLIGHT` / `QUEUE_MAX_PENDING_PER_USER` / `QUEUE_MAX_GLOBAL` | back, worker | `2` / `500` / `5000` |
| `WORKER_CONCURRENCY` | worker | `1` (= réplicas de la IA que atiende) |
| `WORKER_MAX_TRIES` / `WORKER_HEARTBEAT_SECONDS` / `REAPER_STALE_MINUTES` | worker | `3` / `30` / `10` |
| `EMAIL_PROVIDER` / `RESEND_API_KEY` / `EMAIL_FROM` / `FRONTEND_URL` | back, worker | `resend` / — / `no-responder@<dominio>` / `https://<dominio>` |
| `EMAIL_DAILY_CAP` / `EMAIL_MONTHLY_CAP` | back | `80` / `2500` (por debajo de 100 y 3000 del plan gratuito de Resend) |
| `PASSWORD_RESET_TTL_MINUTES` | back | `30` |
| `BURST_WINDOW_MINUTES` | back | `5` (el usuario lo puede cambiar en cada consulta, 1–60) |
| `NEARBY_RADIUS_M` / `REGION_BBOX` | back | `30` / `-69.7,-22.9,-57.4,-9.6` (Bolivia; solo se usa para detectar coordenadas invertidas, **no** limita) |
| `MAP_DEFAULT_CENTER` / `MAP_DEFAULT_ZOOM` | back (lo expone `/config/public`) | `-17.7833,-63.1821` (Santa Cruz) / `8` |

---

## 9. Almacenamiento de fotogramas

**Decisión (DD-3):** por ahora se guardan en **disco local**, en un volumen de Docker. El diseño queda listo para S3 sin tocar los servicios.

```python
# integrations/storage/base.py
class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
```

- **Implementaciones:** `LocalStorage(base_path)` ahora; `S3Storage(bucket, prefix)` en el futuro. Se elige con `STORAGE_BACKEND`.
- **Clave:** `evidence/{yyyy}/{mm}/{classification_id}.jpg`. La BD guarda **solo la clave** (`evidence_key`), nunca la ruta absoluta ni la URL, así se puede migrar de backend copiando los archivos sin tocar la BD.
- **Entrega al front:** `GET /api/v1/classifications/{id}/evidence`, que **verifica el dueño o la visibilidad** y responde el JPEG con `Cache-Control: private`. **No** se monta `/data/evidence` como estático público, porque los fotogramas de cámaras privadas o anónimas no deben ser accesibles sin permiso. Con S3 se reemplaza por una URL prefirmada de corta duración, sin cambiar el contrato con el front (el endpoint responde un `302`).
- **Formato:** JPEG ≤ 960 px de lado mayor, calidad 80, sin EXIF, con el recuadro dibujado. La IA lo entrega en base64 y el back lo valida con Pillow antes de guardarlo.
- **Minuto y segundo:** `evidence_timestamp_seconds` (y `evidence_frame_index`) se guardan siempre. Para imágenes, `0` o `null`.
- **Consistencia:** primero se escribe el archivo y después la fila. Si falla la fila, se borra el archivo; si falla el archivo, no se crea la fila (o queda en `error`). Los huérfanos los limpia FL-31.
- **Backups:** el volumen de fotogramas entra en FL-32.

---

## 10. Clean code y herramientas

### 10.1 Python (back, IA, escritorio)

| Tema | Regla |
|---|---|
| Versión | Python 3.11 en los tres (fijada en el Dockerfile y en el build del escritorio). |
| Lint y formato | **`ruff`** (lint + format, reemplaza a black, isort y flake8), con reglas `E,F,I,B,UP,SIM,ASYNC,S` y línea de 100 caracteres. |
| Tipos | *Type hints* en todo lo público; **`mypy`** en modo gradual (estricto en `core/` y `services/`). |
| Nombres | El código y los identificadores van en **inglés**; los mensajes al usuario, en **español**. Clases en `PascalCase`, funciones y variables en `snake_case`, constantes en `UPPER_CASE`. |
| Funciones | Hacen una sola cosa; ≤ 40 líneas como guía; sin parámetros *booleanos* que cambien el comportamiento (dos funciones mejor que una con `if flag`). |
| *Magic values* | Los estados, categorías y rangos van como `Enum` en `core/enums.py`; los umbrales, en `Settings`. |
| Async | Nada bloqueante dentro de `async def`: lo pesado en CPU o el I/O síncrono (OpenCV, Pillow, openpyxl) va con `await asyncio.to_thread(...)` o en el *worker*. |
| Transacciones | Una unidad de trabajo por caso de uso; el *commit* va en el servicio, nunca en el repositorio. |
| Código muerto | Prohibido dejar bloques comentados; para eso está Git. |
| `print` | Prohibido; se usa el logger. |
| Dependencias | Versiones fijadas (`requirements.txt` con `==` o `uv`/`pip-tools` con *lock*). |
| *Docstrings* | Solo donde el **por qué** no sea obvio. El código se explica con nombres. |

### 10.2 Front
- ESLint con `no-console`, `react-hooks/exhaustive-deps` y `no-unused-vars`, más Prettier.
- Toda llamada HTTP pasa por `services/*` → `apiClient`; ningún componente usa `fetch` o `axios` directo.
- Sin *mocks* ni datos inventados en `src/` (los *fixtures* van solo en tests).
- Las constantes de dominio van en `enums.js`, alineadas con los enums del back.

### 10.3 *Pre-commit* (los tres repos)
`ruff check`, `ruff format --check`, la detección de secretos (`gitleaks` o `detect-secrets`), y `eslint` y `prettier` en el front. Se instala con `pre-commit install`.

---

## 11. Pruebas

| Tipo | Back | IA | Front |
|---|---|---|---|
| Unitarias | Servicios con repositorios y `AiClient` simulados | `taxonomy`, `aggregation`, `sampling`, `metadata` con fotogramas sintéticos | Utilidades (`errorMessages`, formateo `mm:ss`) |
| Integración | API + Postgres de test (contenedor), la IA simulada con el **JSON del contrato** | API con imágenes y videos cortos de ejemplo | — |
| Contrato | Valida que el *fixture* de la IA cumpla el schema `DetectResponse` | **El mismo schema** se valida sobre la salida real | — |
| Por flujo | Un test por regla del TDR: anónimo + asociación (FL-03/04), duplicados, 15 s, IA caída → 502 sin datos inventados, IDOR, estadísticas, Excel | Imagen con animal, imagen vacía, video ≤ 15 s, formato inválido | e2e (DEP-04) |
| Precisión | — | `eval.py` sobre el set de validación (IA-10 / IA-17) | — |

- **Schema compartido:** el schema Pydantic del contrato IA → back vive en `ia-deteccion/wwm_pipeline/contract.py`. El back lo copia (o lo instala como paquete) y un test verifica que ambas versiones sean idénticas.
- **CI** (GitHub Actions) en cada PR: lint, tipos, tests y build (Docker, o `npm run build`). No se hace *merge* con el CI en rojo.

---

## 12. Flujo de trabajo en Git

- **Ramas:** `main` (estable y desplegable) · `develop` (integración, opcional) · `feature/<ID>-<slug>` (por ejemplo `feature/BE-03-ai-client`) · `fix/<ID>-<slug>`.
- **Commits:** Conventional Commits con el ID de la tarea, por ejemplo `feat(classification): guardar fotograma en storage local [BE-05]`. Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`.
- **PR:** una tarea por PR (o un grupo pequeño y coherente). La plantilla incluye:
  - qué cambia;
  - el flujo afectado (FL-xx);
  - los códigos de error nuevos;
  - cómo se probó;
  - capturas, si toca la UI.
- **Revisión:** al menos 1 *review*. Los cambios de contrato (§3 del plan) o del catálogo de errores los revisa Diego.
- **Versionado:** SemVer con *tag* en `main` (`v1.0.0`). `APP_VERSION` sale del *tag*.

---

## 13. Definición de terminado

Una tarea está terminada cuando:
1. Cumple su criterio de aceptación del plan.
2. Las respuestas usan la envoltura estándar y los errores tienen un código del catálogo.
3. Los logs del flujo tienen `flow`, `step` y `event`, sin datos sensibles.
4. Tiene tests (unitarios o de integración) y el CI está en verde.
5. `ruff`, `mypy`, `eslint` y el build pasan sin advertencias nuevas.
6. Las variables nuevas están en `.env.example` y en §8.
7. Si cambia el contrato o un endpoint, se actualiza el plan (§3) y se avisa a los otros dos.

---

## 14. Estado actual frente al estándar

| Tema | Back hoy | IA hoy | Acción |
|---|---|---|---|
| Envoltura de respuesta | `StandardResponse {status,data,message}` en algunos routers; `species` y `reports` sin envolver | Respuesta propia, `HTTPException(detail=…)` | STD-01, STD-02 |
| Códigos de error | Texto libre | Texto libre en inglés (`"Failed to store uploaded file: {e}"`, que expone la excepción) | STD-03 |
| Logs | `logging` en `f-string` con prefijo `[Video Router]`, sin `request_id`; imprime el JSON completo de la IA | `basicConfig` + `uvicorn.error`; hay un `app_error.log` versionado en la raíz | STD-04, STD-05 |
| Capas | Existen `api/`, `services/`, `crud/` e `interfaces/`, pero `videos.py` tiene lógica, I/O de disco y llamadas a la IA dentro del router | Pipeline duplicado entre `main.py` y `desktop_app.py` | STD-06, IA-02 |
| Prefijo | Sin `/api/v1` | `/api/v1/detect` ✅ | STD-07 |
| Herramientas | Sin `ruff`, `mypy`, *pre-commit* ni CI | Igual | STD-08 |

Las tareas STD-xx están en el [plan §6.F, §4.E y §7.E](PLAN_IMPLEMENTACION_TDR.md).
