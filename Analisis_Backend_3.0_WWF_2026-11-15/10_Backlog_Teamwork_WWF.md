---
title: "10 - Backlog Ejecutivo Ajustado para Teamwork (M0–M4)"
date: 2026-11-20
project: BACKWWF
version: "1.2.0 TDR (Ajustado, contrato IA 1.0.0)"
tags: [teamwork, backlog, hu, bug, spike, ponytail, docker, env, wwf]
---

# 10. Backlog de Ejecución en Teamwork (`BACKWWF` — Proceso Ajustado)

> [!NOTE]
> Matriz de riesgos: [[09_Matriz_Flujos_y_Casos_Borde]] | DoD único: [[DEFINITION_OF_DONE]] | To-Do `/teamwork`: [[11_Teamwork_Todolist_WWF]] | Rutina con agentes: [[12_Guia_Rutina_Implementacion_con_Agentes]]

**Reglas del proceso ajustado:**
1. **Un solo DoD:** Todos los tickets enlazan `[[DEFINITION_OF_DONE]]` (sin duplicar checklists).
2. **Walking Skeleton IA en M0 (`SPIKE-01`):** Llamada real a `POST /detect` antes de construir cola, storage y esquema canónico.
3. **Criterios de Aceptación:** Gherkin **exclusivo** para seguridad, privacidad e integridad crítica; el resto en lista de 1 línea. Sin estimación en horas por UT.
4. **Revisión selectiva:** Diego revisa obligatoriamente tickets marcados `Revisión obligatoria: Diego` (seguridad, privacidad DD-17, contrato IA). El resto se fusiona con CI verde + revisión asíncrona.
5. **Desbloqueo paralelo a Front:** Avisar a Miguel **al abrir el PR** (no al cerrarlo) cuando exista `Desbloquea Front`.

## Contexto de Entorno e Infraestructura para Agentes

Antes de ejecutar cualquier ticket, todo agente debe operar sobre la topología real de desarrollo y respetar la separación de entornos:

1. **Contenedores Docker en ejecución (`development`):**
   - `fauna_api` (`fauna-monitoring-api:local`): API FastAPI en `0.0.0.0:8000->8000/tcp` con `--reload`.
   - **Servicio IA (`../ia-clasificacion-fauna`):** API real o **`ia-fake`** en puerto **`8001`** (`http://ia:8001` en compose / `http://host.docker.internal:8001` desde `fauna_api`; header `X-API-Key: dev-key` en desarrollo y `AI_API_KEY` obligatoria en producción). **El contenedor viejo `wwf-wildlife-api:8081` no cumple el contrato v1.0.0 y no sirve como evidencia de ningún ticket**; se apaga al terminar `SPIKE-01`.
   - PostgreSQL `faunadb` en el host Windows en el puerto `5433` (accesible desde `fauna_api` vía `host.docker.internal:5433/faunadb`).
2. **Inicialización del esquema en Docker (desde `HU-02`, 20/11/2026):**
   - El esquema lo crea **solo Alembic**: `docker compose exec -T api alembic upgrade head` (la imagen incluye `alembic.ini` y `migrations/`). Ya no existen `Base.metadata.create_all`, `seed_db.py` ni `seed_massive.py`.
   - Tablas esperadas en `pg_tables` (14 + `alembic_version`): `users`, `refresh_tokens`, `password_reset_tokens`, `anon_sessions`, `camera_stations`, `projects`, `project_camera_stations`, `classification_batches`, `classifications`, `desktop_imports`, `admin_audit_log`, `system_settings`, `anon_purge_runs`, `email_log`. Las 10 tablas legadas (`species`, `videos`, `media_files`, `individuals`, `reports`, `project_stations`…) las borra la migración `0001`.
   - **Sin datos de prueba** hasta `HU-16` (`app/cli.py seed-e2e`). Mientras tanto, cada ticket crea sus datos en los tests.
   - `0001` es destructiva (borra las tablas legadas). Todavía no hay base de producción: cuando se elija dónde vive, se hace un respaldo antes de migrar. Las migraciones siguientes (`0002`…) son aditivas.
3. **Dos configuraciones independientes por variables de entorno (`development` vs `production`):**
   - El código fuente es **uno solo** (`app/core/config.py`), pero lee configuraciones y credenciales **distintas por entorno** desde variables de entorno (`.env` local no versionado en `development`; secretos encriptados del PaaS en `production`).
   - Nunca se reutilizan credenciales de producción en desarrollo ni se hardcodean secretos, contraseñas o API keys en código, scripts o manifiestos (`docker-compose.yml`, `check_db.py`). No hay manifiestos de una plataforma de producción (D1): el cliente elige dónde desplegar al cerrar el proyecto.

---

## Contrato IA vigente (referencia única para todas las HU)

> [!IMPORTANT]
> **Orden de precedencia cuando dos fuentes se contradicen:**
> 1. Código de `../ia-clasificacion-fauna` (`wwm_pipeline/contract.py`, `enums.py`, `formats.py`, `package.py`, `package_validator.py`, `api/errors.py`, `api/routes.py`) y su `README.md` / `fake/README.md`.
> 2. Esta sección.
> 3. `tareas-job/contratos/API_IA_BACK.md` y `PAQUETE_ESCRITORIO.md` (v2, 19/11).
> 4. El resto de `tareas-job/` (`ESTANDARES_BACKEND_IA.md`, `CASOS_BORDE.md`, `TAREAS_BACKEND.md`…), que se redactó contra la IA antigua y conserva desvíos (ver "Desvíos conocidos").
>
> `tareas-job/` no se edita (es referencia normativa); cuando contradice al nivel 1 o 2, **prevalece lo de arriba** y el desvío se anota aquí.

**Versión de referencia:** `CONTRACT_VERSION = "1.0.0"` · `ia-clasificacion-fauna@cdf3292` (20/11/2026) · licencia del contrato: MIT (`LICENSE-CONTRATO-MIT.txt`).

### Conexión
| Tema | Valor |
|---|---|
| Variables del back | `AI_SERVICE_URL` (sin `/api/v1`; dev `http://host.docker.internal:8001`, compose `http://ia:8001`), `AI_API_KEY` (`dev-key` en dev; obligatoria en prod), `AI_TIMEOUT_SECONDS` = `180`. **No** se agrega `AI_BASE_URL`: el código usa `AI_SERVICE_URL` y `Settings` ignora la sobrante. |
| Petición | `POST {AI_SERVICE_URL}/api/v1/detect`, `multipart/form-data` con `file` y `file_name` (+ `client_mtime` opcional). Headers `X-API-Key`, `X-Request-ID`, `X-Flow`. |
| Tiempos | La IA corta a 150 s (`504 IA_PROCESSING_TIMEOUT`); el back espera 180 s. |
| Respuesta | Envoltura `{status, data, message, error, meta}`; `data` = `DetectResult` estricto (`extra="forbid"` en todo, `ModelInfo` sin `geofence`). |

