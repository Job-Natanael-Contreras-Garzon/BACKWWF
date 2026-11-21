---
title: "11 - To-Do List de Ejecución para Antigravity /teamwork (M0–M4)"
date: 2026-11-20
project: BACKWWF
version: "1.2.0 TDR"
tags: [teamwork, antigravity, todolist, swarm, ponytail, docker, env, wwf]
---

# 11. To-Do List Maestro para `/teamwork` (`BACKWWF` M0–M4)

> [!NOTE]
> Backlog completo: [[10_Backlog_Teamwork_WWF]] · Matriz `FL/CB`: [[09_Matriz_Flujos_y_Casos_Borde]] · DoD Único: [[DEFINITION_OF_DONE]] · Guía de rutina: [[12_Guia_Rutina_Implementacion_con_Agentes]]

Este checklist está diseñado para ejecutarse por **oleadas (*Waves*)** con el comando **`/teamwork`** de Antigravity (o en sesiones individuales con modelo local 9B). Cada tarea delimita explícitamente **los archivos que posee** para que varios agentes puedan trabajar en paralelo sin pisarse el mismo archivo.

## Contexto Operativo del Entorno (Lectura Obligatoria para Agentes)

1. **Contenedores Docker en desarrollo (`docker ps`):**
   - `fauna_api` (`fauna-monitoring-api:local`): API FastAPI en `0.0.0.0:8000->8000/tcp` con `--reload`.
   - **Servicio IA objetivo (`../ia-clasificacion-fauna`):** API real o **`ia-fake`** en puerto **`8001`** (`AI_SERVICE_URL=http://host.docker.internal:8001` / `http://ia:8001` en compose; `X-API-Key: dev-key` en dev). *(`wwf-wildlife-api:8081` es la IA vieja: no cumple el contrato `1.0.0` y no cuenta como evidencia; se apaga al cerrar `SPIKE-01`. Contrato y tabla de errores: sección "Contrato IA vigente" de [[10_Backlog_Teamwork_WWF]]).*
   - PostgreSQL `faunadb` en el host Windows en el puerto `5433` (`host.docker.internal:5433/faunadb` desde `fauna_api`).
2. **Dos configuraciones por variables de entorno (`development` vs `production`):**
   - Toda credencial, clave JWT, API key y DSN se lee exclusivamente desde variables de entorno en `Settings` (`app/core/config.py`).
   - `development` (`.env` local, nunca en Git) y `production` (variables secretas del PaaS con `?ssl=require`) comparten el mismo código y esquema de variables, pero usan **credenciales, hosts y CORS distintos**. Prohibido hardcodear secretos en Python, scripts (`check_db.py`) o manifiestos (`digitalocean.yaml`).
3. **Inicialización en Docker (PowerShell, desde `HU-02`):**
   - El esquema lo crea solo Alembic: `docker compose exec -T api alembic upgrade head` → 14 tablas + `alembic_version` en `pg_tables` (comandos en [[12_Guia_Rutina_Implementacion_con_Agentes]] §1.3).
   - `create_all`, `seed_db.py` y `seed_massive.py` ya no existen. No hay datos de prueba hasta `seed-e2e` (`HU-16`); cada ticket crea los suyos en los tests.
   - ⚠️ La migración `0001` borra las tablas legadas: nunca contra producción (Aiven) sin `pg_dump`.

**Reglas para cada agente / worker:**
1. Cargar antes de programar: `.agents/skills/ponytail/SKILL.md`, `wwf-backend-standards`, `wwf-api-contracts`, `wwf-flows-and-edge-cases` y `wwf-dev-workflow`.
2. Construir desde los contratos (`skills`), **no** copiando código legacy (el código actual solo indica qué borrar).
3. Código mínimo funcional (Ponytail), sin stubs S3 ni mocks silenciosos, y verificado contra PostgreSQL (`faunadb`)/Redis/`ia-fake` o `ia-clasificacion-fauna` (`:8001`) reales según [[DEFINITION_OF_DONE]].

---

## Milestone 0 — Saneamiento, Walking Skeleton IA y Cimientos

