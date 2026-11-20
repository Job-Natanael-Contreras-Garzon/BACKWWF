---
name: wwf-api-contracts
description: Contrato compacto de los 44 endpoints Back-Front, contrato IA-Back y validaciones de paquete de escritorio.
---

# Contratos Oficiales WWF (`BACKWWF`)

**Base URL:** `/api/v1` · **Auth:** `Authorization: Bearer <jwt>` o `X-Anon-Token: <token>` · **Envoltura:** `{status, data, message, error, meta}`. Implementa solo lo especificado, con el mínimo código funcional.

## 1. Índice Compacto de los 44 Endpoints (`API_BACK_FRONT.md`)

### Auth, Anónimos y Sistema (#1 – #12)
| # | Ruta | Auth | Request / Reglas / Response (`data`) |
| :---: | :--- | :--- | :--- |
| 1 | `POST /auth/register` | — (+`X-Anon-Token` opc) | `{email, password(≥8, letra+num), full_name, institution?}` -> `201` `{user, tokens, anon_session}` |
| 2 | `POST /auth/login` | — (+`X-Anon-Token` opc) | `{email, password}` (Rate limit 10/min IP, 5/min admin) -> `200` `{user, tokens, anon_session}` |
| 3 | `POST /auth/refresh` | — | `{refresh_token}` (rotación + detección reuso) -> `200` `{tokens}` |
| 4 | `POST /auth/logout` | Bearer | `{refresh_token}` (revoca token en BD) -> `200` `null` |
| 5 | `GET / PATCH /auth/me` | Bearer | `GET` -> `User`. `PATCH` `{full_name?, institution?}` -> `User` |
| 6 | `POST /auth/me/password` | Bearer | `{current_password, new_password}` (revoca otros refresh) -> `200` `null` |
| 6b | `POST /auth/password/forgot` · `GET .../reset/validate?token=` · `POST .../reset` | — | `forgot` `{email}` -> 200 genérico (envío en worker). `validate` -> `{valid, expires_at?, email_hint?}`. `reset` `{token, new_password}` -> `null` |
| 7 | `POST /anon-sessions` | — | Rate limit 5/h IP -> `201` `{anon_token, expires_at, data_retention}` (guardar hash) |
| 8 | `GET /anon-sessions/current` | Anon | -> `200` `{status, expires_at, data_retention, counts, limits}` |
| 9 | `POST /anon-sessions/claim` | Bearer+Anon | Asocia cámaras/proyectos/clasificaciones; renombra códigos duplicados (`-2`) -> `{claimed, renamed_camera_stations}` |
| 10 | `POST /anon-sessions/current/close` | Anon | Expira sesión -> `200` `{status:"expired", data_retained}` |
| 11 | `GET /config/public` | — | Límites media/anónimos/upload/import, mapa, `password_recovery.enabled`, `app_version` |
| 12 | `GET /health` · `GET /health/ready` | — | `/health` `{status:"ok", version}`. `/health/ready` verifica `database, ai, storage` (503 si falla); `ai` = `GET {AI_SERVICE_URL}/api/v1/health` sin clave, solo `200 ok` cuenta como listo (`loading`/`models_missing`/`error` → `down`) |

### Cámaras y Proyectos (#13 – #20)
| # | Ruta | Auth | Request / Reglas / Response (`data`) |
| :---: | :--- | :--- | :--- |
| 13 | `GET / POST /camera-stations` | — / Dueño | `GET` `?scope,view(full|map),project_id,bbox,q,still_installed,page,page_size,sort`. `POST` `CameraStationInput` -> `201` (coords exactas solo dueño) |
| 14 | `GET / PATCH / DELETE /camera-stations/{id}` | Visib / Dueño | Privada ajena -> `404`. `PATCH` exige `If-Match: <version>`. `DELETE` cascada lógica -> `204` |
| 15 | `GET /camera-stations/{id}/stats` | Visib | `?from,to,only_validated,source,sections` -> `Stats` |
| 15b | `GET /camera-stations/nearby` | Dueño | `?lat,lng,radius_m(≤200),exclude_id,deployed_at,retrieved_at` -> `{mine, public_others(distance_band)}` |
| 15c | `POST /camera-stations/{id}/redeploy` | Dueño | `{code?, deployed_at, close_previous, previous_retrieved_at?, observations?}` -> `201` `{camera_station, previous}` |
| 15d | `POST /camera-stations/{id}/time-offset` | Dueño | `{offset_seconds, from?, to?, reason}` -> `{updated}` |
| 16 | `GET / POST /projects` | — / Dueño | `GET` `?scope,q,page,page_size,sort`. `POST` `{name, description?, visibility, camera_station_ids?}` -> `201` `ProjectDetail` |
| 17 | `GET / PATCH / DELETE /projects/{id}` | Visib / Dueño | `PATCH` exige `If-Match: <version>`. `DELETE` lógico (no borra cámaras) -> `204` |
| 18 | `POST /projects/{id}/camera-stations` | Dueño | `{camera_station_id}` (cámara y proyecto deben ser del dueño) -> `200` `ProjectDetail` |
| 19 | `DELETE /projects/{id}/camera-stations/{cid}` | Dueño | Desasocia relación -> `204` |
| 20 | `GET /projects/{id}/stats` | Visib | `Stats` (incluye `by_camera`; terceros solo ven cámaras públicas) |

