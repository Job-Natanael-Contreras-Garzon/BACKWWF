---
title: "13B - Guía Paso a Paso en Swagger (Bloques 1 al 11 — 80 Rutas Operativas)"
date: 2026-11-21
project: BACKWWF
version: "2.0.0"
status: active
tags: [testing, swagger, e2e, endpoints, frontend-handover, wwf]
---

# 13B. Guía y Secuencia Paso a Paso en Swagger (Bloques 1 al 11)

> [!NOTE]
> **Paneles compañeros:**
> - Anota y copia tus tokens/UUIDs en **`[[13A_Hoja_Tokens_IDs_y_Arranque]]`**.
> - Consulta las pruebas específicas del contenedor de IA real (`:8001`), carga de 50 archivos, CLI/Resend/Backups (Bloque 12) y tabla de certificación final en **`[[13C_Protocolo_IA_Real_Operacion_y_Certificacion]]`**.

---

## Envoltura Estándar para Frontend (Referencia para Miguel)

Salvo los endpoints binarios (`GET /classifications/{id}/evidence`, `GET /admin/classifications/{id}/evidence`, `GET /reports/excel`, `GET /reports/pdf`, `GET /admin/reports/excel`) y los `204 No Content` (`DELETE`), **todas las respuestas HTTP (`2xx`, `4xx`, `5xx`)** usan `ApiResponse` (`app/core/responses.py`):

```json
{
  "status": "success",
  "data": { "...": "..." },
  "message": "OK",
  "error": null,
  "meta": {
    "request_id": "c4f1a8b0-...",
    "timestamp": "2026-11-21T16:00:00Z",
    "pagination": { "page": 1, "page_size": 50, "total": 1, "total_pages": 1 },
    "warnings": []
  }
}
```
Y en caso de error (`status: "error"`):
```json
{
  "status": "error",
  "data": null,
  "message": "Mensaje legible para mostrar en UI.",
  "error": {
    "code": "CODIGO_ESTABLE_CATALOGO",
    "flow": "FL-05",
    "details": [{ "field": "body.email", "code": "value_error", "message": "...", "context": {} }]
  },
  "meta": {
    "request_id": "c4f1a8b0-...",
    "timestamp": "2026-11-21T16:00:00Z",
    "pagination": null,
    "warnings": []
  }
}
```

---

## Bloque 1: Salud del Sistema, Configuración Pública y Catálogo SpeciesNet (`FL-10`, `/`, `#11`, `#12`, `#30`)

**Situación:** Simulamos el arranque inicial de la SPA: verifica que el backend esté vivo, que PostgreSQL, `LocalStorage` y el contenedor de IA real en `:8001` estén en `"ok"`, descarga la configuración pública y consulta el catálogo SpeciesNet en RAM (3538 taxones).

### 1.1 `GET /` — Raíz informativa del servicio
- **Auth:** Ninguna.
- **Esperado (`200 OK`):** `data: {"app_name": "Fauna Monitoring API", "version": "dev", "environment": "development", "docs_url": "/docs"}`, `message: "Backend de Monitoreo de Fauna WWF operativo."`.
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y verificado.

### 1.2 `GET /api/v1/health` — Liveness probe (`#12`)
- **Auth:** Ninguna.
- **Esperado (`200 OK`):** `data: {"status": "ok", "version": "dev"}`.
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y verificado.

### 1.3 `GET /api/v1/health/ready` — Readiness probe contra IA Real (`#12`)
- **Auth:** Ninguna.
- **Esperado (`200 OK` con IA real cargada en `:8001`):** `data: {"database": "ok", "ai": "ok", "storage": "ok"}`, `message: "Servicio listo."`.
- **Prueba de Error (`503 SERVICE_UNAVAILABLE`):** Si la IA está apagada o en estado `loading`, responde HTTP `503`, `error.code: "SERVICE_UNAVAILABLE"`, `data: {"database": "ok", "ai": "down", "storage": "ok"}`.
- [ ] **Camino Feliz (`200 OK` — 3 servicios en `"ok"`) y Caso Error (`503`):** Ejecutados y verificados.

### 1.4 `GET /api/v1/config/public` — Configuración pública para Frontend (`#11`)
- **Auth:** Ninguna.
- **Esperado (`200 OK`):**
  ```json
  {
    "anon_data_retention": true,
    "media": {
      "max_file_mb": 300,
      "max_video_seconds": 15,
      "image_extensions": ["bmp", "jpeg", "jpg", "png", "tiff", "webp"],
      "video_extensions": ["avi", "flv", "mkv", "mov", "mp4", "webm", "wmv"],
      "browser_duration_check_extensions": ["mp4", "mov", "webm"]
    },
    "anon_limits": { "max_files": 50, "max_camera_stations": 5 },
    "upload": { "max_parallel_files": 3, "max_pending_per_user": 500, "poll_interval_seconds": 3 },
    "password_recovery": { "enabled": false },
    "map": {
      "default_center": { "lat": -17.7833, "lng": -63.1821 },
      "default_zoom": 8,
      "label": "Santa Cruz, Bolivia"
    },
    "import": { "max_package_mb": 200, "supported_format_versions": ["1.0"] },
    "app_version": "dev"
  }
  ```
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y verificado.

### 1.5 `GET /api/v1/catalog/species` — Búsqueda en Catálogo SpeciesNet (`#30`)
- **Auth:** Ninguna.
- **Query Params:** `q=Jaguár` *(con tilde y mayúscula para verificar normalización `CA-2`)*, `limit=10`.
- **Esperado (`200 OK`):** Lista de taxones donde aparece primero *Panthera onca* (`common_name: "jaguar"`, `rank: "species"`). Guarda su `label_id` en **`13A`** como **`LABEL_ID_CATALOGO`**.
- **Pruebas de Error:** `q=a` (1 letra) → `422 VALIDATION_ERROR`; `limit=99` (> 50) → `422 VALIDATION_ERROR`.
- [ ] **Camino Feliz (`200 OK`) y Casos Error (`422`):** Ejecutados y guardado `LABEL_ID_CATALOGO`.

### 1.6 `GET /api/v1/catalog/species/{label_id}` — Detalle de un taxón por ID (`#30`)
- **Auth:** Ninguna · **Path Param:** `<LABEL_ID_CATALOGO>`.
- **Esperado (`200 OK`):** Objeto con `label_id, rank, class, order, family, genus, species, scientific_name, common_name`.
- **Prueba de Error (`404 CATALOG_TAXON_NOT_FOUND`):** `label_id=00000000-no-existe` → `404 CATALOG_TAXON_NOT_FOUND`.
- [ ] **Camino Feliz (`200 OK`) y Caso Error (`404`):** Ejecutados y verificados.

---

## Bloque 2: Ciclo de Vida de Sesión Anónima y Límites sin Cuenta (`FL-03`, `#7`, `#8`, `#10`, `#13`)

**Situación:** Un visitante pulsa *"Probar sin cuenta"*. Probamos abrir y cerrar una sesión descartable; luego creamos **`ANON_TOKEN_1`** (con una cámara `CAM-01` para probar el reclamo y renombrado `-2` en el Bloque 3) y **`ANON_TOKEN_2`** (con una cámara `CAM-ANON-02` que NO reclamaremos para que el Admin la audite en el Bloque 11).

> [!WARNING]
> Verifica que el botón **`Authorize`** de Swagger esté **desconectado (`Logout`)** durante todo el Bloque 2.