### Oleada 0A (Secuencial — Bloqueante inicial) ✅ **Completada**
- [x] **[BUG-01] Purga y rotación de secretos expuestos y configuración estricta** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: Ninguna` · **✅ PR #1 (`bcc398c`)**
  - **Scope / Archivos:** `digitalocean.yaml`, `check_db.py`, `app/services/species_data_service.py`, `app/core/config.py`, `app/services/video_service.py`, `.env.example`, `.pre-commit-config.yaml` (`gitleaks`).
  - **Estado:** Cerrado en PR #1 (`Settings` fail-fast en producción, secretos fuera de código/scripts).

### Oleada 0B (Paralelizable en `/teamwork`: 3 agentes en archivos disjuntos tras `BUG-01`)
- [x] **[BUG-02] Cierre de brechas BOLA/IDOR y eliminación de routers legacy sin autenticación** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01]` · **✅ PR #2 (`46024a3`)**
  - **Scope / Archivos:** `app/main.py`, routers legacy y controles BOLA/IDOR en `project_service.py` / `users.py`.
  - **Estado:** Cerrado en PR #2 (routers legacy desmontados y BOLA cerrado; gestión admin de usuarios migra en `HU-15a`).

- [x] **[BUG-03] Eliminación de bloqueo del Event Loop y fuga de errores 500** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01]` · **✅ PR #3 (`5913183`)**
  - **Scope / Archivos:** `app/main.py`, `app/services/media_service.py`.
  - **Estado:** Cerrado en PR #3 (`aiofiles`/chunks no bloqueante y `INTERNAL_ERROR` 500 sin fuga de `str(exc)`).

- [x] **[SPIKE-01] Walking Skeleton: Llamada real a `POST /api/v1/detect` sin cola ni storage** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01]` · **✅ `feat/spike-01-realign-contract` (`eb477f4` docs, `e6b5812` código)**
  - **Scope / Archivos:** `app/integrations/ia_contract/` (copia sin editar de `contract.py` + `enums.py` MIT, `SOURCE.md`, licencia; reemplaza `ai_contract.py`), `app/integrations/ai_client.py`, `app/core/config.py` (`AI_TIMEOUT_SECONDS`), `.env.example`, `docker-compose.yml` (default `:8001`), `scripts/verify_ai_spike.py`, `tests/fixtures/ai/*.json`, `tests/test_spike01_ai_{contract,client}.py`.
  - **Objetivo:** Reemplazar el contrato v0 de PR #4 por la copia exacta del `contract.py` `1.0.0` (sin `geofence`, `extra="forbid"`, `frames_discarded.cap`, `truncated_at_seconds`, `low_evidence`) y hacer que `ai_client` traduzca los errores IA con la tabla canónica (`400`/`415` distinguidos por HTTP, `too_many_pixels`, 1 reintento en `500 IA_INTERNAL`, sin inventar datos) antes de `HU-11`. Reintentos con espera quedan para `HU-11`.
  - **Spec:** [[10_Backlog_Teamwork_WWF]] (`SPIKE-01`, CA-1..CA-5, UT-1..UT-3) · **Verificación:** `verify_ai_spike.py` contra `ia-fake` en `:8001` con los escenarios `_image`, `_toolong`, `_blank`, `_badformat`, `_crash`, `_busy`, `_badcontract` y clave incorrecta.
  - **Estado:** Cerrado (20/11/2026). 34 tests (Nivel 1 + parametrizados), `ruff` y `mypy --strict` en verde. Corrida real desde `fauna_api` contra `ia-fake :8001`: 4 éxitos (incluye `truncated_at_seconds=15.0` y fotograma JPEG 960x540), 4 errores traducidos, 1 reintento en `IA_INTERNAL`, `401` → `AI_UNAVAILABLE` + CRITICAL sin filtrar la clave, mismos `request_id` en los logs de la IA. Relacionados: `fix/bug-01-settings-test` (test de BUG-01 truncado) y `fix/deps-security-update` (`pip-audit` en 0; FastAPI 0.133.1, Starlette 1.3.1, Pillow 13.0.0). Pendiente con Diego: mapeo del `400`, reintento de `IA_MODEL_NOT_READY`, retirar `IA_DURATION_EXCEEDED` y fijar `pexpect` en `requirements-api.txt` de la IA.