### Comportamientos de la IA que el back debe respetar
| Tema | Regla (verificada en código) | HU afectadas |
|---|---|---|
| Duración (`F1-D10`) | Ningún video se rechaza por duración. Pasados 15 s **+ 0,5 s de tolerancia** (`sampling.DURATION_TOLERANCE_SECONDS`) se analiza hasta 15 s y llega `analysis.truncated_at_seconds = 15.0` → warning `VIDEO_TRUNCATED`. `IA_DURATION_EXCEEDED` ya no se emite. | HU-08, HU-11, HU-12 |
| Baja evidencia | `analysis.low_evidence = true` cuando hubo un solo voto de fauna con peso < 0,25 (`config.min_single_vote`). Se guarda y se expone. | HU-02, HU-11, HU-12 |
| Alternativas | Máx. 3, `score > 0,005`; vacías si `category != animal`. | HU-11, HU-12 |
| Evidencia web | `animal`, `person` y `vehicle` traen `evidence` (JPEG ≤ 960 px); `blank` no. En imágenes `frame_index = 0` y `timestamp_seconds = 0`. | HU-11 |
| Evidencia en paquete (`F2-D2`/`F2-D9`) | Solo `animal` lleva `evidence`; `person`/`vehicle` llegan con `evidence: null`. Códigos por línea: `LINE_INVALID`, `EVIDENCE_INVALID`, `EVIDENCE_MISSING`, `CATALOG_TAXON_NOT_FOUND`. | HU-10 |
| Formatos (`formats.py`) | Imagen: `jpg jpeg png bmp webp tiff`. Video: `mp4 avi mov mkv wmv flv webm`. Se valida extensión **y** firma (familia imagen/video). `heic/heif`, `tif`, `m4v`, `3gp`, `mts`, `m2ts` → `IA-16` (no aceptar aún). | HU-03, HU-08 |
| Límites | 300 MB por archivo; imagen ≤ 100 MP (`too_many_pixels`). | HU-03, HU-08 |
| Catálogo | `GET /api/v1/catalog` con `X-API-Key`, 3538 taxones, `ETag` = sha256, `304` con `If-None-Match`. Fixture `sample` = 558. `common_name` en **inglés**. | HU-10, HU-12, HU-13 |
| Salud | `GET /api/v1/health` sin clave ni envoltura: `200 ok` / `503 loading · models_missing · error`; `config.max_file_mb = 300`. | HU-03 |

### Traducción de errores IA → back (canónica)
`ai_client` traduce **en el borde** y nunca inventa datos (DD-4). El reintento lo decide quien aparece en la columna "Reintenta".

| IA (HTTP · código) | Código del back | Reintenta | Nota |
|---|---|---|---|
| `400 IA_INVALID_FORMAT` (falta `file`/`file_name`) | `AI_BAD_RESPONSE` | No | Bug de nuestro cliente, no del usuario: log `ERROR ai.request.rejected` con `context.errors`. No se crea `AI_BAD_REQUEST` (no está en el catálogo). ⚠️ Pendiente de confirmar con Diego. |
| `401 IA_UNAUTHORIZED` | `AI_UNAVAILABLE` | No | Log `CRITICAL ai.unauthorized` (clave desalineada). |
| `413 IA_FILE_TOO_LARGE` | `MEDIA_TOO_LARGE` | No | |
| `415 IA_INVALID_FORMAT` | `MEDIA_UNSUPPORTED_FORMAT` | No | El mapeo mira el **HTTP**, no solo el código: `400` y `415` comparten `IA_INVALID_FORMAT`. |
| `422 IA_DECODE_FAILED` con `reason = too_many_pixels` | `MEDIA_TOO_LARGE` | No | |
| `422 IA_DECODE_FAILED` (otro) | `MEDIA_DECODE_FAILED` | No | |
| `500 IA_INTERNAL` | `AI_BAD_RESPONSE` | **Cliente: 1 vez** | README IA: "Sí, una vez". |
| `503 IA_MODEL_NOT_READY` | `AI_NOT_READY` | Worker (5 s / 30 s) | ⚠️ Pendiente con Diego: README dice "sí, en unos segundos"; `tareas-job` no lo reintentaba. |
| `503 IA_BUSY` | `AI_UNAVAILABLE` tras agotar | Worker (5 s / 30 s) | `CB-37`. |
| `504 IA_PROCESSING_TIMEOUT` / `httpx.TimeoutException` | `AI_TIMEOUT` | Worker (5 s / 30 s) | `CB-37`. |
| Conexión / DNS | `AI_UNAVAILABLE` | Worker (5 s / 30 s) | `CB-37`. |
| `200` fuera de contrato, cuerpo no-JSON o código `IA_*` desconocido | `AI_BAD_RESPONSE` | No | Log `ERROR` con las **claves** recibidas, sin base64. Los errores de la IA se leen tolerantes (`code` + `context`); el `extra="forbid"` aplica solo al `200`. |

**División de responsabilidades:** `ai_client` (SPIKE-01) hace la traducción + el único reintento de `IA_INTERNAL`; el worker (`HU-11`) hace los reintentos transitorios con espera, porque es quien conoce el heartbeat y el estado del ítem.

### Cómo se copia el contrato (aplica a `SPIKE-01`, `HU-10`, `HU-16`)
- Se copian **sin editar** los archivos MIT a `app/integrations/ia_contract/` (`contract.py`, `enums.py`; en `HU-08` se suma `formats.py`; en `HU-10`, `package.py`), más `LICENSE-CONTRATO-MIT.txt` y un `SOURCE.md` con el commit de origen. Al quedar idénticos, el test de igualdad por hash (`BE-03` CA-4) es posible.
- Para actualizar: se vuelve a copiar desde el repo de la IA y se cambia el commit en `SOURCE.md`. Nunca se parchea a mano.
- Los JSON de `ia-clasificacion-fauna/tests/fixtures/` (`ai/`, `package/`, `catalog/`) se copian a `tests/fixtures/` y son la entrada de los tests de contrato.
- `ruff`/`mypy` excluyen `app/integrations/ia_contract/` (código de terceros, estilo `Optional`/`Dict`), configurado en `HU-01`.