### Lotes, Clasificaciones y Catálogo (#21 – #31)
| # | Ruta | Auth | Request / Reglas / Response (`data`) |
| :---: | :--- | :--- | :--- |
| 21 | `GET / POST /classification-batches` | Dueño | `GET ?active=true`. `POST {camera_station_id, expected_files(1..500)}` -> `201` `Batch(open)` |
| 22 | `GET /classification-batches/{id}` | Dueño | `?since=<ISO>` -> `Batch` con `items` actualizados |
| 23 | `POST /classification-batches/{id}/files` | Dueño | Multipart `file, client_index, client_mtime?` -> `202` `BatchItem(queued)` o `200` `BatchItem(error)` |
| 24 | `POST /classification-batches/{id}/complete` | Dueño | Cierra recepción -> `200` `Batch(processing)` |
| 24b | `POST .../cancel` · `DELETE .../items/{i}` · `POST .../items/{i}/retry` | Dueño | Cancela `queued` -> `200`/`204`; reintenta `error` si existe temporal -> `202` o `410` |
| 25 | `GET /classifications` | Dueño/Púb | Filtros `camera_station_id,project_id,batch_id,status,category,validation_status,taxon,min/max_confidence,from,to,source,sort,page` |
| 26 | `GET / PATCH / DELETE /classifications/{id}` | Púb / Dueño | `GET ?include=validation_history`. `PATCH {camera_station_id}`. `DELETE` lógico -> `204` |
| 27 | `GET /classifications/{id}/evidence` | Dueño/Púb | Responde `image/jpeg` binario (`Cache-Control: private, max-age=3600`) |
| 28 | `PUT /classifications/{id}/validation` | Dueño | `{action: confirm|correct|correct_unlisted|reject|discard_repeat|reset, label_id?, correction_source?, suggested_name?, repeat_of?, notes?}` -> `Classification` |
| 29 | `POST /classifications/validation-batch` | Dueño | `{ids(≤500), action(confirm|reject|reset), notes?}` -> `{updated, skipped}` |
| 29b | `GET .../burst-candidates` · `POST .../repeat-batch` · `POST .../repeat-batch/dismiss` | Dueño | Agrupa ráfagas (misma cámara+taxón, Δt ≤ `window_minutes`); `repeat-batch {keep_ids, discard_ids, notes?}` |
| 30 | `GET /catalog/species` · `GET /catalog/species/{label_id}` | — | Busca en `speciesnet_catalog.json` en RAM (`3538` taxones, sync vía `/api/v1/catalog` con `ETag`/`304`; `common_name` EN por defecto; `q≥2`, `rank?`, `limit≤50`) -> `CatalogTaxon[]` |
| 31 | `GET /reports/excel` · `GET /reports/pdf` | Visib | `?camera_station_id | project_id, from?, to?, only_validated?, source?` -> Binario `.xlsx`/`.pdf` (coords redondeadas a terceros) |