### Oleada 0C (Secuencial tras Oleada 0B)
- [x] **[HU-01] Infraestructura Core estándar y `LocalStorage` (sin stub S3)** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01], [BUG-03], [SPIKE-01]` · **✅ `feat/hu-01-core-infra` (`08135f5`)**
  - **Scope / Archivos:** `app/core/{responses,errors,logging,middleware}.py`, `app/api/v1/router.py`, `app/integrations/storage/{base,local}.py`, `app/main.py`, `pyproject.toml` (`ruff`, `mypy`).
  - **Objetivo:** `ApiResponse`, `AppError`, logs JSON con `X-Request-ID`/`flow`/`step`, middlewares de seguridad, `StorageBackend` + `LocalStorage` (sin `s3.py`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (envoltura estándar `apiClient.js`).
  - **Estado:** Cerrado (20/11/2026), PR pendiente de aprobación de Diego. `ApiResponse` con `meta.request_id`, `AppError` + handlers globales, logs JSON enmascarados con `request_id`/`flow`/`step`, middlewares ASGI (`X-Request-ID`, cabeceras de seguridad), `StorageBackend` + `LocalStorage`, rutas bajo **`/api/v1`** (cambio para el front) y `/health` como *liveness*. `pyproject.toml` con `ruff` + `mypy --strict` y lista de deuda (*ratchet*) de 58 archivos legados. 73 tests; verificado en `fauna_api` (Docker). Pendiente: `/health/ready` en HU-03. *(El código provisorio `NOT_FOUND` para `HTTPException` legado dejó de aplicar: HU-02 retiró el legado.)*

### Oleada 0D (Paralelo parcial tras `HU-01`)
- [x] **[HU-02] Esquema canónico PostgreSQL, migración inicial Alembic y repositorios + UoW** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-02], [HU-01]` · **✅ `feat/hu-02-canonical-schema` (`f9d3702`)**
  - **Scope / Archivos:** `app/models/*.py`, `app/db/uow.py`, `app/repositories/*.py`, `app/services/policies.py`, `migrations/versions/0001_canonical_schema.py`.
  - **Objetivo:** Esquema completo `FLUJOS_SISTEMA.md §3`, índices únicos parciales (`CB-13`, `CB-50`), `upgrade`/`downgrade` limpios, repositorios sin `commit()` y sin `lazy="selectin"` en cascada.
  - **Desbloquea Front:** Avisar a Miguel al abrir PR: **el front pierde login, cámaras y proyectos** hasta `HU-03`, `HU-06` y `HU-07` (`/api/v1` queda vacío).
  - **Estado:** Cerrado (20/11/2026), PR pendiente de aprobación de Diego. 14 tablas con enums `VARCHAR`+`CHECK`, `owner_xor`, índices parciales `CB-13`, `CB-50`, `CB-82` y email único sin mayúsculas; migración `0001` (borra las 10 tablas y tipos `ENUM` legados, siembra `anon_data_retention=true`); `UnitOfWork`, 13 repositorios y `policies.py`. Retirado el código legado (43 archivos, routers, `crud`, `seed_db.py`, `seed_massive.py`). Fixes: `alembic.ini` sin `prepend_sys_path` y `migrations/env.py` apagando los loggers de la app. 88 tests con PostgreSQL 16; verificado en `fauna_api` contra `faunadb` (`upgrade` → `downgrade base` → `upgrade`, `alembic current` = `0001 (head)`). Columnas fuera de §3 para que revise Diego: `projects.version`; `classifications.label_id`, `alternatives`, `evidence_width`/`evidence_height`, `client_index`.