### Desvíos conocidos de `tareas-job/` (prevalece esta sección)
| Dónde | Dice | Lo correcto |
|---|---|---|
| `API_IA_BACK.md` §2.5 | `400` → `AI_BAD_RESPONSE / VALIDATION_ERROR` | `AI_BAD_RESPONSE` (sin `VALIDATION_ERROR`, que es para el usuario). |
| `ESTANDARES_BACKEND_IA.md` §6.2 | `400` → `AI_BAD_REQUEST / 400` | `AI_BAD_RESPONSE` (no se crea código nuevo). |
| `ESTANDARES_BACKEND_IA.md` §6.2 | Fila `IA_UNSUPPORTED_FORMAT` 422 | Ese código **no existe** en la IA; formato no soportado es `415 IA_INVALID_FORMAT`. |
| `ESTANDARES_BACKEND_IA.md` §6.2 | `IA_DECODE_FAILED` → `MEDIA_DECODE_FAILED` sin excepción | Si `reason = too_many_pixels` → `MEDIA_TOO_LARGE`. |
| `ESTANDARES_BACKEND_IA.md` §8 | `API_KEY` (IA), "legado `:8081`" | La IA usa `AI_API_KEY`; `:8081` no se usa. |
| `ESTANDARES_BACKEND_IA.md` §2.2 / §11, `PLAN_IMPLEMENTACION_TDR.md`, `TAREAS_BACKEND.md` BE-03 | `ia-deteccion/` | El repo local es `ia-clasificacion-fauna` (`ia-deteccion` es el nombre de la carpeta en su README). |
| `TAREAS_BACKEND.md` BE-03 CA-4 | `ai_contract.py` idéntico a `contract.py` | Idénticos `ia_contract/contract.py` + `ia_contract/enums.py` (un solo archivo fusionado no puede tener el mismo hash). |
| `API_IA_BACK.md` §2.2 y `API_BACK_FRONT.md` (ejemplos) | `common_name` en español (`"ocelote"`, `"tapir amazónico"`) | Llega en inglés (`"ocelot"`, `"lowland tapir"`). **Decidido (D4): el estándar es inglés**, sin traducción en el back. |
| IA `contract.py` `IA_ERROR_HTTP` | Incluye `IA_DURATION_EXCEEDED` | Resto anterior a `F1-D10`; avisar a Diego. El back lo trata como código desconocido (excepción documentada en el test de contratos de `HU-16`, M4-6). |

---

## Decisiones registradas tras la Oleada 3 (21/11/2026)

Las tomó Job sobre el informe de decisiones de la Oleada 3. Están aplicadas en la rama `fix/oleada3-decisions`, salvo D3, que son comandos de Git que corre Job.

| # | Decisión | Qué quedó en el código |
|---|---|---|
| D1 | Sin manifiestos de despliegue: el cliente elige la plataforma al cerrar el proyecto | Se borraron `digitalocean.yaml` y `koyeb.yml`. `docker-compose.yml` (api + worker + Redis) es la referencia; el test de secretos revisa todos los YAML del repo. |
| D2 | El validador de paquetes sigue técnicamente al de la IA | `app/services/package_validator.py` replica paso a paso a `wwm_pipeline/package_validator.py` (mismos controles, orden y códigos), con paridad verificada en 14 casos. Cuando Diego lo publique como MIT, se copia sin editar. |
| D3 | Nada de archivos de usuarios en el repo | `uploads/` entero en `.gitignore`; el video del hackathon se saca con `git rm --cached`. |
| D4 | `common_name` en inglés | Sin traducción en el back. |
| D5 | `by_month` y `by_hour` en orden cronológico | Así está desde HU-13. |
| D6 | Mover a una cámara privada ajena → 404; pública ajena → 403 `CAMERA_NOT_OWNED` | Así está desde HU-12. |
| D7 | Los archivos rechazados al subir no crean fila | El error va en la respuesta del ítem y en `total`/`failed` del lote. |
| D8 | El temporal se conserva ante errores de la IA | Así está desde HU-11 (lo limpia FL-31 a las 24 h). |
| D9 | PDF con `reportlab` | `reportlab==5.1.0`; diseño en `app/reports/brand.py` y logo/fuentes en `app/reports/assets/` (sección del README). |
| D10 | Confirmación de importación en el worker | `POST /imports/{id}/confirm` → `202`; job `import_package` en arq; `GET /imports/{id}` (`processing` → `completed` / `failed`). FL-31 marca `failed` lo que el worker dejó colgado más de 1 h. |
| D11 | Estadísticas en SQL | `app/repositories/stats.py`: cada sección es una agregación en PostgreSQL. |
| D12 | Catálogo en el repo y sincronización manual | Sin cambios; se revisa durante el año de mantenimiento. |
| D13 | Cancelar la cola antes de purgar sesiones anónimas | FL-30 cancela los `queued` (`ANON_SESSION_EXPIRED`) y deja para la próxima corrida las sesiones con algo en proceso. |
| D14 | `#15d time-offset` ahora, no después de la demo | Migración `0002` (`captured_at_original`, tabla `camera_time_offsets`) y endpoint `POST /camera-stations/{id}/time-offset`. |
| D15 | Defaults heredados de SPIKE-01 | `400` de la IA → `AI_BAD_RESPONSE`; `IA_MODEL_NOT_READY` se reintenta a los 5 y 30 s; `IA_DURATION_EXCEEDED` se trata como código desconocido. |

**Base de datos:** todavía no hay producción. Puede o no quedar en Aiven; la migración se aplica cuando se elija, con un respaldo previo.

## Decisiones y hallazgos del Milestone 4 (21/11/2026)

Tomadas durante la implementación de `HU-15a`, `HU-16` y `HU-15b` (sin consulta previa; quedan para revisión de Diego en cada PR).

| # | Decisión / hallazgo | Qué quedó en el código |
|---|---|---|
| M4-1 | `PASSWORD_RECOVERY_ENABLED` solo apaga el **envío** de correos | `forgot` responde `503` con la bandera apagada; `validate` y `reset` aceptan cualquier enlace vigente. Sin esto, el enlace manual del admin (`CB-76`) no servía con la bandera en su valor por defecto. Test de HU-04 ajustado. |
| M4-2 | La configuración del admin vive en `admin_service` | Sin `settings_service` aparte (una sola clave, `anon_data_retention`). |
| M4-3 | Borrado admin por `POST /admin/{entity}/{id}/delete` | Como el contrato §13.6, no `DELETE`. Restaurar devuelve solo lo de la misma operación (mismo `deleted_at` y `deleted_by`). |
| M4-4 | `reset-admin-password` revoca los refresh tokens; el access token vigente vence solo | Igual que el cambio de contraseña normal (JWT sin estado). |
| M4-5 | Matriz IDOR que falla ante rutas nuevas | `tests/security/test_idor_matrix.py` recorre `app.routes`: toda ruta con `{param}` necesita su caso. |
| M4-6 | `IA_DURATION_EXCEEDED` sigue en `IA_ERROR_HTTP` de la IA | Excepción documentada en `tests/contracts/test_contracts.py` (resto de `F1-D10`). **Pedir a Diego** que lo retire de la IA. |
| M4-7 | Respaldos con herramientas estándar | `scripts/backup.sh` / `restore_test.sh` (`pg_dump` custom, credenciales por `PG*`, `MANIFEST` + `SHA256SUMS`); sirven para Aiven u otro PostgreSQL. `*.sh` con LF (`.gitattributes`). |
| M4-8 | `requirements-dev.txt` | Fija ruff, mypy, pytest, pytest-asyncio, pytest-cov y pip-audit para el CI; no entra en la imagen. |
| M4-9 | Sugerencias no catalogadas agrupadas en Python | Evita depender de la extensión `unaccent` (puede no estar en Aiven). |
| M4-10 | Excel global con tope de 200 000 filas en *Clasificaciones* | El total real queda en la auditoría (`export`). `excel.safe` pasa a UTC las fechas con zona. |