### 2.1 `POST /api/v1/anon-sessions` — Crear sesión anónima descartable (`#7`)
- **Auth:** Ninguna · **Body:** Ninguno.
- **Esperado (`201 Created`):** `message: "Sesión temporal iniciada."`, `data: {"anon_token": "<TOKEN_DESCARTABLE>", "expires_at": "...", "data_retention": true}`.
- [ ] **Camino Feliz (`201 Created`):** Ejecutado.

### 2.2 `POST /api/v1/anon-sessions/current/close` — Cerrar sesión temporal (`#10`)
- **Header:** `X-Anon-Token: <TOKEN_DESCARTABLE>`.
- **Esperado (`200 OK`):** `message: "Sesión temporal cerrada."`, `data: {"status": "expired", "data_retained": true}`.
- **Prueba de Error (`401 ANON_SESSION_EXPIRED`):** Repetir la llamada (o `GET /current`) con `<TOKEN_DESCARTABLE>` → `401 ANON_SESSION_EXPIRED`.
- [ ] **Camino Feliz (`200 OK`) y Caso Error (`401 ANON_SESSION_EXPIRED`):** Ejecutados y verificados.

### 2.3 Crear Sesión Anónima #1 (`ANON_TOKEN_1`) para Reclamo y poblarla (`#7`, `#8`, `#13`)
1. `POST /api/v1/anon-sessions` → Guarda `data.anon_token` en **`13A`** como **`ANON_TOKEN_1`**.
2. `POST /api/v1/camera-stations` con Header `X-Anon-Token: <ANON_TOKEN_1>`:
   ```json
   {
     "code": "CAM-01",
     "name": "Cámara Anónima Río Beni",
     "latitude": -14.833333,
     "longitude": -64.900000,
     "deployed_at": "2026-10-01T08:00:00",
     "still_installed": true,
     "retrieved_at": null,
     "visibility": "private",
     "observations": "Instalada en modo sin cuenta"
   }
   ```
   - **Esperado (`201 Created`):** Guarda `data.id` en **`13A`** como **`ANON_CAM_ID`**.
3. **Prueba de Error (`422 ANON_PUBLIC_NOT_ALLOWED` — `CB-20b`):** Enviar `"visibility": "public"` y `"code": "CAM-PUB-FAIL"` con `X-Anon-Token: <ANON_TOKEN_1>` → `422 ANON_PUBLIC_NOT_ALLOWED`.
4. `GET /api/v1/anon-sessions/current` (`#8`) con `X-Anon-Token: <ANON_TOKEN_1>` → `200 OK` (`counts.camera_stations: 1`, `limits.max_camera_stations: 5`).
- [ ] **Sesión `ANON_TOKEN_1`, cámara `ANON_CAM_ID` (`201`), error `422` y `/current` (`200`):** Ejecutados y verificados.

### 2.4 Crear Sesión Anónima #2 (`ANON_TOKEN_2`) para el Panel Admin (Bloque 11)
1. `POST /api/v1/anon-sessions` → Guarda `data.anon_token` en **`13A`** como **`ANON_TOKEN_2`**.
2. `POST /api/v1/camera-stations` con Header `X-Anon-Token: <ANON_TOKEN_2>`:
   ```json
   {
     "code": "CAM-ANON-02",
     "name": "Cámara Anónima Chapare",
     "latitude": -16.950000,
     "longitude": -65.400000,
     "deployed_at": "2026-10-12T07:00:00",
     "still_installed": true,
     "retrieved_at": null,
     "visibility": "private"
   }
   ```
   - **Esperado (`201 Created`):** Guarda `data.id` en **`13A`** como **`ANON_CAM_2_ID`**.
- [ ] **Sesión `ANON_TOKEN_2` y cámara `ANON_CAM_2_ID` creadas (`201`):** Ejecutado.

---

## Bloque 3: Autenticación JWT, Detección de Reuso de Refresh, Perfil y Claim Anónimo (`FL-01..04`, `FL-14`, `#1`–`#6b`, `#9`)

**Situación:** Registramos a **Usuario A** (dueño principal, enviando `X-Anon-Token: <ANON_TOKEN_1>` para recibir el hint `anon_session.has_data: true`) y a **Usuario B** (tercero para pruebas DD-17, IDOR y carga). Probamos rotación y detección de robo de `refresh_token` (`CB-78`), perfil, contraseña y el reclamo `/anon-sessions/claim` con renombrado automático `CAM-01` → `CAM-01-2`.

### 3.1 `POST /api/v1/auth/register` — Registro de Usuario A con Hint de Sesión Anónima (`#1`)
- **Header opcional:** `X-Anon-Token: <ANON_TOKEN_1>`
- **Body JSON:**
  ```json
  {
    "email": "investigador.a@wwf.org",
    "password": "Fauna2026Password",
    "full_name": "Dr. Armando Rivera",
    "institution": "WWF Bolivia"
  }
  ```
- **Esperado (`201 Created`):**
  - Guarda `data.user.id` como **`USER_A_ID`**, `data.tokens.access_token` como **`USER_A_ACCESS`** y `data.tokens.refresh_token` como **`USER_A_REFRESH`**.
  - `data.anon_session`: `{"has_data": true, "counts": {"classifications": 0, "camera_stations": 1, "projects": 0}}`.
- **Pruebas de Error:**
  - Email duplicado en mayúsculas `"INVESTIGADOR.A@wwf.org"` → `409 AUTH_EMAIL_TAKEN` (`CB-72`).
  - Contraseña débil `"password": "corta"` → `422 AUTH_WEAK_PASSWORD`.
- [ ] **Camino Feliz (`201 Created`) y Casos Error (`409`, `422`):** Ejecutados y guardados `USER_A_ID`, `USER_A_ACCESS`, `USER_A_REFRESH`.

### 3.2 `POST /api/v1/auth/register` — Registro de Usuario B (Tercero)
- **Header `X-Anon-Token`:** Vacío.
- **Body JSON:**
  ```json
  {
    "email": "investigador.b@wwf.org",
    "password": "Fauna2026Password",
    "full_name": "Dra. Elena Gutiérrez",
    "institution": "Instituto de Ecología"
  }
  ```
- **Esperado (`201 Created`):** Guarda `data.user.id` como **`USER_B_ID`** y `data.tokens.access_token` como **`USER_B_ACCESS`**.
- [ ] **Usuario B registrado (`201 Created`):** Ejecutado y guardados `USER_B_ID` y `USER_B_ACCESS`.

### 3.3 `POST /api/v1/auth/login` — Inicio de sesión (`#2`)
- **Body JSON:** `{"email": "investigador.a@wwf.org", "password": "Fauna2026Password"}` → `200 OK` (actualiza `USER_A_ACCESS` y `USER_A_REFRESH`).
- **Prueba de Error (`401 AUTH_INVALID_CREDENTIALS`):** Enviar `"password": "PasswordIncorrecto123"` → `401 AUTH_INVALID_CREDENTIALS`.
- [ ] **Camino Feliz (`200 OK`) y Caso Error (`401`):** Ejecutados y verificados.