- [x] **[BUG-04] Eliminación de `timeout=2.0`, mock de *Panthera onca* y `ai_router.py`** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-02], [SPIKE-01], [HU-01]` · **✅ `fix/bug-04-remove-ai-mock` (`574964a`, sobre HU-01)**
  - **Scope / Archivos:** Eliminar `app/services/ai_service.py` y `app/api/v1/ai_router.py` (reemplazados por `ai_client.py`).
  - **Objetivo:** Cero mocks silenciosos (DD-4); fallo de IA se traduce a `AI_TIMEOUT`/`AI_UNAVAILABLE`.
  - **Estado:** Cerrado (20/11/2026), PR pendiente de aprobación de Diego (se mezcla después de HU-01). `ai_service.py` eliminado (`ai_router.py` ya lo quitó BUG-02); `media_service` usa `ai_client.detect_media`; `AiClientError` es `DependencyError` con HTTP, nivel y mensaje por código (`AI_UNAVAILABLE` 502, `AI_TIMEOUT` 504, `AI_NOT_READY` 503, `AI_BAD_RESPONSE` 502, `MEDIA_*` 413/415/422). Test rojo → verde `test_ai_failure_never_returns_mock_jaguar`; 76 tests. Verificado de punta a punta contra `ia-fake` (clave mala → CRITICAL + 502, ocupada → 502, ok → 200). Pendiente: el fallo de la IA se registra dos veces (cliente + handler), se unifica en HU-11.

---

## Milestone 1 — Núcleo: Auth, Sesiones Anónimas, Cámaras y Proyectos

### Oleada 1A (Secuencial tras `HU-02`)
- [x] **[HU-03] Autenticación JWT completa, rotación/reuso de refresh tokens, perfil y sistema** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-02]` · **✅ `feat/hu-03-auth`**
  - **Scope / Archivos:** `app/api/v1/{auth,config,health,router}.py`, `app/api/deps.py`, `app/services/auth_service.py`, `app/repositories/users.py` (vía `UnitOfWork`, sin archivos `{user,token}_repo.py`), `app/schemas/auth.py`, `app/core/{config,errors,security}.py`, `app/integrations/ia_contract/formats.py`, `app/main.py`.
  - **Objetivo:** Endpoints `#1–#6`, `#11`, `#12` (`register`, `login` con rate limit, `refresh` con rotación, `logout`, `GET/PATCH /me`, `me/password`, `/config/public`, `/health`, `/health/ready`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-01`..`FE-04`).
  - **Estado:** Cerrado (20/11/2026). Implementado con `PyJWT==2.15.1` y `bcrypt==5.0.0` (cost 12, sin `passlib`), `sid` en access token para `me/password` (usando `delete_all_except` en `RefreshTokenRepository`, anotado para Diego en el PR), detección de reuso `CB-78`, `CB-72` case-insensitive, rate limiter in-memory (`10/min` por `request.client.host` ignorando `X-Forwarded-For`, `5/min` por email para todos los correos existan o no para evitar oráculo de admin; `shortcut:` single-process hasta `HU-08`), `formats.py@cdf3292` (sha256 verificado), `/api/v1/config/public` (`password_recovery.enabled=false`), `/api/v1/health` (actualizados `Dockerfile`, `docker-compose.yml`, `digitalocean.yaml`, `koyeb.yml`) y `/api/v1/health/ready` (`database`, `storage`, `ai` sin clave; `503` con nuevo código `SERVICE_UNAVAILABLE` registrado en `app/core/errors.py`). 121 tests en verde (`pytest --cov=app` contra `faunadb_test`: 91% global, 91% `auth_service.py`), `ruff check/format`, `mypy --strict` (38 archivos) y `pip-audit` (0 vulnerabilidades). Verificado en vivo en `fauna_api` contra `faunadb :5433` e `ia-fake :8001` (200/503). Nota para Miguel: `X-Anon-Token` se acepta pero devuelve `anon_session: null` hasta `HU-05`, agregar `SERVICE_UNAVAILABLE` a `utils/errorMessages.js`, discriminar `401 AUTH_INVALID_CREDENTIALS` en `/me/password`, y considerar que el access JWT sigue vigente hasta 30 min tras `logout`.

### Oleada 1B (Paralelizable tras `HU-03`: 2 agentes)
- [x] **[HU-05] Sesiones anónimas temporales, `claim` atómico y cron `FL-30`** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [HU-03]` · **✅ `feat/hu-05-anon-sessions`**
  - **Scope / Archivos:** `app/api/v1/{anon_sessions,auth,router}.py`, `app/api/deps.py`, `app/core/{config,rate_limit}.py`, `app/schemas/{anon_session,auth}.py`, `app/services/{anon_session_service,auth_service}.py`, `app/repositories/{anon_sessions,camera_stations}.py`, `app/worker/cron_anon.py`, `app/cli.py`, `.env.example`, `pyproject.toml`, `tests/test_hu05_anon_sessions.py`.
  - **Objetivo:** Endpoints `#7–#10` (`POST /anon-sessions`, `/current`, `/claim` renombrando `-2`, `/close`), `anon_session` en `register`/`login`, `get_anon_session`/`get_owner` (`Bearer > X-Anon-Token`) y purga `FL-30` (`anon_retain`) vía `app.cli purge-anon`.
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`AnonBanner`, `ClaimDialog`).
  - **Estado:** Cerrado (20/11/2026), pendiente revisión obligatoria de Diego. Token `secrets.token_urlsafe(32)` almacenado solo por `hash_token` SHA-256 (sin logs), rate limit 5/h por IP directa (`SlidingWindowRateLimiter` movido a `app/core/rate_limit.py`, `shortcut:` single-process hasta `HU-08`), TTL deslizante de 24h con umbral de 60s y commit inmediato en `get_anon_session` (resiste rollback posterior), `claim` atómico con `SELECT ... FOR UPDATE` y 4 `UPDATE` masivos (incl. `is_deleted`, `CB-41` lotes/cola, renombres case-insensitive `-2`/`-3` dentro de `String(50)`, idempotencia 200 mismo usuario y 409 otro usuario; bloqueo de la fila del usuario para serializar claims simultáneos de varias sesiones del mismo usuario), `close` marcando `expired` sin borrar (`data_retained` desde `anon_retain` o fallback a `system_settings`), `anon_session` en `register`/`login` sin auto-claim, y `FL-30` (`purge_anon_sessions` + `python -m app.cli purge-anon`; `shortcut:` CLI manual hasta `arq` horario en `HU-08`) con borrado físico FK-seguro (`CB-43`), eliminación de fotogramas post-commit vía `StorageBackend` y `AnonPurgeRun` solo cuando hay filas purgadas. 146 tests en verde (25 nuevos HU-05; `pytest --cov=app` contra `faunadb_test`: 93% global, 100% `anon_session_service.py`, 98% `cron_anon.py`), `ruff check/format`, `mypy --strict` (45 archivos) y `pip-audit` (0 vulnerabilidades). Verificación en vivo en `fauna_api` (`faunadb :5433` + `python -m app.cli purge-anon`): reportada por el agente, evidencia pendiente en el PR.

