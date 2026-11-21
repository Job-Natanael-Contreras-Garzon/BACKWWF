# Contrato de API · Back → Front

> Documento interno · CETERIS404 · v1 — 07/11/2026
> **Fuente única de verdad** de lo que el back expone y el front consume. Si el código y este documento no coinciden, se corrige el que esté mal y se avisa a los tres.
> **Dueños:** Job implementa, Miguel consume y Diego aprueba los cambios.
> **Relacionados:** las reglas de negocio están en [FLUJOS_SISTEMA.md](../FLUJOS_SISTEMA.md) y los recorridos paso a paso en [FLUJOS_DETALLADOS.md](../flujos/FLUJOS_DETALLADOS.md); la envoltura, los errores y los logs, en [ESTANDARES_BACKEND_IA.md](../ESTANDARES_BACKEND_IA.md); lo que la IA entrega al back, en [API_IA_BACK.md](API_IA_BACK.md).

---

## Índice

0. [Convenciones](#0-convenciones)
1. [Schemas comunes](#1-schemas-comunes)
2. [Autenticación y cuenta](#2-autenticación-y-cuenta)
3. [Sesión anónima](#3-sesión-anónima)
4. [Configuración pública y salud](#4-configuración-pública-y-salud)
5. [Cámaras trampa](#5-cámaras-trampa)
6. [Proyectos](#6-proyectos)
7. [Clasificación: lotes y archivos](#7-clasificación-lotes-y-archivos)
8. [Clasificaciones: consulta, fotograma y validación](#8-clasificaciones-consulta-fotograma-y-validación)
9. [Catálogo de especies](#9-catálogo-de-especies)
10. [Estadísticas](#10-estadísticas)
11. [Reportes Excel y PDF](#11-reportes-excel-y-pdf)
12. [Importación desde la app de escritorio](#12-importación-desde-la-app-de-escritorio)
13. [Administración](#13-administración)
14. [Matriz de permisos](#14-matriz-de-permisos)
15. [Resumen de endpoints](#15-resumen-de-endpoints)

---

## 0. Convenciones

| Tema | Regla |
|---|---|
| Base URL | `{VITE_API_URL}` = `https://<dominio>/api/v1` (en desarrollo, `http://localhost:8000/api/v1`). Las rutas de este documento son **relativas** a esa base. |
| Envoltura | Todo JSON va como `{status, data, message, error, meta}` ([ESTANDARES §4](../ESTANDARES_BACKEND_IA.md#4-formato-de-respuesta-estándar)). En este documento, **"Respuesta"** muestra solo el contenido de `data`. |
| Errores | `status:"error"`, `error.code` del [catálogo](../ESTANDARES_BACKEND_IA.md#6-catálogo-de-códigos-de-error). Cada endpoint lista sus códigos propios; además, todos pueden devolver `VALIDATION_ERROR` (422), `RATE_LIMITED` (429) e `INTERNAL_ERROR` (500). |
| Autenticación | `Authorization: Bearer <access_token>` (usuario) **o** `X-Anon-Token: <token>` (sesión anónima). Si llegan los dos, manda el Bearer, salvo en `/anon-sessions/claim`, que necesita ambos. |
| Correlación | El front envía `X-Request-ID` (UUID v4) en cada petición; el back lo devuelve en el header y en `meta.request_id`. |
| Fechas | ISO 8601. Las del servidor van en UTC con `Z`. `captured_at`, `deployed_at` y `retrieved_at` van en **hora local sin zona** (`2026-03-15T04:22:10`), porque las cámaras no registran la zona. |
| IDs | UUID v4 en texto. |
| Paginación | `?page=1&page_size=50` (máximo 200) → `meta.pagination = {page, page_size, total, total_pages}`. |
| Orden | `?sort=campo` o `?sort=-campo` (descendente). |
| "Dueño" | El usuario autenticado o la sesión anónima que creó el recurso. |
| Visibilidad | `public` o `private`. El contenido anónimo es siempre `private` (respecto de otros usuarios). |
| Advertencias | Una operación que se guarda pero merece atención trae `meta.warnings: [{code, message, context}]` (por ejemplo `CAMERA_COORDS_SUSPECT`). El front las muestra; no son errores. Ver [CASOS_BORDE.md](../flujos/CASOS_BORDE.md). |
| Ubicación (DD-17) | Las coordenadas de una cámara solo se envían **exactas a su dueño**. A cualquier otra persona (visitante, otro usuario, admin con cámaras públicas de usuarios) se le envían **redondeadas a 2 decimales (~1 km)** y con `location_precision: "approx_1km"`. Aplica en listados, detalle, mapa, `nearby`, stats, Excel y PDF. |
| Concurrencia | Las cámaras y los proyectos tienen `version` (entero). Los `PATCH` envían `If-Match: <version>`; si no coincide → `409 CONFLICT_STALE` (CB-15). |

---

## 1. Schemas comunes

### 1.1 `User`
```json
{
  "id": "6f1c…",
  "email": "investigador@wwf.org.bo",
  "full_name": "Ana Rojas",
  "institution": "WWF Bolivia",
  "role": "user",
  "is_active": true,
  "created_at": "2026-11-07T15:04:05Z",
  "last_login_at": "2026-11-07T15:04:05Z"
}
```
`role`: `user` | `admin`.

### 1.2 `AuthTokens`
```json
{ "access_token": "eyJ…", "refresh_token": "eyJ…", "token_type": "bearer", "expires_in": 1800 }
```
`expires_in` está en segundos: 1800 para usuarios y 900 para el admin.

### 1.3 `Owner` (se incluye en cámaras y proyectos)
```json
{ "type": "user", "is_mine": true, "display_name": "Ana Rojas", "institution": "WWF Bolivia" }
```
- `type`: `user` | `anonymous`.
- `display_name` e `institution` solo se envían cuando el contenido es público o es tuyo. En los demás casos van en `null`.

### 1.4 `CameraStation`
```json
{
  "id": "c77…",
  "code": "CAM01",
  "name": "Quebrada norte",
  "latitude": -17.78345,
  "longitude": -63.18211,
  "deployed_at": "2026-03-01T08:30:00",
  "retrieved_at": null,
  "still_installed": true,
  "observations": "Sobre sendero de tapires",
  "visibility": "private",
  "owner": { "type": "user", "is_mine": true, "display_name": "Ana Rojas", "institution": "WWF Bolivia" },
  "project_ids": ["p12…"],
  "counts": { "classifications": 120, "sightings": 87, "species": 14, "pending_validation": 39 },
  "last_capture_at": "2026-03-28T03:44:00",
  "location_precision": "exact",
  "previous_camera_station_id": null,
  "version": 3,
  "created_at": "2026-11-07T15:04:05Z",
  "updated_at": "2026-11-07T15:04:05Z"
}
```
`previous_camera_station_id` apunta a la instalación anterior en el mismo punto (reinstalación, §5.8).

**`CameraStationMapItem`** (con `?view=map`, liviano para pintar marcadores):
```json
{ "id": "c77…", "code": "CAM01", "name": "Quebrada norte", "latitude": -17.78, "longitude": -63.18,
  "location_precision": "approx_1km", "visibility": "public", "is_mine": false, "still_installed": true, "sightings": 87, "species": 14 }
```

### 1.5 `CameraStationInput` (crear o editar)
| Campo | Tipo | Crear | Reglas |
|---|---|---|---|
| `code` | string ≤ 50 | **obligatorio** | Único por dueño **sin distinguir mayúsculas** entre las cámaras no borradas (CB-13). Se normaliza con `trim` y se muestra tal como se escribió. |
| `name` | string ≤ 120 | opcional | — |
| `latitude` | number | **obligatorio** | −90 a 90, con 6 decimales. |
| `longitude` | number | **obligatorio** | −180 a 180, con 6 decimales. |
| `deployed_at` | datetime local | **obligatorio** | No puede ser futura (más de 1 día) → `CAMERA_INVALID_DATES` (CB-12). |
| `still_installed` | bool | **obligatorio** | Si es `true`, `retrieved_at` debe ser `null`. |
| `retrieved_at` | datetime local | obligatorio si `still_installed=false` | `≥ deployed_at` y no futura; si no, `CAMERA_INVALID_DATES`. |
| `observations` | string ≤ 2000 | opcional | — |
| `visibility` | `public`/`private` | opcional (por defecto `private`) | Un anónimo con `public` → `ANON_PUBLIC_NOT_ALLOWED`. |
| `project_id` | uuid | opcional, solo al crear | Crea la cámara y la asocia al proyecto en la misma transacción (crear una cámara dentro del proyecto). |

En `PATCH` todos los campos son opcionales; se validan las mismas reglas sobre el resultado final.

**Advertencias** (`meta.warnings`, no bloquean):
- `CAMERA_COORDS_SUSPECT`: coordenadas `0,0`, o latitud y longitud que parecen invertidas (fuera de Bolivia, pero dentro si se intercambian) (CB-07). Las ubicaciones fuera de Bolivia son **válidas**;
- `CAMERA_MOVED_WITH_DATA`: `PATCH` que mueve más de 50 m una cámara con clasificaciones (CB-09).

### 1.6 `Project`
```json
{
  "id": "p12…",
  "name": "Área protegida Amboró — 2026",
  "description": "Monitoreo de mamíferos medianos y grandes",
  "visibility": "public",
  "owner": { "type": "user", "is_mine": true, "display_name": "Ana Rojas", "institution": "WWF Bolivia" },
  "camera_station_ids": ["c77…", "c78…"],
  "counts": { "camera_stations": 2, "classifications": 240, "sightings": 150, "species": 19 },
  "created_at": "2026-11-07T15:04:05Z",
  "updated_at": "2026-11-07T15:04:05Z"
}
```
**`ProjectDetail`** = `Project` + `camera_stations: CameraStation[]`, que contiene las cámaras que el que consulta puede ver.

### 1.7 `Taxonomy`
```json
{
  "label_id": "5c7ce479-…",
  "class": "mammalia", "order": "carnivora", "family": "felidae",
  "genus": "panthera", "species": "onca",
  "scientific_name": "Panthera onca", "common_name": "jaguar",
  "rank": "species"
}
```
- `rank`: `species` | `genus` | `family` | `order` | `class`.
- Los niveles por debajo de `rank` van en `null`. Por ejemplo, con `rank=genus`, `species` es `null` y `scientific_name` es `"Panthera"`.

### 1.8 `Classification`
```json
{
  "id": "k91…",
  "batch_id": "b12…",
  "camera_station_id": "c77…",
  "source": "web",
  "file_name": "CAM01_20260315_042210.mp4",
  "file_sha256": "9f2c…",
  "media_type": "video",
  "duration_seconds": 14.8,
  "captured_at": "2026-03-15T04:22:10",
  "captured_at_source": "filename",
  "status": "done",
  "error": null,
  "warnings": [],
  "queue": null,
  "category": "animal",
  "taxonomy": { "label_id": "…", "class": "mammalia", "order": "carnivora", "family": "felidae", "genus": "panthera", "species": "onca", "scientific_name": "Panthera onca", "common_name": "jaguar", "rank": "species" },
  "confidence": 0.94,
  "alternatives": [
    { "label_id": "…", "scientific_name": "Puma concolor", "common_name": "puma", "rank": "species", "score": 0.03 },
    { "label_id": "…", "scientific_name": "Leopardus pardalis", "common_name": "ocelote", "rank": "species", "score": 0.01 }
  ],
  "frames_analyzed": 45,
  "evidence": {
    "url": "/api/v1/classifications/k91…/evidence",
    "frame_index": 212,
    "timestamp_seconds": 7.07,
    "timestamp_label": "00:07",
    "bbox": [0.31, 0.12, 0.78, 0.66],
    "width": 960, "height": 540
  },
  "validation": {
    "status": "unvalidated",
    "correction_source": null,
    "corrected_taxonomy": null,
    "suggested_name": null,
    "repeat_of": null,
    "notes": null,
    "validated_by": null,
    "validated_at": null
  },
  "effective_taxonomy": { "…": "igual a taxonomy, o a corrected_taxonomy si existe" },
  "model": { "detector": "MDv5a", "classifier": "speciesnet-4.0.2a", "sampling": "10fps@0-2s+4fps/max60/hasta15s", "pipeline_version": "0.1.0" },
  "low_evidence": false,
  "created_at": "2026-11-07T15:04:05Z"
}
```

**Reglas:**
- `category`: `animal` | `person` | `vehicle` | `blank`. Si no es `animal`, `taxonomy`, `alternatives` y `effective_taxonomy` van en `null`. El fotograma (`evidence`) sí puede venir en `person` y `vehicle`; en `blank` es `null`.
- `status`: `queued` | `processing` | `done` | `error` | `cancelled`.
  - En `queued`, `queue = {position, estimated_wait_seconds}`; en los demás estados es `null`.
  - En `queued`, `processing`, `error` y `cancelled`, todo lo de la IA va en `null`.
  - En `error` y `cancelled`, `error = {code, message}`. Solo las filas `done` cuentan como clasificaciones; las `error`, en `totals.files_error`.
- `warnings`: advertencias del archivo, por ejemplo `[{code:"CAPTURE_OUTSIDE_DEPLOYMENT", message}]` (CB-17) o `[{code:"VIDEO_TRUNCATED", message}]` cuando un video supera 15 s y la IA analiza los primeros 15 s (`F1-D10`).
- `low_evidence`: `true` si la IA votó con evidencia débil (`low_evidence` de `API_IA_BACK.md`), útil para mostrar aviso suave al revisor sin degradar el estado a error.
- `evidence.url` es relativa a la base del dominio y **requiere autenticación** (§8.3). `timestamp_label` va en formato `mm:ss`. En imágenes, `timestamp_seconds` es `0` y `timestamp_label` es `null`.
- `bbox` usa coordenadas **normalizadas** `[x1, y1, x2, y2]` en el rango 0–1, sobre el fotograma.
- `validation.status`: `unvalidated` | `confirmed` | `corrected` | `corrected_unlisted` | `rejected` | `discarded_repeat`.
- `validation.repeat_of`: con `discarded_repeat`, el ID de la clasificación que se conservó como avistamiento de esa ráfaga (§8.8).
- `validation.correction_source`: `alternative` (eligió una de las `alternatives`) | `catalog` (la buscó en el catálogo) | `unlisted` (no está en el catálogo) | `null`.
- `validation.suggested_name`: el nombre que escribió el usuario cuando la especie no está en el catálogo (CB-65).
- `captured_at_source`: `exif` | `container` | `filename` | `client_mtime` | `upload_time`.

### 1.9 `Batch` y `BatchItem`
```json
{
  "id": "b12…",
  "camera_station_id": "c77…",
  "camera_station_code": "CAM01",
  "source": "web",
  "status": "processing",
  "expected_files": 3,
  "counts": { "received": 3, "queued": 1, "processing": 1, "done": 0, "failed": 1, "cancelled": 0 },
  "queue": { "next_position": 4, "estimated_wait_seconds": 210 },
  "created_at": "2026-11-07T15:04:05Z",
  "completed_at": null,
  "items": [
    { "client_index": 0, "file_name": "A.mp4", "status": "processing", "classification_id": "k91…",
      "queue": null, "classification": null, "error": null, "updated_at": "…" },
    { "client_index": 1, "file_name": "B.mp4", "status": "queued", "classification_id": "k92…",
      "queue": { "position": 4, "estimated_wait_seconds": 210 }, "classification": null, "error": null, "updated_at": "…" },
    { "client_index": 2, "file_name": "C.mp4", "status": "error", "classification_id": null, "queue": null, "classification": null,
      "error": { "code": "MEDIA_TOO_LARGE", "message": "El archivo supera el máximo permitido (300 MB o 100 MP)." }, "updated_at": "…" }
  ]
}
```
- `status` del lote: `open` (recibiendo archivos) | `processing` (todo recibido, quedan ítems en cola) | `completed` | `completed_with_errors` | `cancelled` | `incomplete` (se cerró por inactividad sin recibir todo).
- `item.status`: `queued` | `processing` | `done` | `error` | `cancelled`. Con `done`, `classification` es el `Classification` completo.
- `queue.position`: la posición **efectiva**, considerando el reparto justo entre dueños (§7.0). `estimated_wait_seconds` = posición × el tiempo medio de procesamiento ÷ la cantidad de *workers* activos.

### 1.10 `Stats`
Ver §10.

### 1.11 `CatalogTaxon`
```json
{ "label_id": "…", "rank": "species", "class": "mammalia", "order": "perissodactyla", "family": "tapiridae",
  "genus": "tapirus", "species": "terrestris", "scientific_name": "Tapirus terrestris", "common_name": "tapir amazónico" }
```

---

## 2. Autenticación y cuenta

### 2.1 `POST /auth/register`
**Body**
```json
{ "email": "ana@wwf.org.bo", "password": "********", "full_name": "Ana Rojas", "institution": "WWF Bolivia" }
```
- `password`: 8 caracteres o más, con al menos una letra y un número.
- `institution` es opcional.
- Header opcional `X-Anon-Token`, para avisar en la respuesta si hay datos anónimos que se pueden asociar.

**Respuesta 201**
```json
{
  "user": { "…": "User" },
  "tokens": { "…": "AuthTokens" },
  "anon_session": { "has_data": true, "counts": { "classifications": 12, "camera_stations": 1, "projects": 0 } }
}
```
`anon_session` es `null` si no llegó `X-Anon-Token` o si el token ya no es válido.

**Errores:** `AUTH_EMAIL_TAKEN` (409), `AUTH_WEAK_PASSWORD` (422).

### 2.2 `POST /auth/login`
**Body:** `{ "email": "…", "password": "…" }` + `X-Anon-Token` opcional.
**Respuesta 200:** la misma forma que el registro.
**Errores:**
- `AUTH_INVALID_CREDENTIALS` (401): el mismo mensaje si falla el correo o la contraseña;
- `ACCOUNT_DISABLED` (403);
- `RATE_LIMITED` (429): 10 intentos por minuto por IP; 5 para la cuenta de admin.

### 2.3 `POST /auth/refresh`
**Body:** `{ "refresh_token": "…" }`
**Respuesta 200:** `{ "tokens": AuthTokens }`. **Rotación:** se emite un *refresh token* nuevo y el anterior queda revocado; si se reutiliza uno revocado, se revocan todos los de ese usuario.
**Errores:** `AUTH_TOKEN_INVALID` (401), `AUTH_TOKEN_EXPIRED` (401), `ACCOUNT_DISABLED` (403).

### 2.4 `POST /auth/logout`
**Body:** `{ "refresh_token": "…" }` · **Auth:** Bearer. **Respuesta 200:** `data: null`. Revoca ese *refresh token*.

### 2.5 `GET /auth/me`
**Respuesta 200:** `User`. **Errores:** `AUTH_TOKEN_EXPIRED` / `AUTH_TOKEN_INVALID` (401).

### 2.6 `PATCH /auth/me`
**Body:** `{ "full_name"?: "…", "institution"?: "…" }` → `User`. No se pueden cambiar el correo ni el rol.

### 2.7 `POST /auth/me/password`
**Body:** `{ "current_password": "…", "new_password": "…" }` → `data: null`. Revoca todos los *refresh tokens* salvo el actual.
**Errores:** `AUTH_INVALID_CREDENTIALS` (401), `AUTH_WEAK_PASSWORD` (422).

### 2.8 `POST /auth/password/forgot`
Sin auth. **Body:** `{ "email": "ana@wwf.org.bo" }`.
**Respuesta 200**, siempre la misma, exista o no el correo (CB-73):
```json
{ "message": "Si el correo está registrado, recibirás un enlace en unos minutos. Revisa también la carpeta de spam." }
```
- El correo se envía **en segundo plano** (trabajo de la cola), así el tiempo de respuesta no revela si la cuenta existe.
- **Límites:**
  - por correo: 3 por hora y 5 por día;
  - por IP: 10 por hora;
  - global: `EMAIL_DAILY_CAP` (por defecto 80, menor que el límite de 100 al día del plan gratuito de Resend) y `EMAIL_MONTHLY_CAP` (2500, de 3000).

  Si se supera un límite **por correo o por IP**, la respuesta sigue siendo la genérica (no se envía nada).

**Errores:**
- `EMAIL_TEMPORARILY_UNAVAILABLE` (503): solo si se alcanzó el tope **global**, que aplica a todos por igual (CB-76);
- `RATE_LIMITED` (429): abuso evidente por IP.

### 2.9 `GET /auth/password/reset/validate?token=…`
Sin auth. El front lo llama al abrir el enlace, antes de mostrar el formulario.
**Respuesta 200:** `{ "valid": true, "expires_at": "2026-11-07T15:34:05Z", "email_hint": "a***@wwf.org.bo" }` o `{ "valid": false }`.

### 2.10 `POST /auth/password/reset`
Sin auth. **Body:** `{ "token": "…", "new_password": "…" }`.
**Respuesta 200:** `data: null`, con el mensaje "Contraseña actualizada; inicia sesión".
- El token tiene 32 bytes aleatorios; en la BD se guarda solo su hash; dura `PASSWORD_RESET_TTL_MINUTES` (30) y es de **un solo uso**. Al pedir uno nuevo, los anteriores se invalidan.
- Al restablecer, se revocan todos los *refresh tokens* del usuario.

**Errores:** `AUTH_RESET_TOKEN_INVALID` (400: vencido, usado o inexistente), `AUTH_WEAK_PASSWORD` (422).

> **Requisito:** Resend exige un **dominio verificado** (registros DNS SPF y DKIM) para enviar a cualquier destinatario. Hasta tener el dominio (SEC-07), la recuperación por correo no funciona en producción, y existe el respaldo del admin (§13.7, enlace manual).

---

## 3. Sesión anónima

### 3.1 `POST /anon-sessions`
Sin auth. Se llama **una sola vez**, en la primera acción que guarda algo.
**Respuesta 201**
```json
{ "anon_token": "Qm9…(43 caracteres)", "expires_at": "2026-11-08T15:04:05Z", "data_retention": true }
```
**Errores:** `RATE_LIMITED` (5 sesiones por hora por IP).

### 3.2 `GET /anon-sessions/current`
**Auth:** `X-Anon-Token`.
**Respuesta 200**
```json
{ "status": "active", "expires_at": "2026-11-08T15:04:05Z", "data_retention": true,
  "counts": { "classifications": 12, "camera_stations": 1, "projects": 0 },
  "limits": { "max_files": 50, "max_camera_stations": 5, "used_files": 12, "used_camera_stations": 1 } }
```
**Errores:** `ANON_SESSION_EXPIRED` (401).

### 3.3 `POST /anon-sessions/claim`
**Auth:** Bearer **y** `X-Anon-Token`.
**Respuesta 200**
```json
{ "claimed": { "classifications": 12, "camera_stations": 1, "projects": 0 },
  "renamed_camera_stations": [ { "id": "c90…", "old_code": "CAM01", "new_code": "CAM01-2" } ] }
```
**Errores:** `ANON_SESSION_EXPIRED` (401), `ANON_SESSION_ALREADY_CLAIMED` (409). Si la sesión ya la reclamó el mismo usuario → 200 con `claimed` en 0.

### 3.4 `POST /anon-sessions/current/close`
**Auth:** `X-Anon-Token`. "No asociar": la sesión pasa a `expired`.
**Respuesta 200:** `{ "status": "expired", "data_retained": true }`. `data_retained` indica si los datos se conservan, según `anon_retain`.

---

## 4. Configuración pública y salud

### 4.1 `GET /config/public`
Sin auth. El front la carga al iniciar y la mantiene en memoria.
```json
{
  "anon_data_retention": true,
  "media": {
    "max_file_mb": 300,
    "max_video_seconds": 15,
    "image_extensions": ["jpg", "jpeg", "png", "bmp", "webp", "tiff"],
    "video_extensions": ["mp4", "avi", "mov", "mkv", "wmv", "flv", "webm"],
    "browser_duration_check_extensions": ["mp4", "mov", "webm"]
  },
  "anon_limits": { "max_files": 50, "max_camera_stations": 5 },
  "upload": { "max_parallel_files": 3, "max_pending_per_user": 500, "poll_interval_seconds": 3 },
  "password_recovery": { "enabled": true },
  "map": { "default_center": { "lat": -17.7833, "lng": -63.1821 }, "default_zoom": 8, "label": "Santa Cruz, Bolivia" },
  "import": { "max_package_mb": 200, "supported_format_versions": ["1.0"] },
  "app_version": "1.0.0"
}
```
**Formatos (D4 / `formats.py`):** la plataforma acepta hoy los formatos soportados por `wwm_pipeline/formats.py` en la IA (imágenes: `jpg, jpeg, png, bmp, webp, tiff`; videos: `mp4, avi, mov, mkv, wmv, flv, webm`), cubriendo las cámaras trampa habituales (Bushnell, Browning, Reconyx, Spypoint, Stealth Cam). Formatos adicionales (`heic/heif`, `tif`, `m4v`, `3gp`, `mts`, `m2ts`) quedan diferidos a `IA-16`.
- **Duración (`F1-D10`):** los videos mayores a 15 s **no se rechazan**: el front/back informa y la IA analiza únicamente los primeros `15.0 s`, devolviendo `truncated_at_seconds = 15.0` que el Back expone como warning `VIDEO_TRUNCATED`.
- **Peso máximo:** 300 MB por archivo (y hasta 100 MP por imagen), configurable con `MAX_FILE_MB`.

### 4.2 `GET /health` · `GET /health/ready`
- `/health` → `{ "status": "ok", "version": "1.0.0" }`.
- `/health/ready` → `{ "database": "ok", "ai": "ok", "storage": "ok" }`, o 503 si alguno falla.

---

## 5. Cámaras trampa

### 5.1 `GET /camera-stations`
| Query | Valores | Por defecto |
|---|---|---|
| `scope` | `mine` (propias, incluida la sesión anónima) · `public` (públicas de todos) · `all` (`mine` + `public`) | `all` |
| `view` | `full` (`CameraStation`) · `map` (`CameraStationMapItem`) | `full` |
| `project_id` | uuid | — |
| `bbox` | `minLng,minLat,maxLng,maxLat` | — |
| `q` | busca en `code` y `name` | — |
| `still_installed` | `true`/`false` | — |
| `page`, `page_size`, `sort` | `sort` ∈ `code`, `-created_at`, `-last_capture_at` | `-created_at` |

Con `view=map`, `page_size` admite hasta 2000.
**Respuesta 200:** `CameraStation[]` o `CameraStationMapItem[]` + `meta.pagination`.

### 5.2 `POST /camera-stations`
**Body:** `CameraStationInput`. **Respuesta 201:** `CameraStation`.
**Errores:**
- `CAMERA_CODE_TAKEN` (409), `CAMERA_INVALID_DATES` (422);
- `ANON_PUBLIC_NOT_ALLOWED` (422), `ANON_LIMIT_REACHED` (422);
- `PROJECT_NOT_FOUND` (404), `FORBIDDEN` (403, el proyecto no es tuyo);
- `AUTH_REQUIRED` (401, sin Bearer ni token anónimo).

### 5.3 `GET /camera-stations/{id}`
**Respuesta 200:** `CameraStation`. **Errores:** `CAMERA_NOT_FOUND` (404, también si es privada y ajena).

### 5.4 `PATCH /camera-stations/{id}`
**Header:** `If-Match: <version>`. **Body:** un `CameraStationInput` parcial. **Respuesta 200:** `CameraStation` (con `version` + 1).
**Errores:** los de 5.2, `FORBIDDEN` y `CONFLICT_STALE` (409).

### 5.5 `DELETE /camera-stations/{id}`
Borrado lógico de la cámara y sus clasificaciones; se quita de los proyectos. **Respuesta 204.**
**Errores:** `CAMERA_NOT_FOUND`, `FORBIDDEN`, `ENTITY_ALREADY_DELETED`.

### 5.6 `GET /camera-stations/{id}/stats`
Ver §10.

### 5.7 `GET /camera-stations/nearby?lat=&lng=&radius_m=30&exclude_id=&deployed_at=&retrieved_at=`
**Auth:** dueño (usuario o anónimo). El front lo llama **antes** de guardar una cámara nueva o al moverla (CB-01…CB-06). `radius_m` es como máximo 200.
**Respuesta 200**
```json
{
  "mine": [
    { "id": "c77…", "code": "CAM01", "name": "Quebrada norte", "distance_m": 12.4, "still_installed": true,
      "deployed_at": "2026-03-01T08:30:00", "retrieved_at": null, "classifications": 120,
      "same_location": false, "overlapping_period": true }
  ],
  "public_others": [
    { "id": "c99…", "code": "QN-A", "distance_band": "<10m",
      "owner": { "type": "user", "is_mine": false, "display_name": "Luis Pérez", "institution": "Museo Noel Kempff" } }
  ]
}
```
- `same_location`: `distance_m < 1`. `overlapping_period`: el periodo de la cámara existente se superpone con el `deployed_at` y `retrieved_at` de la *query*.
- **Nunca** incluye cámaras privadas de otros usuarios (CB-05).
- En `public_others` **no** se envía la distancia exacta, sino una banda (`distance_band`: `"<10m"`, `"<50m"`, `"<200m"`), para que no se pueda triangular la ubicación exacta con varias consultas (DD-17, CB-04).

### 5.8 `POST /camera-stations/{id}/redeploy`
Reinstalación en el mismo punto (CB-03). **Auth:** dueño.
**Body**
```json
{ "code": "CAM01-2", "deployed_at": "2026-05-02T09:00:00", "close_previous": true,
  "previous_retrieved_at": "2026-05-02T08:45:00", "observations": "Cambio de equipo" }
```
- `code` es opcional; si no llega, el back sugiere `<code>-2`, `-3`…
- `close_previous=true` y la anterior sigue instalada → se marca como retirada en `previous_retrieved_at` (por defecto, `deployed_at`).

**Respuesta 201:** `{ "camera_station": CameraStation, "previous": CameraStation }`. La nueva copia `latitude`, `longitude`, `name`, `visibility` y los **proyectos** de la anterior, y tiene `previous_camera_station_id` = `{id}`.
**Errores:** `CAMERA_CODE_TAKEN`, `CAMERA_INVALID_DATES` (la nueva colocación es anterior a la colocación de la previa).

### 5.9 `POST /camera-stations/{id}/time-offset` (P2)
Corrige el reloj de la cámara (CB-18). **Body:** `{ "offset_seconds": 3600, "from": null, "to": null, "reason": "Reloj en horario incorrecto" }`.
Aplica el desfase a `captured_at` de las clasificaciones con fuente `exif`, `container` o `filename` en ese rango, y guarda `captured_at_original`.
**Respuesta 200:** `{ "updated": 118 }`. Se registra en la auditoría.

---

## 6. Proyectos

### 6.1 `GET /projects`
Query: `scope` (`mine` / `public` / `all`), `q`, `page`, `page_size`, `sort`. **Respuesta 200:** `Project[]`.

### 6.2 `POST /projects`
**Body**
```json
{ "name": "Área protegida Amboró — 2026", "description": "…", "visibility": "private", "camera_station_ids": ["c77…"] }
```
- `name` ≤ 150 caracteres y es obligatorio.
- `camera_station_ids` es opcional y solo admite cámaras **propias**.

**Respuesta 201:** `ProjectDetail`.
**Errores:** `CAMERA_NOT_OWNED` (403), `ANON_PUBLIC_NOT_ALLOWED` (422), `AUTH_REQUIRED` (401).

### 6.3 `GET /projects/{id}`
**Respuesta 200:** `ProjectDetail`. Si el proyecto es público pero una de sus cámaras es privada, esa cámara **no se incluye** y no cuenta en sus estadísticas para otros usuarios (§10.4).
**Errores:** `PROJECT_NOT_FOUND` (404).

### 6.4 `PATCH /projects/{id}`
**Header:** `If-Match: <version>`. **Body:** `{ "name"?, "description"?, "visibility"? }` → `ProjectDetail`. **Errores:** `CONFLICT_STALE` (409).

### 6.5 `DELETE /projects/{id}`
Borrado lógico del proyecto; las cámaras **no se borran**. **Respuesta 204.**

### 6.6 `POST /projects/{id}/camera-stations`
**Body:** `{ "camera_station_id": "c78…" }` → `ProjectDetail`.
**Errores:** `CAMERA_NOT_OWNED` (403), `ALREADY_ASSOCIATED` (409), `CAMERA_NOT_FOUND`, `PROJECT_NOT_FOUND`.

### 6.7 `DELETE /projects/{id}/camera-stations/{camera_station_id}`
Desasocia la cámara (no la borra). **Respuesta 204.**

### 6.8 Crear una cámara dentro del proyecto
Es `POST /camera-stations` con `project_id` en el body (§5.2).

### 6.9 `GET /projects/{id}/stats`
Ver §10.

---

## 7. Clasificación: lotes, cola y archivos

### 7.0 Diseño (DD-12)

```
Navegador ──(1) subir archivo──▶ Back API ──(2) valida, sha256, temporal──▶ /data/tmp-uploads
   ▲                                │ (3) fila classifications status=queued + trabajo en Redis
   │  202 queued + posición          ▼
   │                         Redis (cola arq) ──▶ Worker(s) ──(4)──▶ IA /detect
   │                                                  │ (5) fotograma al storage, fila done, borra el temporal
   └──(6) polling cada 3 s: GET /classification-batches?active=true ◀──┘
```

1. **Subir es rápido:** el back valida (formato, firma, peso, duración, duplicado), guarda el archivo en un **temporal compartido** con el *worker*, crea la fila `classifications` con `status=queued`, encola el trabajo y responde **202** en segundos. El usuario puede seguir navegando.
2. **Analizar es asíncrono:** los *workers* (`arq` sobre Redis) llaman a la IA, guardan el fotograma y la fila `done` y **borran el temporal**. El archivo original nunca se conserva (DD-3).
3. **Cola justa:** cada dueño tiene como máximo `QUEUE_PER_OWNER_INFLIGHT` (2) trabajos despachados a la vez; el resto espera en su lista y se reparte por turnos (*round-robin*) entre dueños. Así, quien sube 3 archivos no espera detrás de un lote de 500.
4. **La BD es la fuente de verdad** del estado de cada ítem. Redis solo transporta la cola; si se pierde, el *reaper* re-encola desde la BD (CB-38).
5. **Seguimiento:** el front consulta cada `poll_interval_seconds` (3 s; 15 s con la pestaña oculta) mientras haya ítems pendientes. El tiempo real por SSE queda como mejora P2.

### 7.1 `POST /classification-batches`
**Auth:** dueño (Bearer o `X-Anon-Token`).
**Body**
```json
{ "camera_station_id": "c77…", "expected_files": 12 }
```
- `camera_station_id` es **obligatorio siempre**, también para el anónimo: se sube a una cámara registrada (TDR §3.1, D7).
- `expected_files` va de 1 a 500.

**Respuesta 201:** `Batch` con `status:"open"` e `items: []`.
**Errores:**
- `CAMERA_REQUIRED` (422);
- `CAMERA_NOT_FOUND` (404), `FORBIDDEN` (403);
- `ANON_LIMIT_REACHED` (422);
- `QUEUE_USER_LIMIT` (429): los pendientes actuales más `expected_files` superan `max_pending_per_user`.

### 7.2 `POST /classification-batches/{id}/files`
**multipart/form-data:**

| Campo | Tipo | Obligatorio | Uso |
|---|---|---|---|
| `file` | archivo | sí | Imagen o video |
| `client_index` | int | sí | Posición en la selección del usuario |
| `client_mtime` | datetime ISO | no | `File.lastModified` del navegador (respaldo de `captured_at`) |

**Respuesta:** un `BatchItem` en dos casos.
- **202**, el archivo es válido y quedó en cola: `status:"queued"`, con `queue.position`, `queue.estimated_wait_seconds` y `classification_id`.
- **200**, el archivo es inválido y **no** entra en la cola: `status:"error"` con uno de estos `error.code`:
  - `MEDIA_UNSUPPORTED_FORMAT`, `MEDIA_TOO_LARGE` (incluye > 300 MB o > 100 MP `too_many_pixels`), `MEDIA_DECODE_FAILED`; (si un video supera 15 s entra igual y genera warning `VIDEO_TRUNCATED` per `F1-D10`).
  - `DUPLICATE_FILE` (misma cámara), con `error.details[0].context.classification_id`;
  - `DUPLICATE_FILE_OTHER_CAMERA` (otra cámara del dueño), con `context.classification_id` y `context.camera_station_code`.

**Errores de la petición:**
- `BATCH_NOT_FOUND` (404), `BATCH_CLOSED` (409), `FORBIDDEN`;
- `ANON_SESSION_EXPIRED` (401);
- `QUEUE_USER_LIMIT` (429), `QUEUE_FULL` (503), `QUEUE_UNAVAILABLE` (503);
- `RATE_LIMITED`.

**Reintento:** volver a subir el mismo `client_index` reemplaza un ítem en `error` o `cancelled`.

### 7.3 `POST /classification-batches/{id}/complete`
Indica que el front terminó de **enviar**. El lote pasa a `processing` (o directamente al estado final si no quedan pendientes). Si nadie lo llama, a los `BATCH_IDLE_CLOSE_MINUTES` (60) sin archivos nuevos el lote se cierra como `incomplete`.
**Respuesta 200:** `Batch`.

### 7.4 `GET /classification-batches/{id}?since=<ISO>`
**Respuesta 200:** `Batch`. Con `since`, `items` trae solo los que cambiaron después de esa fecha (`updated_at`), lo que sirve para un *polling* eficiente.

### 7.5 `GET /classification-batches?active=true`
Lo usa la **bandeja de subidas** (`UploadTray`) en cualquier pantalla.
**Respuesta 200:** `Batch[]` **sin `items`**, con los lotes del dueño en estado `open` o `processing`, más los terminados en los últimos 10 minutos (para mostrar "Listo"). Sin `active`, devuelve el historial paginado (`camera_station_id`, `status`, `page`).

### 7.6 `POST /classification-batches/{id}/cancel`
Cancela todos los ítems `queued` del lote y borra sus temporales. Los `processing` terminan normalmente.
**Respuesta 200:** `Batch` (los cancelados quedan con `error.code = CANCELLED_BY_USER`).

### 7.7 `DELETE /classification-batches/{id}/items/{client_index}`
Cancela un ítem `queued`. **Respuesta 204.** **Errores:** `ITEM_NOT_CANCELLABLE` (409), si ya está `processing` o terminado.

### 7.8 `POST /classification-batches/{id}/items/{client_index}/retry`
Re-encola un ítem en `error` **si su temporal sigue disponible** (por ejemplo, tras `AI_UNAVAILABLE`). **Respuesta 202:** `BatchItem` `queued`.
**Errores:** `RETRY_FILE_UNAVAILABLE` (410): el temporal ya no existe y hay que volver a subir el archivo (§7.2).

### 7.9 Errores asíncronos del ítem
Los asigna el *worker* y el front los ve por *polling*:
- `AI_UNAVAILABLE`, `AI_TIMEOUT`, `AI_NOT_READY`, `AI_BAD_RESPONSE` (después de 2 reintentos automáticos);
- `MEDIA_DECODE_FAILED` (si lo detecta la IA);
- `STORAGE_WRITE_FAILED`;
- `PROCESSING_EXPIRED` (más de 24 h en cola);
- `CAMERA_DELETED`, `ACCOUNT_DISABLED`, `CANCELLED_BY_USER`.

## 8. Clasificaciones: consulta, fotograma y validación

### 8.1 `GET /classifications`
| Query | Valores |
|---|---|
| `camera_station_id` / `project_id` / `batch_id` | uuid. Sin ninguno, devuelve **todas las propias**. |
| `status` | `done` (por defecto) · `error` · `all` |
| `category` | `animal` · `person` · `vehicle` · `blank` (se pueden combinar con comas) |
| `validation_status` | `unvalidated` · `confirmed` · `corrected` · `rejected` (se pueden combinar con comas) |
| `taxon` | `label_id` de cualquier nivel (filtra por especie, género o familia efectiva) |
| `min_confidence` / `max_confidence` | 0–1 |
| `from` / `to` | sobre `captured_at` |
| `source` | `web` · `desktop` |
| `page`, `page_size`, `sort` | `sort` ∈ `-captured_at` (por defecto), `confidence`, `-created_at`, `file_name` |

**Respuesta 200:** `Classification[]` + paginación. Solo contenido propio o de cámaras públicas.

### 8.2 `GET /classifications/{id}` → `Classification`

### 8.3 `GET /classifications/{id}/evidence`
**Respuesta 200:** `image/jpeg` (binario), `Cache-Control: private, max-age=3600`.
- El front lo pide **con su cliente autenticado** (Bearer o `X-Anon-Token`) y lo muestra con `URL.createObjectURL(blob)`, porque una etiqueta `<img src>` no envía headers.
- **Errores** (en JSON): `CLASSIFICATION_NOT_FOUND` (404, también si no tiene permiso).

### 8.4 `PATCH /classifications/{id}`
**Body:** `{ "camera_station_id": "c77…" }`. Mueve la clasificación a otra cámara propia; por ejemplo, tras `DUPLICATE_FILE_OTHER_CAMERA` o si se subió a la cámara equivocada.
**Errores:** `CAMERA_NOT_OWNED`, `DUPLICATE_FILE` (409, si la cámara de destino ya tiene ese archivo).

### 8.5 `DELETE /classifications/{id}`
Borrado lógico, solo el dueño. **Respuesta 204.**

### 8.6 `PUT /classifications/{id}/validation`
**Auth:** dueño. Un anónimo también puede validar.

**Cómo lo presenta el front (FD G1):** muestra la especie propuesta (la de mayor confianza) con dos botones, **Correcto** y **No es esta especie**. El segundo despliega:
1. las `alternatives` (hasta 2), cada una con su %;
2. **Buscar otra especie** (en el catálogo);
3. **No está en el catálogo** (escribir el nombre);
4. **No hay ningún animal**.

**Body** según la acción:
```json
{ "action": "confirm", "notes": null }
{ "action": "correct", "label_id": "…", "correction_source": "alternative", "notes": null }
{ "action": "correct", "label_id": "…", "correction_source": "catalog", "notes": "Se ve la mancha de la cola" }
{ "action": "correct_unlisted", "suggested_name": "Leopardus colocolo (gato de las pampas)", "label_id": "<opcional: taxón superior, p. ej. el género Leopardus>", "notes": null }
{ "action": "reject", "notes": "Hojas movidas por el viento" }
{ "action": "discard_repeat", "repeat_of": "k91…", "notes": "Misma ráfaga" }
{ "action": "reset" }
```

| `action` | Requiere | Efecto |
|---|---|---|
| `confirm` | — | `validation.status = confirmed` |
| `correct` | `label_id` del catálogo + `correction_source` (`alternative` o `catalog`) | `corrected`; `corrected_taxonomy` sale del catálogo; `effective_taxonomy` = la corregida. Si la `category` era distinta de `animal`, pasa a `animal`. Con `correction_source=alternative`, el `label_id` debe estar en `alternatives` (si no → `VALIDATION_ERROR`). |
| `correct_unlisted` | `suggested_name` (3–120 caracteres); `label_id` opcional (un taxón **superior** del catálogo) | `corrected_unlisted`. Con `label_id`, `effective_taxonomy` = ese taxón (cuenta en `by_genus` y `by_family`); sin él, `effective_taxonomy = null` y cuenta en `unidentified_to_species.unlisted`. El nombre queda registrado para futuras mejoras (§13.11). |
| `reject` | — | `rejected`: no cuenta en las estadísticas (la IA se equivocó: no hay animal) |
| `discard_repeat` | `repeat_of` (el ID que se conserva, de la misma cámara) | `discarded_repeat`: es el mismo animal que otro registro de la ráfaga. **No cuenta como avistamiento**, pero **no** se considera un error de la IA (no entra en `model_feedback`) y conserva su taxonomía. Para varios a la vez, §8.8. |
| `reset` | — | Vuelve a `unvalidated`; si era `discarded_repeat`, vuelve a contar |

- Cada cambio se agrega a `validation_history` (quién, cuándo, la acción y los valores) y se puede consultar con `GET /classifications/{id}?include=validation_history`.
- **Respuesta 200:** `Classification`.

**Errores:** `CATALOG_TAXON_NOT_FOUND` (422), `CLASSIFICATION_NOT_FOUND` (404), `CLASSIFICATION_NOT_DONE` (409: todavía está en cola o con error), `VALIDATION_ERROR`.

### 8.7 `POST /classifications/validation-batch`
**Body:** `{ "ids": ["k91…", "k92…"], "action": "confirm", "notes": null }`. Solo admite `confirm`, `reject` y `reset`, con 500 IDs como máximo.
**Respuesta 200**
```json
{ "updated": 48, "skipped": [ { "id": "k99…", "code": "CLASSIFICATION_NOT_FOUND" } ] }
```

### 8.8 Ráfagas: registros repetidos del mismo animal (D10)
**Regla:** por defecto, **cada archivo con el animal cuenta como un avistamiento** (opción A). El sistema **sugiere** posibles ráfagas, pero **nunca descarta solo**: decide el investigador, que puede conservar todos o dejar uno (o los que quiera).

**`GET /classifications/burst-candidates`**
| Query | Valores | Por defecto |
|---|---|---|
| `camera_station_id` **o** `project_id` | uuid | obligatorio uno |
| `window_minutes` | 1–60 | `BURST_WINDOW_MINUTES` (5) |
| `include_reviewed` | `true` incluye los grupos ya revisados | `false` |

Agrupa las clasificaciones `done` de **la misma cámara**, con la **misma taxonomía efectiva** (especie, o el nivel alcanzado), no `rejected`, y con `captured_at` a ≤ `window_minutes` del registro anterior del grupo (encadenado). Excluye las que tienen `captured_at_source = upload_time`. Solo devuelve grupos de 2 o más.

**Respuesta 200**
```json
[
  {
    "group_key": "c77…|5c7ce479…|2026-03-15T04:22:10",
    "camera_station_id": "c77…", "camera_station_code": "CAM01",
    "taxonomy": { "scientific_name": "Panthera onca", "common_name": "jaguar", "rank": "species" },
    "start": "2026-03-15T04:22:10", "end": "2026-03-15T04:23:02", "span_seconds": 52,
    "suggested_keep_id": "k91…",
    "items": [
      { "id": "k91…", "file_name": "IMG_001.JPG", "captured_at": "2026-03-15T04:22:10", "confidence": 0.95, "validation_status": "unvalidated", "evidence_url": "/api/v1/classifications/k91…/evidence" },
      { "id": "k92…", "file_name": "IMG_002.JPG", "captured_at": "2026-03-15T04:22:31", "confidence": 0.91, "validation_status": "unvalidated", "evidence_url": "…" },
      { "id": "k93…", "file_name": "IMG_003.JPG", "captured_at": "2026-03-15T04:23:02", "confidence": 0.88, "validation_status": "unvalidated", "evidence_url": "…" }
    ]
  }
]
```
`suggested_keep_id` es el de **mayor confianza**. Es solo una sugerencia: el usuario puede elegir otro.

**`POST /classifications/repeat-batch`**
```json
{ "keep_ids": ["k91…"], "discard_ids": ["k92…", "k93…"], "notes": "Misma ráfaga" }
```
- Las `discard_ids` pasan a `discarded_repeat` con `repeat_of` = el primer `keep_id`.
- Las `keep_ids` que estaban `unvalidated` pasan a `confirmed`; las que ya estaban validadas no cambian.
- Todas deben ser de la **misma cámara** y del dueño. Si no → `REPEAT_MIXED_CAMERAS` (422).
- `keep_ids` necesita al menos uno (`REPEAT_KEEP_REQUIRED`, 422). Para conservar **todas**, se usa `POST /classifications/repeat-batch/dismiss` `{ "group_key": "…" }`, que marca el grupo como revisado y deja de sugerirlo, sin cambiar ningún registro.

**Respuesta 200:** `{ "kept": 1, "discarded": 2 }`. Para deshacer, se usa `reset` en cada una (§8.6).

---

## 9. Catálogo de especies

### 9.1 `GET /catalog/species`
Sin auth. Query: `q` (2 caracteres o más; busca en el nombre común, el científico, el género y la familia, sin distinguir tildes), `rank` (opcional), `limit` (≤ 50, por defecto 20).
**Respuesta 200:** `CatalogTaxon[]`, ordenado por coincidencia y luego por `rank` (las especies primero).
**Origen:** `speciesnet_catalog.json` (3538 taxones de SpeciesNet, `IA-19`), sincronizado desde `GET /api/v1/catalog` (soporta `ETag`/`304`). Nota: `common_name` viene en inglés por defecto (con traducción progresiva en español vía `common_names_es.csv` / campo ES cuando aplique).

### 9.2 `GET /catalog/species/{label_id}` → `CatalogTaxon` · `CATALOG_TAXON_NOT_FOUND` (404).

---

## 10. Estadísticas

### 10.1 Endpoints
`GET /camera-stations/{id}/stats` · `GET /projects/{id}/stats`

| Query | Valores | Por defecto |
|---|---|---|
| `from` / `to` | fecha (sobre `captured_at`) | — |
| `only_validated` | `true` → solo `confirmed` y `corrected` | `false` |
| `source` | `web` · `desktop` | ambos |
| `sections` | lista: `totals,richness,non_animal,taxa,by_camera,by_month,by_hour,effort` | todas |

### 10.2 Respuesta
```json
{
  "scope": "project",
  "scope_id": "p12…",
  "scope_name": "Área protegida Amboró — 2026",
  "filters": { "from": null, "to": null, "only_validated": false, "source": null },
  "generated_at": "2026-11-07T15:04:05Z",
  "totals": {
    "files_processed": 240, "files_with_fauna": 150, "files_without_fauna": 82, "files_error": 8,
    "sightings": 144, "validated": 90, "corrected": 12, "rejected": 3, "discarded_repeat": 6, "pending_validation": 57
  },
  "richness": { "species": 19, "genera": 15, "families": 11 },
  "non_animal": { "person": 9, "vehicle": 2, "blank": 71 },
  "by_species": [
    { "label_id": "…", "scientific_name": "Panthera onca", "common_name": "jaguar", "genus": "panthera", "family": "felidae",
      "count": 12, "pct": 8.0, "validated": 8, "mean_confidence": 0.91,
      "first_seen": "2026-03-02T21:10:00", "last_seen": "2026-03-28T03:44:00", "camera_stations": 2 }
  ],
  "by_genus":  [ { "label_id": "…", "name": "panthera", "family": "felidae", "count": 12, "pct": 8.0 } ],
  "by_family": [ { "label_id": "…", "name": "felidae", "count": 18, "pct": 12.0 } ],
  "unidentified_to_species": { "genus": 6, "family": 3, "order": 1, "class": 0, "unlisted": 2 },
  "by_camera": [ { "camera_station_id": "c77…", "code": "CAM01", "sightings": 87, "species": 14,
                   "species_counts": [ { "label_id": "…", "count": 9 } ] } ],
  "by_month": [ { "month": "2026-03", "sightings": 150 } ],
  "by_hour":  [ { "hour": 0, "sightings": 11 }, { "hour": 1, "sightings": 9 } ],
  "effort": { "trap_days": 312.5, "sightings_per_100_trap_days": 48.0, "camera_stations_without_retrieval": 1 }
}
```

### 10.3 Reglas de cálculo (iguales en pantalla, Excel y PDF)
- **Avistamiento** = una clasificación con `status=done`, `category=animal`, `validation.status ∉ {rejected, discarded_repeat}` y no borrada. Se usa `effective_taxonomy`. Los `discarded_repeat` se informan en `totals.discarded_repeat`.
- `by_species` solo incluye las filas con `rank=species`; `by_genus`, las de `rank ≤ genus` agrupadas por género; `by_family`, las de `rank ≤ family` agrupadas por familia. Las que no llegan a especie se informan en `unidentified_to_species`, para que la suma cierre.
- `pct` = `count / totals.sightings × 100`, con 1 decimal.
- `by_month` y `by_hour` excluyen `captured_at_source = upload_time`.
- `effort.trap_days` = Σ por cámara de (`retrieved_at` o el fin del filtro o ahora) − (`deployed_at` o el inicio del filtro), en días.
- `by_camera` solo aparece en un proyecto.
- **Proyecto visto por otro usuario:** solo suma las cámaras públicas del proyecto.
- Los arreglos van ordenados por `count` de mayor a menor.
- `unidentified_to_species.unlisted`: correcciones `correct_unlisted` sin taxón superior.
- Las filas en `queued`, `processing` o `cancelled` **no** cuentan en nada; solo cuentan las `done` y las `error` (estas en `files_error`).

### 10.4 Errores
`CAMERA_NOT_FOUND`, `PROJECT_NOT_FOUND` (404).

---

## 11. Reportes Excel y PDF

`GET /reports/excel` · `GET /reports/pdf`

| Query | Regla |
|---|---|
| `camera_station_id` **o** `project_id` | Uno de los dos es obligatorio |
| `from`, `to`, `only_validated`, `source` | Los mismos de §10 |

**Respuesta 200:** el binario directo (sin envoltura).
- Excel: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- PDF: `application/pdf`.
- `Content-Disposition: attachment; filename="WWM_<codigo-o-proyecto>_<AAAAMMDD>.xlsx"`.

**Contenido del Excel:**

| Hoja | Columnas |
|---|---|
| Resumen | Alcance, nombre, filtros, fecha de generación, `request_id`, versión del modelo, totales, riqueza, clases no animales |
| Por especie | Nombre científico, nombre común, género, familia, avistamientos, %, validados, confianza media, primera y última fecha, n.º de cámaras |
| Por género | Género, familia, avistamientos, % |
| Por familia | Familia, avistamientos, % |
| Clasificaciones | Archivo, código de cámara, latitud, longitud, fecha de captura, fuente de la fecha, minuto:segundo del fotograma, **cuenta como avistamiento (sí/no)**, **repetido de (archivo)**, categoría, especie, género y familia de la IA, confianza, estado de validación, especie, género y familia validados, notas, origen (web o escritorio), modelo |

**Ubicación:** si quien descarga no es el dueño de la cámara, latitud y longitud van redondeadas (DD-17).

**PDF:** portada (alcance, filtros, fecha), totales, gráficos de barras por especie, género y familia (las 15 con más avistamientos) y las mismas tablas resumidas. El pie lleva la página y el `request_id`.

**Errores** (en JSON): `REPORT_EMPTY` (404), `CAMERA_NOT_FOUND`, `PROJECT_NOT_FOUND`, `VALIDATION_ERROR` (sin alcance).

---

## 12. Importación desde la app de escritorio

El formato del paquete está en [PAQUETE_ESCRITORIO.md](PAQUETE_ESCRITORIO.md).

### 12.1 `POST /imports/desktop`
**Auth:** Bearer (solo con sesión). **multipart:** `package` (`.wwm.zip`) + **o** `camera_station_id` (uuid de una cámara propia) **o** `create_camera=true` (crear la cámara con los datos de `manifest.camera`, [PKG §2](PAQUETE_ESCRITORIO.md#2-manifestjson)).
Valida todo **sin escribir clasificaciones** y deja el paquete en un temporal durante 1 h.
**Respuesta 201**
```json
{
  "import_id": "i33…",
  "status": "preview",
  "expires_at": "2026-11-07T16:04:05Z",
  "camera_station": { "id": "c77…", "code": "CAM01", "deployed_at": "2026-03-01T08:30:00", "retrieved_at": null },
  "package": { "format_version": "1.0", "app_version": "1.2.0", "camera_code": "CAM01",
               "created_at": "2026-03-20T15:04:05Z", "model": { "detector": "MDv5a", "classifier": "speciesnet-4.0.2a", "sampling": "15fps@0-2s+6fps/max120", "pipeline_version": "0.1.0" } },
  "counts": { "lines": 340, "new": 320, "duplicates": 12, "invalid": 8, "outside_deployment_range": 3,
              "by_category": { "animal": 87, "person": 4, "vehicle": 1, "blank": 240 } },
  "camera_code_matches": true,
  "camera_from_package": { "code": "CAM01", "name": "Quebrada norte", "latitude": -17.78345, "longitude": -63.18211,
                           "deployed_at": "2026-03-01T08:30:00", "retrieved_at": "2026-03-19T17:00:00", "still_installed": false,
                           "observations": "Sobre sendero de tapires", "complete": true },
  "matching_camera_station_id": "c77…",
  "issues": [
    { "line": 17, "file_name": "CAM01_20260302_101500.mp4", "severity": "error", "code": "CATALOG_TAXON_NOT_FOUND", "message": "…" },
    { "line": 40, "file_name": "CAM01_20260229_235900.mp4", "severity": "warning", "code": "CAPTURE_OUTSIDE_DEPLOYMENT", "message": "…" }
  ]
}
```
Se devuelven hasta 200 `issues`; el resto se resume en `counts`.

**Errores:**
- `IMPORT_INVALID_PACKAGE` (422), `IMPORT_UNSUPPORTED_VERSION` (422), `IMPORT_CHECKSUM_MISMATCH` (422);
- `IMPORT_TOO_LARGE` (413);
- `IMPORT_ALREADY_IMPORTED` (409): el mismo `package_sha256` ya se importó en esa cámara. `details.context.import_id` apunta al anterior;
- `CAMERA_NOT_OWNED` (403), `AUTH_REQUIRED` (401).

### 12.2 `POST /imports/{id}/confirm`
**Body:** `{ "include_warnings": true, "camera": null }`. Las líneas con advertencia se importan si `include_warnings` es `true`; las inválidas nunca.
- Si la vista previa se hizo con `create_camera=true`, la cámara se crea **en la confirmación** con los datos de `manifest.camera`. `camera` admite un `CameraStationInput` para completar o corregir esos datos (por ejemplo, ubicar el punto en el mapa si el paquete no trae coordenadas). Se aplican las mismas reglas y advertencias que en §5.2 (`nearby`, códigos, fechas).
- `matching_camera_station_id`: si el `code` del paquete coincide con una cámara propia, el front la sugiere en lugar de crear otra.
**Respuesta 200**
```json
{ "import_id": "i33…", "status": "completed", "batch_id": "b55…", "imported": 320, "skipped_duplicates": 12, "skipped_invalid": 8 }
```
**Errores:** `IMPORT_PREVIEW_EXPIRED` (410), `IMPORT_NOT_FOUND` (404), `VALIDATION_ERROR` (los datos de cámara del paquete están incompletos y no llegó `camera`), `CAMERA_CODE_TAKEN` (409).

### 12.3 `DELETE /imports/{id}`
Cancela una vista previa y borra el temporal. **Respuesta 204.**

### 12.4 `GET /imports`
Query: `camera_station_id`, `page`. **Respuesta 200**
```json
[ { "import_id": "i33…", "status": "completed", "camera_station_id": "c77…", "camera_code": "CAM01",
    "package_created_at": "2026-03-20T15:04:05Z", "imported": 320, "created_at": "2026-11-07T15:04:05Z" } ]
```

---

## 13. Administración

**Todas** las rutas `/admin/*` exigen Bearer con `role=admin`; si no → `ADMIN_REQUIRED` (403). La matriz de privacidad está en [FLUJOS_SISTEMA §11.1](../FLUJOS_SISTEMA.md#111-matriz-de-privacidad-qué-ve-el-administrador). **Nunca** se devuelve contenido de cámaras o proyectos privados; para eso hay solo conteos.

**Ubicación para el admin:** las cámaras **públicas de usuarios** se le muestran **redondeadas** (no es su dueño, DD-17); las **anónimas**, exactas, porque no tienen un dueño identificable al que proteger y son datos de la plataforma.

**`scope`** en los endpoints de contenido: `anonymous` · `public` · `all` (= `anonymous` + `public`; **nunca** incluye lo privado). Por defecto `all`.

### 13.1 `GET /admin/stats`
Query: `from`, `to` (sobre `created_at` para las cifras de plataforma y sobre `captured_at` para la fauna), `scope`, `include_deleted`.
```json
{
  "users": { "total": 85, "active": 80, "disabled": 5, "with_classifications": 52,
             "new_by_month": [ { "month": "2026-11", "count": 12 } ] },
  "anon_sessions": { "total": 430, "active": 12, "claimed": 61, "expired": 357, "conversion_rate": 14.2,
                     "avg_classifications_per_session": 6.3 },
  "content": {
    "camera_stations": { "public": 40, "private": 95, "anonymous": 210, "deleted": 7 },
    "projects": { "public": 10, "private": 22, "anonymous": 30, "deleted": 1 },
    "classifications": { "total": 18400, "by_source": { "web": 12100, "desktop": 6300 },
                         "errors_by_code": { "AI_TIMEOUT": 14, "MEDIA_DECODE_FAILED": 22 } },
    "storage": { "evidence_files": 9100, "evidence_gb": 0.91 }
  },
  "model_feedback": {
    "validated": 3400,
    "confirmed_pct": 81.2,
    "corrected_with_alternative_pct": 7.5,
    "corrected_from_catalog_pct": 5.1,
    "corrected_unlisted_pct": 0.9,
    "rejected_pct": 5.3,
    "top_confusions": [ { "predicted": "Puma concolor", "corrected_to": "Panthera onca", "count": 14 } ]
  },
  "anon_retention": {
    "current": true,
    "retained_classifications": 2600,
    "purged": { "classifications": 340, "camera_stations": 12, "projects": 3, "frames": 300 }
  },
  "fauna": { "…": "la misma forma que Stats (§10.2) sin by_camera, calculada con el scope pedido" },
  "fauna_map": [ { "latitude": -17.78, "longitude": -63.18, "sightings": 87, "scope": "public" } ]
}
```
- `content.*.private` son **solo conteos**, que incluyen lo privado; `classifications.total` también los incluye como número. `fauna` y `fauna_map` **excluyen siempre** lo privado.
- En `fauna_map`, las coordenadas se redondean a 2 decimales (~1 km) para el mapa de calor.
- `model_feedback` mide el acierto real de la IA a partir de las validaciones, solo con datos anónimos y públicos. Los `discarded_repeat` **no** cuentan como error ni como acierto (se excluyen).
- Las especies del bloque `fauna` se cuentan **una vez por `sha256`** aunque dos usuarios hayan subido el mismo archivo (CB-52).

### 13.2 `GET /admin/camera-stations`
Query: `scope`, `q`, `anon_session_id`, `include_deleted`, `page`.
**Respuesta 200:** `CameraStation[]`, con `owner.display_name = "Anónimo #a91f"` para las anónimas y los campos extra `is_deleted`, `deleted_at`, `deleted_reason`.

### 13.3 `GET /admin/classifications`
Query: las mismas de §8.1 + `scope`, `anon_session_id`, `include_deleted`.
**Respuesta 200:** `Classification[]` + `is_deleted`, `deleted_at`, `deleted_reason`, `owner_type`.

### 13.4 `GET /admin/classifications/{id}/evidence`
JPEG. Se aplica la misma matriz: lo privado → 404.

### 13.5 `GET /admin/anon-sessions`
Query: `status`, `from`, `to`, `page`.
```json
[ { "id": "s01…", "label": "Anónimo #a91f", "status": "expired", "created_at": "…", "last_activity_at": "…",
    "counts": { "classifications": 8, "camera_stations": 1, "projects": 0 }, "retained": true, "is_deleted": false } ]
```

### 13.6 Borrado lógico y restauración
| Ruta | Body | Respuesta |
|---|---|---|
| `POST /admin/{entity}/{id}/delete` | `{ "reason": "Archivos de prueba" }` | `{ "deleted": { "classifications": 8, "camera_stations": 1, "projects": 0 } }` |
| `POST /admin/{entity}/{id}/restore` | `{ "reason": "…" }` (opcional) | `{ "restored": { … } }` |
| `POST /admin/delete-batch` | `{ "entity": "classifications", "ids": ["…"], "reason": "…" }` | `{ "deleted": {…}, "skipped": [ { "id": "…", "code": "…" } ] }` |

- `entity`: `classifications` · `camera-stations` · `projects` · `anon-sessions`.
- **Cascada:** borrar una cámara borra sus clasificaciones; borrar una sesión anónima borra todo lo suyo. Restaurar devuelve **solo** lo que se borró en esa misma operación.

**Errores:**
- `DELETE_REASON_REQUIRED` (422);
- `ENTITY_ALREADY_DELETED` (409), `ENTITY_NOT_DELETED` (409);
- 404 si el recurso es privado o no existe.

### 13.7 Usuarios
| Ruta | Respuesta |
|---|---|
| `GET /admin/users?q=&status=active\|disabled&page=` | `[ { …User, "counts": { "camera_stations_public": 3, "camera_stations_private": 5, "projects_public": 1, "projects_private": 2, "classifications": 410 } } ]` |
| `POST /admin/users/{id}/deactivate` `{reason}` | `User` (`is_active: false`) |
| `POST /admin/users/{id}/reactivate` `{reason?}` | `User` |

| `POST /admin/users/{id}/password-reset-link` `{reason}` | `{ "reset_url": "https://<dominio>/restablecer?token=…", "expires_at": "…" }`. Es el respaldo cuando no hay correo (CB-76); el admin se lo entrega al usuario por otro medio. **No** permite ver ni fijar la contraseña. Queda en la auditoría. |

**Errores:** `CANNOT_DEACTIVATE_SELF` (409), `DELETE_REASON_REQUIRED` (422).

### 13.8 Configuración
- `GET /admin/settings` → `{ "anon_data_retention": { "value": true, "updated_by": "admin@…", "updated_at": "…" } }`.
- `PUT /admin/settings` `{ "anon_data_retention": false, "reason": "Pedido de WWF" }` → la misma forma.

**Errores:** `SETTING_INVALID` (422), `DELETE_REASON_REQUIRED` (422, el motivo es obligatorio).

### 13.9 `GET /admin/audit-log`
Query: `action`, `entity_type`, `from`, `to`, `page`.
```json
[ { "id": "…", "action": "update_setting", "entity_type": "system_settings", "entity_id": "anon_data_retention",
    "old_value": true, "new_value": false, "reason": "Pedido de WWF", "created_at": "…", "request_id": "…" } ]
```

### 13.10a `GET /admin/queue`
El estado de la cola de procesamiento y del envío de correos:
```json
{ "workers": { "active": 1, "busy": 1 }, "queued": 42, "processing": 1,
  "avg_processing_seconds": 52.3, "oldest_queued_age_seconds": 610,
  "by_owner": [ { "label": "Ana Rojas", "queued": 30 }, { "label": "Anónimo #a91f", "queued": 12 } ],
  "last_hour": { "done": 64, "error": 2 },
  "email": { "sent_today": 3, "daily_cap": 80, "sent_month": 41, "monthly_cap": 2500 } }
```

### 13.10 `GET /admin/reports/excel`
Query: `scope`, `from`, `to`. Contiene las hojas *Plataforma* (usuarios, sesiones, contenido), *Fauna por especie*, *Por género*, *Por familia* y *Clasificaciones* (solo anónimas y públicas; las anónimas van con `Anónimo #xxxx`). Queda registrado en la auditoría.

### 13.11 `GET /admin/unlisted-suggestions`
Los nombres sugeridos por los usuarios para especies que no están en el catálogo (CB-65), agrupados (normalizados, sin tildes y en minúsculas), solo de datos anónimos y públicos:
```json
[ { "suggested_name": "leopardus colocolo", "count": 4, "parent_taxon": "Leopardus", "first_at": "…", "last_at": "…", "classification_ids": ["…"] } ]
```
Sirve como insumo para una futura ampliación del catálogo, que está fuera del alcance del TDR. También va como hoja *Sugerencias* en `GET /admin/reports/excel`.

---

## 14. Matriz de permisos

| Recurso / acción | Visitante sin token | Anónimo (dueño) | Usuario (dueño) | Otro usuario | Admin |
|---|---|---|---|---|---|
| Ver cámaras y proyectos públicos y sus stats | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ver lo privado ajeno | ❌ (404) | ❌ | ❌ | ❌ | ❌ (solo conteos) |
| Ver los datos anónimos ajenos | ❌ | ❌ | ❌ | ❌ | ✅ |
| Crear una cámara o un proyecto | crea una sesión anónima primero | ✅ privado | ✅ | — | ✅ (como usuario) |
| Marcar como público | ❌ | ❌ | ✅ | — | — |
| Clasificar | crea una sesión anónima primero | ✅ (límites) | ✅ | — | ✅ |
| Validar o corregir | ❌ | ✅ | ✅ | ❌ | ❌ |
| Exportar Excel o PDF | solo lo público | ✅ lo suyo | ✅ | solo lo público | `/admin/reports` |
| Importar un paquete de escritorio | ❌ | ❌ (`AUTH_REQUIRED`) | ✅ | — | ✅ |
| Borrado lógico | — | ✅ lo suyo | ✅ lo suyo | ❌ | ✅ lo anónimo y lo público |
| Restaurar | — | ❌ | ❌ | ❌ | ✅ |

---

## 15. Resumen de endpoints

| # | Método | Ruta | Auth | Flujo |
|---|---|---|---|---|
| 1 | POST | `/auth/register` | — | FL-01 |
| 2 | POST | `/auth/login` | — | FL-02 |
| 3 | POST | `/auth/refresh` | — | FL-02 |
| 4 | POST | `/auth/logout` | Bearer | FL-02 |
| 5 | GET / PATCH | `/auth/me` | Bearer | FL-02 |
| 6 | POST | `/auth/me/password` | Bearer | FL-02 |
| 6b | POST · GET · POST | `/auth/password/forgot`, `/auth/password/reset/validate`, `/auth/password/reset` | — | FL-14 |
| 7 | POST | `/anon-sessions` | — | FL-03 |
| 8 | GET | `/anon-sessions/current` | Anon | FL-03 |
| 9 | POST | `/anon-sessions/claim` | Bearer + Anon | FL-04 |
| 10 | POST | `/anon-sessions/current/close` | Anon | FL-04 |
| 11 | GET | `/config/public` | — | Todos |
| 12 | GET | `/health`, `/health/ready` | — | — |
| 13 | GET / POST | `/camera-stations` | — / dueño | FL-05, FL-13 |
| 14 | GET / PATCH / DELETE | `/camera-stations/{id}` | según visibilidad / dueño | FL-06 |
| 15 | GET | `/camera-stations/{id}/stats` | según visibilidad | FL-11 |
| 15b | GET | `/camera-stations/nearby` | dueño | FL-05 |
| 15c | POST | `/camera-stations/{id}/redeploy` | dueño | FL-15 |
| 15d | POST | `/camera-stations/{id}/time-offset` (P2) | dueño | FL-06 |
| 16 | GET / POST | `/projects` | — / dueño | FL-07 |
| 17 | GET / PATCH / DELETE | `/projects/{id}` | según visibilidad / dueño | FL-07 |
| 18 | POST | `/projects/{id}/camera-stations` | dueño | FL-07 |
| 19 | DELETE | `/projects/{id}/camera-stations/{cid}` | dueño | FL-07 |
| 20 | GET | `/projects/{id}/stats` | según visibilidad | FL-11 |
| 21 | GET / POST | `/classification-batches` | dueño | FL-08 |
| 22 | GET | `/classification-batches/{id}` | dueño | FL-08 |
| 23 | POST | `/classification-batches/{id}/files` | dueño | FL-08 |
| 24 | POST | `/classification-batches/{id}/complete` | dueño | FL-08 |
| 24b | POST · DELETE · POST | `/classification-batches/{id}/cancel`, `/items/{i}`, `/items/{i}/retry` | dueño | FL-09 |
| 25 | GET | `/classifications` | dueño / público | FL-08, FL-10 |
| 26 | GET / PATCH / DELETE | `/classifications/{id}` | dueño (GET: también lo público) | FL-08, FL-10 |
| 27 | GET | `/classifications/{id}/evidence` | dueño / público | FL-08 |
| 28 | PUT | `/classifications/{id}/validation` | dueño | FL-10 |
| 29 | POST | `/classifications/validation-batch` | dueño | FL-10 |
| 29b | GET · POST · POST | `/classifications/burst-candidates`, `/classifications/repeat-batch`, `/repeat-batch/dismiss` | dueño | FL-16 |
| 30 | GET | `/catalog/species`, `/catalog/species/{label_id}` | — | FL-10 |
| 31 | GET | `/reports/excel`, `/reports/pdf` | según visibilidad | FL-12 |
| 32 | POST | `/imports/desktop` | Bearer | FL-23 |
| 33 | POST | `/imports/{id}/confirm` | Bearer | FL-23 |
| 34 | DELETE | `/imports/{id}` | Bearer | FL-23 |
| 35 | GET | `/imports` | Bearer | FL-23 |
| 36 | GET | `/admin/stats` | Admin | FL-40 |
| 37 | GET | `/admin/camera-stations`, `/admin/classifications`, `/admin/anon-sessions` | Admin | FL-41 |
| 38 | GET | `/admin/classifications/{id}/evidence` | Admin | FL-41 |
| 39 | POST | `/admin/{entity}/{id}/delete`, `/restore`, `/admin/delete-batch` | Admin | FL-42 |
| 40 | GET / POST | `/admin/users`, `/admin/users/{id}/deactivate`, `/reactivate`, `/password-reset-link` | Admin | FL-43, FL-14 |
| 41 | GET / PUT | `/admin/settings` | Admin | FL-44 |
| 42 | GET | `/admin/audit-log`, `/admin/reports/excel` | Admin | FL-40…44 |
| 43 | GET | `/admin/queue` | Admin | FL-45 |
| 44 | GET | `/admin/unlisted-suggestions` | Admin | FL-46 |

**Se eliminan** del back actual: `/users/*` (lo reemplazan `/auth/me` y `/admin/users`), `/users/me/claim`, `/users/me/history`, `/videos/*`, `/individuals/*`, `/media-files/*`, `/camera-stations/{id}/files`, `/species/*`, `/reports/indicators/*`, `/projects/{id}/collaborators` y el `/ai/*` público.
