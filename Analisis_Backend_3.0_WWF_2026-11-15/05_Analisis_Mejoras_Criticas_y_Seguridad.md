---
title: "05 - Análisis de Mejoras Críticas, Seguridad y Cuellos de Botella"
date: 2026-11-15
project: BACKWWF
version: "4.0.0 (MVP Hackathon)"
tags: [auditoria, vulnerabilidades, rendimiento, refactorizacion, wwf]
---

# 5. Análisis de Mejoras Críticas, Seguridad y Refactorización

> [!NOTE]
> Documento anterior: [[04_Seguridad_Autenticacion_y_Firewall]] | Siguiente: [[06_Matriz_Base_Para_TDR]]

---

## 5.1 Vulnerabilidades de Seguridad (Críticas y Altas)

| Severidad | Vulnerabilidad | Archivo y Líneas Exactas | Impacto y Riesgo |
| :---: | :--- | :--- | :--- |
| **CRÍTICA** | **Credenciales de Base de Datos expuestas en Git** | `digitalocean.yaml` (L39) y `check_db.py` (L5) | Contraseña real de PostgreSQL en Aiven (`AVNS_...`) en texto plano dentro del repositorio. Requiere rotación inmediata de credenciales y limpieza del historial Git. |
| **CRÍTICA** | **API Key de terceros hardcodeada** | `app/services/species_data_service.py` (L180) | Clave de VisualCrossing (`4CVBMAAYQ2HW86J7AARDANRDA`) expuesta en código fuente en lugar de `settings`. |
| **CRÍTICA** | **Secretos JWT con valores por defecto inseguros** | `app/core/config.py` (L16-17) | `SECRET_KEY` y `REFRESH_SECRET_KEY` tienen strings por defecto predecibles (`"super-secret-key-..."`). Si faltan en `.env`, cualquiera puede forjar tokens JWT válidos. |
| **CRÍTICA** | **Broken Object Level Authorization (BOLA / IDOR)** | `app/api/v1/users.py` (L157-220) y `app/services/project_service.py` (L208-293) | Cualquier usuario autenticado puede modificar (`is_active`) o eliminar a **cualquier otro usuario** (`PATCH/DELETE /users/{user_id}`). Asimismo, usuarios anónimos pueden asociar/desasociar estaciones de cualquier proyecto (`POST/DELETE /projects/{id}/stations`). |
| **ALTA** | **Endpoints críticos de mutación/borrado sin autenticación** | `app/api/v1/videos.py` (L31, L196), `species.py` (L35, L46), `individuals.py` (L11, L28, L34), `reports.py` (L141, L155), `ai_router.py` (L13) | Cualquier actor en internet puede subir videos, disparar inferencias IA, falsificar verificaciones científicas (`is_verified`), o borrar registros de la base de datos y archivos del disco. |
| **ALTA** | **Subida de archivos sin límite de tamaño ni validación binaria** | `app/services/media_service.py` (L78-115) y `app/api/v1/videos.py` (L49-75) | No existe `MAX_FILE_SIZE`; permite DoS por agotamiento de disco/memoria. Acepta `application/octet-stream` y confía solo en la extensión y el header `Content-Type` (spoofing trivial). `filename` no se sanitiza con `os.path.basename` / regex estricta. |
| **MEDIA** | **Fuga de información en errores 500** | `app/main.py` (L95-100) | `global_exception_handler` retorna `f"Error interno del servidor: {str(exc)}"` al cliente, exponiendo detalles de SQLAlchemy, rutas internas o drivers. |
| **MEDIA** | **CORS permisivo en producción y falta de Rate Limiting** | `app/core/config.py` (L53-57) y `app/main.py` (L106-114) | Se fuerzan orígenes `localhost` en producción y no hay `slowapi` ni `TrustedHostMiddleware`. |
| **BAJA** | **Inyección SQL** | Todos los servicios y CRUDs | **Mitigado actualmente:** se usan consultas parametrizadas vía ORM SQLAlchemy 2.0. No se detectaron queries SQL concatenadas con `f-strings`. |

---

## 5.2 Cuellos de Botella en Procesamiento de Video e IA

1. **Bloqueo del Event Loop en I/O de Disco:**
   - `app/services/media_service.py` (L109-110) y `app/api/v1/videos.py` (L74-75) ejecutan `with open(file_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)` dentro de funciones `async def`. Al subir videos pesados de cámaras trampa, el worker de Uvicorn queda completamente bloqueado sin atender otras peticiones ni `/health`.
2. **Timeout de 2.0s y Mock Silencioso en IA (`app/services/ai_service.py` L86-123):**
   - `httpx.AsyncClient(timeout=2.0)` aborta cualquier subida/inferencia real de video que tarde más de 2 segundos y **guarda detecciones falsas de Jaguar en PostgreSQL** como si fueran reales.
   - `with open(file_path, "rb")` lee el archivo de forma síncrona.