- [x] **[HU-04] Recuperación de contraseña por correo (Resend) *(Condicional / Diferible)*** · `Prioridad: Low` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-03]` · **✅ `feat/hu-04-password-reset` (apagada por defecto)**
  - **Scope / Archivos:** `app/services/password_reset_service.py`, `app/integrations/email/{base,resend,console}.py`, `app/worker/send_email_job.py`, `app/api/v1/{auth,config}.py`, `app/schemas/auth.py`, `app/repositories/users.py`, `app/core/{config,errors}.py`, `tests/conftest.py` (fixtures de BD compartidas), `tests/test_hu04_password_reset.py`.
  - **Objetivo:** Endpoint `#6b` (`forgot`, `validate`, `reset`) con límites y cuotas Resend; confirmar con WWF si entra en fecha de hackathon (si no, usar enlace manual de `HU-15a`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-14`).
  - **Estado:** Cerrado (20/11/2026), **sale apagada** (`PASSWORD_RECOVERY_ENABLED=false`: los 3 endpoints responden `503 EMAIL_TEMPORARILY_UNAVAILABLE` y `/config/public` dice `enabled:false`). Activarla en producción requiere dominio verificado en Resend (SEC-07/SEC-12). Anti-enumeración por diseño: `forgot` solo aplica límite por IP y tope global (`EMAIL_DAILY_CAP=80`/`EMAIL_MONTHLY_CAP=2500` → 503 para todos) y encola; la búsqueda del usuario, los límites por correo (3/h, 5/día, contados en BD), el token (32 bytes, hash, 30 min, invalida los anteriores) y el envío ocurren en segundo plano (`BackgroundTasks`, `shortcut:` hasta arq en `HU-08`). 429 solo por abuso (> 30/h por IP, umbral propio). `reset` con `FOR UPDATE` (un solo uso aun en concurrencia) revoca todos los refresh (`CB-78`). Resend por httpx sin SDK (2 reintentos en 429/5xx) y proveedor `console` que escribe el correo en `DEV_MAILBOX_PATH` (ignorado por Git), nunca en logs. `Settings` aborta en producción si está activa sin `resend`, clave, remitente o `FRONTEND_BASE_URL` https. 169 tests en verde (23 nuevos), `ruff`, `mypy --strict` (51 archivos). Verificado con uvicorn real + PostgreSQL 16 (forgot → buzón → validate → reset → refresh viejo 401).