### 3.4 `POST /api/v1/auth/refresh` — Rotación y Detección de Reuso (`#3`, `CB-78`)
1. **Rotación (`200 OK`):** Enviar `{"refresh_token": "<USER_A_REFRESH_VIEJO>"}` → Devuelve `<USER_A_REFRESH_NUEVO>`.
2. **Detección de Reuso (`401 AUTH_TOKEN_INVALID` — `CB-78`):** Volver a enviar `{"refresh_token": "<USER_A_REFRESH_VIEJO>"}` → `401 AUTH_TOKEN_INVALID` (`"Se detectó reutilización de sesión. Inicia sesión nuevamente."`).
3. **Revocación total:** Enviar `{"refresh_token": "<USER_A_REFRESH_NUEVO>"}` → También da `401 AUTH_TOKEN_INVALID`.
4. **Re-login limpio:** Ejecutar `POST /api/v1/auth/login` con Usuario A, actualizar `USER_A_ACCESS` y `USER_A_REFRESH` en **`13A`** y pegar `USER_A_ACCESS` en el botón **`Authorize`** de Swagger.
- [ ] **Rotación (`200`), Detección de Reuso (`401 CB-78`) y Re-login en `Authorize`:** Ejecutados y verificados.

### 3.5 `GET /api/v1/auth/me` y `PATCH /api/v1/auth/me` — Perfil (`#5`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- `GET /api/v1/auth/me` → `200 OK` (sin token da `401 AUTH_REQUIRED`).
- `PATCH /api/v1/auth/me` con `{"full_name": "Dr. Armando Rivera M.", "institution": "WWF Bolivia - Dirección Científica"}` → `200 OK`.
- **Prueba de Error (`422 VALIDATION_ERROR`):** Enviar `{"full_name": "   "}` o campo extra `{"role": "admin"}` → `422`.
- [ ] **Camino Feliz (`GET` y `PATCH` → `200 OK`) y Casos Error (`401`, `422`):** Ejecutados y verificados.

### 3.6 `POST /api/v1/auth/me/password` — Cambio de contraseña (`#6`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Prueba de Error (`401 AUTH_INVALID_CREDENTIALS`):** `{"current_password": "MalPassword1", "new_password": "NuevaPassword2026"}` → `401 AUTH_INVALID_CREDENTIALS`.
- **Camino Feliz (`200 OK`):** `{"current_password": "Fauna2026Password", "new_password": "Fauna2026Password"}` → `200 OK`.
- [ ] **Caso Error (`401`) y Camino Feliz (`200 OK`):** Ejecutados y verificados.

### 3.7 `POST /api/v1/auth/logout` — Cierre de sesión (`#4`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Camino Feliz (`200 OK`):** `{"refresh_token": "<USER_A_REFRESH>"}` → `200 OK`.
- **Prueba de Error (`401 AUTH_TOKEN_INVALID`):** `{"refresh_token": "token-invalido"}` → `401`.
- [ ] **Camino Feliz (`200 OK`) y Caso Error (`401`):** Ejecutados y verificados.

### 3.8 Recuperación de Contraseña (`#6b` — `FL-14`)
- Con `PASSWORD_RECOVERY_ENABLED=false` (por defecto):
  1. `POST /api/v1/auth/password/forgot` con `{"email": "investigador.a@wwf.org"}` → `503 EMAIL_TEMPORARILY_UNAVAILABLE`.
  2. `GET /api/v1/auth/password/reset/validate?token=token-falso` → `200 OK`, `data: {"valid": false, "expires_at": null, "email_hint": null}` *(sigue activo sin correo para soportar los enlaces manuales del Admin en el Bloque 11.8)*.
  3. `POST /api/v1/auth/password/reset` con `{"token": "token-falso", "new_password": "Fauna2026Password"}` → `400 AUTH_RESET_TOKEN_INVALID`.
- [ ] **Verificados `503` en `/forgot`, `200 valid:false` en `/validate` y `400` en `/reset`:** Ejecutados y verificados.

### 3.9 `POST /api/v1/anon-sessions/claim` — Reclamar Sesión Anónima #1 con Renombrado `-2` (`#9`, `FL-04`)
1. **Paso previo:** Con `Bearer <USER_A_ACCESS>`, crea en la cuenta de Usuario A una cámara pública llamada `"CAM-01"` (`POST /api/v1/camera-stations`):
   ```json
   {
     "code": "CAM-01",
     "name": "Cámara Principal Madidi",
     "latitude": -14.500000,
     "longitude": -67.500000,
     "deployed_at": "2026-09-01T10:00:00",
     "still_installed": true,
     "retrieved_at": null,
     "visibility": "public",
     "observations": "Cámara pública principal de Usuario A"
   }
   ```
   - **Esperado (`201 Created`):** Guarda `data.id` en **`13A`** como **`CAM_PUB_ID`**.
2. **Ejecutar `POST /api/v1/anon-sessions/claim`:**
   - **Auth:** `Bearer <USER_A_ACCESS>` + Header `X-Anon-Token: <ANON_TOKEN_1>`.
   - **Esperado (`200 OK`):** `claimed.camera_stations: 1` y `renamed_camera_stations: [{"id": "<ANON_CAM_ID>", "old_code": "CAM-01", "new_code": "CAM-01-2"}]`.
