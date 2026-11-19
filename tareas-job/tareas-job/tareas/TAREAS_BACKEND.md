# Tareas · Backend (`BACKWWF`) — Job

> Documento interno · CETERIS404 · **v2 — 08/11/2026**
> **Qué produce el back:** exactamente [contratos/API_BACK_FRONT.md](../contratos/API_BACK_FRONT.md) (**API §n**).
> **Qué consume:** [contratos/API_IA_BACK.md](../contratos/API_IA_BACK.md) (**IA §n**) y [contratos/PAQUETE_ESCRITORIO.md](../contratos/PAQUETE_ESCRITORIO.md) (**PKG §n**).
> **Cómo se hace:** [ESTANDARES_BACKEND_IA.md](../ESTANDARES_BACKEND_IA.md) (**STD §n**).
> **Reglas y modelo de datos:** [FLUJOS_SISTEMA.md](../FLUJOS_SISTEMA.md) (**FS**). **Recorridos:** [FLUJOS_DETALLADOS.md](../flujos/FLUJOS_DETALLADOS.md) (**FD Xn**). **Casos borde:** [CASOS_BORDE.md](../flujos/CASOS_BORDE.md) (**CB-xx**). **Dependencias e hitos:** [DEPENDENCIAS.md](DEPENDENCIAS.md).

---

## Cómo leer cada tarea