### Oleada 1C (Secuencial tras `HU-05`)
- [x] **[HU-06] Cámaras trampa, privacidad DD-17, `nearby`, `redeploy` y `time-offset`** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [HU-05]` · **✅ `feat/hu-06-camera-stations` (sin `#15d`)**
  - **Scope / Archivos:** `app/api/v1/camera_stations.py`, `app/services/camera_station_service.py`, `app/repositories/camera_stations.py` (extendido; no `camera_repo.py`), `app/schemas/camera_station.py`, `app/services/policies.py` (`serialize_location`, `is_mine_sql`), `app/core/geo.py`, `app/api/deps.py` (`get_optional_owner`), `app/core/config.py`, `tests/test_hu06_camera_stations.py`.
  - **Objetivo:** Endpoints `#13`, `#14`, `#15b`, `#15c`, `#15d` (`If-Match`, `serialize_location` DD-17, `CB-01..CB-21`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (Mapa, `CameraFormModal`, `NearbyCamerasDialog`).
  - **Estado:** Cerrado (20/11/2026) salvo **`#15d time-offset` (P2), pendiente**: necesita la columna `classifications.captured_at_original` (migración nueva) y una auditoría para usuarios no admin (`admin_audit_log` exige un admin); se decide con Diego. Hecho: `#13` (lista `scope`/`view=map` hasta 2000/`bbox`/`q`/`still_installed`/`sort`/paginación, y alta con `project_id`, `ANON_PUBLIC_NOT_ALLOWED`, `ANON_LIMIT_REACHED`, `CAMERA_CODE_TAKEN` también por índice en carrera `CB-14`), `#14` (GET con DD-17: exacta solo al dueño, 2 decimales + `approx_1km` al resto; privada ajena 404; PATCH con `If-Match` → `CONFLICT_STALE`, 403 en pública ajena; DELETE 204 en cascada `CB-21`: cancela `queued` con `CAMERA_DELETED`, borra lógicamente las clasificaciones, sale de los proyectos; `ENTITY_ALREADY_DELETED`), `#15b` (`nearby` con `distance_m`/`same_location`/`overlapping_period` solo para lo propio y banda de distancia para públicas ajenas; radio máx. 200 m), `#15c` (`redeploy` con código sugerido `-2`/`-3`, copia de ubicación/visibilidad/proyectos y cierre de la anterior). Advertencias `CAMERA_COORDS_SUSPECT` (`CB-07`, `REGION_BBOX`) y `CAMERA_MOVED_WITH_DATA` (`CB-09`). El `bbox` filtra las cámaras ajenas por su coordenada redondeada (`CB-05b`: no se puede triangular con un bbox diminuto). 182 tests en verde (13 nuevos), `ruff`, `mypy --strict` (55 archivos). Verificado con uvicorn real + PostgreSQL 16.

### Oleada 1D (Paralelizable tras `HU-06`: 2 agentes en dominios disjuntos)
- [ ] **[HU-07] Gestión de proyectos y asociación N:M segura de cámaras propias** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-06]`
  - **Scope / Archivos:** `app/api/v1/projects.py`, `app/services/project_service.py`, `app/repositories/project_repo.py`, `app/schemas/project.py`.
  - **Objetivo:** Endpoints `#16–#19` (privacidad independiente, `If-Match`, `CAMERA_NOT_OWNED` `CB-23`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-10`).