### Importación Escritorio y Administración (#32 – #44)
| # | Ruta | Auth | Request / Reglas / Response (`data`) |
| :---: | :--- | :--- | :--- |
| 32 | `POST /imports/desktop` | Bearer | Multipart `package(.wwm.zip)` + (`camera_station_id` o `create_camera=true`) -> `201` preview TTL 1h (`counts`, max 200 `issues`) |
| 33 | `POST /imports/{id}/confirm` | Bearer | `{include_warnings, camera?}` -> `200` `{import_id, status:"completed", batch_id, imported, skipped_duplicates, skipped_invalid}` |
| 34 | `DELETE /imports/{id}` | Bearer | Cancela preview y borra temporal -> `204` |
| 35 | `GET /imports` | Bearer | `?camera_station_id, page` -> Lista importaciones propias |
| 36 | `GET /admin/stats` | Admin | `?from,to,scope,include_deleted` -> Métricas plataforma, `model_feedback`, `fauna` (dedup `sha256`), `fauna_map` (sin datos privados) |
| 37 | `GET /admin/camera-stations` · `/classifications` · `/anon-sessions` | Admin | `scope ∈ {anonymous, public, all}` (nunca privado) + `include_deleted` |
| 38 | `GET /admin/classifications/{id}/evidence` | Admin | JPEG público/anónimo; privado -> `404` |
| 39 | `POST /admin/{entity}/{id}/delete` · `restore` · `/admin/delete-batch` | Admin | Exige `reason`; cascada lógica + registro en `admin_audit_log` |
| 40 | `GET /admin/users` · `POST .../deactivate` · `reactivate` · `password-reset-link` | Admin | Gestión de usuarios y enlace reset manual auditado |
| 41 | `GET / PUT /admin/settings` | Admin | Lee/actualiza `anon_data_retention` con `reason` obligatorio |
| 42 | `GET /admin/audit-log` · `GET /admin/reports/excel` | Admin | Auditoría paginada y Excel global (incluye hoja *Sugerencias*) |
| 43 | `GET /admin/queue` | Admin | Estado cola `arq`/Redis, pendientes por dueño y cuota diaria/mensual de emails |
| 44 | `GET /admin/unlisted-suggestions` | Admin | Agrupa `suggested_name` normalizados (solo público/anónimo) |

## 2. Contrato IA (`ia-clasificacion-fauna`, `CONTRACT_VERSION = "1.0.0"`) — Solo Worker
- **Qué manda si dos fuentes chocan:** (1) el código de `../ia-clasificacion-fauna` (`wwm_pipeline/contract.py`, `enums.py`, `formats.py`, `package*.py`, `api/errors.py`, `api/routes.py`) y su `README.md`; (2) la sección "Contrato IA vigente" de `10_Backlog_Teamwork_WWF.md`; (3) `tareas-job/contratos/API_IA_BACK.md` y `PAQUETE_ESCRITORIO.md`; (4) el resto de `tareas-job/` (redactado contra la IA vieja). Cita archivo y línea de la IA cuando decidas.
- **Endpoint:** `POST {AI_SERVICE_URL}/api/v1/detect` (`AI_SERVICE_URL` **sin** `/api/v1`: dev `http://host.docker.internal:8001`, compose `http://ia:8001`; no se usa `AI_BASE_URL`). El contenedor viejo `:8081` **no** cumple el contrato y no vale como evidencia · **Headers:** `X-API-Key` (`AI_API_KEY`, `dev-key` en dev, obligatoria en prod), `X-Request-ID`, `X-Flow` · **Timeout:** `AI_TIMEOUT_SECONDS = 180` (la IA corta a 150 s).
- **Multipart:** `file`, `file_name` (obligatorios), `client_mtime?`. Enviar el archivo en streaming (hasta 300 MB).
- **Response:** envoltura `{status, data, message, error, meta}`; `data` = `DetectResult` estricto (`extra="forbid"` en todo): `media {file_name, media_type, sha256, size_bytes, duration_seconds, fps, width, height}`, `capture {captured_at, source(exif|container|filename|none)}`, `result {category(animal|person|vehicle|blank), taxonomy?, confidence, alternatives[≤3, score>0.005]}`, `evidence? {frame_index, timestamp_seconds, bbox[4], detection_confidence, image_base64, image_mime, width, height}` (en `animal|person|vehicle`; `null` en `blank`), `analysis {frames_sampled, frames_with_animal, frames_discarded:{duplicate,blurry,cap}, votes, truncated_at_seconds, low_evidence, processing_ms}`, `model {detector, classifier, sampling, pipeline_version}` (**sin `geofence`**). `common_name` llega en **inglés**.
- **Copia del contrato:** se copian **sin editar** los archivos MIT a `app/integrations/ia_contract/` (`contract.py`, `enums.py`; luego `formats.py`, `package.py`, `package_validator.py`) con `SOURCE.md` (commit de origen) y `LICENSE-CONTRATO-MIT.txt`. Nunca se parchean a mano: se re-copian. Los fixtures de `ia-clasificacion-fauna/tests/fixtures/{ai,package,catalog}` son la entrada de los tests de contrato.
- **Errores IA → Back** (traduce `ai_client` en el borde; el mapeo mira el **HTTP**, porque `400` y `415` comparten `IA_INVALID_FORMAT`):