| Campo | Significado |
|---|---|
| **P · S** | Prioridad (P0 bloquea un entregable · P1 necesaria · P2 deseable) y semana objetivo. |
| **Flujos / casos** | Los `FL-xx` que implementa y los `CB-xx` que debe cubrir con tests. |
| ⛔ **Necesita** | Lo que debe existir para **terminarla**: de otra tarea propia, de Diego (IA o escritorio) o de Miguel. |
| 🔁 **Mientras tanto** | Con qué se puede avanzar si lo anterior no está (ver [DEPENDENCIAS §1](DEPENDENCIAS.md#1-sustitutos-para-no-bloquearse)). |
| ➡️ **Desbloquea** | Las tareas que esperan esta (sobre todo de Miguel). |
| **Criterios de aceptación** | Verificables, en formato *dado / cuando / entonces*. **Cada criterio es un test automatizado** (BE-35), salvo que diga *manual*. |

**Definición de terminado (todas las tareas):**
1. Cumple todos los criterios de aceptación con tests en verde.
2. Respuestas con la envoltura estándar y errores con códigos del catálogo (STD §4–§6).
3. Logs con `flow`, `step` y `event`, sin datos sensibles (STD §7).
4. `ruff` y `mypy` en verde, y CI en verde.
5. Variables nuevas en `.env.example`.
6. Si cambió algo del contrato, el contrato está actualizado y Diego y Miguel están avisados.

**Datos de prueba comunes** (`tests/factories.py`): usuarios `ana` (dueña), `luis` (otro usuario) y `admin`; una sesión anónima `anon1`; las cámaras `CAM01` (privada de ana), `CAM02` (pública de ana) y `QN-A` (pública de luis); el proyecto `P1` de ana con CAM01 y CAM02.

---

## Épica 0 · Fundaciones (S1–S2)

Van primero: todo endpoint nuevo se escribe ya sobre ellas.

### STD-07 · `Settings` validado y `.env.example` *(✅ Cerrado en PR #1 / `BUG-01`)*
- **P · S:** P0 · S1 · **Flujos:** todos
- **Estado:** Validación `pydantic-settings` fail-fast implementada en `app/core/config.py` y `.env.example` documentado con perfiles `development` / `production`.
- **Qué hacer:**
  - un único `core/config.py` (pydantic-settings) con **todas** las variables de STD §8, con tipos y valores por defecto de desarrollo;
  - validación al arrancar: en `ENVIRONMENT=production`, `SECRET_KEY` y `REFRESH_SECRET_KEY` de 32 bytes o más y distintas, `AI_API_KEY`, `REDIS_URL` y `DATABASE_URL` obligatorias;
  - eliminar todo `os.environ` fuera de `config.py` y las URLs escritas en `check_db.py` y `digitalocean.yaml` (BE-30);
  - `.env.example` con un comentario por variable y sin valores reales.
- **Criterios de aceptación:**
  1. Dado `ENVIRONMENT=production` sin `SECRET_KEY`, cuando arranca el back, entonces el proceso termina con código ≠ 0 y el log tiene `level=CRITICAL event=config.invalid` con el nombre de la variable (sin su valor).
  2. Dado `SECRET_KEY` de 10 caracteres en producción, entonces ocurre lo mismo que en 1.
  3. `grep -R "os.environ\|os.getenv" app/ | grep -v core/config.py` → 0 resultados.
  4. Cada variable de `Settings` aparece en `.env.example` (lo verifica un test que compara ambas listas).

### BE-51 · Cerrar la exposición de usuarios (seguridad) *(✅ Cerrado en PR #2 / `BUG-02`)*
- **P · S:** P0 · **S1, primer día** · **Casos:** CB-96
- **Estado:** Endpoints `/users` cerrados con auth y validación de dueño/IDOR en PR #2; pendiente migrar gestión administrativa a `/admin/users` en `BE-50`.
- **Qué hacer:**
  - **parche inmediato**, sin esperar la reestructura: quitar `GET /users` y `GET /users/{id}`, y en `PATCH` y `DELETE /users/{id}` exigir `user_id == current_user.id`;
  - después, todo `/users/*` desaparece: lo reemplazan `/auth/me` (BE-14) y `/admin/users` (BE-56);
  - avisar a Miguel de que `UserManagerModal` deja de funcionar (se reemplaza en FE-60).
- **Criterios de aceptación:**
  1. Dado un visitante sin token, cuando pide `GET /users`, entonces recibe 404 (la ruta ya no existe).
  2. Dado `luis` autenticado, cuando hace `PATCH` o `DELETE /users/{id de ana}`, entonces recibe 403 y `ana` no cambia en la BD.
  3. Dado `ana`, cuando hace `PATCH /users/{su id}`, entonces funciona igual que antes (hasta que se migre a `/auth/me`).

### STD-01 · Envoltura `ApiResponse`
- **P · S:** P0 · S1
- ⛔ **Necesita:** STD-07  ➡️ **Desbloquea:** FE-50, todo endpoint
- **Qué hacer:** `core/responses.py` con `ApiResponse[T]`, `ErrorBody`, `Meta` (`request_id`, `timestamp`, `pagination`, `warnings`), `ok()`, `paginated()` y `with_warnings()` (STD §4.6). Las descargas binarias (Excel, PDF, JPEG) van **sin** envoltura.
- **Criterios de aceptación:**
  1. Un test recorre **todas** las rutas del OpenAPI con respuesta JSON 2xx y verifica que tengan exactamente las claves `status`, `data`, `message`, `error` y `meta`, y que `meta` tenga `request_id` y `timestamp`.
  2. Dado un listado con 120 elementos y `page_size=50`, entonces `meta.pagination = {page:1, page_size:50, total:120, total_pages:3}`.
  3. Dado `page_size=500`, entonces se aplica 200 (o se devuelve `VALIDATION_ERROR`; se documenta cuál en el OpenAPI).

### STD-03 · `AppError`, catálogo de códigos y handlers
- **P · S:** P0 · S1–S2
- ⛔ **Necesita:** STD-01  ➡️ **Desbloquea:** FE-51 (Miguel arma su mapa de mensajes con esta lista)
- **Qué hacer:**
  - `core/errors.py` con la jerarquía de STD §5.1 y **todos** los códigos de STD §6.1 (incluidos los de cola, correo, ráfagas, importación y admin);
  - los handlers globales de STD §5.2; en `production`, ningún *stack*, SQL ni ruta interna en la respuesta;
  - publicar `GET /api/v1/meta/error-codes` (solo en desarrollo) con la lista de códigos, el HTTP y el mensaje, para que Miguel la compare con la suya.
- **Criterios de aceptación:**
  1. Test parametrizado: para cada código del catálogo, el HTTP que devuelve el handler coincide con la tabla de STD §6.1.
  2. `grep -R "HTTPException(" app/services app/api app/repositories` → 0.
  3. Dado un error no controlado en producción, entonces la respuesta es 500 `INTERNAL_ERROR` con un mensaje genérico y `meta.request_id`, y el log `ERROR` tiene el *stack* y ese mismo `request_id`.
  4. Dado un body inválido, entonces la respuesta es 422 `VALIDATION_ERROR` con `error.details[]` = `{field, code, message}` por campo.

### STD-04 · Logs JSON y correlación
- **P · S:** P0 · S2
- ⛔ **Necesita:** STD-01; para el criterio 3, que la IA lea `X-Request-ID` (IA-42, Diego)  🔁 **Mientras tanto:** `ia-fake` ya registra el header
- **Qué hacer:** `structlog` en JSON (STD §7.1), `RequestContextMiddleware`, la dependencia `flow("FL-xx")` en **cada** router, `log_step()` en los servicios, *access log* propio con la plantilla de ruta, y reenvío de `X-Request-ID` y `X-Flow` a la IA.
- **Criterios de aceptación:**
  1. Dada una petición con `X-Request-ID: abc`, entonces la respuesta tiene ese mismo header y `meta.request_id = "abc"`, y todas las líneas de log de esa petición tienen `request_id=abc`.
  2. Dada una petición sin el header, entonces el back genera uno, lo devuelve y lo usa en los logs.
  3. Dado un archivo que falla en la IA, entonces se puede encontrar por `request_id` la línea `classification.ai_call.failed` en el back y la línea correspondiente en la IA.
  4. El *access log* registra `route="/api/v1/camera-stations/{id}"`, no el ID real.

### STD-05 · Sin datos sensibles en los logs
- **P · S:** P0 · S2
- ⛔ **Necesita:** STD-04
- **Qué hacer:** quitar `json.dumps(ai_response)` de `videos.py` y `echo=True`; enmascarar los correos; un filtro de *structlog* que borre las claves `password`, `token`, `access_token`, `refresh_token`, `anon_token`, `x-api-key`, `authorization` e `image_base64`.
- **Criterios de aceptación:**
  1. Un test hace login, registro, refresh y una clasificación con `ia-fake`, captura todos los logs y verifica que no aparezcan la contraseña, ningún token, la API key, ningún base64 ni el correo completo.

### STD-06 · Reestructurar en capas
- **P · S:** P1 · S2–S3 (a medida que se reescribe cada recurso; **no** en un PR gigante)
- ⛔ **Necesita:** STD-01, STD-03
- **Qué hacer:** la estructura de STD §2.1: `crud/` → `repositories/` (sin `commit`), servicios sin `fastapi`, `integrations/` (IA, storage, cola, email) y `worker/`.
- **Criterios de aceptación:**
  1. `grep -R "from fastapi" app/services app/repositories app/integrations app/worker` → 0.
  2. `grep -R "commit()" app/repositories` → 0.
  3. Ningún router supera 40 líneas de lógica (revisión en el PR).

### BE-11 · Prefijo `/api/v1` y rutas del contrato
- **P · S:** P0 · S2 · **se integra el mismo día que FE-09 (Miguel)**
- ⛔ **Necesita:** STD-01  ➡️ **Desbloquea:** FE-09
- **Qué hacer:** `api/v1/router.py` con `prefix="/api/v1"`, las rutas **exactas** de API §15, y eliminar las de la lista final de API §15.
- **Criterios de aceptación:**
  1. Un test compara las rutas del OpenAPI con la tabla de API §15: no sobra ni falta ninguna (salvo `/docs`, `/openapi.json` y `/meta/*` en desarrollo).
  2. `GET /videos`, `/species`, `/users` y `/reports/indicators/x` → 404.

### BE-27 · Migración inicial de Alembic
- **P · S:** P0 · S2 (esquema) / S3 (definitiva)
- ⛔ **Necesita:** el modelo de FS §3 (BE-04, BE-07, BE-01, BE-55, BE-58, BE-62)  ➡️ **Desbloquea:** todo lo que persiste
- **Qué hacer:** **una** migración con todo el modelo de FS §3, más `refresh_tokens`; índices y *constraints*:
  - `CHECK` de dueño XOR;
  - único `(dueño, lower(code)) WHERE NOT is_deleted`;
  - único `(camera_station_id, file_sha256) WHERE status IN ('queued','processing','done') AND NOT is_deleted`;
  - `(owner_user_id, visibility)`, `(anon_session_id)`, `(camera_station_id, captured_at)`, `(status, queued_at)` y la taxonomía efectiva.

  Datos semilla: `system_settings.anon_data_retention = true`. El arranque ejecuta `alembic upgrade head`; nada de `create_all`.
- **Criterios de aceptación:**
  1. Sobre una BD vacía: `upgrade head`, luego `downgrade base` y otra vez `upgrade head`, sin errores.
  2. Insertar una cámara con `owner_user_id` **y** `anon_session_id` → violación del `CHECK`.
  3. Dos cámaras de `ana` con `CAM01` y `cam01` → violación del índice único; si la primera está borrada, se permite.
  4. `grep -R "create_all" app/` → 0.

### STD-08 · Herramientas y CI
- **P · S:** P1 · S2
- **Qué hacer:** `ruff`, `mypy` (`core/`, `services/`), *pre-commit* con `gitleaks`, GitHub Actions (lint + tipos + tests con Postgres y Redis de servicio + `docker build`) y la plantilla de PR (STD §12).
- **Criterios de aceptación:**
  1. Un PR con un error de lint o un test roto → el CI queda en rojo y no se puede hacer *merge* (protección de rama).
  2. Un commit con una cadena que parece una clave → *pre-commit* lo bloquea.

---

## Épica 1 · Autenticación, sesión anónima y configuración (S1–S4)

### BE-14 · Autenticación según el contrato
- **P · S:** P0 · S1–S2 · **Flujos:** FL-01, FL-02 · **Casos:** CB-72, CB-78
- ⛔ **Necesita:** STD-03, BE-27 (tabla `refresh_tokens`)  ➡️ **Desbloquea:** FE-28, FE-11
- **Qué hacer:**
  - API §2.1–2.7: register, login, refresh **con rotación**, logout, `GET/PATCH /auth/me` y cambio de contraseña;
  - `anon_session` en la respuesta de register y login cuando llega `X-Anon-Token`;
  - `expires_in` de 1800 s para usuarios y 900 s para el admin;
  - `last_login_at`;
  - `must_change_password` → `PASSWORD_CHANGE_REQUIRED` (BE-50).
- **Criterios de aceptación:**
  1. Dado un correo nuevo y una contraseña `abc12345`, cuando se registra, entonces recibe 201 con `user`, `tokens` y `anon_session: null`.
  2. Dada la contraseña `abcdefgh` (sin número), entonces 422 `AUTH_WEAK_PASSWORD`.
  3. Dado un correo ya registrado (en cualquier combinación de mayúsculas), entonces 409 `AUTH_EMAIL_TAKEN`.
  4. Dado un login con la contraseña incorrecta y otro con un correo inexistente, entonces ambos dan 401 `AUTH_INVALID_CREDENTIALS` con el **mismo** mensaje.
  5. Dado un usuario desactivado, cuando hace login, entonces 403 `ACCOUNT_DISABLED`.
  6. Dado un refresh válido R1, cuando se usa, entonces devuelve R2 y R1 queda revocado; si se vuelve a usar R1, entonces 401 `AUTH_TOKEN_INVALID` **y** R2 también queda revocado.
  7. Dado `X-Anon-Token` de una sesión con 3 clasificaciones, cuando hace login, entonces `anon_session = {has_data:true, counts:{classifications:3,…}}`.
  8. Dado el undécimo intento de login en un minuto desde la misma IP, entonces 429 `RATE_LIMITED`.

### BE-02 · Dependencia `get_owner`
- **P · S:** P0 · S1
- ⛔ **Necesita:** BE-14
- **Qué hacer:** `Owner = UserOwner | AnonOwner`; `require_user` (`AUTH_REQUIRED`); `require_role("admin")` (`ADMIN_REQUIRED`); actualización deslizante de `expires_at` de la sesión anónima (como máximo una escritura por minuto).
- **Criterios de aceptación:**
  1. Si llegan Bearer y `X-Anon-Token`, gana el Bearer (salvo en `/anon-sessions/claim`).
  2. Un token anónimo vencido → 401 `ANON_SESSION_EXPIRED`.
  3. Sin ninguno de los dos, en un endpoint que crea algo → 401 `AUTH_REQUIRED`.
  4. 10 peticiones anónimas en 30 s → como máximo 1 `UPDATE` de `last_activity_at` (se verifica con un contador de consultas).

### BE-01 · Sesión anónima y asociación a la cuenta
- **P · S:** P0 · S1–S2 · **Flujos:** FL-03, FL-04 · **Casos:** CB-41, CB-42, CB-70, CB-71
- ⛔ **Necesita:** BE-02, BE-58 (para `anon_retain`)  🔁 **Mientras tanto:** `anon_retain` fijo en `true` hasta que esté BE-58
- ➡️ **Desbloquea:** FE-01, FE-02, FE-11, FE-34
- **Qué hacer:**
  - API §3: crear sesión, `current`, `claim` y `close`;
  - el token con `secrets.token_urlsafe(32)` y solo su `sha256` en la BD;
  - `anon_retain` al insertar cada recurso anónimo;
  - `claim` atómico e idempotente, con renombrado de códigos;
  - límites `ANON_MAX_FILES` y `ANON_MAX_CAMERAS`;
  - `ANON_PUBLIC_NOT_ALLOWED`;
  - eliminar `anon_session.py` viejo, `X-Anon-Session-ID`, `/users/me/claim` y `/users/me/history`.
- **Criterios de aceptación:**
  1. `POST /anon-sessions` → 201 con `anon_token` (43 caracteres), `expires_at` = ahora + 24 h y `data_retention`; en la BD **no** está el token en claro.
  2. Seis creaciones en 1 h desde la misma IP → la sexta da 429.
  3. Un anónimo crea una cámara con `visibility=public` → 422 `ANON_PUBLIC_NOT_ALLOWED`.
  4. Un anónimo crea la sexta cámara → 422 `ANON_LIMIT_REACHED`.
  5. **Asociación:** dado `anon1` con la cámara `CAM01` y 3 clasificaciones, y `ana` que ya tiene `CAM01`, cuando `ana` hace `claim`, entonces las 3 clasificaciones y la cámara pasan a `ana`, la cámara se llama `CAM01-2`, la respuesta lista `renamed_camera_stations` y la sesión queda `claimed`.
  6. Repetir el `claim` con el mismo usuario → 200 con los conteos en 0. Con otro usuario → 409 `ANON_SESSION_ALREADY_CLAIMED`.
  7. **Atomicidad:** si falla el `UPDATE` de una tabla durante el `claim`, no cambia ninguna (*rollback*).
  8. `close` → la sesión pasa a `expired`; la respuesta trae `data_retained` según `anon_retain`.
  9. `grep -R "X-Anon-Session-ID\|anon_session_id_header\|/users/me/claim" app/` → 0.

### BE-58 · Configuración en caliente
- **P · S:** P1 · S2–S3 · **Flujos:** FL-44 · **Casos:** CB-43
- ⛔ **Necesita:** BE-27, BE-60 (*pub/sub* para invalidar la caché entre procesos)  ➡️ **Desbloquea:** FE-34, FE-60 (Configuración)
- **Qué hacer:** `SettingsService.get` (caché de 30 s, invalidación por Redis *pub/sub*), `GET/PUT /admin/settings` (API §13.8) con motivo obligatorio y auditoría (`old_value`, `new_value`).
- **Criterios de aceptación:**
  1. Dado `anon_data_retention=true` y 5 clasificaciones anónimas existentes, cuando el admin lo cambia a `false`, entonces las 5 siguen con `anon_retain=true`, y una clasificación anónima creada 1 s después tiene `anon_retain=false`, en **todos** los procesos (API y worker).
  2. `PUT` sin `reason` → 422 `DELETE_REASON_REQUIRED`.
  3. El cambio deja una fila en `admin_audit_log` con `action=update_setting`, `old_value=true` y `new_value=false`.

### BE-15 · `GET /config/public`
- **P · S:** P0 · S2
- ⛔ **Necesita:** STD-07; BE-58 para `anon_data_retention`  ➡️ **Desbloquea:** FE-13
- **Criterios de aceptación:**
  1. La respuesta tiene **exactamente** la forma de API §4.1 (test de schema), con los formatos de DD-18, `map.default_center` de Santa Cruz y `password_recovery.enabled` (falso si no hay `RESEND_API_KEY`).
  2. Cambiar `MAX_FILE_MB` en `.env` cambia `media.max_file_mb` sin tocar el código.

### BE-20 · Tareas programadas FL-30, FL-31 y FL-33
- **P · S:** P0 · S2 · **Casos:** CB-38, CB-39, CB-42
- ⛔ **Necesita:** BE-01, BE-60, BE-61 (el *reaper*)
- **Qué hacer:** cron de `arq` en el `worker` con ejecución única: FL-30 (cada hora), FL-31 (cada hora y al arrancar) y FL-33 (cada 5 min), según FS §10.
- **Criterios de aceptación:**
  1. **Retención activa:** dada una sesión vencida con `anon_retain=true`, cuando corre FL-30, entonces queda `expired` y conserva el 100 % de sus filas y fotogramas.
  2. **Retención inactiva:** dada una sesión vencida con `anon_retain=false`, entonces quedan 0 filas y 0 fotogramas, y hay una fila en `anon_purge_runs` con los conteos.
  3. **Mixta:** dadas 2 clasificaciones con `true` y 2 con `false`, entonces quedan solo las 2 con `true`.
  4. Una clasificación `queued` con `anon_retain=false` en una sesión vencida **no** se borra hasta que termina su procesamiento.
  5. Con 2 *workers*, FL-30 corre una sola vez por hora (lo verifica un *lock*).
  6. Un lote `open` sin archivos por 61 min → `incomplete`.

---

## Épica 2 · Cámaras y proyectos (S1–S3)

### BE-07 · Cámaras según el TDR
- **P · S:** P0 · S1–S2 · **Flujos:** FL-05, FL-06, FL-13 · **Casos:** CB-08, CB-11…CB-14, CB-16, CB-19…CB-21
- ⛔ **Necesita:** STD-01/03, BE-02, BE-27  ➡️ **Desbloquea:** FE-14, FE-20, FE-21
- **Qué hacer:**
  - API §5.1–5.6;
  - `CameraStationInput` con **todas** las reglas de API §1.5;
  - `CameraStation` con `owner`, `project_ids`, `counts`, `last_capture_at`, `location_precision` y `version`;
  - `view=map`, `bbox`, `q`, `scope` y paginación;
  - el serializador único `serialize_location(camera, viewer)` (DD-17);
  - `DELETE` lógico en cascada.

  Los campos fuera del TDR (marca, modelo, IR…) salen del schema público.
- **Criterios de aceptación:**
  1. Dado `ana` con `CAM01` en (-17.783451, -63.182114), cuando `ana` la pide, entonces recibe las coordenadas exactas y `location_precision="exact"`; cuando la pide `luis` (si es pública) o un visitante, entonces recibe (-17.78, -63.18) y `"approx_1km"`.
  2. **Ningún endpoint filtra coordenadas exactas:** un test recorre `GET /camera-stations`, `/{id}`, `view=map`, `/nearby`, `/projects/{id}`, `/stats`, `/reports/excel` y `/admin/*` como `luis` y como `admin` y verifica que ninguna coordenada de las cámaras de `ana` tenga más de 2 decimales.
  3. `retrieved_at < deployed_at` → 422 `CAMERA_INVALID_DATES`; `deployed_at` a 2 días en el futuro → ídem.
  4. `still_installed=true` con `retrieved_at` → 422 `VALIDATION_ERROR`.
  5. `luis` pide `GET /camera-stations/{CAM01 privada de ana}` → 404 `CAMERA_NOT_FOUND`.
  6. `GET /camera-stations?view=map&bbox=…` con 1500 cámaras → menos de 300 ms (prueba de carga *manual*, documentada).
  7. `counts` de 50 cámaras se calcula con **1** consulta (contador de consultas).
  8. `DELETE /camera-stations/{id}` → 204; la cámara y sus clasificaciones quedan `is_deleted=true`, salen de `P1` y de `/projects/P1/stats`.

### BE-08 · Proyectos individuales
- **P · S:** P1 · S2 · **Flujos:** FL-07 · **Casos:** CB-22…CB-27
- ⛔ **Necesita:** BE-07  ➡️ **Desbloquea:** FE-27, FE-08
- **Qué hacer:** API §6 (CRUD, `ProjectDetail`, asociar y desasociar, crear la cámara dentro del proyecto con `project_id`); eliminar `colaborators`; `status` → `visibility`; `version` + `If-Match`.
- **Criterios de aceptación:**
  1. `POST /projects` con `camera_station_ids` que incluye una cámara de `luis` → 403 `CAMERA_NOT_OWNED` y no se crea nada.
  2. `POST /camera-stations` con `project_id=P1` → la cámara queda creada **y** asociada; si falla la asociación, no se crea la cámara.
  3. Asociar dos veces la misma cámara → 409 `ALREADY_ASSOCIATED`.
  4. `luis` pide `GET /projects/P1` (público, con CAM01 privada y CAM02 pública) → solo ve `CAM02`, y `counts` solo suma CAM02.
  5. `DELETE /projects/P1` → las cámaras siguen existiendo.

### BE-23 · Autorización por dueño y visibilidad
- **P · S:** P0 · S2 · **Casos:** CB-96
- ⛔ **Necesita:** BE-02
- **Qué hacer:** los filtros obligatorios `visible_to(viewer)` y `owned_by(owner)` en los repositorios; lo privado ajeno → **404**; dueños desactivados excluidos de lo público.
- **Criterios de aceptación:**
  1. **Batería IDOR:** para **cada** endpoint con `{id}` (cámaras, proyectos, clasificaciones, fotogramas, lotes, importaciones), `luis` intentando leer o modificar un recurso privado de `ana` → 404, y la BD no cambia.
  2. Un anónimo intentando leer un recurso de otra sesión anónima → 404.
  3. Si se desactiva a `ana`, su `CAM02` pública desaparece de `GET /camera-stations?scope=public`.

### BE-63 · Cámaras cercanas, reinstalación y concurrencia
- **P · S:** P1 · S3 · **Flujos:** FL-05, FL-15 · **Casos:** CB-01…CB-07, CB-09, CB-10, CB-15, CB-05b
- ⛔ **Necesita:** BE-07  ➡️ **Desbloquea:** FE-17
- **Qué hacer:** API §5.7 `nearby` (Haversine), §5.8 `redeploy`, `If-Match` → `CONFLICT_STALE`, `meta.warnings` (`CAMERA_COORDS_SUSPECT`, `CAMERA_MOVED_WITH_DATA`), P2: §5.9 `time-offset`.
- **Criterios de aceptación:**
  1. Dado `ana` con `CAM01` a 12 m del punto consultado, entonces `nearby.mine` la incluye con `distance_m≈12` y `overlapping_period` correcto según las fechas de la *query*.
  2. Dada `QN-A` (pública de `luis`) a 8 m, entonces `nearby.public_others` la incluye con `distance_band="<10m"` y **sin** `distance_m` ni las coordenadas exactas.
  3. Dada una cámara **privada** de `luis` a 5 m, entonces **no** aparece en ninguna parte de la respuesta.
  4. `redeploy` de `CAM01` (instalada) con `close_previous=true` → crea `CAM01-2` con la misma ubicación y los mismos proyectos, `previous_camera_station_id=CAM01`, y `CAM01` queda retirada en `previous_retrieved_at`; todo en una transacción.
  5. Dos `PATCH` con el mismo `If-Match: 3` → el primero da 200 (`version=4`) y el segundo 409 `CONFLICT_STALE`.
  6. Coordenadas (-63.18, -17.78) (invertidas) → se guarda y `meta.warnings` contiene `CAMERA_COORDS_SUSPECT`. Coordenadas de Lima, Perú → se guarda **sin** advertencia. (0,0) → advertencia.
  7. Mover `CAM01` (con clasificaciones) 80 m → `meta.warnings` contiene `CAMERA_MOVED_WITH_DATA`.

### BE-06 · Limpieza de modelos fuera de alcance
- **P · S:** P1 · S2
- **Qué hacer:** eliminar `video`, `individual`, `media_file`, `species` (tabla vieja), `report` (si solo alimenta los indicadores) y sus routers, schemas y servicios.
- **Criterios de aceptación:**
  1. `grep -Ri "individual\|VideoModel\|media_file" app/` → 0.
  2. Los tests siguen en verde.

---

## Épica 3 · Clasificación: subida, cola y worker (S2–S3)

### BE-60 · Infraestructura de la cola
- **P · S:** P0 · S2
- ⛔ **Necesita:** STD-07; `ia-fake` (Diego, fin de S1) para el `docker-compose.dev.yml`
- ➡️ **Desbloquea:** BE-13, BE-61, BE-20, BE-31, BE-58, BE-62; **el entorno de desarrollo de Miguel**
- **Qué hacer:**
  - `docker-compose.dev.yml` con `backend`, `worker`, `redis`, `db` e `ia-fake` (y el *profile* `ia` para la IA real);
  - Redis con contraseña, AOF y `noeviction`, sin puerto publicado;
  - el volumen `tmp_uploads` compartido;
  - `integrations/queue.py`;
  - `/health/ready` con `redis`.
- **Criterios de aceptación:**
  1. *Manual:* en una máquina limpia, `docker compose -f docker-compose.dev.yml up` levanta todo, y `GET /api/v1/health/ready` responde `database`, `redis`, `ai` y `storage` en `ok`.
  2. Con Redis detenido, `/health/ready` → 503 con `redis: "down"`, y `GET /camera-stations` **sigue** funcionando.
  3. Documentado en el README del back cómo lo levanta Miguel (con un `.env.example` de desarrollo).

### BE-03 · Cliente de la IA *(🚧 v0 `SPIKE-01` en PR #4 — requiere realineación)*
- **P · S:** P0 · S1–S2
- ⛔ **Necesita:** **IA-21 (Diego): `contract.py` + fixtures (✅ listo en `ia-clasificacion-fauna`)**  🔁 **Mientras tanto:** `ia-fake` en `:8001` y fixtures reales
- **Qué hacer:** alinear `integrations/ai_client.py` y `integrations/ai_contract.py` (creados en PR #4) al contrato v2 final de Diego: puerto base `:8001` (`AI_SERVICE_URL` / `AI_BASE_URL`), timeout de 180 s, headers `X-API-Key`, `X-Request-ID` y `X-Flow`, schema sin `geofence` (`extra="forbid"`), campos `low_evidence` y `truncated_at_seconds`, mapeo de `400 IA_INVALID_FORMAT` / `too_many_pixels`, 1 reintento en `500 IA_INTERNAL`, y **eliminar el "Jaguar 94,5 %"** de routers/servicios.
- **Criterios de aceptación:**
  1. Contra `ia-fake`: un archivo normal → `DetectResult` válido; `*_blank*` → `category=blank` y `evidence=null`.
  2. IA apagada → `AiUnavailableError` (`AI_UNAVAILABLE`); `*_slow*` con timeout de 5 s → `AI_TIMEOUT`; `*_error_decode*` → `MEDIA_DECODE_FAILED`; una respuesta sin `result` → `AI_BAD_RESPONSE` (el log lista las claves recibidas, sin base64).
  3. Una API key incorrecta → `AI_UNAVAILABLE` + log `CRITICAL` `ai.unauthorized`.
  4. **Test de igualdad:** `app/integrations/ai_contract.py` es idéntico a `ia-deteccion/wwm_pipeline/contract.py` (hash del archivo, o comparación del JSON Schema exportado).
  5. `grep -Ri "jaguar\|94.5\|fallback" app/integrations app/services` → 0.

### BE-04 · Modelo `classifications` y su guardado
- **P · S:** P0 · S2 (modelo) / S3 (con la IA real)
- ⛔ **Necesita:** BE-27, BE-03; **IA-13, IA-14, IA-15 e IA-20 (✅ listos en `ia-clasificacion-fauna`)**: una respuesta por archivo con taxonomía completa, fotograma en base64, `timestamp_seconds`, `low_evidence`, `truncated_at_seconds` y `capture` (sin `geofence`)
- 🔁 **Mientras tanto:** `ia-fake` (`:8001`)  ➡️ **Desbloquea:** FE-24
- **Qué hacer:** las tablas de FS §3 (`classification_batches`, `classifications`, `alternatives`, `evidence_*`, `warnings` con `VIDEO_TRUNCATED`, `validation_history`…), el mapeo de IA §5 (`low_evidence`, `model_*` sin `geofence`) y las columnas `eff_*` de taxonomía efectiva.
- **Criterios de aceptación:**
  1. Dado el fixture de jaguar, entonces se guarda **una** fila con `family="felidae"`, `rank="species"`, `evidence_timestamp_seconds=7.07`, `evidence_frame_index=212`, `alternatives` con 2 elementos y `model_*` poblados.
  2. Dado el fixture de un animal identificado solo hasta el género, entonces `species=null`, `genus="dasyprocta"`, `family="dasyproctidae"` y `eff_genus="dasyprocta"`.
  3. Dada una corrección (BE-10), entonces `eff_*` toma la taxonomía corregida sin tocar la de la IA.
  4. *Integración real (S3):* con la IA real y los videos de prueba, todas las filas tienen `family` no nulo cuando `rank ∈ {species, genus, family}`.

### BE-05 · Storage de fotogramas y archivos temporales
- **P · S:** P0 · S2 · **Casos:** CB-59
- ⛔ **Necesita:** STD-06  ➡️ **Desbloquea:** FE-06
- **Qué hacer:**
  - `StorageBackend` + `LocalStorage` + *stub* de `S3Storage` (STD §9);
  - la clave `evidence/{yyyy}/{mm}/{id}.jpg`;
  - la validación y re-codificación con Pillow (JPEG ≤ 960 px, calidad 80, sin EXIF, `MAX_IMAGE_PIXELS`);
  - el orden archivo → fila;
  - `GET /classifications/{id}/evidence` con autorización;
  - eliminar `uploads/`, `file_url` y el estático `/detections`.
- **Criterios de aceptación:**
  1. Tras procesar 10 archivos, en el storage hay exactamente 10 JPEG (o menos, si hubo `blank`) y en `TMP_UPLOAD_PATH` hay **0** archivos.
  2. El JPEG guardado no tiene EXIF y su lado mayor es ≤ 960 px.
  3. Un base64 que no es JPEG → el ítem queda en `error` `STORAGE_WRITE_FAILED` y no se crea ninguna fila `done`.
  4. `GET …/evidence` como dueño → 200 `image/jpeg` con `Cache-Control: private`; como `luis` sobre una cámara privada → 404; como visitante sobre una pública → 200.
  5. Simular un fallo al guardar la fila → el JPEG recién escrito se borra.

### BE-21 · Validador de medios
- **P · S:** P0 · S2 · **Casos:** CB-56…CB-59, CB-57b, CB-57c
- ⛔ **Necesita:** BE-15 (`config.media`); `ffmpeg` en la imagen de Docker
- **Qué hacer:** extensión + firma binaria (`filetype`) alineadas a `wwm_pipeline/formats.py` base (`IA-16` pendiente para HEIC/TIF/extra); tamaño en *streaming* (corta al superar `MAX_FILE_MB` = 300 MB) y resolución ≤ 100 MP (`too_many_pixels` → `MEDIA_TOO_LARGE`); lectura de duración con `ffprobe` solo informativa: si un video supera 15 s **no se rechaza** (`F1-D10`), entra a cola y el back emite el warning `VIDEO_TRUNCATED`; `details.context`.
- **Criterios de aceptación:**
  1. Un archivo de cada extensión de `formats.py` base → pasa la validación; `.heic`/`.cr2` → `MEDIA_UNSUPPORTED_FORMAT` con `context.accepted`.
  2. Un `.mp4` que es un PDF → `MEDIA_UNSUPPORTED_FORMAT`.
  3. Un video de 15,6 s → pasa a cola, se analiza hasta `15.0 s` y genera warning `VIDEO_TRUNCATED` (`F1-D10`).
  4. Un archivo de `MAX_FILE_MB` + 1 o imagen > 100 MP → `MEDIA_TOO_LARGE`, sin leer el archivo completo en memoria (memoria del proceso < 100 MB durante la prueba).
  5. Un MP4 truncado → `MEDIA_DECODE_FAILED`.

### BE-13 · Lotes y subida por archivo
- **P · S:** P0 · S2 · **Flujos:** FL-08, FL-09 · **Casos:** CB-30…CB-36, CB-40, CB-50, CB-51, CB-54
- ⛔ **Necesita:** BE-04, BE-05, BE-21, BE-60  ➡️ **Desbloquea:** **FE-22, FE-15, FE-23, FE-52** (el corazón de la subida en el front)
- **Qué hacer:**
  - API §7.1–7.8: crear el lote (cámara **obligatoria siempre**), `files` (202 `queued` o 200 `error`), `complete`, `GET` por ID con `since`, `GET ?active=true`, `cancel`, `DELETE items/{i}` y `items/{i}/retry`;
  - `UploadService.accept_file()` **sin llamar a la IA**: validar → temporal + `sha256` en *streaming* → duplicados → fila `queued` → encolar → posición;
  - los límites `QUEUE_*`.
- **Criterios de aceptación:**
  1. `POST /classification-batches` sin `camera_station_id` (también como anónimo) → 422 `CAMERA_REQUIRED`.
  2. Con `ia-fake` **detenida**, subir un archivo válido de 50 MB → **202** en menos de 3 s, con `status="queued"`, `queue.position ≥ 1` y `classification_id`.
  3. Subir un video de 16 s → según `F1-D10`, **no se rechaza**: responde **202** `queued`, se analiza hasta `15.0 s` y genera warning `VIDEO_TRUNCATED`. Para archivo `.mp4` falso o `> MAX_FILE_MB` → **200** `status="error"` (`MEDIA_UNSUPPORTED_FORMAT` / `MEDIA_TOO_LARGE`) sin encolar ni dejar temporal.
  4. Subir dos veces el mismo archivo a `CAM01` → el segundo da 200 `error` `DUPLICATE_FILE` con `context.classification_id`. Si el original está en `CAM02` → `DUPLICATE_FILE_OTHER_CAMERA` con `context.camera_station_code="CAM02"`.
  5. Renombrar el archivo y subirlo de nuevo → igual se detecta (por `sha256`).
  6. Con 500 pendientes de `ana`, `POST /classification-batches {expected_files:1}` → 429 `QUEUE_USER_LIMIT`.
  7. Con Redis detenido → 503 `QUEUE_UNAVAILABLE`, sin fila creada ni temporal.
  8. Con el disco del temporal al 86 % → 503 `QUEUE_FULL`.
  9. `GET /classification-batches?active=true` → solo los lotes del dueño en `open` o `processing`, más los terminados hace menos de 10 min, **sin** `items`.
  10. `GET /classification-batches/{id}?since=T` → solo los ítems con `updated_at > T`.
  11. `POST …/cancel` con 3 en cola y 1 en proceso → los 3 quedan `cancelled` (`CANCELLED_BY_USER`) sin temporal, y el que estaba en proceso termina normalmente.
  12. `DELETE …/items/{i}` de uno en proceso → 409 `ITEM_NOT_CANCELLABLE`.
  13. Subir de nuevo el mismo `client_index` que estaba en `error` → reemplaza el ítem (sigue habiendo uno solo con ese índice).
  14. `POST /classification-batches/{lote de luis}/files` como `ana` → 404.

### BE-61 · Worker de clasificación, cola justa y *reaper*
- **P · S:** P0 · S2–S3 · **Flujos:** FL-08, FL-09, FL-33 · **Casos:** CB-30, CB-37…CB-44
- ⛔ **Necesita:** BE-03, BE-13, BE-60; **para cerrar: la IA real (IA-13/14/15/20) y el tiempo medio de IA-17 (Diego)**
- 🔁 **Mientras tanto:** `ia-fake` (con `*_slow*` para simular demoras)  ➡️ **Desbloquea:** FE-15 (seguimiento real de la bandeja)
- **Qué hacer:** `classify_file_job` idempotente con latido; el despachador justo (`QUEUE_PER_OWNER_INFLIGHT`, *round-robin*, Lua); reintentos solo para los errores transitorios; conservar el temporal hasta el TTL si el error permite reintentar; el *reaper* FL-33; las cancelaciones en cascada (cámara borrada, cuenta desactivada, sesión borrada por el admin); la media móvil del tiempo de procesamiento.
- **Criterios de aceptación:**
  1. **Equidad:** dados 1 *worker* y `ia-fake` con 2 s por archivo, `ana` sube 50 archivos y 5 s después `luis` sube 3. Entonces los 3 de `luis` terminan antes que el archivo n.º 10 de `ana`.
  2. **Idempotencia:** ejecutar `classify_file_job(id)` dos veces seguidas → una sola fila `done` y un solo fotograma.
  3. **Caída del worker:** matar el *worker* durante un archivo (`processing`) → a los 10 min el *reaper* lo pasa a `queued`, otro *worker* lo termina y `attempts=2`. Tras 3 caídas → `error` `PROCESSING_INTERRUPTED`.
  4. **Redis reiniciado sin datos:** los ítems `queued` de la BD se re-encolan en la siguiente pasada del *reaper*.
  5. **IA caída:** con `ia-fake` detenida → 3 intentos (con *backoff*) y luego el ítem en `error` `AI_UNAVAILABLE`, con el temporal **conservado**; con `ia-fake` levantada, `POST …/retry` → `queued` → `done`.
  6. Más de 24 h en cola → `error` `PROCESSING_EXPIRED` y temporal borrado.
  7. **Asociación durante la cola:** `anon1` sube 3 archivos, hace `claim` con `ana` mientras están en cola, y al terminar las 3 filas son de `ana`.
  8. **Cascadas:** borrar `CAM01` con 5 en cola → los 5 quedan `cancelled` (`CAMERA_DELETED`); desactivar a `ana` → sus `queued` quedan `cancelled` (`ACCOUNT_DISABLED`).
  9. `queue.estimated_wait_seconds` está en ±50 % del tiempo real en la prueba del criterio 1 (con la media móvil ya calentada).
  10. Logs `queue.item.enqueued`, `.started`, `.completed` y `.failed` con `queue_wait_ms` y `processing_ms`.

### BE-22 · Fecha de captura (`captured_at`)
- **P · S:** P0 · S3 · **Casos:** CB-17, CB-18
- ⛔ **Necesita:** BE-13; **IA-20 (Diego)**: `capture` en la respuesta  🔁 **Mientras tanto:** los fixtures con `capture`
- **Qué hacer:** orden `capture` de la IA → `client_mtime` → `upload_time`; `captured_at_source`; la advertencia `CAPTURE_OUTSIDE_DEPLOYMENT` en `classifications.warnings`.
- **Criterios de aceptación:**
  1. IA con `source=filename` → se guarda tal cual.
  2. IA con `source=none` y `client_mtime` presente → `captured_at_source=client_mtime`; sin `client_mtime` → `upload_time`.
  3. Una captura del 2000-01-01 en una cámara colocada en 2026 → la fila tiene `warnings=[{code:"CAPTURE_OUTSIDE_DEPLOYMENT"}]`.

### BE-64 · Duplicados entre cámaras y deduplicación global
- **P · S:** P1 · S3 · **Casos:** CB-51, CB-52, CB-55
- ⛔ **Necesita:** BE-13
- **Criterios de aceptación:**
  1. El criterio 4 de BE-13 (`DUPLICATE_FILE_OTHER_CAMERA`), también al importar un paquete (BE-40).
  2. Dado el mismo `sha256` subido por `ana` (pública) y por `luis` (pública), entonces en `GET /admin/stats` la fauna cuenta **1** avistamiento, y en las stats de cada cámara, 1 en cada una.

### BE-28 · Procesamiento en segundo plano (opcional)
- **P · S:** P2 · — · Reemplazado por la cola de BE-60/61. No se implementa.

---

## Épica 4 · Clasificaciones, validación y catálogo (S3–S4)

### BE-16 · Listado y gestión de clasificaciones
- **P · S:** P0 · S3
- ⛔ **Necesita:** BE-04, BE-23  ➡️ **Desbloquea:** FE-24
- **Qué hacer:** `GET /classifications` con **todos** los filtros de API §8.1; `GET`, `PATCH` (mover a otra cámara propia) y `DELETE` por ID; `?include=validation_history`.
- **Criterios de aceptación:**
  1. Cada filtro de API §8.1 tiene su test (por ejemplo, `category=animal,person` devuelve solo esas dos; `taxon=<label del género Panthera>` devuelve las de *Panthera onca* y las que quedaron solo en *Panthera*).
  2. `status` por defecto es `done`: las `queued`, `processing` y `error` no aparecen salvo que se pidan.
  3. `PATCH {camera_station_id: CAM02}` sobre una de `CAM01` → se mueve; si `CAM02` ya tiene ese `sha256` → 409 `DUPLICATE_FILE`.
  4. `sort=confidence` ordena de menor a mayor confianza (para la cola de validación).

### BE-25 · Catálogo de especies
- **P · S:** P1 · S3
- ⛔ **Necesita:** **IA-19 (✅ listo: `speciesnet_catalog.json` con 3538 taxones y `GET /api/v1/catalog` con `ETag`)**  🔁 **Mientras tanto:** `speciesnet_catalog.sample.json` (558 taxones)
- ➡️ **Desbloquea:** FE-25
- **Qué hacer:** carga/sincronización en memoria con índice normalizado (sin tildes, en minúsculas) y API §9, orden exacta → prefijo → contiene → `rank` (`common_name` viene en inglés por defecto desde la IA).
- **Criterios de aceptación:**
  1. `q=jag` → la primera coincidencia es *Panthera onca* (jaguar); `q=tapír` y `q=tapir` dan el mismo resultado.
  2. `q=pant&rank=genus` → solo devuelve géneros.
  3. p95 menor a 50 ms para 1000 consultas aleatorias (*benchmark* en CI).
  4. `q=j` (1 carácter) → 422 `VALIDATION_ERROR`.

### BE-10 · Validación individual
- **P · S:** P0 · S3 · **Flujos:** FL-10 · **Casos:** CB-61…CB-67
- ⛔ **Necesita:** BE-04, BE-25  ➡️ **Desbloquea:** FE-25
- **Qué hacer:** `PUT /classifications/{id}/validation` (API §8.6) con `confirm`, `correct` (`alternative` o `catalog`), `correct_unlisted`, `reject`, `discard_repeat` y `reset`; `validation_history`.
- **Criterios de aceptación:**
  1. `confirm` → `validation.status=confirmed`, `validated_by` y `validated_at` poblados, y una entrada nueva en `validation_history`.
  2. `correct` con `correction_source=alternative` y un `label_id` que **no** está en `alternatives` → 422 `VALIDATION_ERROR`.
  3. `correct` con `correction_source=catalog` y un `label_id` de *Puma concolor* → `corrected_taxonomy` = la del catálogo (familia incluida), `effective_taxonomy` = puma; `/stats` cuenta un puma y ya no un jaguar.
  4. `correct` sobre una fila con `category=blank` → pasa a `category=animal`.
  5. `correct_unlisted` con `suggested_name="Leopardus colocolo"` y el `label_id` del género *Leopardus* → `status=corrected_unlisted`, cuenta en `by_genus[leopardus]` y no en `by_species`. Sin `label_id` → cuenta en `unidentified_to_species.unlisted`.
  6. `correct_unlisted` con un `label_id` de `rank=species` → 422 (debe ser un taxón superior).
  7. `reject` → deja de contar en `sightings` y cuenta en `totals.rejected`.
  8. `reset` → vuelve a `unvalidated` y a contar como antes.
  9. Sobre una fila `queued` → 409 `CLASSIFICATION_NOT_DONE`.
  10. `anon1` valida su clasificación, hace `claim` con `ana`, y la validación se conserva.

### BE-24 · Validación en lote
- **P · S:** P1 · S3
- ⛔ **Necesita:** BE-10  ➡️ **Desbloquea:** FE-25 (lote)
- **Criterios de aceptación:**
  1. 48 IDs propios + 2 de `luis` con `action=confirm` → `{updated:48, skipped:[2 × CLASSIFICATION_NOT_FOUND]}`.
  2. 501 IDs → 422.
  3. `action=correct` → 422 (solo se admiten `confirm`, `reject` y `reset`).

### BE-66 · Ráfagas (registros repetidos)
- **P · S:** P1 · S4 · **Flujos:** FL-16 · **Casos:** CB-60…CB-60d
- ⛔ **Necesita:** BE-10, BE-16, BE-22  ➡️ **Desbloquea:** FE-18
- **Qué hacer:** API §8.8: `burst-candidates` (*window functions*), `repeat-batch`, `dismiss`; `discard_repeat` en BE-10; `discarded_repeat` en las stats y el Excel, excluido de `model_feedback`.
- **Criterios de aceptación:**
  1. Dadas 3 fotos de jaguar en `CAM01` a las 04:22:10, 04:22:31 y 04:23:02, y un puma a las 04:22:40, con `window_minutes=5`, entonces hay **un** grupo de 3 jaguares (sin el puma) y `suggested_keep_id` = el de mayor confianza.
  2. Con `window_minutes=0.25` (15 s) → no se forma ningún grupo con esas 3 (salvo si dos están a menos de 15 s).
  3. `repeat-batch {keep_ids:[k1], discard_ids:[k2,k3]}` → `/stats` pasa de 3 a 1 jaguar, `totals.discarded_repeat=2`, y k2 y k3 tienen `repeat_of=k1`.
  4. `reset` sobre k2 → vuelven a contarse 2.
  5. `repeat-batch` con `keep_ids=[]` → 422 `REPEAT_KEEP_REQUIRED`; con IDs de dos cámaras distintas → 422 `REPEAT_MIXED_CAMERAS`.
  6. `dismiss` → el grupo no vuelve a aparecer en `burst-candidates` (salvo con `include_reviewed=true`).
  7. Los archivos con `captured_at_source=upload_time` nunca forman grupos.
  8. `model_feedback` no cambia al descartar repetidos.

---

## Épica 5 · Estadísticas y reportes (S3–S5)

### BE-09 · `StatsService` y `/stats`
- **P · S:** P0 · S3 (obligatorias) / P1 · S4 (complementarias) · **Flujos:** FL-11
- ⛔ **Necesita:** BE-04, BE-23  ➡️ **Desbloquea:** **FE-26, FE-33**; BE-26, BE-26b, BE-53
- **Qué hacer:** `GET /camera-stations/{id}/stats` y `/projects/{id}/stats` con la respuesta **exacta** de API §10.2 y **todas** las reglas de §10.3; un único `StatsService.compute(scope, filters, sections, viewer)`; agregaciones en SQL.
- **Dataset fijo de pruebas** (`tests/fixtures/stats_dataset.py`): 2 cámaras, 20 clasificaciones con especie, género, familia, `blank`, `person`, `rejected`, `discarded_repeat`, borradas y `queued`, y fechas en 2 meses y varias horas. **Las cifras esperadas se escriben a mano en el test.**
- **Criterios de aceptación:**
  1. Con el dataset fijo, **cada** número de la respuesta coincide con el esperado (test por sección: `totals`, `richness`, `non_animal`, `by_species`, `by_genus`, `by_family`, `unidentified_to_species`, `by_camera`, `by_month`, `by_hour` y `effort`).
  2. **Cierre:** `Σ by_species.count + Σ unidentified_to_species.* = totals.sightings`.
  3. `/projects/P1/stats` = la suma de `/camera-stations/CAM01/stats` y `/CAM02/stats` en `totals.sightings` y en cada especie.
  4. Las filas `rejected`, `discarded_repeat`, borradas, `queued`, `processing` y `cancelled` no cuentan como avistamiento.
  5. `only_validated=true` → solo cuentan `confirmed`, `corrected` y `corrected_unlisted`.
  6. `from` y `to` filtran por `captured_at`; `by_month` y `by_hour` excluyen `upload_time`.
  7. `luis` sobre `P1` (público, con CAM01 privada) → solo suma CAM02.
  8. `sections=totals` → la respuesta solo trae `totals` (y el encabezado).
  9. Con 10 000 clasificaciones → menos de 500 ms (*benchmark* *manual*, documentado).

### BE-26 · Excel
- **P · S:** P0 · S4 · **Flujos:** FL-12
- ⛔ **Necesita:** BE-09  ➡️ **Desbloquea:** FE-07 (Excel)
- **Qué hacer:** `GET /reports/excel` (API §11) con las hojas y columnas **aprobadas** de API §11 (incluidas "Cuenta como avistamiento" y "Repetido de"), coordenadas redondeadas si quien descarga no es el dueño, openpyxl en `to_thread` y `write_only` para *Clasificaciones*.
- **Criterios de aceptación:**
  1. El archivo empieza con los *magic bytes* `PK` y abre con `openpyxl.load_workbook` en el test; *manual:* abre en Excel y en LibreOffice.
  2. La hoja *Resumen* tiene los mismos `totals` que `/stats` con los mismos filtros (test).
  3. *Por especie*, *Por género* y *Por familia* coinciden fila por fila con `by_species`, `by_genus` y `by_family`.
  4. *Clasificaciones* tiene una fila por clasificación `done` del alcance, con las columnas en el orden de API §11.
  5. Descargado por `luis` (público de `ana`) → latitud y longitud con 2 decimales.
  6. Sin datos con los filtros → 404 `REPORT_EMPTY` (JSON).
  7. 10 000 filas → se genera en menos de 15 s y con menos de 300 MB de memoria.

### BE-26b · PDF
- **P · S:** P0 · S5
- ⛔ **Necesita:** BE-09, BE-26  ➡️ **Desbloquea:** FE-07 (PDF)
- **Qué hacer:** ReportLab + matplotlib (`Agg`); portada, totales, gráficos de las 15 con más avistamientos por especie, género y familia, tablas; `request_id` y página en el pie.
- **Criterios de aceptación:**
  1. Los *magic bytes* son `%PDF`.
  2. El texto extraído (con `pypdf`) contiene los mismos `totals.sightings` y el primer puesto de `by_species` que `/stats`.
  3. *Manual:* se ve bien en A4, los gráficos son legibles y hay acentos y ñ correctos.

### BE-12 · Eliminar los indicadores y VisualCrossing
- **P · S:** P1 · S3
- **Criterios de aceptación:**
  1. `grep -Ri "visualcrossing\|indicator\|weckel\|rai_" app/` → 0.
  2. El back arranca sin ninguna clave de clima.

---

## Épica 6 · Importación desde escritorio (S5)

### BE-40 · Importar paquetes `.wwm.zip`
- **P · S:** P1 · S5 · **Flujos:** FL-23 · **Casos:** CB-55, CB-80…CB-87
- ⛔ **Necesita:** BE-13, BE-25, BE-63; **IA-21 (`package.py` + `package_validator.py`) y DS-17 (`make_sample_packages.py`) — ✅ listos en `ia-clasificacion-fauna`**
- 🔁 **Mientras tanto:** `sample.wwm.zip` + paquetes inválidos reales  ➡️ **Desbloquea:** FE-32
- **Qué hacer:**
  - API §12: la vista previa (con `camera_station_id` **o** `create_camera=true`), `confirm` (con `camera` opcional), `DELETE` y `GET`;
  - todas las validaciones de PKG §5 (incluyendo `LINE_INVALID`, `EVIDENCE_MISSING` y `evidence` obligatorio solo en `category == animal` por `F2-D2`/`F2-D9`);
  - `camera_from_package` y `matching_camera_station_id`;
  - la confirmación en una transacción (crea la cámara si corresponde e inserta en bloques), reutilizando el guardado de BE-04 y BE-05, con `source=desktop`.

  Para paquetes grandes, la confirmación va a la cola (CB-85).
- **Criterios de aceptación:**
  1. `sample.wwm.zip` en `CAM01` → la vista previa tiene los `counts` exactos del manifiesto y `issues=[]`; la confirmación crea N filas `source=desktop` (`person`/`vehicle` sin evidencia por `F2-D2`), con fotograma en `animal`, `family` y `evidence_timestamp_seconds`.
  2. El mismo paquete de nuevo → 409 `IMPORT_ALREADY_IMPORTED` con `context.import_id`.
  3. Paquetes inválidos: zip slip / línea malformada → `IMPORT_INVALID_PACKAGE` / `LINE_INVALID`; checksum → `IMPORT_CHECKSUM_MISMATCH`; versión 2.0 → `IMPORT_UNSUPPORTED_VERSION`; JPG corrupto o faltante en `animal` → *issue* `EVIDENCE_INVALID` / `EVIDENCE_MISSING` en esa línea (el resto se importa); taxón inexistente → `CATALOG_TAXON_NOT_FOUND`; sin manifest → `IMPORT_INVALID_PACKAGE`.
  4. Un paquete de 201 MB → 413 `IMPORT_TOO_LARGE`.
  5. **Crear la cámara:** con `create_camera=true` y `manifest.camera` completo → la confirmación crea una cámara **privada** con esos datos y luego importa; si falta la latitud y no llega `camera` → 422 `VALIDATION_ERROR`; con `camera.latitude` → la crea.
  6. Un `manifest.camera.code` igual a una cámara propia → `matching_camera_station_id` poblado.
  7. Confirmar después de 61 min → 410 `IMPORT_PREVIEW_EXPIRED`.
  8. Una línea con un archivo que ya está en la cámara (subido por la web) → cuenta en `duplicates` y no se duplica.
  9. Test de igualdad de `package.py` con el de Diego.

---

## Épica 7 · Recuperación de contraseña y administración (S3–S4)

### BE-62 · Recuperación de contraseña con Resend
- **P · S:** P1 · S4 · **Flujos:** FL-14 · **Casos:** CB-73…CB-78
- ⛔ **Necesita:** BE-14, BE-60; para la prueba real, **SEC-12 (Diego): la cuenta de Resend y el dominio verificado**
- 🔁 **Mientras tanto:** `EMAIL_PROVIDER=console` (escribe el correo en el log de desarrollo, con el enlace)  ➡️ **Desbloquea:** FE-16
- **Qué hacer:** API §2.8–2.10 y el enlace manual del admin (§13.7); `EmailProvider` (`resend`, `console`, *stub* `smtp`); plantillas en español; límites en Redis; `send_email_job`; `email_log`; topes `EMAIL_DAILY_CAP` y `EMAIL_MONTHLY_CAP`.
- **Criterios de aceptación:**
  1. `forgot` con un correo existente y con uno inexistente → la **misma** respuesta 200; la diferencia de tiempo entre ambos es menor a 50 ms (medido en 20 ejecuciones).
  2. Un correo existente → se encola **un** envío y se crea un token (hash en la BD, vence en 30 min).
  3. Un cuarto pedido en 1 h para el mismo correo → la misma respuesta 200, pero **no** se encola nada (`email_log.status=skipped_limit`).
  4. Con `EMAIL_DAILY_CAP=3` y 3 envíos hoy → 503 `EMAIL_TEMPORARILY_UNAVAILABLE` para **cualquier** correo.
  5. `validate` con un token válido → `valid:true` y `email_hint` enmascarado; vencido o usado → `valid:false`.
  6. `reset` con un token válido → cambia la contraseña, el token queda usado y todos los *refresh tokens* revocados; reusar el token → 400 `AUTH_RESET_TOKEN_INVALID`.
  7. Pedir dos enlaces seguidos → el primero deja de servir.
  8. Resend responde 429 → 2 reintentos y luego `email_log.status=failed` (con Resend simulado).
  9. Una cuenta desactivada → la misma respuesta genérica, y no se envía nada.
  10. Ningún log contiene el correo completo ni el token.
  11. `POST /admin/users/{id}/password-reset-link` → devuelve `reset_url` y queda en `admin_audit_log`.

### BE-50 · Rol de admin y CLI
- **P · S:** P1 · S3
- ⛔ **Necesita:** BE-02, BE-14  ➡️ **Desbloquea:** todo `/admin/*`, FE-60
- **Qué hacer:** `users.role`, `require_role("admin")`, el CLI `create-admin --email` (falla si ya existe un admin; crea la cuenta con `must_change_password=true`), `reset-admin-password` y `transfer-admin --to`.
- **Criterios de aceptación:**
  1. `create-admin` con un admin existente → termina con código ≠ 0 y un mensaje claro.
  2. El primer login del admin nuevo → 403 `PASSWORD_CHANGE_REQUIRED`; solo funciona `POST /auth/me/password`, y después todo lo demás.
  3. `POST /auth/register` con `"role":"admin"` en el body → se crea con `role=user`.
  4. `ana` en cualquier `/admin/*` → 403 `ADMIN_REQUIRED`.

### BE-52 · `AdminScope` (privacidad del admin)
- **P · S:** P1 · S3 · **Casos:** CB-96
- ⛔ **Necesita:** BE-23, BE-50
- **Qué hacer:** un filtro único `admin_visible` (públicas de usuarios + anónimas, sin privadas); los conteos de lo privado por consultas `COUNT(*)` separadas; coordenadas redondeadas para las públicas de usuarios y exactas para las anónimas.
- **Criterios de aceptación:**
  1. Para **cada** endpoint `/admin/*`, el admin pidiendo un recurso privado de `ana` (cámara, clasificación, fotograma) → 404, y ningún listado ni estadística de fauna incluye sus datos.
  2. `GET /admin/stats` → `content.camera_stations.private` = el número real de cámaras privadas, pero ningún dato de ellas en `fauna` ni en `fauna_map`.
  3. Las coordenadas de `CAM02` (pública de `ana`) para el admin → 2 decimales; las de una cámara anónima → exactas.

### BE-53 · `GET /admin/stats` y Excel de admin
- **P · S:** P1 · S4 · **Flujos:** FL-40
- ⛔ **Necesita:** BE-09, BE-52, BE-64, BE-65  ➡️ **Desbloquea:** FE-60 (Resumen y Fauna)
- **Criterios de aceptación:**
  1. La respuesta tiene la forma exacta de API §13.1.
  2. `users`, `anon_sessions` y `content` cuadran con conteos directos en la BD (test).
  3. `fauna` = `StatsService` con `AdminScope` y la deduplicación por `sha256`.
  4. `anon_retention.purged` = la suma de `anon_purge_runs`.
  5. `GET /admin/reports/excel` → las hojas *Plataforma*, *Fauna por especie*, *Por género*, *Por familia*, *Clasificaciones* (solo anónimas y públicas) y *Sugerencias*; queda en la auditoría.

### BE-54 · Exploración del admin
- **P · S:** P1 · S4 · **Flujos:** FL-41
- ⛔ **Necesita:** BE-52  ➡️ **Desbloquea:** FE-60 (Explorar, Sesiones anónimas)
- **Criterios de aceptación:**
  1. `GET /admin/classifications?scope=anonymous` → solo las anónimas; `scope=public` → solo las públicas de usuarios; nunca las privadas.
  2. `owner.display_name` de una anónima = `"Anónimo #xxxx"` (los 4 primeros caracteres del hash), sin IP.
  3. `include_deleted=true` → incluye las borradas con `is_deleted`, `deleted_at` y `deleted_reason`.

### BE-55 · Borrado lógico unificado y restauración
- **P · S:** P1 · S4 · **Flujos:** FL-42 · **Casos:** CB-97
- ⛔ **Necesita:** BE-27, BE-50  ➡️ **Desbloquea:** FE-60 (borrar y restaurar)
- **Criterios de aceptación:**
  1. El admin borra la sesión `anon1` (con 1 cámara y 8 clasificaciones) → las 9 entidades quedan `is_deleted`, con el **mismo** `deleted_at` y `deleted_by=admin`; la respuesta trae `{deleted:{classifications:8, camera_stations:1, projects:0}}`.
  2. Restaurarla → vuelven solo esas 9, no otras que se hubieran borrado antes por separado.
  3. Sin `reason` → 422 `DELETE_REASON_REQUIRED`. Borrar algo ya borrado → 409 `ENTITY_ALREADY_DELETED`.
  4. Lo borrado no aparece en listados, `/stats` ni el Excel, ni para el usuario ni para el admin, salvo con `include_deleted`.
  5. Borrar una sesión con ítems en cola → los `queued` quedan `cancelled`.

### BE-56 · Gestión de usuarios
- **P · S:** P1 · S4 · **Flujos:** FL-43 · **Casos:** CB-44, CB-98
- ⛔ **Necesita:** BE-50, BE-61 (cancelación en cascada)  ➡️ **Desbloquea:** FE-60 (Usuarios)
- **Criterios de aceptación:**
  1. `GET /admin/users` → cada usuario con los `counts` de API §13.7, sin datos de su contenido privado.
  2. Desactivar a `ana` → no puede hacer login (`ACCOUNT_DISABLED`), sus *refresh tokens* quedan revocados, su contenido público deja de listarse y sus ítems en cola quedan `cancelled`.
  3. El admin desactivándose a sí mismo → 409 `CANNOT_DEACTIVATE_SELF`.
  4. Reactivar → vuelve todo menos los ítems cancelados.

### BE-57 · Auditoría
- **P · S:** P1 · S4
- ⛔ **Necesita:** BE-50
- **Criterios de aceptación:**
  1. Cada acción de admin (borrar, restaurar, desactivar, reactivar, cambiar configuración, exportar, generar enlace) crea **una** fila en `admin_audit_log` en la misma transacción. Si la acción falla, no queda fila.
  2. No existe ningún endpoint ni servicio que haga `UPDATE` o `DELETE` sobre `admin_audit_log` (`grep`).
  3. `GET /admin/audit-log?action=update_setting` filtra correctamente.

### BE-65 · Monitor de la cola, desempeño del modelo y sugerencias
- **P · S:** P1 · S4 · **Flujos:** FL-45, FL-46
- ⛔ **Necesita:** BE-61, BE-10, BE-52, BE-62 (contadores de correo)  ➡️ **Desbloquea:** FE-60 (Cola, Modelo)
- **Criterios de aceptación:**
  1. `GET /admin/queue` con 3 en cola de `ana` y 2 de `anon1` → `queued=5` y `by_owner` con ambos; `email` con los contadores del día y del mes.
  2. `model_feedback` con un dataset fijo de validaciones → los porcentajes esperados (escritos a mano), sin contar `discarded_repeat`.
  3. `top_confusions` lista "Puma concolor → Panthera onca" si es la corrección más frecuente.
  4. `unlisted-suggestions` agrupa "Leopardus colocolo", "leopardus colocolo " y "Leopardus Colocolo" en **una** fila con `count=3`.

---

## Épica 8 · Seguridad, calidad y salud (S4–S5)

| ID | Tarea | P · S | Criterios de aceptación |
|---|---|---|---|
| BE-29 | `GET /health` y `/health/ready` (API §4.2: BD, Redis, IA, storage) | P1 · S4 | Cada dependencia caída se refleja con un 503 en `/ready`; `/health` sigue en 200. Lo usa el *healthcheck* de Docker. |
| BE-30 | Secretos solo por `.env` | P0 · S1 | Cubierto por STD-07; `gitleaks` en CI sin hallazgos. |
| BE-31 | *Rate limiting* con Redis: login y registro 10/min por IP (5 para el admin); `POST /anon-sessions` 5/h por IP; `/files` 60/min por dueño; `/catalog` 120/min por IP; `/auth/password/forgot` según BE-62 | P1 · S4 | Un test por límite → 429 `RATE_LIMITED` con el header `Retry-After`. |
| BE-32 | Límite del *body* (`MAX_FILE_MB` + 1 MB; importación `IMPORT_MAX_MB`), cabeceras `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Permissions-Policy`, CORS solo para `FRONTEND_URL` | P1 · S4 | Un body mayor → 413; un `Origin` distinto → sin cabeceras CORS. |
| BE-33 | Sin *stack traces* en producción | P1 · S4 | Cubierto por STD-03, criterio 3. |
| BE-34 | Sin `echo=True` en producción | P2 · S4 | Cubierto por STD-05. |
| BE-35 | **Suite por flujo y por caso borde:** un test por flujo FL-01…FL-46, por cada CB-xx del back y por cada código de error; IA simulada con `ia-fake` o los fixtures; cobertura de `services/` ≥ 70 % | P0 · S5 | El reporte de cobertura en CI; una tabla `tests/TRAZABILIDAD.md` con FL o CB → nombre del test. |
| BE-36 | Limpieza del repo (`scratch/`, `koyeb.yml`, `digitalocean.yaml` si no se usan, `.mp4` en `uploads/`, `__pycache__`) | P2 · S4 | `git ls-files` sin esos archivos. |
| BE-37 | Corregir `BACKLOG_TECNICO.md` (IMP-02 e IMP-03 no existen en la IA) | P2 · S1 | — |

---

## Orden sugerido

```
S1: BE-51 (día 1) → STD-07 → STD-01 → STD-03 → BE-14 → BE-02 → BE-07 → BE-03 (con fixtures)
S2: STD-04/05 → BE-11 (+FE-09, mismo día) → BE-27 (esquema) → BE-60 (+ia-fake) → BE-01 → BE-15 → BE-23 → BE-08
    → BE-04 → BE-05 → BE-21 → BE-13 → BE-61 (base) → BE-20 → BE-06 → STD-06/08
    ═══ H2: front en /api/v1, sesión, cámaras, proyectos, cola con ia-fake ═══
S3: BE-27 (final) → BE-61 (con la IA real) → BE-22 → BE-16 → BE-63 → BE-64 → BE-25 → BE-10 → BE-24
    → BE-09 (obligatorias) → BE-12 → BE-50 → BE-52 → BE-58
    ═══ H3: clasificar y validar con la IA real ═══
S4: BE-26 → BE-09 (complementarias) → BE-66 → BE-62 → BE-53 → BE-54 → BE-55 → BE-56 → BE-57 → BE-65 → BE-29 → BE-31…36
    ═══ H4: estadísticas, Excel, ráfagas, recuperación, APIs de admin ═══
S5: BE-26b → BE-40 → BE-35 → DEP-01
    ═══ H5: completo y dockerizado ═══
```

**Lo que Job necesita de los demás:** ver [DEPENDENCIAS §4 y §5](DEPENDENCIAS.md#4-matriz-el-back-necesita-de-la-ia-y-del-escritorio). Lo más importante:

| Necesita | De | Para | Cuándo |
|---|---|---|---|
| `contract.py` + fixtures + **`ia-fake`** + catálogo de muestra (`558`) | Diego (IA-21, IA-22) | BE-03, BE-04, BE-60 | ✅ **Listo** |
| Paquetes de prueba `.wwm.zip` (válido + inválidos) | Diego (IA-21 / `make_sample_packages.py`) | BE-40 | ✅ **Listo** |
| Muestras de formatos adicionales (`heic/tif/mts`) | Diego (IA-16) | BE-21 ampliado | ⏳ **Pendiente `IA-16`** |
| IA real con una respuesta por archivo (`contract.py` final) | Diego (IA-13/14/15/20) | Cerrar BE-04, BE-22, BE-61 | ✅ **Listo** |
| `speciesnet_catalog.json` completo (`3538` taxones) | Diego (IA-19) | Cerrar BE-25 | ✅ **Listo** |
| Cuenta de Resend + dominio verificado | Diego (SEC-12) | Prueba real de BE-62 | S4–S6 |
| Cambio de rutas del front el mismo día | Miguel (FE-09) | BE-11 | S2 |