- [ ] **[HU-08] Creación de lotes y subida no bloqueante a cola justa Redis/`arq`** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-06]`
  - **Scope / Archivos:** `app/api/v1/batches.py`, `app/services/{batch_service,media_validator}.py`, `app/integrations/queue.py`, `app/worker/dispatcher.py`.
  - **Objetivo:** Endpoints `#21`, `#23`, `#24` (`aiofiles`, `python-magic`, formatos `formats.py` base y rechazo `.heic` hasta `IA-16`, Pillow ≤ 100 MP, lectura informativa `ffprobe` para warning `VIDEO_TRUNCATED` en > 15s por `F1-D10`, SHA-256 deduplicado `CB-50..54`, dispatcher justo `CB-30`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-15`: `UploadWidget`, `UploadTray`).

---

## Milestone 2 — Control de Cola, Crons y Seguimiento

### Oleada 2A (Secuencial tras `HU-08`)
- [ ] **[HU-09] Seguimiento (`?since=`), cancelación, reintentos y crons (`FL-31`, `FL-33`)** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-08]`
  - **Scope / Archivos:** `app/api/v1/batches.py`, `app/services/batch_service.py`, `app/worker/cron_jobs.py`.
  - **Objetivo:** Endpoints `#22`, `#24b` (`?since=`, `cancel`, `DELETE item`, `retry`), cron `FL-33` (*Reaper*) y cron `FL-31` (limpieza de temporales/huérfanos).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-22`, `FE-23`).

---

## Milestone 3 — Worker IA Real, Clasificaciones, Catálogo e Importación

### Oleada 3A (Secuencial tras `HU-09` y `BUG-04`)
- [ ] **[HU-11] Worker `arq` `classify_file_job`, evidencia en `LocalStorage` y entrega `/evidence`** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-04], [SPIKE-01], [HU-08], [HU-09]`
  - **Scope / Archivos:** `app/worker/{main,classify_file_job}.py`, `app/api/v1/classifications.py` (solo `/evidence` y esquema base).
  - **Objetivo:** Endpoint `#27` + worker real conectado a `ai_client.py` en `:8001` (`ia-clasificacion-fauna` / `ia-fake` ya listos; reintentos del worker 5s/30s en `AI_UNAVAILABLE`/`AI_TIMEOUT`/`AI_NOT_READY` sobre el `ai_client` de `SPIKE-01` (que ya traduce errores y reintenta 1 vez `IA_INTERNAL`), persistir `low_evidence` y warning `VIDEO_TRUNCATED` sin `geofence`, Pillow sin EXIF, borrado temporal en `finally`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (resultados reales y fotogramas).

### Oleada 3B (Secuencial tras `HU-07` y `HU-11`)
- [ ] **[HU-13] Catálogo SpeciesNet en RAM y estadísticas ecológicas oficiales** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-06], [HU-07], [HU-11]`
  - **Scope / Archivos:** `app/api/v1/catalog.py`, `app/services/{catalog_service,stats_service}.py`, `app/repositories/stats_repo.py`, `app/schemas/stats.py`.
  - **Objetivo:** Endpoints `#15`, `#20`, `#30` (`/catalog/species*` alimentado por `speciesnet_catalog.json` `3538` taxones / sync `GET /api/v1/catalog` con `ETag`/`304`, `common_name` EN por defecto; `/camera-stations/{id}/stats`, `/projects/{id}/stats`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-25`, `FE-26`).

### Oleada 3C (Paralelizable tras `HU-13`: 3 agentes en módulos disjuntos)
- [ ] **[HU-12] Consulta de clasificaciones, validación humana y revisión de ráfagas** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-11], [HU-13]`
  - **Scope / Archivos:** `app/api/v1/classifications.py` (resto de rutas), `app/services/{classification_service,burst_service}.py`, `app/repositories/classification_repo.py`.
  - **Objetivo:** Endpoints `#25`, `#26`, `#28`, `#29`, `#29b` (`CB-51`, `CB-60..67`, exponiendo `low_evidence` y `warnings: VIDEO_TRUNCATED`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-24`, `FE-25`).

- [ ] **[HU-10] *(Milestone 3–4)* Importación segura de paquetes `.wwm.zip` de escritorio** · `Prioridad: Medium` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-08], [HU-13]`
  - **Scope / Archivos:** `app/api/v1/imports.py`, `app/services/import_service.py`, `app/integrations/ia_contract/{package,package_validator}.py` (copia MIT sin editar), `app/worker/import_job.py`.
  - **Objetivo:** Endpoints `#32–#35` alineados a `package.py` / `package_validator.py` listos (`DS-17` ya listo en `ia-clasificacion-fauna`: `evidence` solo requerido en `category == animal` `F2-D2`/`F2-D9`, sin `geofence`, códigos `LINE_INVALID` y `EVIDENCE_MISSING`, Zip Slip/Bomb, checksum, Pillow, `create_camera`, `import_job` `CB-80..87`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-32`: `ImportDesktopModal`).