## Cierre de pendientes técnicos (21/11/2026, rama `feat/dev-redis-limits-email-worker`)

| # | Pendiente | Resolución |
|---|---|---|
| T1 | Límites de intentos en memoria por proceso (con `--workers 2` se duplicaban) | **Resuelto.** `app/core/rate_limit.py`: ventana deslizante atómica en Redis (Lua), clave hasheada (sin IP ni correo en claro). Si Redis no responde, cuenta en memoria y reintenta Redis cada 30 s. Probado con 2 procesos: login 10 intentos y luego `429`. |
| T2 | Correo de recuperación por `BackgroundTasks` (se perdía al reiniciar la API) | **Resuelto.** Job `send_reset_email` en el worker. El job lleva solo un ticket; el correo y la IP quedan en Redis 1 h y el worker los lee y borra, porque arq escribe los argumentos en su log. Sin Redis, la API envía en segundo plano como respaldo. CLI `send-test-email`. |
| SP-1 | Mapeo del `400` de la IA | **Cerrado:** `400 IA_INVALID_FORMAT` → `AI_BAD_RESPONSE` + log ERROR. Un 400 significa que el back armó mal la petición: es un bug nuestro, no del usuario. Se mantiene. |
| SP-2 | Reintento de `IA_MODEL_NOT_READY` | **Cerrado:** el worker reintenta a los 5 y 30 s (como `AI_UNAVAILABLE`/`AI_TIMEOUT`). Cubre el arranque en frío de la IA sin fallar la subida. Se mantiene. |
| SP-3 | `IA_DURATION_EXCEEDED` en `IA_ERROR_HTTP` de la IA | **Parche listo para Diego** (`ia_retirar_IA_DURATION_EXCEEDED.patch`, una línea; no cambia `CONTRACT_VERSION`). Nadie lo devuelve desde F1-D10. Cuando se aplique en la IA: recopiar `contract.py`, actualizar su sha256 en SPIKE-01 y quitarlo de `INTENTIONAL_BAD_RESPONSE` en `tests/contracts/test_contracts.py`. |
| SP-4 | Fijar `pexpect` en `requirements-api.txt` de la IA | **Resuelto en la IA** (rama `fix/docker-linux-deps`, `3179dc7`; corrige lo anotado el 21/11, que decía "ya no aplica"). El lock se generó en Windows, donde `ipython` no pide `pexpect`, así que el `pip install --require-hashes` de la imagen Linux fallaba. Se fijan `pexpect==4.9.0` y `ptyprocess==0.7.0` con hashes verificados contra PyPI, y el Dockerfile agrega `libgl1` (lo necesita `opencv-python`). |
| HU02-1 | Columnas fuera del esquema original | **Aprobadas por uso**, todas necesarias: `projects.version` (`If-Match`, `CONFLICT_STALE`); `classifications.label_id` (taxón del catálogo para corregir y para `by_genus`/`by_family`); `alternatives` (validación con alternativas de la IA, §8.6); `evidence_width`/`evidence_height` (el front dibuja el recuadro sin descargar la imagen); `client_index` (idempotencia de la subida y `DELETE`/`retry` por ítem, `#24b`). |

## Pedidos del front contra el contrato (24/11/2026, rama `feat/fe-contract-gaps`)

Miguel comparó el back con `TAREAS_FRONTEND.md`; las 4 diferencias eran reales y se resolvieron en el back.

| # | Pedido | Respaldo | Resolución |
|---|---|---|---|
| FG-1 | `GET /meta/error-codes` + `SERVICE_UNAVAILABLE` sin catalogar | `TAREAS_BACKEND` (FE-51) | Catálogo único `app/core/error_catalog.py` (80 códigos: §6.1 + 7 que el back ya usaba) y endpoint solo en desarrollo (404 en producción). Tests: todo código usado en `app/` está catalogado y con el HTTP correcto. `CATALOG_TAXON_NOT_FOUND` tiene 422 (§8.6) y 404 (§9.2). |
| FG-2 | `must_change_password` / `PASSWORD_CHANGE_REQUIRED` | `BE-50`, `SEC-11` | Migración `0004`. `create-admin` y `reset-admin-password` dejan una contraseña temporal (12+ caracteres). El login responde 200 con `user.must_change_password: true` (si fuera 403 no habría token para cambiarla); todo lo demás responde `403 PASSWORD_CHANGE_REQUIRED` salvo `POST /auth/me/password`, `GET /auth/me` y `logout`. |
| FG-3 | `Retry-After` en 429 y en CORS | FE-51 CA-3 | Segundos reales de la ventana (Redis o memoria) en los `RATE_LIMITED`. CORS expone `Retry-After` y ya no `X-Anon-Session-ID` (nombre viejo). `QUEUE_USER_LIMIT` no lo lleva: depende de la cola, no de un reloj (el front usa 60 s). |
| FG-4 | Filtros de `GET /admin/classifications` | API §13.3 | Todos los de §8.1 (`category`, `validation_status`, `taxon`, `from`/`to`, confianza, `source`, `sort`, `batch_id`, `project_id`), compartidos con `/classifications` vía `apply_filters`/`build_filters`. |

**Pendiente de BE-50 (no lo pidió el front):** que `create-admin` falle si ya hay un admin (hoy asciende la cuenta) y el comando `transfer-admin`. **Pendiente de BE-31:** límites para el registro (10/min), `/files` (60/min por dueño) y `/catalog` (120/min).

---

## Milestone 0 — Saneamiento, Walking Skeleton IA y Cimientos

### Task List: `M0 - Seguridad y Saneamiento`

---

# BUG · [BUG-01] Purga y rotación de secretos expuestos y configuración estricta

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `security`, `config`, `env`, `S13`, `STD-08`
- **Dependencias:** Ninguna
- **Revisión:** Obligatoria: Diego
- **DoD:** Ver [[DEFINITION_OF_DONE]]

- **Severidad:** Bloqueante
- **Componente:** Back
- **Flujo afectado:** Todos (arranque y configuración) · **HU o tarea relacionada:** SEC-01 / `ESTANDARES §8`
- **Entorno:** local (`development`) | develop | producción (`production`) · **Versión / commit:** `4.0.0`

## Pasos para reproducir
1. Revisar `digitalocean.yaml` (L39), `check_db.py` (L5), `app/services/species_data_service.py` (L180), `app/core/config.py` (L12-18, L53-57) y `app/services/video_service.py` (L6-7).