| IA | Back | Reintenta |
|---|---|---|
| `400 IA_INVALID_FORMAT` (falta `file`/`file_name`: bug nuestro) | `AI_BAD_RESPONSE` + log ERROR `ai.request.rejected` (no crear `AI_BAD_REQUEST`; pendiente confirmar Diego) | No |
| `401 IA_UNAUTHORIZED` | `AI_UNAVAILABLE` + log CRITICAL `ai.unauthorized` | No |
| `413 IA_FILE_TOO_LARGE` | `MEDIA_TOO_LARGE` | No |
| `415 IA_INVALID_FORMAT` | `MEDIA_UNSUPPORTED_FORMAT` | No |
| `422 IA_DECODE_FAILED` (`reason=too_many_pixels` / otro) | `MEDIA_TOO_LARGE` / `MEDIA_DECODE_FAILED` | No |
| `500 IA_INTERNAL` | `AI_BAD_RESPONSE` | `ai_client`: 1 vez |
| `503 IA_MODEL_NOT_READY` | `AI_NOT_READY` | Worker 5 s/30 s (pendiente confirmar Diego) |
| `503 IA_BUSY` · `504` / `httpx.TimeoutException` · conexión/DNS | `AI_UNAVAILABLE` · `AI_TIMEOUT` · `AI_UNAVAILABLE` | Worker 5 s/30 s (`CB-37`) |
| `200` fuera de contrato, no-JSON o código `IA_*` desconocido (incl. `IA_DURATION_EXCEEDED`, ya retirado) | `AI_BAD_RESPONSE` + log ERROR con las **claves** recibidas, sin base64 | No |

- Los cuerpos de **error** se leen tolerantes (`error.code` + `details[0].context`); `extra="forbid"` aplica solo al `200`.
- **Videos > 15 s (`F1-D10`):** NO dan error; pasados 15 s + 0,5 s de tolerancia devuelve `200` con `truncated_at_seconds = 15.0` y el Back emite warning `VIDEO_TRUNCATED`. `low_evidence=true` (un solo voto con peso < 0,25) se guarda y se expone. **Prohibido inventar datos (DD-4).**
- **Otros endpoints IA:** `GET /api/v1/health` (sin clave ni envoltura; `200 ok` / `503 loading|models_missing|error`) y `GET /api/v1/catalog` (con clave; 3538 taxones, `ETag`=sha256, `304` con `If-None-Match`).

## 3. Validaciones Paquete Escritorio (`PAQUETE_ESCRITORIO.md`)
- **Contrato en código:** `app/integrations/ia_contract/{package,package_validator}.py` (copia MIT sin editar); fixtures `tests/fixtures/package/*.wwm.zip` (válidos, `zip_slip`, checksum, versión 2, JPG corrupto, taxón desconocido).
- **Estructura exacta ZIP:** `manifest.json`, `classifications.jsonl`, `evidence/<sha256>.jpg` (rechazar `../`, rutas absolutas, *symlinks* -> `IMPORT_INVALID_PACKAGE`; sin `geofence` en `manifest.model`).
- **Límites:** ZIP ≤ `IMPORT_MAX_MB` (200 MB), descomprimido ≤ 3× límite, ≤ 20,000 entradas (`IMPORT_TOO_LARGE`).
- **Integridad:** `format == "wwm-desktop-export"`, `format_version` `1.x` (`IMPORT_UNSUPPORTED_VERSION`), SHA-256 de `classifications.jsonl` (`IMPORT_CHECKSUM_MISMATCH`), `counts` exactos, `package_sha256` único por cámara (`IMPORT_ALREADY_IMPORTED`).
- **Por línea JSONL:** validar schema (`LINE_INVALID`), `taxonomy.label_id` en catálogo (`CATALOG_TAXON_NOT_FOUND`), `evidence/*.jpg` requerido **solo cuando `category == "animal"`** (`F2-D2`/`F2-D9`: missing -> `EVIDENCE_MISSING`, corrupto -> `EVIDENCE_INVALID`; `person`/`vehicle` permiten `evidence: null`), duplicado `(camera_station_id, file_sha256)` se salta, fecha fuera de despliegue emite warning `CAPTURE_OUTSIDE_DEPLOYMENT`.
