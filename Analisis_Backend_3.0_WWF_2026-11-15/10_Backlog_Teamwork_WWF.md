---
title: "10 - Backlog Ejecutivo Ajustado para Teamwork (M0–M4)"
date: 2026-11-16
project: BACKWWF
version: "1.0.0 TDR (Ajustado)"
tags: [teamwork, backlog, hu, bug, spike, ponytail, wwf]
---

# 10. Backlog de Ejecución en Teamwork (`BACKWWF` — Proceso Ajustado)

> [!NOTE]
> Matriz de riesgos: [[09_Matriz_Flujos_y_Casos_Borde]] | DoD único: [[DEFINITION_OF_DONE]] | To-Do `/teamwork`: [[11_Teamwork_Todolist_WWF]]

**Reglas del proceso ajustado:**
1. **Un solo DoD:** Todos los tickets enlazan `[[DEFINITION_OF_DONE]]` (sin duplicar checklists).
2. **Walking Skeleton IA en M0 (`SPIKE-01`):** Llamada real a `POST /detect` antes de construir cola, storage y esquema canónico.
3. **Criterios de Aceptación:** Gherkin **exclusivo** para seguridad, privacidad e integridad crítica; el resto en lista de 1 línea. Sin estimación en horas por UT.
4. **Revisión selectiva:** Diego revisa obligatoriamente tickets marcados `Revisión obligatoria: Diego` (seguridad, privacidad DD-17, contrato IA). El resto se fusiona con CI verde + revisión asíncrona.
5. **Desbloqueo paralelo a Front:** Avisar a Miguel **al abrir el PR** (no al cerrarlo) cuando exista `Desbloquea Front`.

---

## Milestone 0 — Saneamiento, Walking Skeleton IA y Cimientos

### Task List: `M0 - Seguridad y Saneamiento`

---

# BUG · [BUG-01] Purga y rotación de secretos expuestos y configuración estricta

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `security`, `config`, `S13`, `STD-08`
- **Dependencias:** Ninguna
- **Revisión:** Obligatoria: Diego
- **DoD:** Ver [[DEFINITION_OF_DONE]]

- **Severidad:** Bloqueante
- **Componente:** Back
- **Flujo afectado:** Todos (arranque y configuración) · **HU o tarea relacionada:** SEC-01 / `ESTANDARES §8`
- **Entorno:** local | develop | producción · **Versión / commit:** `4.0.0`

## Pasos para reproducir
1. Revisar `digitalocean.yaml` (L39), `check_db.py` (L5), `app/services/species_data_service.py` (L180), `app/core/config.py` (L16-17, L53-57) y `app/services/video_service.py` (L6-7).

## Resultado esperado
Cero secretos en Git (`gitleaks` activo), `Settings` único en `app/core/config.py` que falla al arrancar con `CRITICAL config.invalid` si faltan claves o `SECRET_KEY`/`REFRESH_SECRET_KEY` < 32 bytes, `localhost` solo en `development`, y `ffprobe` tomado del `PATH`.

## Resultado obtenido
Contraseña real de Aiven y API key de VisualCrossing en texto plano en el repo; secretos JWT débiles por defecto; ruta local Windows de FFmpeg hardcodeada.

## Evidencia
- `digitalocean.yaml` L39 · `check_db.py` L5 · `app/services/species_data_service.py` L180 · `app/core/config.py` L16-17, L53-57 · `app/services/video_service.py` L6-7

## Para cerrar
- [ ] Contraseña Aiven rotada, historial limpio (`git filter-repo`) y `gitleaks` en pre-commit
- [ ] Test que falla antes del arreglo y pasa después (`test_settings_rejects_weak_jwt_secrets_in_production`)
- [ ] PR enlazado (ver [[DEFINITION_OF_DONE]])

---

# BUG · [BUG-02] Cierre de brechas BOLA/IDOR y eliminación de routers legacy sin autenticación

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `security`, `idor`, `FL-07`, `FL-10`, `FL-11`, `FL-43`, `CB-23`
- **Dependencias:** `BUG-01`
- **Revisión:** Obligatoria: Diego
- **DoD:** Ver [[DEFINITION_OF_DONE]]

- **Severidad:** Bloqueante
- **Componente:** Back
- **Flujo afectado:** FL-07, FL-10, FL-11, FL-43 · **HU o tarea relacionada:** `API §15` / `CB-23`
- **Entorno:** local | develop | producción · **Versión / commit:** `4.0.0`

## Pasos para reproducir
1. Llamar sin JWT a `GET /users/`, `POST /` (`videos.py`), `DELETE /{video_id}`, `POST /species/{id}/verify`, `DELETE /species/{id}`, `individuals/*`, `reports/*`, `ai/process-video/{id}`.
2. Como Usuario A, llamar `PATCH/DELETE /users/{id_B}` (`app/api/v1/users.py` L157-220) o asociar estación ajena en `POST /projects/{id}/stations` (`project_service.py` L208-293).

## Resultado esperado
Routers legacy removidos de `app/main.py` (`API §15` L1098) y verificación estricta de propiedad/rol en cualquier ruta activa (`403 CAMERA_NOT_OWNED` / `FORBIDDEN`).

## Resultado obtenido
Routers legacy expuestos haciendo mutaciones y hard deletes; BOLA/IDOR en `users.py` y `project_service.py`.

## Evidencia
- `app/api/v1/users.py` L93-220 · `app/services/project_service.py` L208-293 · `videos.py`, `species.py`, `individuals.py`, `reports.py`, `ai_router.py`

## Para cerrar
- [ ] Routers legacy removidos y validación de dueño en proyectos/usuarios verificada
- [ ] Test que falla antes del arreglo y pasa después (`test_legacy_routes_removed_and_idor_blocked`)
- [ ] PR enlazado (ver [[DEFINITION_OF_DONE]])

---

# BUG · [BUG-03] Bloqueo del Event Loop en ingesta de archivos y fuga de errores internos 500

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `performance`, `security`, `FL-08`, `S7`, `S9`
- **Dependencias:** `BUG-01`
- **Revisión:** Obligatoria: Diego
- **DoD:** Ver [[DEFINITION_OF_DONE]]

- **Severidad:** Alta
- **Componente:** Back
- **Flujo afectado:** FL-08 · **HU o tarea relacionada:** `ESTANDARES §4.3, §9, §10.1`
- **Entorno:** local | develop | producción · **Versión / commit:** `4.0.0`

## Pasos para reproducir
1. Subir archivo pesado en `media_service.py` (L109-110) o provocar excepción no controlada en `app/main.py` (L95-100).

## Resultado esperado
I/O asíncrono en chunks con límite de tamaño (`MAX_FILE_MB`) y respuesta 500 genérica (`INTERNAL_ERROR`) sin `str(exc)` ni stack trace al cliente.

## Resultado obtenido
`shutil.copyfileobj` síncrono bloquea Uvicorn; sin límite de tamaño; `global_exception_handler` retorna `str(exc)` en claro.

## Evidencia
- `app/services/media_service.py` L109-110 · `app/api/v1/videos.py` L74-75 · `app/main.py` L95-100

## Para cerrar
- [ ] Eliminado `shutil.copyfileobj` síncrono y ocultado `str(exc)` en respuesta 500
- [ ] Test que falla antes del arreglo y pasa después (`test_500_handler_hides_internal_exception_details`)
- [ ] PR enlazado (ver [[DEFINITION_OF_DONE]])

---