## Resultado esperado
- **Cero secretos en Git (`gitleaks` activo):** Ninguna credencial literal en código, scripts (`check_db.py` debe leer `settings.DATABASE_URL`; `seed-e2e` no expone credenciales productivas) ni manifiestos (`digitalocean.yaml` debe usar `${DATABASE_URL}` / `type: SECRET`).
- **Configuración única por variables de entorno (`Settings` en `app/core/config.py`):** Todos los secretos y conexiones (`DATABASE_URL`, `SECRET_KEY`, `REFRESH_SECRET_KEY`, `AI_SERVICE_URL`, `AI_API_KEY`, `ALLOWED_ORIGINS`, `VISUALCROSSING_API_KEY` si aplica) se leen exclusivamente desde variables de entorno (`pydantic-settings`), prohibiendo `os.getenv`/`load_dotenv` fuera de `config.py`.
- **Dos perfiles (`ENVIRONMENT=development` vs `ENVIRONMENT=production`) con estructura idéntica y credenciales distintas:**
  - `development`: conecta mediante `.env` local a `host.docker.internal:5433/faunadb` y `http://host.docker.internal:8081` (`wwf-wildlife-api`), permite `localhost:5173`/`3000` en `ALLOWED_ORIGINS` y usa claves JWT de desarrollo (`≥ 32` bytes, distintas entre sí).
  - `production`: recibe credenciales exclusivas desde variables de entorno secretas del PaaS (Aiven con `?ssl=require`, IA productiva con `AI_API_KEY`, claves `SECRET_KEY` y `REFRESH_SECRET_KEY` criptográficas únicas de producción `≥ 32` bytes), rechaza valores por defecto/placeholders o `SECRET_KEY == REFRESH_SECRET_KEY` abortando el arranque con `CRITICAL config.invalid`, y no inyecta `localhost` en CORS.
- `ffprobe` se resuelve desde el `PATH` del sistema (sin rutas locales de Windows hardcodeadas).
- `.env.example` documenta las variables requeridas para ambos entornos usando únicamente placeholders.

## Criterios de seguridad (Gherkin)
```gherkin
CA-1 · Separación estricta de secretos entre development y production
  Dado Settings cargado con ENVIRONMENT=production
  Cuando falta DATABASE_URL, SECRET_KEY o REFRESH_SECRET_KEY, miden menos de 32 bytes, son iguales o conservan placeholders/valores por defecto
  Entonces la aplicación aborta el arranque con log CRITICAL config.invalid
    Y no añade localhost:5173 ni localhost:3000 a cors_origins

CA-2 · Arranque validado en development desde variables de entorno (.env)
  Dado ENVIRONMENT=development con credenciales locales propias en .env (faunadb en 5433 y AI_SERVICE_URL en 8081)
  Cuando Settings valida la configuración
  Entonces la aplicación arranca conectando al entorno local de desarrollo sin compartir secretos de producción
    Y cors_origins habilita los orígenes locales definidos para desarrollo
```

## Resultado obtenido
Contraseña real de Aiven y API key de VisualCrossing en texto plano en el repo; `check_db.py` hardcodea el DSN de Aiven; `app/core/config.py` define secretos JWT débiles por defecto e inyecta `localhost` en CORS sin distinguir `development` vs `production`; ruta local Windows de FFmpeg hardcodeada.

## Evidencia
- `digitalocean.yaml` L39 · `check_db.py` L5 · `app/services/species_data_service.py` L180 · `app/core/config.py` L12-18, L53-57 · `app/services/video_service.py` L6-7

## Para cerrar *(✅ Cerrado en PR #1 — commit `bcc398c` en `develop`)*
- [x] Secretos y URLs literales saneados en `check_db.py`, `digitalocean.yaml`, `.env.example` y `Settings` (`development` vs `production` fail-fast)
- [x] Test `tests/` verificando rechazo de secretos débiles en producción y carga válida en desarrollo
- [x] PR #1 fusionado a `develop` (`bcc398c`) · *(Nota: mantener rotación externa de credenciales heredadas antes de producción; ver [[DEFINITION_OF_DONE]])*

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

## Para cerrar *(✅ Cerrado en PR #2 — commit `46024a3` en `develop`)*
- [x] Routers legacy removidos y validación de dueño/IDOR en proyectos y usuarios verificada (`tests/` en verde)
- [x] PR #2 fusionado a `develop` (`46024a3`) · *(La gestión administrativa de `/users` migrará a `/admin/users` en `HU-15a`)*

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

## Para cerrar *(✅ Cerrado en PR #3 — commit `5913183` en `develop`)*
- [x] Eliminado `shutil.copyfileobj` síncrono en ingesta (`aiofiles`/chunks) y ocultado `str(exc)` en respuesta 500
- [x] PR #3 fusionado a `develop` (`5913183`, ver [[DEFINITION_OF_DONE]])

---

# HU-SPIKE-01 · [SPIKE-01] Walking Skeleton: Llamada Real a `POST /api/v1/detect` sin Cola ni Storage

- **Task List (Teamwork):** `M0 - Seguridad y Saneamiento`
- **Prioridad:** High
- **Tags:** `backend`, `ia-integration`, `spike`, `FL-08`, `CB-37`
- **Dependencias:** `BUG-01`
- **Revisión:** Obligatoria: Diego
- **Desbloquea Front:** Confirmación temprana de contrato IA (`API_IA_BACK.md`): forma real de `low_evidence`, `truncated_at_seconds` y `common_name` (inglés)

> **Estado:** ✅ Cerrado (20/11/2026) en `feat/spike-01-realign-contract` (`e6b5812`); reemplaza el v0 de PR #4 (`f46b1e5`) · **Responsable:** Job · **Semana / hito:** S1 / M0

## 1. Historia
**Como** equipo técnico,
**quiero** ejecutar un *walking skeleton* (llamada real `POST /api/v1/detect` contra `ia-clasificacion-fauna` o `ia-fake` desde `BACKWWF`, sin cola Redis ni `StorageBackend`),
**para** comprobar que el back entiende el contrato `1.0.0` real (ver "Contrato IA vigente") antes de construir la cola (`HU-08`) y el worker (`HU-11`) encima.

## 2. Origen
- **Flujos:** FL-08 · **Casos borde:** CB-37 (fallo/lentitud de la IA detectado temprano) · **Diagnóstico:** [[13_Diagnostico_Congruencia_IA_vs_Backend]] (puntos 2, 3, 7 y 8)
- **Contrato:** sección "Contrato IA vigente" de este backlog · `API_IA_BACK.md` §1–§2 · `ia-clasificacion-fauna/README.md` (Endpoints) · **Tarea:** `BE-03`