3. **Idempotencia (`200 OK`):** Repetir con Usuario A devuelve conteos en `0`.
4. **Conflicto (`409 ANON_SESSION_ALREADY_CLAIMED`):** Cambiar `Authorize` a `USER_B_ACCESS` y enviar `X-Anon-Token: <ANON_TOKEN_1>` → `409`. *(Volver a poner `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`200 OK` con renombre a `CAM-01-2`), Idempotencia (`200`) y Conflicto (`409`):** Ejecutados y verificados.

---

## Bloque 4: Estaciones de Cámara Trampa, Privacidad DD-17, `nearby`, `redeploy` y `time-offset` (`FL-05..06`, `FL-13`, `FL-15`, `#13`–`#15d`)

### 4.1 `POST /api/v1/camera-stations` — Crear cámara privada con Warning `CAMERA_COORDS_SUSPECT` (`#13`, `CB-07`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Body JSON:**
  ```json
  {
    "code": "CAM-PRIV-01",
    "name": "Cámara Privada Coordenadas Invertidas",
    "latitude": -64.900000,
    "longitude": -16.500000,
    "deployed_at": "2026-10-10T09:00:00",
    "still_installed": false,
    "retrieved_at": "2026-11-01T17:00:00",
    "visibility": "private",
    "observations": "Retirada tras 22 días"
  }
  ```
- **Esperado (`201 Created`):** Guarda `data.id` en **`13A`** como **`CAM_PRIV_ID`**. En `meta.warnings` aparece `CAMERA_COORDS_SUSPECT`.
- **Pruebas de Error:** `"code": "cam-01"` → `409 CAMERA_CODE_TAKEN` (`CB-13`); `"deployed_at": "2026-10-10T09:00:00Z"` → `422 VALIDATION_ERROR`; `"still_installed": true` con `"retrieved_at"` no nulo → `422 CAMERA_INVALID_DATES`.
- [ ] **Camino Feliz (`201 Created` + warning) y Casos Error (`409`, `422`):** Ejecutados y guardado `CAM_PRIV_ID`.

### 4.2 `GET /api/v1/camera-stations` y `GET /api/v1/camera-stations/{camera_id}` — Privacidad DD-17 (`#13`, `#14`)
- **Como Dueño (`USER_A_ACCESS`):** `GET /api/v1/camera-stations?scope=mine&view=full` y `view=map` → coordenadas exactas (`location_precision: "exact"`).
- **Como Tercero (`USER_B_ACCESS`):**
  - `GET /api/v1/camera-stations/{CAM_PUB_ID}` → `200 OK` con coordenadas a 2 decimales (`-14.5`, `-67.5`) y `location_precision: "approx_1km"`.
  - `GET /api/v1/camera-stations/{CAM_PRIV_ID}` → `404 CAMERA_NOT_FOUND` (`CB-05`).
  - `GET /api/v1/camera-stations?bbox=1,2,3` → `422 VALIDATION_ERROR`.
  - *(Volver a `USER_A_ACCESS`).*
- [ ] **Verificados listado, DD-17 (`approx_1km`), S1 (`404` en privada ajena) y error `bbox` (`422`):** Ejecutados y verificados.

### 4.3 `PATCH /api/v1/camera-stations/{camera_id}` — Edición con `If-Match` (`#14`, `CB-15`)
- **Auth:** `Bearer <USER_A_ACCESS>` · **Path Param:** `<CAM_PUB_ID>` · **Header:** `If-Match: 1`.
- **Body JSON:** `{"name": "Cámara Principal Madidi (Actualizada)", "latitude": -14.512345, "longitude": -67.512345}` → `200 OK` (`version: 2`).
- **Pruebas de Error:** Repetir con `If-Match: 1` → `409 CONFLICT_STALE`; `If-Match: abc` → `422 VALIDATION_ERROR`; con `USER_B_ACCESS` y `If-Match: 2` → `403 FORBIDDEN`. *(Volver a `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`200 OK`) y Casos Error (`409`, `422`, `403`):** Ejecutados y verificados.

### 4.4 `GET /api/v1/camera-stations/nearby` — Cercanía (`#15b`, `CB-04`, `CB-05`)
- **Como Dueño (`USER_A_ACCESS`):** `?lat=-14.512345&lng=-67.512345&radius_m=200` → `data.mine` incluye `CAM-01` con `distance_m: 0.0`.
- **Como Tercero (`USER_B_ACCESS`):** Misma consulta → `data.mine: []`, `data.public_others` incluye `CAM-01` solo con `"distance_band": "<10m"`. *(Volver a `USER_A_ACCESS`).*
- [ ] **Cercanía como Dueño (`distance_m`) y como Tercero (`distance_band`):** Ejecutados y verificados.

### 4.5 `POST /api/v1/camera-stations/{camera_id}/redeploy` — Reinstalación (`#15c`, `FL-15`, `CB-03`)
- **Auth:** `Bearer <USER_A_ACCESS>` · **Path Param:** `<ANON_CAM_ID>` (`CAM-01-2`).
- **Body JSON:**
  ```json
  {
    "code": null,
    "deployed_at": "2026-11-05T10:00:00",
    "close_previous": true,
    "previous_retrieved_at": "2026-11-05T09:30:00",
    "observations": "Cambio de baterías y SD en el mismo punto"
  }
  ```
- **Esperado (`201 Created`):** Crea `CAM-01-3` (guarda su ID como **`CAM_REDEPLOY_ID`**) y cierra `CAM-01-2`.
- **Prueba de Error (`422 CAMERA_INVALID_DATES`):** `deployed_at` anterior a la cámara previa → `422`.
- [ ] **Camino Feliz (`201 Created`) y Caso Error (`422`):** Ejecutados y guardado `CAM_REDEPLOY_ID`.

### 4.6 `DELETE /api/v1/camera-stations/{camera_id}` — Borrado Lógico en Cascada (`#14`, `CB-21`)
- **Auth:** `Bearer <USER_A_ACCESS>` · **Path Param:** `<CAM_REDEPLOY_ID>` → `204 No Content` (repetir da `409 ENTITY_ALREADY_DELETED`).
- [ ] **Camino Feliz (`204`) y Caso Error (`409`):** Ejecutados y verificados.

### 4.7 `POST /api/v1/camera-stations/{camera_id}/time-offset` — Corregir la hora de la cámara (`#15d`, `CB-18`, D14)
> Ejecuta el camino feliz justo después del Bloque 6, cuando `<CAM_PUB_ID>` ya tenga clasificaciones con fecha de `exif`, `container` o `filename`.
- **Auth:** `Bearer <USER_A_ACCESS>` · **Path Param:** `<CAM_PUB_ID>`.
- **Body JSON:** `{"offset_seconds": 3600, "from": null, "to": null, "reason": "Reloj en horario incorrecto"}` → `200 OK`, `data: {"updated": <n>}` (y en `GET /classifications/{id}` verás `captured_at` desplazado 1 h y `captured_at_original` con la fecha original).
- **Pruebas de Error:** `offset_seconds: 0` → `422 VALIDATION_ERROR`; con `USER_B_ACCESS` sobre `<CAM_PUB_ID>` → `403 FORBIDDEN`; sobre `<CAM_PRIV_ID>` → `404 CAMERA_NOT_FOUND`.
- [ ] **Camino Feliz (`200 OK`) y Casos Error (`422`, `403`, `404`):** Ejecutados y verificados.

---

## Bloque 5: Proyectos y Asociación N:M Segura de Cámaras Propias (`FL-07`, `#16`–`#19`)

### 5.1 `POST /api/v1/projects` — Crear proyecto (`#16`, `CB-23`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Body JSON:**
  ```json
  {
    "name": "Monitoreo Jaguar Madidi 2026",
    "description": "Evaluación estacional con cámaras trampa",
    "visibility": "public",
    "camera_station_ids": ["<CAM_PUB_ID>"]
  }
  ```
- **Esperado (`201 Created`):** Guarda `data.id` en **`13A`** como **`PROJ_PUB_ID`**.
- **Prueba de Error IDOR (`403 CAMERA_NOT_OWNED` — `CB-23`):** Con `USER_B_ACCESS`, intentar crear proyecto incluyendo `["<CAM_PUB_ID>"]` → `403 CAMERA_NOT_OWNED`. *(Volver a `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`201 Created`) y Caso Error IDOR (`403`):** Ejecutados y guardado `PROJ_PUB_ID`.

### 5.2 `POST /api/v1/projects/{project_id}/camera-stations` — Asociar cámara privada (`#18`, `CB-24`)
- **Auth:** `Bearer <USER_A_ACCESS>` · **Path Param:** `<PROJ_PUB_ID>`.
- **Body JSON:** `{"camera_station_id": "<CAM_PRIV_ID>"}` → `200 OK`. Repetir da `409 ALREADY_ASSOCIATED`.
- [ ] **Camino Feliz (`200 OK`) y Caso Error (`409`):** Ejecutados y verificados.

### 5.3 `GET /api/v1/projects` y `GET /api/v1/projects/{project_id}` — Dueño vs Tercero (`#16`, `#17`, `CB-20`)
- **Como Dueño (`USER_A_ACCESS`):** `GET /api/v1/projects/{PROJ_PUB_ID}` muestra `counts.camera_stations: 2`.
- **Como Tercero (`USER_B_ACCESS` — `CB-20`):** Muestra `counts.camera_stations: 1` (solo `CAM-01`, redondeada). *(Volver a `USER_A_ACCESS`).*
- [ ] **Visibilidad Dueño (2 cámaras) vs Tercero `CB-20` (1 cámara):** Ejecutadas y verificadas.

### 5.4 `PATCH /api/v1/projects/{project_id}` — Actualizar con `If-Match` (`#17`)
- **Auth:** `Bearer <USER_A_ACCESS>` · **Header:** `If-Match: 1`.
- **Body JSON:** `{"name": "Monitoreo Jaguar Madidi 2026 - Fase I", "description": "Actualizado"}` → `200 OK` (`version: 2`). Repetir con `If-Match: 1` → `409 CONFLICT_STALE`.
- [ ] **Camino Feliz (`200 OK`) y Caso Error (`409`):** Ejecutados y verificados.

### 5.5 `DELETE /api/v1/projects/{project_id}/camera-stations/{camera_station_id}` y `DELETE /api/v1/projects/{project_id}` (`#17`, `#19`, `CB-27`)
- Desasociar `<ANON_CAM_ID>` (no asociada) → `404 CAMERA_NOT_FOUND`.
- Desasociar `<CAM_PRIV_ID>` → `204 No Content`, y volver a asociarla con `POST /api/v1/projects/{PROJ_PUB_ID}/camera-stations` para el Bloque 8.
- Crear proyecto temporal y borrarlo con `DELETE /api/v1/projects/{ID_TEMP}` → `204 No Content` (repetir da `409 ENTITY_ALREADY_DELETED`, cámaras intactas `CB-27`).
- [ ] **Desasociación (`204`/`404`) y Borrado lógico (`204`/`409`):** Ejecutados y verificados.

---

## Bloque 6: Lotes de Clasificación, Subida a Cola `arq`/Redis, Procesamiento con IA Fauna Real y Evidencias (`FL-08..09`, `#21`–`#24b`, `#27`)

> [!IMPORTANT]
> Ejecuta aquí las llamadas HTTP en Swagger y marca en paralelo las verificaciones profundas del motor IA en **`[[13C_Protocolo_IA_Real_Operacion_y_Certificacion]] §1`**.

### 6.1 `POST /api/v1/classification-batches` — Abrir Lote en `CAM_PUB_ID` (`#21`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Body JSON:** `{"camera_station_id": "<CAM_PUB_ID>", "expected_files": 10}` → `201 Created`. Guarda `data.id` en **`13A`** como **`BATCH_1_ID`**.
- **Pruebas de Error:** `{"camera_station_id": null, "expected_files": 2}` → `422 CAMERA_REQUIRED`; con `USER_B_ACCESS` sobre `<CAM_PUB_ID>` → `403 FORBIDDEN`. *(Volver a `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`201 Created`) y Casos Error (`422`, `403`):** Ejecutados y guardado `BATCH_1_ID`.

### 6.2 `POST /api/v1/classification-batches/{batch_id}/files` — Subida Multipart a la IA Real (`#23`)
En `<BATCH_1_ID>` con `Bearer <USER_A_ACCESS>`:
1. **`client_index = 0` (`animal_1.jpg`, `client_mtime = 2026-10-15T14:20:00`):** → `202 Accepted`. Guarda `data.classification_id` como **`CLS_ANIMAL_1_ID`**.
2. **`client_index = 1` (`animal_2.jpg`, `client_mtime = 2026-10-15T14:22:00`):** → `202 Accepted`. Guarda `data.classification_id` como **`CLS_ANIMAL_2_ID`**.
3. **`client_index = 2` (`vacia_blank.jpg`):** → `202 Accepted` (saldrá `category: "blank"`).
4. **`client_index = 3` (`persona.jpg` o `vehiculo.jpg`):** → `202 Accepted` (saldrá `category: "person" | "vehicle"`, `taxonomy: null`).
5. **`client_index = 4` (`video_15s.mp4`):** → `202 Accepted`.
6. **`client_index = 5` (`video_largo.mp4` > 16 s):** → `202 Accepted` con warning `VIDEO_TRUNCATED`.
7. **Rechazo por ítem (`client_index = 6` con `foto.heic`, `falso.jpg` o repitiendo `animal_1.jpg`):** → **`200 OK`** con `data.status: "error"`, `data.classification_id: null` y `data.error.code` = `MEDIA_UNSUPPORTED_FORMAT` o `DUPLICATE_FILE` (`CB-50`).
8. **Formatos adicionales (`client_index = 6, 7, 8` con `.avi`, `.mkv`, `.flv`):** → `202 Accepted`.
9. **Error de protocolo:** `client_index = 15` (`>= expected_files`) → `422 VALIDATION_ERROR`.
- [ ] **Subidas (`202 Accepted`), Rechazos por ítem (`200 OK` con `status: "error"`) y Error `422`:** Ejecutados y guardados `CLS_ANIMAL_1_ID` y `CLS_ANIMAL_2_ID`.

### 6.3 `POST /api/v1/classification-batches/{batch_id}/complete`, Polling `GET /classification-batches/{batch_id}` y `GET /classifications/{id}/evidence` (`#22`, `#24`, `#27`)
1. `POST /api/v1/classification-batches/{BATCH_1_ID}/complete` → `200 OK`. Intentar subir otro archivo al lote cerrado → `409 BATCH_CLOSED`.
2. `GET /api/v1/classification-batches/{BATCH_1_ID}` → Consultar hasta que los ítems estén en `status: "done"`. Probar `?since=2099-01-01T00:00:00Z` → `data.items: []`.
3. `GET /api/v1/classification-batches?active=true` → `200 OK` (`items: null`).
4. `GET /api/v1/classifications/{CLS_ANIMAL_1_ID}/evidence` (`#27`) → `200 OK` (`image/jpeg` recodificado sin EXIF). Con UUID inexistente → `404 CLASSIFICATION_NOT_FOUND`.
- [ ] **Cierre (`200`/`409`), Polling (`done` y `?since=`), Bandeja (`active=true`) y Evidencia (`200 image/jpeg` / `404`):** Ejecutados y verificados.

### 6.4 Cancelación y Reintento (`#24b`)
- `DELETE /api/v1/classification-batches/{BATCH_1_ID}/items/0` (sobre ítem `done`) → `409 ITEM_NOT_CANCELLABLE` (`CB-40`).
- `POST /api/v1/classification-batches/{BATCH_1_ID}/items/0/retry` (sobre ítem `done`) → `200 OK` idempotente.
- Crear un lote nuevo y cancelarlo con `POST /api/v1/classification-batches/{NUEVO_ID}/cancel` → `200 OK` (`status: "cancelled"`).
- [ ] **Cancelación (`409` / `200`) y Retry (`200`) verificados:** Ejecutados y verificados.

---

## Bloque 7: Consulta de Clasificaciones, Validación Humana (6 Acciones) y Ráfagas (`FL-10`, `FL-16`, `#25`, `#26`, `#28`, `#29`, `#29b`)

### 7.1 `GET /api/v1/classifications` — Listado y Filtros (`#25`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Camino Feliz:** `camera_station_id=<CAM_PUB_ID>&status=done&sort=-captured_at` → `200 OK`.
- **Pruebas de Error:** `from=2026-11-10&to=2026-10-01` → `422 VALIDATION_ERROR`; `taxon=fantasma` → `422 CATALOG_TAXON_NOT_FOUND`; `category=ovni` → `422 VALIDATION_ERROR`.
- [ ] **Camino Feliz (`200 OK`) y Casos Error (`422`):** Ejecutados y verificados.

### 7.2 `PUT /api/v1/classifications/{classification_id}/validation` — Las 6 Acciones (`#28`, `CB-62..66`)
Sobre `<CLS_ANIMAL_1_ID>` con `Bearer <USER_A_ACCESS>`:
1. **`confirm`:** `{"action": "confirm", "notes": "Confirmado"}` → `200 OK` (`validation.status: "confirmed"`).
2. **`correct` con `alternative` real de la IA:** Toma un `label_id` de `data.alternatives` de `<CLS_ANIMAL_1_ID>` y envía `{"action": "correct", "label_id": "<ALT_LABEL_ID>", "correction_source": "alternative"}` → `200 OK`. Si envías un `label_id` que no está en `alternatives` → `422 VALIDATION_ERROR`.
3. **`correct` con `catalog`:** `{"action": "correct", "label_id": "<LABEL_ID_CATALOGO>", "correction_source": "catalog"}` → `200 OK` (`data.taxonomy` original de la IA nunca se pisa).
4. **`correct_unlisted` (`CB-64`/`CB-65`):** Con `label_id` de rango `species` → `422 VALIDATION_ERROR`. Con `{"action": "correct_unlisted", "label_id": null, "suggested_name": "Leopardus jacobita"}` → `200 OK` *(déjala aplicada también en otra clasificación pública de `<BATCH_1_ID>` para probar `/admin/unlisted-suggestions` en el Bloque 11.12)*.
5. **`discard_repeat`:** Apuntando a sí mismo → `422 VALIDATION_ERROR`. Apuntando a `<CLS_ANIMAL_2_ID>` → `200 OK`.
6. **`reject` y `reset`:** Enviar `{"action": "reject"}` → `200 OK`; enviar `{"action": "reset"}` → `200 OK`. Finalmente deja `<CLS_ANIMAL_1_ID>` y `<CLS_ANIMAL_2_ID>` corregidos al mismo `<LABEL_ID_CATALOGO>` para formar ráfaga en 7.5.
- [ ] **Las 6 acciones de validación y sus errores `422` verificados:** Ejecutados y verificados.

### 7.3 `GET /api/v1/classifications/{classification_id}?include=validation_history` (`#26`)
- **Como Dueño (`USER_A_ACCESS`):** `data.validation_history` trae todas las entradas auditadas.
- **Como Tercero (`USER_B_ACCESS`):** `data.validation_history` es `null`. *(Volver a `USER_A_ACCESS`).*
- [ ] **Historial visible al dueño y `null` para terceros:** Ejecutado y verificado.

### 7.4 `POST /api/v1/classifications/validation-batch` (`#29`, `CB-67`)
- **Body JSON:** `{"ids": ["<CLS_ANIMAL_1_ID>", "00000000-0000-0000-0000-000000000099"], "action": "confirm"}` → `200 OK` (`updated: 1`, `skipped: [{"id": "...99", "code": "CLASSIFICATION_NOT_FOUND"}]`). *(Re-aplicar `correct` con `<LABEL_ID_CATALOGO>` a `<CLS_ANIMAL_1_ID>` si cambió de taxón).*
- [ ] **Validación por lote (`200 OK` con `skipped`):** Ejecutado y verificado.

### 7.5 Ráfagas: `GET /burst-candidates`, `POST /repeat-batch/dismiss` y `POST /repeat-batch` (`#29b`, `FL-16`, `CB-60..60d`)
1. `GET /api/v1/classifications/burst-candidates` sin parámetros → `422 VALIDATION_ERROR`.
2. `GET /api/v1/classifications/burst-candidates?camera_station_id=<CAM_PUB_ID>&window_minutes=10` → `200 OK`. Guarda `group_key` como **`BURST_GROUP_KEY`**.
3. `POST /api/v1/classifications/repeat-batch/dismiss` con `{"group_key": "<BURST_GROUP_KEY>", "window_minutes": 10}` → `200 OK` (`{"dismissed": 2}`).
4. `POST /api/v1/classifications/repeat-batch`: con `keep_ids: []` → `422 REPEAT_KEEP_REQUIRED` (`CB-60d`). Con `{"keep_ids": ["<CLS_ANIMAL_1_ID>"], "discard_ids": ["<CLS_ANIMAL_2_ID>"]}` → `200 OK` (`{"kept": 1, "discarded": 1}`).
- [ ] **Ráfagas (`/burst-candidates`, `/dismiss`, `/repeat-batch` y errores `422`):** Ejecutadas y verificadas.

### 7.6 `PATCH /api/v1/classifications/{classification_id}` — Mover a `CAM_PRIV_ID` (`#26`, `CB-51`)
- **Path Param:** `<CLS_ANIMAL_2_ID>` · **Body JSON:** `{"camera_station_id": "<CAM_PRIV_ID>"}` → `200 OK`.
- Ejecuta `PUT /api/v1/classifications/{CLS_ANIMAL_2_ID}/validation` con `{"action": "confirm"}` para que cuente como avistamiento en la cámara privada `<CAM_PRIV_ID>`.
- [ ] **Clasificación movida a `<CAM_PRIV_ID>` y confirmada (`200 OK`):** Ejecutado y verificado.

---

## Bloque 8: Estadísticas Ecológicas y Reportes Científicos Excel y PDF (`FL-11`, `FL-12`, `#15`, `#20`, `#31`)

### 8.1 `GET /api/v1/camera-stations/{camera_id}/stats` (`#15`)
- **Como Dueño (`USER_A_ACCESS`) en `<CAM_PUB_ID>`:** `200 OK` completo y con `?sections=totals,effort`.
- **Pruebas de Error:** `?sections=invalida` → `422 VALIDATION_ERROR`; con `USER_B_ACCESS` sobre `<CAM_PRIV_ID>` → `404 CAMERA_NOT_FOUND`. *(Volver a `USER_A_ACCESS`).*
- [ ] **Stats de cámara (`200 OK`) y Casos Error (`422`, `404`):** Ejecutados y verificados.

### 8.2 `GET /api/v1/projects/{project_id}/stats` — Dueño vs Tercero (`#20`, `CB-20`)
- **Como Dueño (`USER_A_ACCESS`) en `<PROJ_PUB_ID>`:** `data.by_camera` lista **2 cámaras** (`CAM-01` y `CAM-PRIV-01`).
- **Como Tercero (`USER_B_ACCESS` — `CB-20`):** `data.by_camera` lista **solo `CAM-01`** (excluye la cámara privada). *(Volver a `USER_A_ACCESS`).*
- [ ] **Stats de proyecto como Dueño vs Tercero (`CB-20`):** Ejecutadas y verificadas.

### 8.3 `GET /api/v1/reports/excel` y `GET /api/v1/reports/pdf` (`#31`, `FL-12`, D9)
- Con `USER_B_ACCESS`: `GET /api/v1/reports/excel?project_id=<PROJ_PUB_ID>` → Descarga `.xlsx` de 5 hojas sin datos de `CAM-PRIV-01` y con coordenadas redondeadas a 2 decimales (`DD-17`).
- Con `USER_A_ACCESS`: `GET /api/v1/reports/pdf?project_id=<PROJ_PUB_ID>` → Descarga `.pdf` (`reportlab` + diseño WWF) con `request_id` en el pie.
- **Pruebas de Error:** Sin parámetros → `422 VALIDATION_ERROR`; con `?project_id=<PROJ_PUB_ID>&from=2020-01-01&to=2020-01-02` → `404 REPORT_EMPTY`.
- [ ] **Excel (5 hojas + DD-17), PDF (`reportlab`) y Casos Error (`422`, `404`):** Ejecutados y verificados.

---

## Bloque 9: Importación Asíncrona de Paquetes de Escritorio `.wwm.zip` (`FL-23`, `#32`–`#35`, D2, D10)

### 9.1 `POST /api/v1/imports/desktop` — Vista Previa y Validaciones (`#32`, D2)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Pruebas de Error con `tests/fixtures/package/`:**
  - Sin cámara ni `create_camera=true` → `422 VALIDATION_ERROR`.
  - `invalid_checksum.wwm.zip` → `422 IMPORT_CHECKSUM_MISMATCH`.
  - `invalid_zip_slip.wwm.zip` → `422 IMPORT_INVALID_PACKAGE`.
  - `invalid_version_2.wwm.zip` → `422 IMPORT_UNSUPPORTED_VERSION`.
- **Camino Feliz (`201 Created`):** Subir `tests/fixtures/package/sample_valid.wwm.zip` con `camera_station_id=<CAM_PUB_ID>` y `create_camera=false`. Guarda `data.import_id` en **`13A`** como **`IMPORT_PREVIEW_ID`**.
- [ ] **Casos Error (`422`) y Camino Feliz (`201 Created` vista previa):** Ejecutados y guardado `IMPORT_PREVIEW_ID`.

### 9.2 `DELETE /api/v1/imports/{import_id}` — Cancelar Vista Previa (`#34`)
- `DELETE /api/v1/imports/{IMPORT_PREVIEW_ID}` → `204 No Content` (repetir da `404 IMPORT_NOT_FOUND`).
- Volver a subir `sample_valid.wwm.zip` con `camera_station_id=<CAM_PUB_ID>` y actualizar **`IMPORT_PREVIEW_ID`**.
- [ ] **Cancelación (`204`/`404`) y nueva vista previa creada:** Ejecutado y verificado.

### 9.3 `POST /api/v1/imports/{import_id}/confirm` y `GET /api/v1/imports/{import_id}` — Confirmar en el Worker (`#33`, D10, `CB-82`)
- **Body JSON:** `{"include_warnings": true, "camera": null}` → **`202 Accepted`** (`status: "processing"`).
- **Seguimiento:** Consultar `GET /api/v1/imports/{IMPORT_PREVIEW_ID}` hasta ver `status: "completed"` y `result.imported: 3`.
- **Pruebas de Error (`409 IMPORT_ALREADY_IMPORTED` — `CB-82`):** Repetir `/confirm` o volver a subir `sample_valid.wwm.zip` en `<CAM_PUB_ID>` → `409 IMPORT_ALREADY_IMPORTED`.
- [ ] **Confirmación en el worker (`202` → `completed`) y bloqueo `409 CB-82`:** Ejecutados y verificados.

### 9.4 `GET /api/v1/imports` — Historial de Importaciones (`#35`)
- `GET /api/v1/imports?camera_station_id=<CAM_PUB_ID>` → `200 OK` (lista la `cancelled` y la `completed`).
- [ ] **Historial de importaciones (`200 OK`):** Ejecutado y verificado.

---

## Bloque 10: Borrado Lógico de Clasificación Individual (`#26`)

### 10.1 `DELETE /api/v1/classifications/{classification_id}` (`#26`)
- **Auth:** `Bearer <USER_A_ACCESS>` · **Path Param:** `<CLS_ANIMAL_2_ID>` → `204 No Content` (consultar o repetir borrado da `404 CLASSIFICATION_NOT_FOUND`).
- **Preparación rápida para `CB-96` del Bloque 11:** Abre un lote de 1 archivo en `<CAM_PRIV_ID>`, sube una foto y anota su `classification_id` en **`13A`** como **`CLS_PRIV_ID`**.
- [ ] **Borrado lógico (`204`/`404`) y `CLS_PRIV_ID` creado en `<CAM_PRIV_ID>`:** Ejecutados y verificados.

---

## Bloque 11: Panel Admin Completo (`HU-15a`, `HU-15b` — `FL-40..46`, `#36`–`#44`)

**Situación:** El administrador (`admin@wwf.org`) audita la plataforma. Regla innegociable: el admin ve lo **anónimo** y lo **público**; lo **privado** solo aparece como **conteo**, y pedirlo por ID responde **404** (`CB-96`). Toda acción mutante exige `reason` (≥ 3 caracteres) y queda en `admin_audit_log`.

### 11.0 Login de Admin (`#2`, `CB-99`)
- Ejecuta `POST /api/v1/auth/login` con `{"email": "admin@wwf.org", "password": "AdminFauna2026Password"}`.
- `ADMIN_ID` ya quedó registrado (`c4f9d76e-7ac1-41b7-9095-815713930c8d`); guarda `data.tokens.access_token` como **`ADMIN_ACCESS`** (`expires_in: 900` = 15 min) en **`13A`**.
- [ ] **Login Admin exitoso y `ADMIN_ACCESS` guardado.**

### 11.1 `GET /api/v1/admin/stats` — Estadísticas de Plataforma (`#36`, `FL-40`, `CB-52`)
- **Con `USER_A_ACCESS`:** `403 ADMIN_REQUIRED`. **Sin token:** `401 AUTH_REQUIRED`.
- **Cambia `Authorize` a `<ADMIN_ACCESS>` y llama con `scope=all`:**
  - `content.camera_stations.private` ≥ 1 (privadas solo como número).
  - `fauna` (`scope: "platform"`) deduplica por `sha256` (`CB-52`) y excluye especies de cámaras privadas.
  - `fauna_map` trae coordenadas redondeadas a 2 decimales (~1 km).
- [ ] **`403` sin rol admin y `200 OK` con privados solo como conteo:** Ejecutados y verificados.

### 11.2 `GET /api/v1/admin/camera-stations` — Explorar Cámaras (`#37`, `FL-41`)
- `<CAM_PUB_ID>` aparece con coordenadas redondeadas (`location_precision: "approx_1km"`).
- `<ANON_CAM_2_ID>` (`CAM-ANON-02`) aparece con coordenadas **exactas** (`location_precision: "exact"`) y `owner.display_name: "Anónimo #xxxx"`.
- `<CAM_PRIV_ID>` **no aparece jamás**.
- [ ] **Lista sin privadas, públicas redondeadas y anónimas exactas:** Ejecutado y verificado.

### 11.3 `GET /api/v1/admin/classifications` y `GET /api/v1/admin/classifications/{id}/evidence` (`#37`, `#38`, `CB-96`)
- `GET /api/v1/admin/classifications?scope=all&status=all` → Solo lista clasificaciones públicas y anónimas.
- `GET /api/v1/admin/classifications/{CLS_ANIMAL_1_ID}/evidence` (pública) → `200 image/jpeg`.
- `GET /api/v1/admin/classifications/{CLS_PRIV_ID}/evidence` (privada — `CB-96`) → **`404 CLASSIFICATION_NOT_FOUND`**.
- [ ] **Evidencia pública `200` y privada `404` (`CB-96`):** Ejecutadas y verificadas.

### 11.4 `GET /api/v1/admin/anon-sessions` — Sesiones Anónimas (`#37`)
- Cada sesión aparece con `label: "Anónimo #xxxx"` (nunca el token), `status`, `counts` y `retained`.
- Copia el `id` de la sesión `active` (la de `ANON_TOKEN_2`) en **`13A`** como **`ANON_SESSION_2_ID`**.
- [ ] **Lista sin tokens y `ANON_SESSION_2_ID` guardado:** Ejecutado y verificado.

### 11.5 Borrado Lógico y Restauración (`POST /admin/{entity}/{id}/delete` y `/restore` — `#39`, `FL-42`)
1. `POST /api/v1/admin/classifications/{CLS_ANIMAL_1_ID}/delete` con `{}` → **`422 DELETE_REASON_REQUIRED`**.
2. Mismo endpoint con `{"reason": "Prueba de bitácora"}` → `200 OK` (`deleted.classifications: 1`).
3. Repetir paso 2 → **`409 ENTITY_ALREADY_DELETED`**.
4. `POST /api/v1/admin/camera-stations/{CAM_PUB_ID}/delete` con `{"reason": "Cascada"}` → `200 OK` (borra la cámara y sus clasificaciones vivas).
5. `POST /api/v1/admin/camera-stations/{CAM_PUB_ID}/restore` con `{"reason": "Restaurar cascada"}` → `200 OK` (**restaura solo lo del paso 4**; `<CLS_ANIMAL_1_ID>`, borrada en el paso 2, sigue borrada).
6. `POST /api/v1/admin/classifications/{CLS_ANIMAL_1_ID}/restore` con `{"reason": "Restaurar individual"}` → `200 OK`. Repetirlo → **`409 ENTITY_NOT_DELETED`**.
7. `POST /api/v1/admin/camera-stations/{CAM_PRIV_ID}/delete` con `{"reason": "Privada"}` → **`404 CAMERA_NOT_FOUND`** (`CB-96`).
- [ ] **Motivo obligatorio (`422`), `409` por repetir, cascada y restauración parcial, privada `404`:** Ejecutados y verificados.

### 11.6 `POST /api/v1/admin/delete-batch` (`#39`)
- **Body JSON:** `{"entity": "classifications", "ids": ["<CLS_ANIMAL_2_ID>", "<CLS_PRIV_ID>"], "reason": "Limpieza por lote"}`.
- **Esperado (`200 OK`):** `skipped` incluye `<CLS_PRIV_ID>` con `CLASSIFICATION_NOT_FOUND` y `<CLS_ANIMAL_2_ID>` con `ENTITY_ALREADY_DELETED` (borrada en Bloque 10).
- [ ] **Lote con `skipped` por ítem:** Ejecutado y verificado.

### 11.7 Gestión de Usuarios (`GET /admin/users`, `deactivate`, `reactivate` — `#40`, `FL-43`, `CB-98`)
1. `GET /api/v1/admin/users?q=investigador` → Lista usuarios con `counts`.
2. `POST /api/v1/admin/users/{ADMIN_ID}/deactivate` con `{"reason": "Auto"}` → **`409 CANNOT_DEACTIVATE_SELF`** (`CB-98`).
3. `POST /api/v1/admin/users/{USER_B_ID}/deactivate` con `{"reason": "Prueba suspensión"}` → `200 OK` (`is_active: false`, revoca sus refresh tokens y cancela su cola).
4. Con `USER_B_ACCESS`, llamar a `GET /api/v1/auth/me` → **`403 ACCOUNT_DISABLED`**. *(Volver a poner `ADMIN_ACCESS`).*
5. `POST /api/v1/admin/users/{USER_B_ID}/reactivate` con `{"reason": "Fin de prueba"}` → `200 OK` (`is_active: true`).
- [ ] **Autodesactivación bloqueada (`409`), desactivar corta acceso (`403`) y reactivar lo devuelve (`200`):** Ejecutados y verificados.

### 11.8 `POST /api/v1/admin/users/{user_id}/password-reset-link` (`#40`, `CB-76`) + Uso del Enlace (`#6b`)
1. Sobre `<ADMIN_ID>` con `{"reason": "Reset admin"}` → **`403 FORBIDDEN`** (`"La cuenta admin se recupera con la CLI."`).
2. Sobre `<USER_B_ID>` con `{"reason": "Sin acceso al correo"}` → `200 OK`, devuelve `reset_url` (`http://localhost:5173/restablecer?token=<RESET_TOKEN_MANUAL>`) y `expires_at`.
3. Copia `<RESET_TOKEN_MANUAL>` y pruébalo en `#6b`:
   - `GET /api/v1/auth/password/reset/validate?token=<RESET_TOKEN_MANUAL>` → `200 OK` (`valid: true`, `email_hint: "i***b@wwf.org"`).
   - `POST /api/v1/auth/password/reset` con `{"token": "<RESET_TOKEN_MANUAL>", "new_password": "Fauna2026Password"}` → `200 OK`.
   - Repetir `POST /api/v1/auth/password/reset` con el mismo token → `400 AUTH_RESET_TOKEN_INVALID` (`CB-75`).
- [ ] **Enlace manual generado, validado y consumido (`200` / `400 CB-75`):** Ejecutado y verificado.

### 11.9 `GET` y `PUT /api/v1/admin/settings` (`#41`, `FL-44`, `CB-43`)
- `GET /api/v1/admin/settings` → `anon_data_retention.value: true`.
- `PUT` con `{"anon_data_retention": "no", "reason": "Motivo"}` → **`422 SETTING_INVALID`**.
- `PUT` con `{"anon_data_retention": false, "reason": ""}` → **`422 DELETE_REASON_REQUIRED`**.
- `PUT` con `{"anon_data_retention": false, "reason": "Prueba de bitácora"}` → `200 OK` (`value: false`, `updated_by: "admin@wwf.org"`).
- Volver a dejar en `true` con `{"anon_data_retention": true, "reason": "Restaurar valor por defecto"}` → `200 OK`.
- [ ] **Configuración validada, actualizada y restaurada (`200` / `422`):** Ejecutado y verificado.

### 11.10 `GET /api/v1/admin/audit-log` (`#42`)
- Prueba filtros `action=soft_delete`, `action=update_setting`, `entity_type=users`.
- Verifica que cada acción de `11.5` a `11.9` tiene `reason`, `old_value`/`new_value` y `request_id`, y que `password_reset_link` **solo guardó `expires_at` y nunca el token** (`CB-76`).
- [ ] **Auditoría verificada sin fuga de tokens (`200 OK`):** Ejecutado y verificado.

### 11.11 `GET /api/v1/admin/queue` (`#43`, `FL-45`)
- **Con el worker corriendo:** `workers.alive: true`, `concurrency: 2`, `busy`, `queued`, `processing`, `avg_processing_seconds`, `last_hour` y `email`.
- *(Opcional)* Detener el worker (`docker compose stop worker`), esperar ~40 s y consultar → `workers.alive: false`. Volver a levantarlo (`docker compose start worker`).
- [ ] **Estado de cola y latido del worker (`200 OK`):** Ejecutado y verificado.

### 11.12 `GET /api/v1/admin/unlisted-suggestions` (`#44`, `FL-46`, `CB-65`)
- Devuelve las sugerencias `correct_unlisted` de cámaras públicas/anónimas agrupadas sin tildes ni mayúsculas (`"leopardus jacobita"`), con `count`, `parent_taxon` y `classification_ids`.
- [ ] **Sugerencias no catalogadas agrupadas (`200 OK`):** Ejecutado y verificado.

### 11.13 `GET /api/v1/admin/reports/excel` (`#42`, `FL-40`)
- Descarga `WWM_admin_all_<AAAAMMDD>.xlsx` con **6 hojas** (*Plataforma*, *Fauna por especie*, *Por género*, *Por familia*, *Clasificaciones*, *Sugerencias*), sin filas de `CAM_PRIV_ID`, con anónimos como `Anónimo #xxxx` y registro `action: "export"` en `audit-log`.
- [ ] **Excel global descargado (6 hojas, sin privados) y auditado:** Ejecutado y verificado.