# HU-SPIKE-01 · [SPIKE-01] Walking Skeleton: Llamada Real a `POST /api/v1/detect` sin Cola ni Storage

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `ia-integration`, `spike`, `FL-08`, `CB-37`
- **Dependencias:** `BUG-01`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Confirmación temprana de contrato IA (`API_IA_BACK.md`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S1 / M0

## 1. Historia
**Como** equipo técnico,
**quiero** ejecutar un *walking skeleton* (llamada real `POST /api/v1/detect` contra `ia-deteccion` o `ia-fake` desde `BACKWWF` sin cola Redis ni `StorageBackend`),
**para** validar en los primeros días el contrato real (puertos, `X-API-Key`, timeouts, forma del JSON y decodificación de `image_base64`) antes de construir la infraestructura completa.

## 2. Origen
- **Flujos:** FL-08 · **Casos borde:** CB-37 (detección temprana de timeout/respuesta real)
- **Contrato:** `API_IA_BACK.md` §1–§2

## 3. Alcance
**Incluye:** Script/cliente mínimo `httpx.AsyncClient(timeout=180)` en `app/integrations/ai_client.py` + `ai_contract.py` (Pydantic) probando 1 imagen y 1 video real contra el servicio de Diego (o `ia-fake`).
**No incluye:** Redis/`arq`, `LocalStorage`, ni persistencia final en `classifications`.

## 4. Criterios de aceptación
- CA-1: Cliente envía `multipart/form-data` (`file`, `file_name`) con headers `X-API-Key`, `X-Request-ID`, `X-Flow=FL-08` a `{AI_BASE_URL}/api/v1/detect`.
- CA-2: Respuesta `200` valida contra `DetectResponse` (`ai_contract.py`) y decodifica `evidence.image_base64` con Pillow sin error.
- CA-3: Si hay discrepancias frente a `API_IA_BACK.md`, se documentan y corrigen en el contrato con Diego antes de iniciar `HU-02`.

## 5. Diseño técnico
- `app/integrations/ai_contract.py`, `app/integrations/ai_client.py`, script de verificación `scripts/verify_ai_spike.py`.

## 6. Riesgos bloqueantes
| Pregunta / Riesgo | Responsable | Resolución |
|---|---|---|
| ¿El servicio real `ia-deteccion` devuelve las claves exactas de `API_IA_BACK.md` dentro de 180 s? | Job / Diego | Ejecutar spike en día 4–5 contra instancia real o `ia-fake` |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]] (ejecución real comprobada contra `ia-deteccion` / `ia-fake` + aprobación de Diego).

---

# HU-01 · Infraestructura Core Estándar y `LocalStorage` (Sin Stubs Innecesarios)

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `architecture`, `logging`, `storage`, `FL-31`, `STD-01..08`
- **Dependencias:** `BUG-01`, `BUG-03`, `SPIKE-01`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Envoltura `{status, data, message, error, meta}` estable para `apiClient.js`

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S1–S2 / M0

## 1. Historia
**Como** equipo de desarrollo,
**quiero** contar con `ApiResponse`, `AppError`, logging JSON (`request_id`, `flow`, `step`), middlewares de seguridad y `LocalStorage` detrás del protocolo `StorageBackend`,
**para** unificar respuestas, errores y trazabilidad sin añadir stubs no utilizados (como `S3Storage`).

## 2. Origen
- **Tarea:** STD-01..08 · **Flujos:** Todos (`FL-01`..`FL-46`), `FL-31` · **Contrato:** `ESTANDARES_BACKEND_IA.md` §2–§9 · **Decisiones:** DD-3

## 3. Alcance
**Incluye:** `core/responses.py`, `core/errors.py`, `core/logging.py`, `core/middleware.py`, `api/v1/router.py` (`/api/v1`), `integrations/storage/base.py` (`Protocol StorageBackend`) + `local.py` (`LocalStorage`), `pyproject.toml` (`ruff`, `mypy`) y `.pre-commit-config.yaml`.
**No incluye:** `S3Storage` stub (regla Ponytail/YAGNI: el protocolo `StorageBackend` basta para añadir S3 cuando se requiera).

## 4. Criterios de aceptación (Seguridad/Privacidad en Gherkin + Funcional)
```gherkin
CA-1 · Enmascaramiento en logs y ocultación de errores internos
  Dado una excepción inesperada o un payload con email/Authorization/X-Anon-Token
  Cuando el middleware y el logger registran la petición y responden al cliente
  Entonces stdout emite 1 línea JSON con request_id, flow, step y datos enmascarados
    Y el cliente recibe 500 INTERNAL_ERROR con meta.request_id y cero detalles internos
```
- CA-2: Todo éxito devuelve `ApiResponse` (`{status, data, message, error: null, meta: {request_id, timestamp, pagination, warnings}}`) y propaga `X-Request-ID`.
- CA-3: `LocalStorage` implementa `put/get/delete/exists` bajo `STORAGE_LOCAL_PATH` lanzando `STORAGE_WRITE_FAILED` ante fallo en disco.
- CA-4: `ruff check`, `ruff format --check` y `mypy` (en `core/` y `services/`) pasan con código `0`.

## 5. Diseño técnico
- `app/main.py`, `app/core/{responses,errors,logging,middleware}.py`, `app/api/v1/router.py`, `app/integrations/storage/{base,local}.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `core/errors.py` + `core/responses.py` + handlers en `main.py` | CA-1, CA-2 |
| UT-2 | `core/logging.py` + `core/middleware.py` (`X-Request-ID`, `AccessLog`, `SecurityHeaders`) | CA-1, CA-2 |
| UT-3 | `StorageBackend` + `LocalStorage` + `pyproject.toml` (`ruff`/`mypy`) | CA-3, CA-4 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-02 · Esquema Canónico PostgreSQL, Migración Inicial Alembic y Repositorios + UoW

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `database`, `alembic`, `CB-13`, `CB-50`
- **Dependencias:** `BUG-02`, `HU-01`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Contratos estables de datos en BD

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S2 / M0

## 1. Historia
**Como** equipo de desarrollo,
**quiero** reemplazar los modelos duplicados por el esquema canónico (`FLUJOS_SISTEMA.md` §3) con migración Alembic, `UnitOfWork` y repositorios sin `commit`,
**para** garantizar integridad referencial, unicidad por dueño/SHA-256 y borrado lógico uniforme.

## 2. Origen
- **Flujos:** Base de `FL-01`..`FL-46` · **Casos borde:** Base de `CB-13`, `CB-50` · **Contrato:** `FLUJOS_SISTEMA.md` §3

## 3. Alcance
**Incluye:** Modelos ORM (`users`, `anon_sessions`, `camera_stations`, `projects`, `project_camera_stations` sin PK triple, `classification_batches`, `classifications`, `desktop_imports`, `refresh_tokens`, `password_reset_tokens`, `email_log`, `system_settings`, `admin_audit_log`, `anon_purge_runs`), índices únicos parciales, `app/db/uow.py`, `app/repositories/`, `app/services/policies.py` y migración `0001_canonical_schema.py` con `downgrade`.
**No incluye:** Endpoints HTTP (Milestones 1–4).

## 4. Criterios de aceptación (Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Integridad de índices únicos parciales y dueño único (CB-13, CB-50)
  Dado una cámara borrada (is_deleted=True) con code="CAM01"
  Cuando el mismo dueño crea otra cámara activa "cam01"
  Entonces PostgreSQL permite el alta; pero rechaza con IntegrityError si la previa sigue activa
    Y toda fila de contenido cumple CHECK (owner_user_id IS NOT NULL XOR anon_session_id IS NOT NULL)
```
- CA-2: `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` ejecuta limpio contra PostgreSQL real.
- CA-3: Repositorios en `app/repositories/` no ejecutan `commit()` y retiran `lazy="selectin"` en cascada; `UnitOfWork` revierte cambios ante excepción.

## 5. Diseño técnico
- `app/models/*.py`, `app/db/uow.py`, `app/repositories/*.py`, `app/services/policies.py`, `migrations/versions/0001_canonical_schema.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | Modelos ORM canónicos + constraints + retiro `lazy="selectin"` | CA-1, CA-3 |
| UT-2 | Migración inicial Alembic (`upgrade`/`downgrade`) + `UnitOfWork` + `policies.py` | CA-2, CA-3 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

## Milestone 1 — Núcleo Administrativo, Auth, Proyectos y Cámaras

### Task List: `M1 - Auth y Sesiones Anonimas`

---

# HU-03 · Autenticación JWT Completa, Rotación de Refresh Tokens, Perfil y Endpoints de Sistema

- **Task List (Teamwork):** `M1 - Auth y Sesiones Anonimas`
- **Prioridad:** High
- **Tags:** `backend`, `auth`, `security`, `FL-01`, `FL-02`, `CB-72`, `CB-78`
- **Dependencias:** `HU-02`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-01`..`FE-04`: Auth, `/config/public`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S2–S3 / M1