## 3. Alcance
**Incluye:**
- Copia sin editar de `contract.py` + `enums.py` (MIT) en `app/integrations/ia_contract/` con `SOURCE.md` (commit `cdf3292`) y `LICENSE-CONTRATO-MIT.txt`. Se elimina `app/integrations/ai_contract.py` del v0.
- `app/integrations/ai_client.py`: `detect_media()` + `AiClientError(code, ia_code, http_status, context)` con la tabla de traducción canónica. `HU-01` la convierte en `AppError` (`DependencyError`).
- `AI_TIMEOUT_SECONDS: float = 180.0` en `Settings` (`app/core/config.py`).
- `.env.example` y default de `docker-compose.yml` a `http://host.docker.internal:8001` y `AI_API_KEY=dev-key` (el default actual `http://localhost:8081` es doblemente incorrecto: puerto viejo y `localhost` dentro del contenedor).
- Copia de `ia-clasificacion-fauna/tests/fixtures/ai/*.json` (10 archivos) a `tests/fixtures/ai/`.
- `scripts/verify_ai_spike.py` (verificación manual contra `:8001`).

**No incluye:** Redis/`arq`, reintentos con espera (`IA_BUSY`, `AI_TIMEOUT`, `AI_UNAVAILABLE`, `AI_NOT_READY` → `HU-11`), `LocalStorage`, persistencia en `classifications`, `GET /catalog` (`HU-13`), `/health` de la IA (`HU-03`), borrar `ai_service.py`/`ai_router.py` (`BUG-04`), `formats.py` (`HU-08`).

## 4. Criterios de aceptación
```gherkin
CA-1 · Nunca inventar datos ni ocultar errores de la IA (DD-4, Nivel 1)
  Dado que la IA responde 401, 500 dos veces, 503, 504, se cae la conexión o devuelve un 200 fuera de contrato
  Cuando el back llama a detect_media()
  Entonces se lanza AiClientError con el código del back de la tabla canónica (AI_UNAVAILABLE, AI_BAD_RESPONSE, AI_NOT_READY, AI_TIMEOUT)
    Y nunca se devuelve un DetectResult
    Y el log no contiene X-API-Key ni image_base64
    Y un 401 se registra como CRITICAL ai.unauthorized y no se reintenta
```
- CA-2: `detect_media()` lee `AI_SERVICE_URL`, `AI_API_KEY` y `AI_TIMEOUT_SECONDS` de `Settings` y envía `multipart` (`file`, `file_name`) a `{AI_SERVICE_URL}/api/v1/detect` con `X-API-Key`, `X-Request-ID` y `X-Flow` (default `FL-08`). Si falta `AI_SERVICE_URL` o `AI_API_KEY`, falla **antes** de llamar con `AI_UNAVAILABLE` + `CRITICAL config.invalid` (no manda la petición sin clave).
- CA-3: Los 7 fixtures de éxito de la IA (`animal_image`, `animal_species_video`, `animal_genus_video`, `animal_video_truncated`, `blank_image`, `person_video`, `vehicle_image`) validan contra `DetectEnvelope`. Ese mismo payload con `model.geofence` añadido **falla** (`extra="forbid"`). `ia_contract/contract.py` y `enums.py` tienen el mismo sha256 que los de `ia-clasificacion-fauna@cdf3292`.
- CA-4: Traducción parametrizada (Nivel 2) con `httpx.MockTransport`: `400→AI_BAD_RESPONSE`, `413→MEDIA_TOO_LARGE`, `415→MEDIA_UNSUPPORTED_FORMAT`, `422 too_many_pixels→MEDIA_TOO_LARGE`, `422→MEDIA_DECODE_FAILED`, `503 IA_MODEL_NOT_READY→AI_NOT_READY`, `503 IA_BUSY→AI_UNAVAILABLE`, `504→AI_TIMEOUT`. `500→200` devuelve el resultado (1 reintento); `500→500` da `AI_BAD_RESPONSE` con exactamente 2 llamadas.
- CA-5 (verificación real): `scripts/verify_ai_spike.py` contra `ia-fake` en `:8001` muestra `OK` para `foto_image.jpg`, `CAM01_20260315_042210.mp4`, `clip_toolong.mp4` (`truncated_at_seconds=15.0`) y `x_blank.jpg`; decodifica `evidence.image_base64` con Pillow (`format=JPEG`, lado mayor ≤ 960); y reporta el código del back esperado para `x_badformat.cr2`, `x_crash.mp4`, `x_busy.mp4`, `x_badcontract.mp4` y una clave incorrecta. Evidencia (salida + líneas de log de `ia-fake` con el mismo `request_id`) pegada en el PR.

## 5. Diseño técnico
- `app/integrations/ia_contract/{__init__,contract,enums}.py` + `SOURCE.md` + `LICENSE-CONTRATO-MIT.txt` · `app/integrations/ai_client.py` · `app/core/config.py` (1 campo) · `.env.example` · `docker-compose.yml` (1 línea) · `scripts/verify_ai_spike.py` · `tests/fixtures/ai/*.json` · `tests/test_spike01_ai_contract.py` · `tests/test_spike01_ai_client.py`.
- Un `httpx.AsyncClient` por llamada (sin pool global): suficiente para el spike; `shortcut: un cliente por llamada, compartirlo en el worker (HU-11)`.
- El archivo se envía en streaming desde disco (no se lee entero en memoria; videos de hasta 300 MB).

## 6. Unidades de trabajo
| UT | Descripción | CA | Nivel de prueba |
|---|---|---|---|
| UT-1 | Copiar `ia_contract/` + fixtures; test de fixtures, de `geofence` rechazado y de hash | CA-3 | Nivel 1 (integridad del contrato) |
| UT-2 | `AI_TIMEOUT_SECONDS` en `Settings`; `ai_client.py` con traducción, 1 reintento en `500` y chequeo de config; `.env.example` + compose | CA-1, CA-2, CA-4 | Nivel 1 (DD-4, secretos) + Nivel 2 (parametrizado) |
| UT-3 | `verify_ai_spike.py` y corrida real contra `ia-fake :8001` | CA-5 | Verificación real (DoD §1) |

