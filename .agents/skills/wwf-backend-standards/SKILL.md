---
name: wwf-backend-standards
description: Reglas innegociables de arquitectura, errores, logs, LocalStorage y código mínimo funcional (Ponytail) para BACKWWF.
---

# Reglas Críticas de Backend (`BACKWWF`)

**Principio (Ponytail):** Escribe el **mínimo código funcional necesario**. Cero abstracciones especulativas, cero stubs "para después" (ej. no crear `s3.py` ahora), cero código comentado muerto, cero `print()`. Funciones ≤ 40 líneas. Type hints obligatorios. Identificadores en inglés; mensajes al usuario en español.

## 1. Estructura de Capas (`app/`)
```text
app/
├── main.py              # FastAPI, middlewares, handlers globales, include_router(/api/v1)
├── core/
│   ├── config.py        # Único Settings (pydantic-settings); falla al arrancar si falta algo o secreto < 32B
│   ├── errors.py        # AppError(code, http_status, message, details, context)
│   ├── logging.py       # JSON stdout (structlog/json) + contextvars (request_id, flow, step)
│   ├── middleware.py    # RequestContext, AccessLog, SecurityHeaders
│   ├── security.py      # JWT, bcrypt, hash de anon_token/reset_token
│   └── responses.py     # ApiResponse[T], ok(), paginated()
├── api/v1/              # Routers finos: ruta + schemas + Depends(get_owner) + Depends(flow("FL-xx")) -> 1 servicio -> ok()
├── schemas/             # Pydantic v2: Create, Update, Read
├── services/            # Casos de uso, autorización (dueño/visibilidad), UoW (commit aquí), lanza AppError
├── repositories/        # Queries SQLAlchemy tipadas (NUNCA hacen commit; sin lazy="selectin" en cascada)
├── integrations/        # ai_client.py, ia_contract/ (copia MIT SIN EDITAR de la IA), storage/ (StorageBackend + LocalStorage), queue.py (arq), email/
├── worker/              # arq WorkerSettings, classify_file_job, dispatcher justo, crons FL-30/31/33
├── reports/             # excel.py, pdf.py
└── db/                  # engine, session, uow.py
```
- **Prohibido:** queries BD o `if` de negocio en `api/v1/*`; importar `fastapi`/`HTTPException` en `services/`; `commit()` en `repositories/`; lógica BD en `integrations/`; editar a mano `integrations/ia_contract/` (se re-copia desde `ia-clasificacion-fauna` y se actualiza `SOURCE.md`).

## 2. Respuestas y Errores (`core/responses.py`, `core/errors.py`)
Todo JSON (éxito o error) usa `ApiResponse`:
```json
{
  "status": "success | error",
  "data": { ... },
  "message": "Texto legible en español",
  "error": null,
  "meta": { "request_id": "7f3a9c2e1b", "timestamp": "2026-11-07T15:04:05Z", "pagination": null, "warnings": [] }
}
```
Error: `"data": null`, `"error": {"code": "CATALOG_CODE", "flow": "FL-08", "details": [...]}`.
- **Nunca** uses `HTTPException(detail="...")`: lanza `AppError` (`NotFoundError`, `ForbiddenError`, `ConflictError`, `BusinessRuleError`, `DependencyError`).
- **Nunca** expongas `str(exc)`, SQL, rutas ni stack traces en HTTP 500 (`INTERNAL_ERROR`).
- **Privacidad:** si un recurso privado es ajeno, responde **`404`** (no `403`).
- **Descargas binarias** (`/reports/excel`, `/reports/pdf`, `/evidence`): devuelven binario directo (errores sí llevan envoltura JSON).

## 3. Logs y Correlación (`core/logging.py`)
- **JSON en una línea a `stdout`:** `ts`, `level`, `service`, `env`, `version`, `request_id`, `event` (`<dominio>.<accion>.<resultado>`), `message`.
- Propaga `X-Request-ID` y `X-Flow` al servicio de IA y devuélvelos en header y `meta.request_id`. Usa `with log_step("ai.call"):`.
- **Nunca loguees:** contraseñas, JWT, `X-Anon-Token`, `AI_API_KEY`, `DATABASE_URL`, `image_base64`, JSON completo de IA, emails sin enmascarar (`d***@gmail.com`) ni IPs anónimas.

## 4. Archivos, `LocalStorage` y Event Loop
- **No conserves archivos originales:** sube en stream (`aiofiles`, chunks 1 MB) a `TMP_UPLOAD_PATH` (`/data/tmp-uploads`), valida extensión + firma con la copia `ia_contract/formats.py` (`formats.check()`; `jpg,jpeg,png,bmp,webp,tiff` y `mp4,avi,mov,mkv,wmv,flv,webm` hoy; `heic/heif`, `tif`, `m4v`, `3gp`, `mts`, `m2ts` diferidos a `IA-16`)/tamaño (`300 MB`, imágenes ≤ 100 MP)/duración informativa `ffprobe` (videos > 15s **no se rechazan**, entran a cola y generan warning `VIDEO_TRUNCATED` per `F1-D10`)/SHA-256 duplicado, crea fila `queued` y responde `202`. El *worker* llama a la IA, valida y re-codifica el fotograma con Pillow (JPEG ≤ 960px, calidad 80, sin EXIF), guarda en `LocalStorage` (`evidence/{yyyy}/{mm}/{id}.jpg`) vía protocolo `StorageBackend`, actualiza BD y borra el temporal en `finally`.
- **Nunca uses `shutil.copyfileobj` ni `open()` síncronos en `async def`:** usa `aiofiles` o `await asyncio.to_thread(...)`.
- **Evidencia privada:** se sirve únicamente por `GET /api/v1/classifications/{id}/evidence` verificando dueño/visibilidad (`Cache-Control: private`).

## 5. Prohibiciones Absolutas
1. **Cero secretos/URLs hardcodeadas:** prohibido `os.getenv`/`load_dotenv` fuera de `core/config.py`. `SECRET_KEY` y `REFRESH_SECRET_KEY` ≥ 32 bytes. IA: `AI_SERVICE_URL` (sin `/api/v1`), `AI_API_KEY`, `AI_TIMEOUT_SECONDS` (180) solo vía `Settings`; sin clave no se llama a la IA.
2. **Cero mocks silenciosos:** si la IA falla/hace timeout, traduce a `AppError` con la tabla de `wwf-api-contracts` §2 (`AI_TIMEOUT`, `AI_UNAVAILABLE`, `AI_NOT_READY`, `AI_BAD_RESPONSE`, `MEDIA_*`). `ai_client` solo reintenta 1 vez `IA_INTERNAL`; los reintentos con espera son del worker. Jamás inventes detecciones.
3. **Ubicación (DD-17):** coordenadas exactas **solo** para el dueño; para terceros/público/admin-en-públicas, redondear a 2 decimales (`location_precision: "approx_1km"`).
4. **Concurrencia:** `PATCH` en cámaras y proyectos exige `If-Match: <version>` (`409 CONFLICT_STALE` si difiere).
5. **Quality Gate:** `ruff` (E,F,I,B,UP,SIM,ASYNC,S, línea 100), `mypy` estricto en `core/` y `services/` (excluir `integrations/ia_contract/`, código de terceros), Alembic real.