3. **Ausencia de Colas Asíncronas y Almacenamiento Efímero:**
   - En contenedores (Docker / DigitalOcean / Koyeb), `uploads/` es almacenamiento efímero: un redeploy borra todos los videos subidos y además no se comparte entre réplicas si se escala horizontalmente.
   - No existe arquitectura de ingesta por lotes (carpetas de meses de grabación), ni procesamiento en background (`Celery` / `ARQ` / `Redis`).
4. **Cálculo de Indicadores en Tiempo de Request (`app/services/species_data_service.py`):**
   - `enrich_species_data` consulta APIs externas (Open-Meteo y VisualCrossing) en tiempo de ejecución usando cachés globales en RAM (`_CACHE_TEMP`, `_CACHE_MOON`) sin límite de tamaño (riesgo de OOM) ni persistencia entre los 2 workers de Uvicorn.
   - Si las APIs externas fallan, guarda valores aleatorios (`random.uniform`) en caché y los sirve como datos científicos.
5. **Extracción de Metadatos Rotos en Contenedor Linux:**
   - `app/services/video_service.py` (L6-7) hardcodea `FFMPEG_PATH = r"C:\Users\contr\..."`. Además, `MediaService` (el flujo v4) ni siquiera llama a `extract_video_metadata`, dejando `duration_seconds` en `NULL`.

---

## 5.3 Refactorización Recomendada de Librerías y Módulos

### Cambio de Librerías y Stack hacia Producción
| Área | Estado Actual | Reemplazo / Adición Recomendada | Justificación |
| :--- | :--- | :--- | :--- |
| **Almacenamiento Multimedia** | Disco local (`uploads/`) + `shutil.copyfileobj` | **S3 / DigitalOcean Spaces (`boto3` / `aioboto3`)** + URLs prefirmadas | Permite subida directa desde el cliente sin saturar FastAPI, persistencia durable y soporte multi-réplica. |
| **Procesamiento de Lotes / IA** | Síncrono en request HTTP (`timeout=2.0`) | **Celery + Redis** (o **ARQ / Dramatiq**) + Webhooks/Polling de estado (`PENDING`, `PROCESSING`, `DONE`, `FAILED`) | Desacopla la subida de carpetas (meses de video) de la inferencia de IA y extracción FFmpeg. |
| **Cliente HTTP / Streaming** | `httpx` sin reintentos, lectura síncrona | **`httpx.AsyncClient`** con timeouts diferenciados (`connect=5s, read=120s`), streaming async (`aiofiles`) y **`tenacity`** | Evita bloqueos del event loop y maneja fallos transitorios del servidor de IA sin inventar mocks. |
| **Validación de Archivos** | Extensión + `Content-Type` | **`python-magic`** (magic bytes) + límite estricto de tamaño en Nginx/middleware | Previene subida de ejecutables o scripts disfrazados de `.mp4`. |
| **Migraciones BD** | `migrations/versions/` vacío | **Alembic** con revisiones generadas (`alembic revision --autogenerate`) | Control de cambios de esquema reproducible en CI/CD. |
| **Seguridad y Observabilidad** | `print()`, sin rate limit | **`slowapi`** (Rate Limiting), **`structlog`** (JSON logs), **Sentry**, `TrustedHostMiddleware` | Trazabilidad empresarial y protección contra abuso/DDoS. |

### Módulos que Requieren Reescritura Urgente
1. `app/services/ai_service.py` (L12, L85-131): Eliminar el fallback mock de Jaguar, unificar `AI_SERVICE_URL` desde `settings`, configurar timeouts realistas y reintentos con `tenacity`.
2. `app/services/media_service.py` (L78-184): Eliminar I/O síncrono (`shutil.copyfileobj`), integrar validación por magic bytes, extraer metadatos reales (`duration_seconds`, `capture_date`) y delegar la inferencia a una cola de trabajos.
3. `app/api/v1/videos.py` y `app/api/v1/ai_router.py`: Deprecar y unificar con `media_files.py` (eliminando la tabla duplicada `videos` o migrando sus datos a `media_files`), y corregir el montaje sin prefix en `app/main.py`.
4. `app/api/v1/users.py` (L93-220) y `app/services/project_service.py` (L208-293): Cerrar brechas BOLA/IDOR añadiendo verificación estricta de propiedad/roles.
5. `app/services/species_data_service.py` (L180, L117-120, L198-201): Mover API key a `settings`, eliminar fallbacks aleatorios y persistir datos climáticos/lunares en PostgreSQL al momento de ingestar la detección en vez de calcularlos en cada `GET`.
6. `app/core/config.py` (L16-17, L53-57): Eliminar secretos JWT por defecto (fallar al arrancar si faltan en `PRODUCTION`) y condicionar orígenes `localhost` únicamente a `ENVIRONMENT == DEVELOPMENT`.