## 6b. Decisiones pendientes (no bloquean empezar)
| Pregunta | Default aplicado | Quién |
|---|---|---|
| `400 IA_INVALID_FORMAT` → ¿`AI_BAD_RESPONSE` o código nuevo `AI_BAD_REQUEST`? | `AI_BAD_RESPONSE` | Diego |
| ¿`Settings` debe abortar en producción sin `AI_SERVICE_URL`/`AI_API_KEY` (como hace la IA sin `AI_API_KEY`)? | No en SPIKE-01; proponer en `HU-11` (ya no hay `digitalocean.yaml`, D1) | Diego |
| Retirar `IA_DURATION_EXCEEDED` de `IA_ERROR_HTTP` en `contract.py` | Se trata como desconocido | Diego |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]] (corrida real contra `ia-fake`/`ia-clasificacion-fauna` en `:8001` con evidencia en el PR + aprobación de Diego). Tras el merge, apagar `wwf-wildlife-api:8081` y apuntar el `.env` local a `:8001`.

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
**Incluye:** Modelos ORM (`users`, `anon_sessions`, `camera_stations`, `projects`, `project_camera_stations` sin PK triple, `classification_batches`, `classifications` con `low_evidence`, `truncated_at_seconds`, `model_detector`, `model_classifier`, `model_sampling`, `pipeline_version` y **sin `geofence`**, `desktop_imports`, `refresh_tokens`, `password_reset_tokens`, `email_log`, `system_settings`, `admin_audit_log`, `anon_purge_runs`), índices únicos parciales, `app/db/uow.py`, `app/repositories/`, `app/services/policies.py` y migración `0001_canonical_schema.py` partiendo de la estructura actual en `faunadb` (las 10 tablas legadas generadas por `seed_db.py`). *Implementado (20/11/2026):* `upgrade` borra las tablas y tipos `ENUM` legados y crea el esquema canónico; `downgrade` deja la BD vacía (no restaura el legado, que no tenía migraciones). `migrations/` ya está incluido en el build de Docker (`.dockerignore`).
**No incluye:** Endpoints HTTP (Milestones 1–4).

## 4. Criterios de aceptación (Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Integridad de índices únicos parciales y dueño único (CB-13, CB-50)
  Dado una cámara borrada (is_deleted=True) con code="CAM01"
  Cuando el mismo dueño crea otra cámara activa "cam01"
  Entonces PostgreSQL permite el alta; pero rechaza con IntegrityError si la previa sigue activa
    Y toda fila de contenido cumple CHECK (owner_user_id IS NOT NULL XOR anon_session_id IS NOT NULL)
```
- CA-2: `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` ejecuta limpio dentro de `fauna_api` contra PostgreSQL real (`faunadb` en `development`).
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
- CA-4: `PATCH /auth/me` solo permite editar `full_name` e `institution`; `GET /config/public` expone límites/formatos tomados de `ia_contract/formats.py` (sin `heic`/`mts` hasta `IA-16`, 300 MB) y `/health/ready` devuelve `503` si falla BD, storage o la IA (`GET {AI_SERVICE_URL}/api/v1/health` sin clave: solo `200 ok` cuenta como listo; `loading`/`models_missing`/`error` → `ai: "down"`).

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
**Incluye:** `GET/POST /classification-batches`, `POST /classification-batches/{id}/files` (streaming `aiofiles` a `TMP_UPLOAD_PATH`, `python-magic`, formatos validados con la copia MIT `app/integrations/ia_contract/formats.py` (`formats.check()`: extensión + firma; rechaza `.heic/.heif` hasta `IA-16`), Pillow ≤ 100 MP, lectura informativa de duración con `ffprobe` — videos > 15s **no se rechazan**, pasan a cola per `F1-D10` para warning `VIDEO_TRUNCATED`, SHA-256 deduplicado, `anon_retain`, dispatcher justo `QUEUE_PER_OWNER_INFLIGHT=2`), `POST .../complete`.
**No incluye:** Worker IA (`HU-11`) ni cancelación/reaper (`HU-09`).

## 4. Criterios de aceptación (Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Deduplicación por SHA-256 sin consumir cola (CB-50, CB-51, CB-52, CB-54)
  Dado un archivo ya clasificado en CAM01
  Cuando el mismo dueño lo sube renombrado a CAM01 o a CAM02
  Entonces responde 200 con item.status="error" (DUPLICATE_FILE o DUPLICATE_FILE_OTHER_CAMERA) sin encolar en Redis
    Y si lo sube otro usuario distinto lo acepta con 202
```
- CA-2: Subida válida (incluye cámara retirada `CB-16`, video > 15s aceptado por `F1-D10` `CB-56`, AVI/WMV/MKV de `formats.py` `CB-57b`) responde `202` en segundos con `queue.position` y `estimated_wait_seconds`.
- CA-3: Archivo con firma binaria falsa (`CB-57`), extensión fuera de `formats.py` o `.heic` previo a `IA-16` (`CB-57c`), corrupto (`CB-58`) o > 100 MP / > 300 MB (`CB-59`) responde `200` `item.status="error"` (`MEDIA_UNSUPPORTED_FORMAT` / `MEDIA_TOO_LARGE` / `MEDIA_DECODE_FAILED`) y borra el temporal.
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
**Incluye:** `WorkerSettings` (`arq`), `classify_file_job` (cliente hacia `ia-clasificacion-fauna` / `ia-fake` `:8001`, heartbeat 30s, reintentos del worker 5s/30s en `AI_UNAVAILABLE` (incluye `IA_BUSY`), `AI_TIMEOUT` y `AI_NOT_READY` (`CB-37`); el `1 reintento en 500 IA_INTERNAL` y la traducción de errores ya los hace `ai_client` (ver "Contrato IA vigente"), Pillow re-codificación JPEG ≤ 960px sin EXIF, `LocalStorage.put()` antes del commit, persistencia de `low_evidence`, `model` sin `geofence`, warnings `CAPTURE_OUTSIDE_DEPLOYMENT` `CB-17` y `VIDEO_TRUNCATED` cuando `truncated_at_seconds != null` `F1-D10`, borrado del temporal en `finally`) y `GET /api/v1/classifications/{id}/evidence`.
**No incluye:** Validación humana y ráfagas (`HU-12`).

## 4. Criterios de aceptación (Privacidad/Integridad en Gherkin + Funcional)
```gherkin
CA-1 · Entrega protegida de evidencia y prohibición de datos inventados (CB-37)
  Dado una clasificación de cámara privada de Ana y otra de cámara pública
  Cuando Luis solicita GET /api/v1/classifications/{id}/evidence
  Entonces recibe 404 en la privada y 200 image/jpeg (Cache-Control: private) en la pública
    Y si la IA falla tras los reintentos, el worker marca status="error" con AI_TIMEOUT/AI_UNAVAILABLE/AI_BAD_RESPONSE/MEDIA_DECODE_FAILED sin datos ficticios
```
- CA-2: Procesa `animal` (species o genus `CB-61`, guardando `low_evidence`), `person`, `vehicle` y `blank` (sin evidencia), emite warning `VIDEO_TRUNCATED` en videos truncados a `15.0 s` (`F1-D10`), guarda `evidence_key` y borra el archivo de `TMP_UPLOAD_PATH` en `finally`.
- CA-3: En fallo de BD tras escribir en `LocalStorage`, elimina el fotograma huérfano antes de propagar error.

## 5. Diseño técnico
- `app/worker/{main,classify_file_job}.py`, `app/api/v1/classifications.py` (`/evidence`).