- [ ] **[HU-14] Exportación de reportes científicos Excel (5 hojas) y PDF con DD-17** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-13]`
  - **Scope / Archivos:** `app/api/v1/reports.py`, `app/reports/{excel,pdf}.py`, `app/services/report_service.py`.
  - **Objetivo:** Endpoint `#31` (`openpyxl` con escape de fórmulas, PDF con gráficos y `request_id`, DD-17).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-26`).

---

## Milestone 4 — Panel Administrativo, Gate de Producción y Extensión

### Oleada 4A (Secuencial tras `HU-05`, `HU-09`, `HU-13`)
- [ ] **[HU-15a] Panel Admin MVP (`AdminScope`, stats, explorar, borrado/restauración, usuarios y settings)** · `Prioridad: Medium` · `Revisión: Obligatoria Diego` · `Depende de: [HU-05], [HU-09], [HU-13]`
  - **Scope / Archivos:** `app/api/v1/admin.py`, `app/services/{admin_service,settings_service}.py`, `app/repositories/admin_repo.py`, `app/cli.py` (`create-admin`, `reset-admin-password`).
  - **Objetivo:** Endpoints `#36–#42` (sin Excel admin), `AdminScope` (`404` en privados `CB-96`), `admin_audit_log`, `password-reset-link`, `anon_data_retention`.
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-40`..`FE-44`).

### Oleada 4B (Paralelizable tras Oleada 3C + `HU-15a`: 2 agentes)
- [ ] **[HU-16] Gate de Producción: Matriz IDOR, Contratos Compartidos, Backups (`FL-32`) y Semilla E2E** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [HU-10], [HU-12], [HU-14], [HU-15a]`
  - **Scope / Archivos:** `tests/security/test_idor_matrix.py`, `tests/contracts/test_contracts.py`, `scripts/{backup,restore_test}.sh`, `app/cli.py` (`seed-e2e`), `.github/workflows/ci.yml`.
  - **Objetivo:** Certificar 0 brechas IDOR en los 44 contratos, paridad por sha256 de `app/integrations/ia_contract/*` con `ia-clasificacion-fauna` (`contract.py`, `enums.py`, `package.py`, `package_validator.py`, `formats.py`, `FL-20..22` implementados + QA `DS-16`), backup/restore `FL-32`, `pip-audit` y `seed-e2e`.
  - **Desbloquea Front:** `DEP-04` (E2E Playwright).

- [ ] **[HU-15b] Panel Admin Extensión Post-Demo (`queue`, `unlisted-suggestions` y Excel global)** · `Prioridad: Low` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-14], [HU-15a]`
  - **Scope / Archivos:** Ampliación en `app/api/v1/admin.py`, `app/services/admin_service.py`, `app/reports/excel.py`.
  - **Objetivo:** Endpoints `#42` (Excel global admin), `#43` (`/admin/queue`), `#44` (`/admin/unlisted-suggestions`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-45`, `FE-46`).

---

## Prompt listo para lanzar `/teamwork` por oleadas

Cuando vayas a ejecutar una oleada con `/teamwork`, puedes usar esta instrucción:

```text
/teamwork Toma las tareas pendientes de la siguiente oleada en @Analisis_Backend_3.0_WWF_2026-11-15/11_Teamwork_Todolist_WWF.md.
Respeta el Scope/Archivos de cada ticket para que no haya colisiones entre agentes.
Cada agente debe cargar las skills wwf-backend-standards, wwf-api-contracts, wwf-flows-and-edge-cases, wwf-dev-workflow y ponytail antes de editar, y cumplir @Analisis_Backend_3.0_WWF_2026-11-15/DEFINITION_OF_DONE.md.
Al terminar cada ticket, marca su casilla [x] en 11_Teamwork_Todolist_WWF.md y ejecuta /ponytail-review sobre el diff.
```