## 1. Historia
**Como** investigador,
**quiero** registrarme, iniciar/cerrar sesión, rotar tokens JWT con detección de reuso, editar mi perfil/contraseña y consultar `/config/public` y `/health/ready`,
**para** operar de forma permanente y segura bajo `API_BACK_FRONT.md`.

## 2. Origen
- **Tarea:** BE-01, BE-02 · **Flujos:** FL-01, FL-02 · **Casos borde:** CB-72, CB-78 · **Contrato:** `API §2.1–2.7, §4.1–4.2` (#1–#6, #11, #12)

## 3. Alcance
**Incluye:** `/auth/register`, `login` (rate limit 10/min IP, 5/min admin), `refresh` (rotación + detección reuso), `logout`, `GET/PATCH /auth/me`, `POST /auth/me/password`, `GET /config/public`, `GET /health`, `GET /health/ready`.
**No incluye:** Recuperación de contraseña (`HU-04`) ni sesiones anónimas (`HU-05`).

## 4. Criterios de aceptación (Seguridad en Gherkin + Funcional)
```gherkin
CA-1 · Rotación de refresh token, detección de reuso y cambio de clave (CB-72, CB-78)
  Dado un refresh_token ya rotado o un cambio de contraseña en POST /auth/me/password
  Cuando se intenta reutilizar el refresh antiguo
  Entonces responde 401 AUTH_TOKEN_INVALID y revoca todos los refresh_tokens activos del usuario
```
- CA-2: `POST /auth/register` valida password ≥ 8 chars (letra+número -> `AUTH_WEAK_PASSWORD`), correo único (`409 AUTH_EMAIL_TAKEN` `CB-72`) y retorna `anon_session` si llega `X-Anon-Token`.
- CA-3: `POST /auth/login` aplica rate limit (`429 RATE_LIMITED`), bloquea cuentas inactivas (`403 ACCOUNT_DISABLED`) y actualiza `last_login_at`.
- CA-4: `PATCH /auth/me` solo permite editar `full_name` e `institution`; `GET /config/public` expone límites/formatos y `/health/ready` devuelve `503` si falla BD, IA o storage.

## 5. Diseño técnico
- `app/api/v1/{auth,config,health}.py`, `app/services/auth_service.py`, `app/repositories/{user,token}_repo.py`, `app/schemas/auth.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `register`, `login` (rate limit) y rotación/reuso de `refresh_tokens` | CA-1, CA-2, CA-3 |
| UT-2 | `logout`, `GET/PATCH /me`, `me/password`, `/config/public`, `/health/ready` | CA-1, CA-4 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-04 · Recuperación de Contraseña por Correo (Resend) [Condicional / Diferible]

- **Task List (Teamwork):** `M1 - Auth y Sesiones Anonimas`
- **Prioridad:** Low
- **Tags:** `backend`, `auth`, `email`, `FL-14`, `CB-73`, `CB-74`, `CB-75`, `CB-76`, `CB-77`
- **Dependencias:** `HU-03`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-14`: `/recuperar` y `/restablecer`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** Condicional (M1 / Post-Demo)

## 1. Historia
**Como** investigador que olvidó su clave,
**quiero** recibir un enlace temporal por correo para restablecer mi contraseña,
**para** recuperar acceso sin depender del administrador cuando el dominio DNS esté verificado en Resend.

## 2. Origen
- **Tarea:** BE-18 · **Flujos:** FL-14 · **Casos borde:** CB-73, CB-74, CB-75, CB-76, CB-77, CB-78 · **Contrato:** `API §2.8–2.10` (#6b)

## 3. Alcance
**Incluye:** `POST /auth/password/forgot`, `GET /auth/password/reset/validate`, `POST /auth/password/reset`, `EmailProvider` (`Resend` + `Console`), job `send_email_job` y cuotas `EMAIL_DAILY_CAP=80`/`EMAIL_MONTHLY_CAP=2500`.
**No incluye:** Respaldo manual del admin (incluido en `HU-15a`, sin bloqueo mutuo).

## 4. Criterios de aceptación (Seguridad en Gherkin + Funcional)
```gherkin
CA-1 · No enumeración de cuentas y tokens de un solo uso (CB-73, CB-74, CB-75, CB-77)
  Dado un correo inexistente o desactivado en POST /auth/password/forgot
  Cuando se solicita recuperación
  Entonces responde 200 genérico en tiempo constante sin encolar correo
    Y al emitir un token nuevo (32 bytes hasheado, TTL 30m) invalida los anteriores; un token expirado o usado retorna 400 AUTH_RESET_TOKEN_INVALID
```
- CA-2: Al alcanzar `EMAIL_DAILY_CAP` o `EMAIL_MONTHLY_CAP` responde `503 EMAIL_TEMPORARILY_UNAVAILABLE` (`CB-76`).
- CA-3: `POST /auth/password/reset` revoca todos los `refresh_tokens` del usuario (`CB-78`).

## 5. Diseño técnico
- `app/services/password_reset_service.py`, `app/integrations/email/{base,resend,console}.py`, `app/worker/send_email_job.py`.

## 6. Riesgos bloqueantes
| Pregunta / Riesgo | Responsable | Resolución |
|---|---|---|
| ¿Es obligatoria la recuperación automática por correo para la fecha del hackathon/demo o basta el enlace manual del admin (`HU-15a`)? (Depende de DNS SPF/DKIM en Resend) | WWF / Diego | Confirmar con WWF; si no es obligatoria para el demo, diferir sin bloquear `HU-15a` |

## 7. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `EmailProvider` (Resend/Console) + `send_email_job` + cuotas | CA-2 |
| UT-2 | `PasswordResetService` + endpoints `forgot`/`validate`/`reset` | CA-1, CA-3 |

## 8. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-05 · Sesiones Anónimas Temporales, Asociación Atómica (`claim`) y Expiración (`FL-30`)

- **Task List (Teamwork):** `M1 - Auth y Sesiones Anonimas`
- **Prioridad:** High
- **Tags:** `backend`, `anon-sessions`, `cron`, `FL-03`, `FL-04`, `FL-30`, `CB-41`, `CB-42`, `CB-70`, `CB-71`
- **Dependencias:** `HU-03`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`AnonBanner`, `ClaimDialog`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S3 / M1

## 1. Historia
**Como** visitante anónimo,
**quiero** operar con una sesión temporal segura y asociar atómicamente mis datos al crear cuenta o iniciar sesión,
**para** probar la plataforma sin perder mis registros ni mezclarlos en equipos compartidos.

## 2. Origen
- **Tarea:** BE-03, BE-04 · **Flujos:** FL-03, FL-04, FL-30 · **Casos borde:** CB-41, CB-42, CB-70, CB-71 · **Contrato:** `API §3.1–3.4` (#7–#10) · **Decisiones:** DD-2

## 3. Alcance
**Incluye:** `POST /anon-sessions` (5/h IP), `GET /anon-sessions/current`, `POST /anon-sessions/claim` (`Bearer` + `X-Anon-Token`, traspasa cámaras/proyectos/lotes/clasificaciones y renombra colisiones `-2`), `POST /anon-sessions/current/close`, y cron horario `FL-30` (`anon_retain`).
**No incluye:** Cambio dinámico de retención por admin (`HU-15a`).

## 4. Criterios de aceptación (Seguridad/Privacidad en Gherkin + Funcional)
```gherkin
CA-1 · Aislamiento de tokens anónimos e idempotencia/conflicto de claim
  Dado una sesión anónima S1 guardada por su hash SHA-256 en BD
  Cuando otro usuario distinto intenta reclamar S1 o el token superó expires_at
  Entonces responde 409 ANON_SESSION_ALREADY_CLAIMED o 401 ANON_SESSION_EXPIRED
    Y el token nunca aparece en URLs ni en logs
```
- CA-2: `POST /anon-sessions/claim` traspasa cámaras, proyectos, lotes y clasificaciones en 1 transacción, renombra códigos repetidos (`-2`) y es idempotente para el mismo usuario (`CB-41`, `CB-70`, `CB-71`).
- CA-3: Cron `FL-30` expira sesiones inactivas, conserva filas con `anon_retain=true`, purga físicamente filas y fotogramas con `anon_retain=false` y registra conteos en `anon_purge_runs` (`CB-42`).

## 5. Diseño técnico
- `app/api/v1/anon_sessions.py`, `app/services/anon_session_service.py`, `app/repositories/anon_session_repo.py`, `app/worker/cron_jobs.py` (`FL-30`).

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | Endpoints `/anon-sessions`, `/current`, `/current/close` + hash/TTL/límites | CA-1 |
| UT-2 | `claim` atómico + cron horario `FL-30` en `arq` | CA-1, CA-2, CA-3 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

### Task List: `M1 - Camaras Trampa y Proyectos`

---

# HU-06 · Cámaras Trampa, Privacidad DD-17, Cercanía (`nearby`), Reinstalación y Desfase Horario

- **Task List (Teamwork):** `M1 - Camaras Trampa y Proyectos`
- **Prioridad:** High
- **Tags:** `backend`, `cameras`, `privacy`, `FL-05`, `FL-06`, `FL-13`, `FL-15`, `CB-01..CB-21`
- **Dependencias:** `HU-05`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Avisar a Miguel al abrir PR (Mapa, `CameraFormModal`, `NearbyCamerasDialog`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S3–S4 / M1

## 1. Historia
**Como** investigador o visitante anónimo,
**quiero** registrar, consultar, editar con bloqueo optimista, reinstalar y retirar cámaras trampa manteniendo exactas mis coordenadas solo para mí,
**para** gestionar campañas en campo sin exponer ubicaciones exactas de fauna sensible.

## 2. Origen
- **Tarea:** BE-05, BE-06, BE-07 · **Flujos:** FL-05, FL-06, FL-13, FL-15 · **Casos borde:** CB-01, CB-02, CB-03, CB-04, CB-05, CB-05b, CB-06, CB-07, CB-08, CB-09, CB-10, CB-11, CB-12, CB-13, CB-14, CB-15, CB-18, CB-19, CB-20, CB-20b, CB-21 · **Contrato:** `API §1.4–1.5, §5.1–5.9` (#13, #14, #15b, #15c, #15d) · **Decisiones:** DD-17

## 3. Alcance
**Incluye:** `GET/POST /camera-stations`, `GET/PATCH/DELETE /camera-stations/{id}` (`If-Match`, cascada lógica y cancelación de cola), `GET /camera-stations/nearby`, `POST /camera-stations/{id}/redeploy`, `POST /camera-stations/{id}/time-offset`.
**No incluye:** Estadísticas de cámara (`HU-13`).

## 4. Criterios de aceptación (Privacidad/Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Privacidad DD-17 y ocultación de cámaras privadas (CB-04, CB-05, CB-05b, CB-20, CB-20b)
  Dado una cámara pública de Ana en (-17.78345, -63.18211) y una cámara privada de Ana
  Cuando Luis consulta GET /camera-stations, GET /camera-stations/{id} o /nearby
  Entonces en la pública recibe (-17.78, -63.18) con location_precision="approx_1km" y banda de distancia (<10m/<50m/<200m)
    Y en la privada ajena recibe 404 CAMERA_NOT_FOUND (y un anónimo intentando visibility=public recibe 422 ANON_PUBLIC_NOT_ALLOWED)

CA-2 · Integridad de código único y bloqueo optimista (CB-13, CB-14, CB-15)
  Dado una cámara activa de Ana en version=3 con code="CAM01"
  Cuando intenta crear "cam01" o hacer PATCH con If-Match: 2
  Entonces responde 409 CAMERA_CODE_TAKEN o 409 CONFLICT_STALE respectivamente
```
- CA-3: Validación de fechas (`CB-11/12` -> `CAMERA_INVALID_DATES`), coordenadas en rango (`CB-08`), advertencias `CAMERA_COORDS_SUSPECT` (`CB-07`) y `CAMERA_MOVED_WITH_DATA` (`CB-09`), y soporte `view=map` (`CB-10`).
- CA-4: `GET /nearby` (`CB-01/02/06`), `POST /redeploy` (`CB-03`), `POST /time-offset` (`CB-18`), y `DELETE` con borrado lógico en cascada + cancelación de `queued` (`CB-21`) -> `204`.

## 5. Diseño técnico
- `app/api/v1/camera_stations.py`, `app/services/camera_station_service.py`, `app/services/policies.py` (`serialize_location`), `app/repositories/camera_repo.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | CRUD + `serialize_location` DD-17 + `If-Match` + validaciones | CA-1, CA-2, CA-3 |
| UT-2 | `GET /nearby`, `POST /redeploy`, `POST /time-offset` y cascada `DELETE` | CA-1, CA-4 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-07 · Gestión de Proyectos y Asociación N:M Segura de Cámaras Propias

- **Task List (Teamwork):** `M1 - Camaras Trampa y Proyectos`
- **Prioridad:** High
- **Tags:** `backend`, `projects`, `FL-07`, `FL-13`, `CB-15`, `CB-20`, `CB-22..CB-27`
- **Dependencias:** `HU-06`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-10`: `ProjectFormModal` y panel proyecto)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S4 / M1

## 1. Historia
**Como** investigador o visitante anónimo,
**quiero** agrupar mis cámaras propias en proyectos privados o públicos sin poder asociar cámaras de terceros,
**para** organizar campañas de monitoreo de forma segura.

## 2. Origen
- **Tarea:** BE-08 · **Flujos:** FL-07, FL-13 · **Casos borde:** CB-15, CB-20, CB-20b, CB-22, CB-23, CB-24, CB-25, CB-26, CB-27 · **Contrato:** `API §1.6, §6.1–6.7` (#16–#19)

## 3. Alcance
**Incluye:** `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` (`If-Match`), `POST/DELETE /projects/{id}/camera-stations`.
**No incluye:** Estadísticas de proyecto (`HU-13`).

## 4. Criterios de aceptación (Seguridad/Privacidad en Gherkin + Funcional)
```gherkin
CA-1 · Privacidad de cámaras y bloqueo IDOR en asociación N:M (CB-20, CB-23)
  Dado un proyecto público de Ana con 1 cámara privada y 1 cámara pública de Luis
  Cuando Luis consulta GET /projects/{id} o Ana intenta asociar la cámara pública de Luis
  Entonces Luis no ve la cámara privada en el proyecto, y el intento de Ana retorna 403 CAMERA_NOT_OWNED
```
- CA-2: `409 ALREADY_ASSOCIATED` si ya está vinculada (`CB-24`); N:M y nombres repetidos permitidos (`CB-25/26`); `404` si proyecto privado ajeno; `If-Match` -> `409 CONFLICT_STALE` (`CB-15`).
- CA-3: `DELETE /projects/{id}` responde `204` conservando cámaras y clasificaciones (`CB-27`).

## 5. Diseño técnico
- `app/api/v1/projects.py`, `app/services/project_service.py`, `app/repositories/project_repo.py`, `app/schemas/project.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | CRUD Proyectos + filtro de privacidad + `If-Match` | CA-1, CA-2, CA-3 |
| UT-2 | Endpoints N:M `/camera-stations` validando propiedad | CA-1, CA-2 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

## Milestone 2 — Ingesta de Lotes, Cola Asíncrona y Temporales

### Task List: `M2 - Lotes Cola y Temporales`

---

# HU-08 · Creación de Lotes y Subida No Bloqueante a Cola Justa Redis/`arq`

- **Task List (Teamwork):** `M2 - Lotes Cola y Temporales`
- **Prioridad:** High
- **Tags:** `backend`, `upload`, `redis`, `arq`, `FL-08`, `CB-16`, `CB-30..36`, `CB-41..44`, `CB-50..59`
- **Dependencias:** `HU-06`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-15`: `UploadWidget`, `UploadTray`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S4–S5 / M2

## 1. Historia
**Como** investigador o visitante anónimo,
**quiero** subir lotes de hasta 500 archivos validados al vuelo y encolados en Redis con reparto justo por dueño,
**para** recibir `202` inmediato sin bloquear la API ni saturar la cola con cargas masivas de un solo usuario.

## 2. Origen
- **Tarea:** BE-13 · **Flujos:** FL-08, FL-09 · **Casos borde:** CB-16, CB-30, CB-31, CB-32, CB-33, CB-34, CB-35, CB-36, CB-41, CB-42, CB-43, CB-44, CB-50, CB-51, CB-52, CB-53, CB-54, CB-56, CB-57, CB-57b, CB-57c, CB-58, CB-59 · **Contrato:** `API §1.9, §7.0–7.3` (#21, #23, #24)

## 3. Alcance
**Incluye:** `GET/POST /classification-batches`, `POST /classification-batches/{id}/files` (streaming `aiofiles` a `TMP_UPLOAD_PATH`, `python-magic`, Pillow pixels, `ffprobe` ≤ 15.5s, SHA-256 deduplicado, `anon_retain`, dispatcher justo `QUEUE_PER_OWNER_INFLIGHT=2`), `POST .../complete`.
**No incluye:** Worker IA (`HU-11`) ni cancelación/reaper (`HU-09`).

## 4. Criterios de aceptación (Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Deduplicación por SHA-256 sin consumir cola (CB-50, CB-51, CB-52, CB-54)
  Dado un archivo ya clasificado en CAM01
  Cuando el mismo dueño lo sube renombrado a CAM01 o a CAM02
  Entonces responde 200 con item.status="error" (DUPLICATE_FILE o DUPLICATE_FILE_OTHER_CAMERA) sin encolar en Redis
    Y si lo sube otro usuario distinto lo acepta con 202
```
- CA-2: Subida válida (incluye cámara retirada `CB-16`, video 15.3s `CB-56`, AVI/HEIC `CB-57b`) responde `202` en segundos con `queue.position` y `estimated_wait_seconds`.
- CA-3: Archivo con firma binaria falsa (`CB-57`), extensión inválida (`CB-57c`), corrupto (`CB-58`), >100 MP (`CB-59`) o >15.5s (`CB-56`) responde `200` `item.status="error"` y borra el temporal.
- CA-4: Límites `429 QUEUE_USER_LIMIT` / `422 ANON_LIMIT_REACHED` (`CB-34`), `503 QUEUE_FULL` (`CB-35`), `503 QUEUE_UNAVAILABLE` con lecturas vivas (`CB-36`), y dispatcher justo (`CB-30`).

## 5. Diseño técnico
- `app/api/v1/batches.py`, `app/services/{batch_service,media_validator}.py`, `app/integrations/queue.py`, `app/worker/dispatcher.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `MediaValidator` (`aiofiles`, SHA-256, `python-magic`, Pillow, `ffprobe`) | CA-2, CA-3 |
| UT-2 | `BatchService`, endpoints `/classification-batches*`, dispatcher Redis/`arq` y límites | CA-1, CA-4 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-09 · Seguimiento (`?since=`), Cancelación, Reintentos y Crons (`FL-31`, `FL-33`)

- **Task List (Teamwork):** `M2 - Lotes Cola y Temporales`
- **Prioridad:** High
- **Tags:** `backend`, `queue`, `cron`, `FL-09`, `FL-31`, `FL-33`, `CB-21`, `CB-32`, `CB-37..40`
- **Dependencias:** `HU-08`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-22`, `FE-23`: acciones en `UploadTray`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S5 / M2

## 1. Historia
**Como** investigador,
**quiero** seguir mis lotes incrementalmente, cancelar ítems en cola, reintentar fallidos y tener recuperación automática de trabajos huérfanos,
**para** garantizar que ningún reinicio o fallo transitorio deje lotes colgados o basura en disco.

## 2. Origen
- **Tarea:** BE-14, BE-62 · **Flujos:** FL-09, FL-31, FL-33 · **Casos borde:** CB-21, CB-32, CB-37, CB-38, CB-39, CB-40 · **Contrato:** `API §7.4–7.8` (#22, #24b)

## 3. Alcance
**Incluye:** `GET /classification-batches/{id}?since=`, `POST .../cancel`, `DELETE .../items/{i}`, `POST .../items/{i}/retry`, cron `FL-33` (*Reaper* cada 5 min + cierre lotes inactivos `BATCH_IDLE_CLOSE_MINUTES`), cron `FL-31` (limpieza de temporales, previews vencidos y fotogramas huérfanos en `LocalStorage`).
**No incluye:** Inferencia IA (`HU-11`).

## 4. Criterios de aceptación
- CA-1: `GET /classification-batches/{id}?since=` devuelve solo `items` actualizados después de `since`.
- CA-2: `POST .../cancel` y `DELETE .../items/{i}` pasan `queued` a `cancelled` (`CANCELLED_BY_USER`) y borran temporales; si está `processing` retorna `409 ITEM_NOT_CANCELLABLE` (`CB-40`).
- CA-3: `POST .../items/{i}/retry` re-encola con `202` si existe el temporal (`CB-37`); si expiró retorna `410 RETRY_FILE_UNAVAILABLE` (`CB-39`).
- CA-4: Cron `FL-33` re-encola `processing` sin `heartbeat_at` > 10m (máx 3 intentos `CB-38`), marca `PROCESSING_EXPIRED` > 24h (`CB-39`), cierra lotes `open` inactivos (`CB-32`).
- CA-5: Cron `FL-31` purga temporales/huérfanos sin borrar evidencias de registros con `is_deleted=True`.

## 5. Diseño técnico
- `app/api/v1/batches.py`, `app/services/batch_service.py`, `app/worker/cron_jobs.py` (`reaper_job`, `cleanup_orphans_job`).

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `?since=`, `cancel`, `DELETE item` y `retry` | CA-1, CA-2, CA-3 |
| UT-2 | Crons `FL-33` (Reaper) y `FL-31` (limpieza temporales/huérfanos) | CA-4, CA-5 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

## Milestone 3 — Integración Real con Servicio de IA, Clasificación y Paquete Escritorio

### Task List: `M3 - Integracion IA y Worker`

---

# BUG · [BUG-04] Eliminación de timeout de 2.0s, mock de Panthera onca y `ai_router.py` roto

- **Task List (Teamwork):** `M3 - Integracion IA y Worker`
- **Prioridad:** High
- **Tags:** `backend`, `ia-integration`, `bug`, `FL-08`, `CB-37`, `DD-4`
- **Dependencias:** `BUG-02`, `SPIKE-01`, `HU-01`
- **Revisión:** Obligatoria: Diego
- **DoD:** Ver [[DEFINITION_OF_DONE]]

- **Severidad:** Bloqueante
- **Componente:** Back
- **Flujo afectado:** FL-08 · **HU o tarea relacionada:** DD-4 / `API_IA_BACK.md`
- **Entorno:** local | develop | producción · **Versión / commit:** `4.0.0`

## Pasos para reproducir
1. Enviar archivo en `app/services/ai_service.py` (L86-123) con el servicio IA apagado o lento (> 2 s), o revisar `app/api/v1/ai_router.py` (L23-33).

## Resultado esperado
Cero mocks silenciosos (DD-4): todo timeout o caída de IA se traduce a `AI_TIMEOUT` / `AI_UNAVAILABLE` sin insertar especies ficticias.

## Resultado obtenido
`timeout=2.0` expira siempre en videos y el fallback mock inserta `Panthera onca / Jaguar` con `0.945` en BD; `ai_router.py` falla por usar `ai_raw_response` inexistente.

## Evidencia
- `app/services/ai_service.py` L12, L86-123 · `app/api/v1/ai_router.py` L23-33

## Para cerrar
- [ ] Eliminado `ai_service.py` legacy (reemplazado por `integrations/ai_client.py` validado en `SPIKE-01`) y borrado `ai_router.py`
- [ ] Test que falla antes del arreglo y pasa después (`test_ai_failure_never_returns_mock_jaguar`)
- [ ] PR enlazado (ver [[DEFINITION_OF_DONE]])

---

# HU-11 · Worker `arq` `classify_file_job`, Guardado de Evidencia y Entrega Protegida

- **Task List (Teamwork):** `M3 - Integracion IA y Worker`
- **Prioridad:** High
- **Tags:** `backend`, `ia-integration`, `worker`, `arq`, `FL-08`, `CB-17`, `CB-37`, `CB-38`, `CB-58`, `CB-61`
- **Dependencias:** `BUG-04`, `SPIKE-01`, `HU-08`, `HU-09`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Avisar a Miguel al abrir PR (resultados reales y `GET .../evidence`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S5–S6 / M3

## 1. Historia
**Como** sistema de monitoreo WWF,
**quiero** conectar el cliente IA ya validado en `SPIKE-01` al worker `arq` para analizar archivos en cola, guardar fotogramas validados en `LocalStorage` y servir la evidencia protegida por permisos,
**para** completar la ingesta asíncrona de extremo a extremo sin conservar los videos originales.

## 2. Origen
- **Tarea:** BE-15, BE-61 · **Flujos:** FL-08 · **Casos borde:** CB-17, CB-37, CB-38, CB-58, CB-61 · **Contrato:** `API_IA_BACK.md` §1–§5 · `API §8.3` (#27)

## 3. Alcance
**Incluye:** `WorkerSettings` (`arq`), `classify_file_job` (heartbeat 30s, reintentos 5s/30s en `IA_BUSY`/transitorios `CB-37`, Pillow re-codificación JPEG ≤ 960px sin EXIF, `LocalStorage.put()` antes del commit, warning `CAPTURE_OUTSIDE_DEPLOYMENT` `CB-17`, borrado del temporal en `finally`) y `GET /api/v1/classifications/{id}/evidence`.
**No incluye:** Validación humana y ráfagas (`HU-12`).

## 4. Criterios de aceptación (Privacidad/Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Entrega protegida de evidencia y prohibición de datos inventados (CB-37)
  Dado una clasificación de cámara privada de Ana y otra de cámara pública
  Cuando Luis solicita GET /api/v1/classifications/{id}/evidence
  Entonces recibe 404 en la privada y 200 image/jpeg (Cache-Control: private) en la pública
    Y si la IA falla tras los reintentos, el worker marca status="error" con AI_TIMEOUT/AI_UNAVAILABLE/MEDIA_DECODE_FAILED sin datos ficticios
```
- CA-2: Procesa `animal` (species o genus `CB-61`), `person`, `vehicle` y `blank` (sin evidencia), guarda `evidence_key` y borra el archivo de `TMP_UPLOAD_PATH` en `finally`.
- CA-3: En fallo de BD tras escribir en `LocalStorage`, elimina el fotograma huérfano antes de propagar error.

## 5. Diseño técnico
- `app/worker/{main,classify_file_job}.py`, `app/api/v1/classifications.py` (`/evidence`).

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `classify_file_job` (heartbeat, reintentos, Pillow, `LocalStorage`, cleanup `finally`) | CA-1, CA-2, CA-3 |
| UT-2 | Endpoint `GET /classifications/{id}/evidence` con verificación de visibilidad | CA-1 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]] (verificado contra `ia-deteccion` real).

---

### Task List: `M3 - Clasificaciones Validacion y Rafagas`

---

# HU-12 · Consulta de Clasificaciones, Validación Humana y Revisión de Ráfagas

- **Task List (Teamwork):** `M3 - Clasificaciones Validacion y Rafagas`
- **Prioridad:** High
- **Tags:** `backend`, `classifications`, `validation`, `bursts`, `FL-10`, `FL-16`, `CB-51`, `CB-60..67`
- **Dependencias:** `HU-11`, `HU-13`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-24`, `FE-25`: `ResultsGallery`, `ValidationDeck`, ráfagas)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S6–S7 / M3

## 1. Historia
**Como** investigador o visitante anónimo dueño,
**quiero** filtrar mis clasificaciones, mover duplicados de cámara, confirmar/corregir/rechazar registros y descartar ráfagas repetidas,
**para** depurar taxonómicamente los resultados antes de reportar.

## 2. Origen
- **Tarea:** BE-16, BE-17 · **Flujos:** FL-10, FL-16 · **Casos borde:** CB-51, CB-60, CB-60b, CB-60c, CB-60d, CB-62, CB-63, CB-64, CB-65, CB-66, CB-67 · **Contrato:** `API §8.1–8.8` (#25, #26, #28, #29, #29b)

## 3. Alcance
**Incluye:** `GET /classifications` (todos los filtros + visibilidad), `GET/PATCH/DELETE /classifications/{id}` (mover cámara `CB-51`, borrado lógico `204`), `PUT /classifications/{id}/validation` (`confirm`, `correct`, `correct_unlisted`, `reject`, `discard_repeat`, `reset`, historial), `POST /validation-batch` (≤500 IDs `CB-67`), `GET /burst-candidates`, `POST /repeat-batch`, `POST /repeat-batch/dismiss`.
**No incluye:** Estadísticas agregadas (`HU-13`).

## 4. Criterios de aceptación (Seguridad en Gherkin + Funcional)
```gherkin
CA-1 · Aislamiento en validación en lote y movimiento de cámara (CB-51, CB-67)
  Dado 3 clasificaciones propias y 1 privada de otro usuario
  Cuando se llama a POST /classifications/validation-batch o PATCH /classifications/{id} hacia cámara ajena
  Entonces validation-batch omite el ID ajeno en skipped[] y PATCH responde 403 CAMERA_NOT_OWNED
```
- CA-2: `PUT /validation` soporta todas las acciones (`CB-62..66`), valida `CLASSIFICATION_NOT_DONE` (`409`), `CATALOG_TAXON_NOT_FOUND` (`422`) y agrega al `validation_history`.
- CA-3: `burst-candidates` agrupa por cámara+taxonomía efectiva (`CB-60b`), excluye `upload_time` (`CB-60c`), `repeat-batch` exige `keep_ids` (`422 REPEAT_KEEP_REQUIRED` `CB-60d`) y `dismiss` marca revisado.

## 5. Diseño técnico
- `app/api/v1/classifications.py`, `app/services/{classification_service,burst_service}.py`, `app/repositories/classification_repo.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `GET/PATCH/DELETE /classifications` + `PUT /validation` + `POST /validation-batch` | CA-1, CA-2 |
| UT-2 | `burst-candidates`, `repeat-batch`, `dismiss` | CA-3 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

### Task List: `M3-4 - Importacion Paquete Escritorio`

---

# HU-10 · Importación Segura de Paquetes `.wwm.zip` desde la App de Escritorio

- **Task List (Teamwork):** `M3-4 - Importacion Paquete Escritorio`
- **Prioridad:** Medium
- **Tags:** `backend`, `imports`, `security`, `FL-21`, `FL-22`, `FL-23`, `CB-17`, `CB-55`, `CB-80..87`, `S8`
- **Dependencias:** `HU-08`, `HU-13`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-32`: `ImportDesktopModal`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S7 / M3–M4

## 1. Historia
**Como** investigador de campo con sesión,
**quiero** subir un paquete `.wwm.zip` de escritorio, revisar la vista previa y confirmar la importación de registros y fotogramas,
**para** sincronizar trabajo offline en la web sin subir videos pesados.

## 2. Origen
- **Tarea:** BE-40 · **Flujos:** FL-23 (conecta FL-21, FL-22) · **Casos borde:** CB-17, CB-55, CB-80..87 · **Contrato:** `API §12.1–12.4` (#32–#35) · `PAQUETE_ESCRITORIO.md`

## 3. Alcance
**Incluye:** `POST /imports/desktop` (Bearer obligatorio, preview TTL 1h, validación Zip Slip/Bomb, checksum SHA-256, `format_version`, catálogo, Pillow, hasta 200 `issues`), `POST /imports/{id}/confirm` (`create_camera=true`, re-codifica JPEGs a `LocalStorage`, worker `import_job` para paquetes grandes `CB-85`), `DELETE /imports/{id}`, `GET /imports`.
**No incluye:** Exportador Tkinter en `ia-deteccion`.

## 4. Criterios de aceptación (Seguridad/Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Defensa Zip Slip, Zip Bomb, checksum y reimportación (CB-82, CB-84)
  Dado un .wwm.zip con "../evil", symlink, > 20 000 entradas, checksum alterado o format_version "2.0"
  Cuando se envía a POST /imports/desktop
  Entonces rechaza sin escribir en BD con IMPORT_INVALID_PACKAGE, IMPORT_TOO_LARGE, IMPORT_CHECKSUM_MISMATCH o IMPORT_UNSUPPORTED_VERSION
    Y reimportar el mismo package_sha256 en la misma cámara retorna 409 IMPORT_ALREADY_IMPORTED
```
- CA-2: Preview detecta `camera_code_matches` (`CB-80`), `matching_camera_station_id` (`CB-87`), `complete=false` (`CB-86`), `duplicates` (`CB-55`, `CB-83`) y `CAPTURE_OUTSIDE_DEPLOYMENT` (`CB-17`, `CB-81`).
- CA-3: `confirm` crea cámara si procede, re-codifica `evidence/*.jpg` sin EXIF a `LocalStorage`, persiste con `source="desktop"` (vía worker si es grande `CB-85`) y borra el temporal.

## 5. Diseño técnico
- `app/api/v1/imports.py`, `app/services/import_service.py`, `app/integrations/package_contract.py`, `app/worker/import_job.py`.

## 6. Riesgos bloqueantes
| Pregunta / Riesgo | Responsable | Resolución |
|---|---|---|
| Paridad exacta de campos con `ia-deteccion/wwm_pipeline/package.py` | Job / Diego | Sincronizar `package_contract.py` antes de codificar |

## 7. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | Validador seguro ZIP en `asyncio.to_thread` + `POST /imports/desktop`, `DELETE`, `GET` | CA-1, CA-2 |
| UT-2 | `confirm` + creación cámara + re-codificación Pillow + `import_job` | CA-3 |

## 8. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

## Milestone 4 — Catálogo, Reportes Científicos, Admin y Gate de Salida QA

### Task List: `M4 - Catalogo y Reportes WWF`

---

# HU-13 · Catálogo de Especies SpeciesNet en Memoria y Estadísticas Ecológicas

- **Task List (Teamwork):** `M4 - Catalogo y Reportes WWF`
- **Prioridad:** High
- **Tags:** `backend`, `catalog`, `stats`, `FL-10`, `FL-11`, `CB-19`, `CB-61`, `CB-65`, `CB-68`
- **Dependencias:** `HU-06`, `HU-07`, `HU-11`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-25`, `FE-26`: autocompletado catálogo y `StatsPanel`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S6 / M4

## 1. Historia
**Como** investigador o visitante,
**quiero** buscar taxones en el catálogo SpeciesNet y consultar estadísticas ecológicas oficiales por cámara o proyecto,
**para** validar clasificaciones y analizar riqueza, abundancia, patrones temporales y esfuerzo de muestreo.

## 2. Origen
- **Tarea:** BE-20, BE-30 · **Flujos:** FL-10, FL-11 · **Casos borde:** CB-19, CB-61, CB-65, CB-68 · **Contrato:** `API §9.1–9.2, §10.1–10.4` (#15, #20, #30)

## 3. Alcance
**Incluye:** `CatalogService` (`speciesnet_catalog.json` en RAM al arrancar), `GET /catalog/species`, `GET /catalog/species/{label_id}`, `StatsService` compartido con reportes (`GET /camera-stations/{id}/stats`, `GET /projects/{id}/stats`).
**No incluye:** Datos externos climáticos/lunares (`FLUJOS_SISTEMA.md` §7 L385).

## 4. Criterios de aceptación (Privacidad en Gherkin + Funcional)
```gherkin
CA-1 · Exclusión de cámaras privadas en estadísticas de proyectos públicos
  Dado un proyecto público con 1 cámara pública y 1 cámara privada
  Cuando un tercero consulta GET /projects/{id}/stats
  Entonces solo se agregan avistamientos y trap_days de la cámara pública (404 si consulta directamente la cámara privada)
```
- CA-2: `GET /catalog/species` busca sin distinguir tildes (`q ≥ 2`, `limit ≤ 50`); ID inexistente -> `404 CATALOG_TAXON_NOT_FOUND`.
- CA-3: `StatsService` excluye `rejected`/`discarded_repeat` de `sightings`, ubica rangos género/familia y `unlisted` en `unidentified_to_species` (`CB-61`, `CB-65`), excluye `upload_time` de `by_month`/`by_hour`, calcula `effort.trap_days` (`CB-19`) y conserva taxonomía histórica (`CB-68`).

## 5. Diseño técnico
- `app/api/v1/catalog.py`, `app/services/{catalog_service,stats_service}.py`, `app/repositories/stats_repo.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `CatalogService` en RAM + endpoints `/catalog/species*` | CA-2 |
| UT-2 | `StatsService` + `StatsRepository` + endpoints `/stats` | CA-1, CA-3 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-14 · Exportación de Reportes Científicos Excel (5 Hojas) y PDF con Privacidad DD-17

- **Task List (Teamwork):** `M4 - Catalogo y Reportes WWF`
- **Prioridad:** High
- **Tags:** `backend`, `reports`, `excel`, `pdf`, `FL-12`, `DD-6`, `DD-17`, `S4`
- **Dependencias:** `HU-13`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-26`: descarga Excel y PDF)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S7 / M4

## 1. Historia
**Como** investigador o visitante de contenido público,
**quiero** descargar reportes en Excel (5 hojas) y PDF (gráficos y tablas) aplicando los filtros activos y protección de ubicación,
**para** entregar informes oficiales a WWF.

## 2. Origen
- **Tarea:** BE-31 · **Flujos:** FL-12 · **Contrato:** `API §11` (#31) · **Decisiones:** DD-6, DD-17, D3

## 3. Alcance
**Incluye:** `GET /reports/excel` (`openpyxl` en `asyncio.to_thread`, escape de fórmulas `=,+,-,@` `GUIA_DESARROLLO` S4) y `GET /reports/pdf` (portada, gráficos top 15, tablas, pie con página y `request_id`).
**No incluye:** Excel global admin (`HU-15b`).

## 4. Criterios de aceptación (Privacidad/Seguridad en Gherkin + Funcional)
```gherkin
CA-1 · Privacidad DD-17 e inyección de fórmulas neutralizada en Excel
  Dado un proyecto público consultado por un tercero con observaciones que inician en "=SUM(A1)"
  Cuando descarga GET /reports/excel?project_id={id}
  Entonces las coordenadas salen redondeadas a 2 decimales y la celda con "=" lleva apóstrofo protector
```
- CA-2: Excel incluye las 5 hojas exactas (*Resumen*, *Por especie*, *Por género*, *Por familia*, *Clasificaciones*); PDF incluye portada, gráficos y `request_id` en pie.
- CA-3: Sin alcance responde `422 VALIDATION_ERROR`; sin datos con filtros responde `404 REPORT_EMPTY` en JSON.

## 5. Diseño técnico
- `app/api/v1/reports.py`, `app/reports/{excel,pdf}.py`, `app/services/report_service.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | Generadores `excel.py` y `pdf.py` (en `asyncio.to_thread`) | CA-1, CA-2 |
| UT-2 | Endpoints `/reports/excel` y `/reports/pdf` + permisos DD-17 | CA-1, CA-3 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

### Task List: `M4 - Panel Administracion y QA`

---

# HU-15a · Panel Admin MVP (Stats, Exploración `AdminScope`, Borrado/Restauración, Usuarios y Settings)

- **Task List (Teamwork):** `M4 - Panel Administracion y QA`
- **Prioridad:** Medium
- **Tags:** `backend`, `admin`, `privacy`, `audit`, `FL-40..44`, `CB-43`, `CB-44`, `CB-52`, `CB-96..99`
- **Dependencias:** `HU-05`, `HU-09`, `HU-13` *(independiente de recuperación por correo)*
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-40..FE-44`: panel admin MVP)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S8 / M4

## 1. Historia
**Como** administrador único de la plataforma,
**quiero** consultar estadísticas globales, explorar datos anónimos/públicos, aplicar/revertir borrados lógicos con auditoría, gestionar usuarios (incluyendo enlace manual de reset) y configurar `anon_data_retention`,
**para** operar la plataforma en producción sin acceder jamás a datos privados de usuarios.

## 2. Origen
- **Tarea:** BE-50, BE-51, BE-52 · **Flujos:** FL-40, FL-41, FL-42, FL-43, FL-44 (respaldo FL-14) · **Casos borde:** CB-43, CB-44, CB-52, CB-96, CB-97, CB-98, CB-99 · **Contrato:** `API §13.1–13.9` (#36–#42 parcial)

## 3. Alcance
**Incluye:** `require_role("admin")`, `AdminScope`, `GET /admin/stats` (`model_feedback`, dedup `sha256` `CB-52`, sin privados), `GET /admin/camera-stations`, `/classifications`, `/classifications/{id}/evidence`, `/anon-sessions`, `POST /admin/{entity}/{id}/delete`, `/restore`, `/delete-batch`, `GET /admin/users`, `POST .../deactivate`, `reactivate`, `password-reset-link`, `GET/PUT /admin/settings`, `GET /admin/audit-log` y `app/cli.py` (`create-admin`, `reset-admin-password`).
**No incluye:** `GET /admin/queue`, `/admin/unlisted-suggestions` y `/admin/reports/excel` (movidos a `HU-15b`).

## 4. Criterios de aceptación (Privacidad/Seguridad en Gherkin + Funcional)
```gherkin
CA-1 · Aislamiento absoluto de contenido privado en AdminScope (CB-96)
  Dado una cámara privada con 10 jaguares y una cámara pública con 2 pumas
  Cuando el administrador consulta GET /admin/stats o GET /admin/classifications/{privada_id}/evidence
  Entonces stats solo incluye las 10 privadas en conteos globales (nunca en fauna/fauna_map)
    Y el acceso directo por ID privado retorna 404

CA-2 · Protección de integridad y auto-desactivación (CB-44, CB-97, CB-98, CB-99)
  Dado el admin en sesión o una sesión anónima con ítems en cola
  Cuando intenta desactivarse a sí mismo retorna 409 CANNOT_DEACTIVATE_SELF
    Y desactivar un usuario o borrar una sesión anónima cancela sus ítems queued; CLI reset-admin-password recupera acceso
```
- CA-3: Borrado y restauración en cascada registran `reason` obligatorio (`DELETE_REASON_REQUIRED`) en `admin_audit_log`.
- CA-4: `PUT /admin/settings` actualiza `anon_data_retention` afectando solo registros futuros (`CB-43`).

## 5. Diseño técnico
- `app/api/v1/admin.py`, `app/services/{admin_service,settings_service}.py`, `app/repositories/admin_repo.py`, `app/cli.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `AdminScope`, `GET /admin/stats`, explorar, `audit-log`, `settings` | CA-1, CA-4 |
| UT-2 | Borrado/restauración en cascada, usuarios, `password-reset-link` y `cli.py` | CA-2, CA-3 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-15b · Panel Admin Extensión Post-Demo (`queue`, `unlisted-suggestions` y Excel Global)

- **Task List (Teamwork):** `M4 - Panel Administracion y QA`
- **Prioridad:** Low
- **Tags:** `backend`, `admin`, `reports`, `FL-40`, `FL-45`, `FL-46`, `CB-65`
- **Dependencias:** `HU-14`, `HU-15a`
- **Revisión:** Asíncrona (CI verde)
- **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-45`, `FE-46`: `/admin/cola`, `/admin/modelo`)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** Post-Demo / M4

## 1. Historia
**Como** administrador,
**quiero** monitorear el estado en vivo de la cola/cuota de correos, revisar las sugerencias de especies no catalogadas y descargar el Excel global de plataforma,
**para** ampliar la observabilidad operativa y alimentar futuras versiones del modelo.

## 2. Origen
- **Tarea:** BE-53 · **Flujos:** FL-40 (Excel), FL-45, FL-46 · **Casos borde:** CB-65 · **Contrato:** `API §13.10, §13.10a, §13.11` (#42 Excel, #43, #44)

## 3. Alcance
**Incluye:** `GET /admin/queue`, `GET /admin/unlisted-suggestions` (normalizado sin tildes/minúsculas, solo público/anónimo), `GET /admin/reports/excel` (con hoja *Sugerencias* y registro en `admin_audit_log`).

## 4. Criterios de aceptación
- CA-1: `GET /admin/queue` reporta workers activos, `queued`, `processing`, antigüedad del más viejo, desglose por dueño y cuota de emails.
- CA-2: `GET /admin/unlisted-suggestions` agrupa `suggested_name` normalizados excluyendo registros privados.
- CA-3: `GET /admin/reports/excel` genera hojas *Plataforma*, *Fauna por especie*, *Por género*, *Por familia*, *Clasificaciones* (anónimos como `Anónimo #xxxx`) y *Sugerencias*.

## 5. Diseño técnico
- `app/api/v1/admin.py`, `app/services/admin_service.py`, `app/reports/excel.py`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `/admin/queue`, `/admin/unlisted-suggestions` y `/admin/reports/excel` | CA-1, CA-2, CA-3 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].

---

# HU-16 · Gate de Producción: Matriz IDOR, Contratos Compartidos, Backups (`FL-32`) y Semilla E2E

- **Task List (Teamwork):** `M4 - Panel Administracion y QA`
- **Prioridad:** High
- **Tags:** `backend`, `security`, `qa`, `contract`, `backup`, `FL-20`, `FL-21`, `FL-22`, `FL-32`, `CB-90..95`
- **Dependencias:** `HU-10`, `HU-12`, `HU-14`, `HU-15a`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** `DEP-04` (Suite E2E Playwright contra `seed-e2e` en producción/staging)

> **Estado:** Borrador · **Responsable:** Job · **Semana / hito:** S8 / M4 (Gate Salida a Producción)

## 1. Historia
**Como** Tech Lead y equipo de QA,
**quiero** validar la matriz completa de IDOR en todos los endpoints, verificar paridad de contratos (`API_IA_BACK.md` y `PAQUETE_ESCRITORIO.md`), automatizar backups (`FL-32`) y entregar `seed-e2e`,
**para** certificar la salida segura a producción de `BACKWWF`.

## 2. Origen
- **Tarea:** BE-23, BE-35, DEP-01..04, FL-32 · **Flujos:** FL-32 + compatibilidad contrato FL-20, FL-21, FL-22 · **Casos borde:** CB-90, CB-91, CB-92, CB-93, CB-94, CB-95 (verificación UTF-8 largo y `source_folder_name` limpio en contrato; resto manual en escritorio) · **Contrato:** `ESTANDARES §11`, `GUIA_DESARROLLO §4`

## 3. Alcance
**Incluye:** `tests/security/test_idor_matrix.py`, `tests/contracts/test_contracts.py` (paridad `ai_contract.py` y `package_contract.py`, UTF-8 largo `CB-95`), `scripts/backup.sh` + `scripts/restore_test.sh` (`pg_dump` + `STORAGE_LOCAL_PATH`, retención 7d/4s, `FL-32`), `app/cli.py seed-e2e` y CI completo (`.github/workflows/ci.yml`).
**No incluye:** UI de app de escritorio (`ia-deteccion/desktop`).

## 4. Criterios de aceptación (Seguridad/Gate en Gherkin + Funcional)
```gherkin
CA-1 · Matriz IDOR en 0 fallos transversales
  Dado recursos privados de Ana y de una sesión anónima
  Cuando Luis o un visitante sin dueño intenta leer, editar, borrar, validar o descargar evidencia en los 44 contratos
  Entonces el 100 % responde 401, 403 o 404 sin filtrar existencia ni coordenadas exactas
```
- CA-2: Tests de contrato pasan contra fixtures de `API_IA_BACK.md` y `PAQUETE_ESCRITORIO.md` (incluyendo rutas/nombres largos UTF-8 de `CB-95` y reglas `FL-20..22`, `CB-90..94`).
- CA-3: `scripts/backup.sh` y `scripts/restore_test.sh` respaldan y restauran BD + `LocalStorage` íntegros (`FL-32`).
- CA-4: CI verde en `develop` (`ruff`, `mypy`, `pip-audit`, `pytest` ≥ 70% global / ≥ 80% `services/`, `docker build`) y `seed-e2e` operativo.

## 5. Diseño técnico
- `tests/security/test_idor_matrix.py`, `tests/contracts/test_contracts.py`, `scripts/{backup,restore_test}.sh`, `app/cli.py`, `.github/workflows/ci.yml`.

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | Matriz IDOR transversal + tests de contrato IA/Escritorio | CA-1, CA-2 |
| UT-2 | Scripts backup/restore (`FL-32`) + `seed-e2e` + CI `pip-audit`/`docker build` | CA-3, CA-4 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]].