## 6. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | `classify_file_job` (heartbeat, reintentos, Pillow, `LocalStorage`, `low_evidence`/`VIDEO_TRUNCATED`, cleanup `finally`) | CA-1, CA-2, CA-3 |
| UT-2 | Endpoint `GET /classifications/{id}/evidence` con verificación de visibilidad | CA-1 |

## 7. Cierre
- **DoD:** Ver [[DEFINITION_OF_DONE]] (verificado contra `ia-clasificacion-fauna` / `ia-fake` en `:8001`).

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
**Incluye:** `GET /classifications` (todos los filtros + visibilidad + `warnings` como `VIDEO_TRUNCATED` y bandera `low_evidence`), `GET/PATCH/DELETE /classifications/{id}` (mover cámara `CB-51`, borrado lógico `204`), `PUT /classifications/{id}/validation` (`confirm`, `correct`, `correct_unlisted`, `reject`, `discard_repeat`, `reset`, historial), `POST /validation-batch` (≤500 IDs `CB-67`), `GET /burst-candidates`, `POST /repeat-batch`, `POST /repeat-batch/dismiss`.
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
**Incluye:** `POST /imports/desktop` (Bearer obligatorio, preview TTL 1h, validación Zip Slip/Bomb, checksum SHA-256, `format_version`, catálogo, Pillow y reglas `F2-D2`/`F2-D9` exigiendo `evidence` **solo cuando `category == "animal"`**, códigos `LINE_INVALID` y `EVIDENCE_MISSING`, `manifest.model` sin `geofence`, hasta 200 `issues`), `POST /imports/{id}/confirm` (`create_camera=true`, re-codifica JPEGs presentes a `LocalStorage`, worker `import_job` para paquetes grandes `CB-85`), `DELETE /imports/{id}`, `GET /imports`.
**No incluye:** Exportador Tkinter en `ia-clasificacion-fauna` (ya implementado en `DS-17`).

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
- `app/api/v1/imports.py`, `app/services/{import_service,package_validator}.py`, `app/integrations/ia_contract/package.py` (copia MIT sin editar), `app/worker/import_job.py`. El validador es una réplica paso a paso del de la IA (D2): hoy ese archivo es AGPL; cuando se publique como MIT, se copia sin editar y se borra la réplica.

## 6. Riesgos bloqueantes
| Pregunta / Riesgo | Responsable | Resolución |
|---|---|---|
| Paridad exacta de campos con `ia-clasificacion-fauna/wwm_pipeline/package.py` y `package_validator.py` | Job / Diego | ✅ `package.py` se copia sin editar; `package_validator.py` se replica con el mismo comportamiento (paridad verificada, D2). Los 8 `tests/fixtures/package/*.wwm.zip` (válidos, `zip_slip`, checksum, versión 2, JPG corrupto, taxón desconocido) son la entrada de los tests (`F2-D2`/`F2-D9`) |

## 7. Unidades de trabajo
| UT | Descripción | CA |
|---|---|---|
| UT-1 | Validador seguro ZIP en `asyncio.to_thread` + `POST /imports/desktop`, `DELETE`, `GET` | CA-1, CA-2 |
| UT-2 | `confirm` (`202`, D10) + creación cámara + `import_job` en el worker (re-codificación Pillow, filas, lote) + `GET /imports/{id}` para el seguimiento | CA-3 |

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
**Incluye:** `CatalogService` (`speciesnet_catalog.json` con **3538 taxones** en RAM al arrancar, `558` en `sample`, sincronizable desde `GET /api/v1/catalog` con `ETag`/`304`; `common_name` en inglés por defecto), `GET /catalog/species`, `GET /catalog/species/{label_id}`, `StatsService` compartido con reportes (`GET /camera-stations/{id}/stats`, `GET /projects/{id}/stats`).
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

**Decidido (D4, 21/11/2026):** `common_name` se muestra en inglés, como lo entregan la IA y el catálogo (el estándar del proyecto). No se traduce en el back.

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
**Incluye:** `GET /reports/excel` (`openpyxl` en `asyncio.to_thread`, escape de fórmulas `=,+,-,@` `GUIA_DESARROLLO` S4) y `GET /reports/pdf` con `reportlab` (portada, gráficos top 15, tablas, pie con página y `request_id`; diseño de WWF en `app/reports/brand.py`, ver README, D9).
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

> **Estado:** Cerrado 21/11/2026 (`feat/hu-15a-admin-panel`; ver [[11_Teamwork_Todolist_WWF]]) · **Responsable:** Job · **Semana / hito:** S8 / M4

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

> **Estado:** Cerrado 21/11/2026 (`feat/hu-15b-admin-extension`; ver [[11_Teamwork_Todolist_WWF]]) · **Responsable:** Job · **Semana / hito:** Post-Demo / M4

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

> **Estado:** Cerrado 21/11/2026 (`feat/hu-16-prod-gate`; ver [[11_Teamwork_Todolist_WWF]]) · **Responsable:** Job · **Semana / hito:** S8 / M4 (Gate Salida a Producción)

## 1. Historia
**Como** Tech Lead y equipo de QA,
**quiero** validar la matriz completa de IDOR en todos los endpoints, verificar paridad de contratos (`API_IA_BACK.md` y `PAQUETE_ESCRITORIO.md`), automatizar backups (`FL-32`) y entregar `seed-e2e`,
**para** certificar la salida segura a producción de `BACKWWF`.

## 2. Origen
- **Tarea:** BE-23, BE-35, DEP-01..04, FL-32 · **Flujos:** FL-32 + compatibilidad contrato FL-20, FL-21, FL-22 · **Casos borde:** CB-90, CB-91, CB-92, CB-93, CB-94, CB-95 (verificación UTF-8 largo y `source_folder_name` limpio en contrato; resto manual en escritorio) · **Contrato:** `ESTANDARES §11`, `GUIA_DESARROLLO §4`

## 3. Alcance
**Incluye:** `tests/security/test_idor_matrix.py`, `tests/contracts/test_contracts.py` (sha256 de cada archivo de `app/integrations/ia_contract/` igual al de `../ia-clasificacion-fauna` en el commit de `SOURCE.md`, y `package_validator.py` cuando se publique como MIT (D2); se salta con aviso si el repo hermano no está, y en CI compara contra los fixtures copiados, UTF-8 largo `CB-95`, sin `geofence`, `F1-D10` y `F2-D2`/`F2-D9`), `scripts/backup.sh` + `scripts/restore_test.sh` (`pg_dump` + `STORAGE_LOCAL_PATH`, retención 7d/4s, `FL-32`), `app/cli.py seed-e2e` (reemplaza al `seed_db.py` retirado en `HU-02`: usuario `admin@wwf.org` / `wwf123456`, estaciones `CAM-01..03`, taxonomía completa y ráfagas) y CI completo (`.github/workflows/ci.yml`).
**No incluye:** UI de app de escritorio (`ia-clasificacion-fauna/desktop`, `FL-20..22` implementados a la espera de QA `DS-16`).

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
