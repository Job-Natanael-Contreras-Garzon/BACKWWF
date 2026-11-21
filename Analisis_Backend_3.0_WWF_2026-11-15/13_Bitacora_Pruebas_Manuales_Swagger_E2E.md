---
title: "13 - Bitácora Física y Plan de Pruebas Manuales E2E en Swagger (Pre-Merge develop → main)"
date: 2026-11-21
project: BACKWWF
version: "1.1.0"
status: active
tags: [testing, swagger, e2e, bitacora, qa, manual-testing, frontend-handover, wwf]
---

# 13. Bitácora Física y Guía de Pruebas Manuales E2E en Swagger (`BACKWWF`)

> [!IMPORTANT]
> **Propósito de este documento:**
> 1. **Bitácora de Certificación Física (`develop` → `main`):** Guía ordenada paso a paso con *checkboxes* (`- [ ]`) para certificar contra la **implementación física real** (`app/api/v1/*`, `app/schemas/*`, `app/services/*`) las **rutas operativas hoy** (contratos `#1` al `#44` de M0–M4, incluido el panel admin), junto con el contenedor real de IA (`ia-clasificacion-fauna` en `:8001`), el worker `arq`, Redis y PostgreSQL.
> 2. **Referencia Exacta para Frontend (Miguel):** Todos los *requests*, *headers*, *query params* y *responses* (`{status, data, message, error, meta}`) de este documento fueron extraídos directamente del código fuente actual en `develop`, sin inventar ningún campo.

> [!NOTE]
> **Alcance (actualizado el 21/11/2026, 100 % del backlog):**
> - **Bloques 1–10:** contratos `#1` al `#35` (`HU-01` a `HU-14`): sistema, auth, recuperación de contraseña, sesiones anónimas, cámaras, proyectos, lotes y cola, worker con IA real y evidencias, catálogo, clasificaciones, validación, ráfagas, estadísticas, reportes e importación de escritorio.
> - **Bloque 11:** panel admin `#36` al `#44` (`HU-15a`, `HU-15b`).
> - **Bloque 12:** operación en desarrollo: correo real con Resend, límites de intentos compartidos en Redis, `seed-e2e` y respaldo/restauración (`HU-16`).

---

## 0. Preparación del Entorno Físico y Tabla de Variables

Antes de abrir Swagger (`http://localhost:8000/docs`), verifica que toda la topología esté levantada y conectada:

### 0.1 Checklist de Arranque de Servicios
- [ ] **1. PostgreSQL (`faunadb` en puerto `5433`):** Base de datos activa y con las migraciones `0001`, `0002` y `0003` aplicadas (`alembic current` = `0003`):
  ```powershell
  docker compose exec -T api alembic upgrade head
  ```
- [ ] **2. Contenedor IA Fauna Real (`../ia-clasificacion-fauna` en puerto `8001`):** Servicio levantado, modelos cargados y respondiendo `{"status": "ok"}` en `http://localhost:8001/api/v1/health` (con `AI_API_KEY=dev-key`).
- [ ] **3. Backend, Worker y Redis (`docker-compose.yml`):**
  ```powershell
  docker compose up -d --build
  docker ps
  ```
  Verificar que estén `Up`: `fauna_api` (`:8000`), `fauna_worker` (`arq app.worker.main.WorkerSettings`) y `fauna_redis` (`:6379`).
- [ ] **4. Archivos de prueba en mano para subir en Swagger:**
  - `animal_1.jpg` y `animal_2.jpg` (dos fotos distintas con un animal claro para que la IA detecte `category: "animal"` y generen ráfaga si tienen timestamps cercanos).
  - `video_largo.mp4` (video > 16 segundos para verificar truncado a `15.0s` y warning `VIDEO_TRUNCATED`).
  - `corrupto.txt` renombrado a `falso.jpg` (o un `.heic`) para probar rechazo limpio `200 OK` con `status: "error"` en el ítem sin tumbar el lote.
  - Paquete válido de escritorio `tests/fixtures/package/sample_valid.wwm.zip` y paquete inválido `tests/fixtures/package/invalid_checksum.wwm.zip` (o `invalid_zip_slip.wwm.zip`).

### 0.2 Hoja de Registro de IDs y Tokens (Llenar durante la prueba)
A medida que avances por los bloques, anota aquí los valores devueltos para reutilizarlos en los pasos siguientes:

| Variable | Descripción | Valor obtenido en Swagger |
| :--- | :--- | :--- |
| `ANON_TOKEN_1` | Token de `POST /api/v1/anon-sessions` (Flujo 2) | `______________________________` |
| `ANON_CAM_ID` | ID de cámara creada como anónimo (`CAM-01`) | `______________________________` |
| `USER_A_ACCESS` | `access_token` de Investigador Principal (Usuario A) | `______________________________` |
| `USER_A_REFRESH` | `refresh_token` inicial de Usuario A | `______________________________` |
| `USER_B_ACCESS` | `access_token` de Investigador Secundario (Usuario B - pruebas IDOR/DD-17) | `______________________________` |
| `CAM_PUB_ID` | ID de Cámara Pública de Usuario A (`CAM-01`, `version` actual) | `______________________________` |
| `CAM_PRIV_ID` | ID de Cámara Privada de Usuario A (`CAM-PRIV-01`) | `______________________________` |
| `CAM_REDEPLOY_ID` | ID de Cámara Reinstalada (`CAM-01-2`) | `______________________________` |
| `PROJ_PUB_ID` | ID de Proyecto Público de Usuario A | `______________________________` |
| `BATCH_1_ID` | ID del Lote Web en `CAM_PUB_ID` | `______________________________` |
| `CLS_ANIMAL_1_ID` | ID de Clasificación `done` #1 (Animal) | `______________________________` |
| `CLS_ANIMAL_2_ID` | ID de Clasificación `done` #2 (Animal en misma cámara para ráfaga) | `______________________________` |
| `BURST_GROUP_KEY` | `group_key` devuelto por `/classifications/burst-candidates` | `______________________________` |
| `IMPORT_PREVIEW_ID` | `import_id` devuelto por `POST /api/v1/imports/desktop` | `______________________________` |
| `ADMIN_ACCESS` | `access_token` del admin creado por CLI (Bloque 11) | `______________________________` |
| `USER_B_ID` | `id` del Usuario B (para desactivar y enlace de reset, Bloque 11) | `______________________________` |
| `ANON_SESSION_ID` | `id` de una sesión anónima en `GET /admin/anon-sessions` | `______________________________` |

> [!TIP]
> **Cómo alternar sesiones en Swagger UI (`http://localhost:8000/docs`):**
> - **Para endpoints con `BearerAuth`:** Haz clic en el botón verde **`Authorize`** arriba a la derecha y pega **solo** el `access_token` (sin la palabra `Bearer`). Swagger lo recordará gracias a `persistAuthorization: True`.
> - **Para endpoints con `X-Anon-Token` o sin autenticación:** Haz clic en **`Authorize` → `Logout`** para limpiar el `Authorization: Bearer`, porque en `get_owner` (`app/api/deps.py#L102-L114`) **el header `Authorization` siempre tiene prioridad sobre `X-Anon-Token`**.

---

## Envoltura Estándar para Frontend (Recordatorio para Miguel)

Salvo los endpoints binarios (`GET /classifications/{id}/evidence`, `GET /reports/excel`, `GET /reports/pdf`) y los `204 No Content` (`DELETE`), **absolutamente todas las respuestas HTTP (`2xx`, `4xx`, `5xx`)** usan `ApiResponse` (`app/core/responses.py`):

```json
{
  "status": "success",
  "data": { "...": "..." },
  "message": "OK",
  "error": null,
  "meta": {
    "request_id": "c4f1a8b0-...",
    "timestamp": "2026-11-21T13:30:00Z",
    "pagination": {
      "page": 1,
      "page_size": 50,
      "total": 1,
      "total_pages": 1
    },
    "warnings": [
      {
        "code": "CAMERA_COORDS_SUSPECT",
        "message": "Revisa las coordenadas: ¿latitud y longitud están invertidas?",
        "context": { "latitude": -64.9, "longitude": -16.5 }
      }
    ]
  }
}
```

Y cuando ocurre un error (`status: "error"`):
```json
{
  "status": "error",
  "data": null,
  "message": "Mensaje legible para mostrar en UI.",
  "error": {
    "code": "CODIGO_ESTABLE_CATALOGO",
    "flow": "FL-05",
    "details": [
      {
        "field": "body.email",
        "code": "value_error",
        "message": "value is not a valid email address",
        "context": {}
      }
    ]
  },
  "meta": {
    "request_id": "c4f1a8b0-...",
    "timestamp": "2026-11-21T13:30:00Z",
    "pagination": null,
    "warnings": []
  }
}
```

---

## Bloque 1: Salud del Sistema, Configuración Pública y Catálogo SpeciesNet (`FL-10`, `#11`, `#12`, `#30`)

**Situación:** Antes de autenticarnos, simulamos el arranque inicial de la SPA de Miguel: verifica que el backend esté vivo, que la base de datos, el disco local y el contenedor real de IA en `:8001` estén listos, descarga la configuración pública para inicializar formularios/mapas, y consulta el catálogo SpeciesNet en RAM (3538 taxones).

### 1.1 `GET /` — Raíz informativa del servicio
- **Auth:** Ninguna.
- **Request:** Sin parámetros.
- **Resultado esperado (`200 OK`):**
  - `data`: `{"app_name": "...", "version": "1.0.0", "environment": "development", "docs_url": "/docs"}`.
  - `message`: `"Backend de Monitoreo de Fauna WWF operativo."`
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y verificado.

### 1.2 `GET /api/v1/health` — Liveness probe (`#12`)
- **Auth:** Ninguna.
- **Request:** Sin parámetros.
- **Resultado esperado (`200 OK`):**
  - `data`: `{"status": "ok", "version": "1.0.0"}`.
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y verificado.

### 1.3 `GET /api/v1/health/ready` — Readiness probe (`#12`)
- **Auth:** Ninguna.
- **Request:** Sin parámetros.
- **Resultado esperado (`200 OK` con IA real arriba):**
  - `data`: `{"database": "ok", "ai": "ok", "storage": "ok"}`.
  - `message`: `"Servicio listo."`
- **Prueba de Error (`503 SERVICE_UNAVAILABLE`):**
  - *Acción física:* Pausa o detén temporalmente el contenedor de IA (`docker stop <contenedor_ia>`) y ejecuta el endpoint. Luego vuelve a iniciarlo (`docker start <contenedor_ia>`).
  - *Esperado:* HTTP `503`, `status: "error"`, `error.code: "SERVICE_UNAVAILABLE"`, y en `data` viene el diagnóstico exacto: `{"database": "ok", "ai": "down", "storage": "ok"}`.
- [ ] **Camino Feliz (`200 OK` — 3 servicios en `"ok"`):** Ejecutado y verificado.
- [ ] **Caso Error (`503 SERVICE_UNAVAILABLE` con IA apagada):** Ejecutado y verificado (y contenedor IA reactivado).

### 1.4 `GET /api/v1/config/public` — Configuración pública para Frontend (`#11`)
- **Auth:** Ninguna.
- **Request:** Sin parámetros.
- **Resultado esperado (`200 OK`):**
  - `data.anon_data_retention`: `true`
  - `data.media`: `{"max_file_mb": 300, "max_video_seconds": 15, "image_extensions": ["jpeg", "jpg", "png", "webp"], "video_extensions": ["avi", "mov", "mp4"], "browser_duration_check_extensions": ["mp4", "mov"]}`
  - `data.anon_limits`: `{"max_files": 50, "max_camera_stations": 3}`
  - `data.upload`: `{"max_parallel_files": 3, "max_pending_per_user": 100, "poll_interval_seconds": 3}`
  - `data.password_recovery`: `{"enabled": false}`
  - `data.map`: `{"default_center": {"lat": -16.5, "lng": -64.9}, "default_zoom": 6, "label": "Bolivia"}`
  - `data.import`: `{"max_package_mb": 200, "supported_format_versions": ["1.0"]}` *(Nota para Miguel: el alias JSON es `"import"`, no `"import_config"`).*
  - `data.app_version`: `"1.0.0"`
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y verificado.

### 1.5 `GET /api/v1/catalog/species` — Búsqueda en Catálogo SpeciesNet (`#30`)
- **Auth:** Ninguna.
- **Query Params (Camino Feliz):**
  - `q`: `"Jaguár"` *(con tilde y mayúscula para verificar normalización `CA-2`)*
  - `rank`: *(dejar vacío o probar `species`)*
  - `limit`: `10`
- **Resultado esperado (`200 OK`):**
  - Lista de taxones donde aparece primero la especie *Panthera onca* (`common_name: "jaguar"`, `rank: "species"`, `family: "Felidae"`, `genus: "Panthera"`). Anota su `label_id` exacto para usarlo en el Bloque 6.
- **Pruebas de Error:**
  - `q`: `"a"` (1 solo carácter) → HTTP `422`, `error.code: "VALIDATION_ERROR"` (`min_length=2`).
  - `limit`: `99` → HTTP `422`, `error.code: "VALIDATION_ERROR"` (`le=50`).
- [ ] **Camino Feliz (`200 OK` búsqueda sin importar tildes/mayúsculas):** Ejecutado y verificado.
- [ ] **Caso Error (`422 VALIDATION_ERROR` con `q` de 1 letra o `limit > 50`):** Ejecutado y verificado.

### 1.6 `GET /api/v1/catalog/species/{label_id}` — Detalle de un taxón por ID (`#30`)
- **Auth:** Ninguna.
- **Path Param (Camino Feliz):** `label_id` obtenido en el paso 1.5.
- **Resultado esperado (`200 OK`):** Objeto con `label_id`, `rank`, `class`, `order`, `family`, `genus`, `species`, `scientific_name`, `common_name`.
- **Prueba de Error (`404 CATALOG_TAXON_NOT_FOUND`):**
  - `label_id`: `"00000000-no-existe"` → HTTP `404`, `error.code: "CATALOG_TAXON_NOT_FOUND"`, `message: "Ese taxón no está en el catálogo."`.
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y verificado.
- [ ] **Caso Error (`404 CATALOG_TAXON_NOT_FOUND`):** Ejecutado y verificado.

---

## Bloque 2: Ciclo de Vida de Sesión Anónima y Límites sin Cuenta (`FL-03`, `#7`, `#8`, `#10`, `#13`, `#16`)

**Situación:** Un investigador entra a la plataforma sin registrarse y pulsa *"Probar sin cuenta"*. El frontend crea una sesión temporal (`X-Anon-Token`), registra una cámara privada llamada `CAM-01` y un proyecto privado. Intentaremos violar las restricciones de anónimos (intentar publicar una cámara en el mapa público o usar un token expirado) para comprobar que el sistema protege la privacidad.

> [!WARNING]
> Asegúrate de que el botón **`Authorize`** de Swagger esté **desconectado (`Logout`)** durante todo el Bloque 2.

### 2.1 `POST /api/v1/anon-sessions` — Crear sesión anónima para probar cierre (`#7`)
- **Auth:** Ninguna.
- **Request:** Sin body.
- **Resultado esperado (`201 Created`):**
  - `message`: `"Sesión temporal iniciada."`
  - `data`:
    ```json
    {
      "anon_token": "<TOKEN_DESCARTABLE>",
      "expires_at": "2026-11-22T...",
      "data_retention": true
    }
    ```
- [ ] **Camino Feliz (`201 Created`):** Ejecutado. Copia ese `<TOKEN_DESCARTABLE>` para cerrarlo en el paso 2.2.

### 2.2 `POST /api/v1/anon-sessions/current/close` — Cerrar sesión temporal (`#10`)
- **Auth:** Header `X-Anon-Token: <TOKEN_DESCARTABLE>`.
- **Request:** Sin body.
- **Resultado esperado (`200 OK`):**
  - `message`: `"Sesión temporal cerrada."`
  - `data`: `{"status": "expired", "data_retained": true}`
- **Prueba de Error (`401 ANON_SESSION_EXPIRED`):**
  - Vuelve a ejecutar `POST /api/v1/anon-sessions/current/close` (o `GET /current`) con el mismo `<TOKEN_DESCARTABLE>` ya cerrado.
  - *Esperado:* HTTP `401`, `error.code: "ANON_SESSION_EXPIRED"`, `message: "Tu sesión sin cuenta expiró; sus datos ya no están disponibles."`.
- [ ] **Camino Feliz (`200 OK` cierre de sesión):** Ejecutado y verificado.
- [ ] **Caso Error (`401 ANON_SESSION_EXPIRED` al reusar token cerrado):** Ejecutado y verificado.

### 2.3 Crear la Sesión Anónima Principal (`ANON_TOKEN_1`) y poblarla (`#7`, `#8`, `#13`, `#16`)
1. **Crear nueva sesión anónima (`POST /api/v1/anon-sessions`):**
   - Guarda el nuevo `data.anon_token` en tu tabla como **`ANON_TOKEN_1`**.
2. **Crear una cámara con `X-Anon-Token: <ANON_TOKEN_1>` (`POST /api/v1/camera-stations`):**
   - **Importante:** Ponle código `"CAM-01"` (para probar en el Bloque 3 la colisión de nombres `-2` al reclamar la sesión).
   - **Body JSON:**
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
   - **Esperado (`201 Created`):** `data.owner` es `{"type": "anonymous", "is_mine": true, "display_name": null, "institution": null}`. Guarda `data.id` como **`ANON_CAM_ID`**.
3. **Probar restricción de visibilidad pública en anónimo (`422 ANON_PUBLIC_NOT_ALLOWED` — `CB-20b`):**
   - Ejecuta `POST /api/v1/camera-stations` con `X-Anon-Token: <ANON_TOKEN_1>` pero cambiando `"visibility": "public"` y `"code": "CAM-PUB-FAIL"`.
   - **Esperado (`422 Unprocessable Entity`):** `error.code: "ANON_PUBLIC_NOT_ALLOWED"`, `message: "Regístrate para publicar cámaras en el mapa."`.
4. **Consultar estado y contadores de la sesión anónima (`GET /api/v1/anon-sessions/current` — `#8`):**
   - **Header:** `X-Anon-Token: <ANON_TOKEN_1>`.
   - **Esperado (`200 OK`):**
     ```json
     {
       "status": "active",
       "expires_at": "2026-11-22T...",
       "data_retention": true,
       "counts": {
         "classifications": 0,
         "camera_stations": 1,
         "projects": 0
       },
       "limits": {
         "max_files": 50,
         "max_camera_stations": 3,
         "used_files": 0,
         "used_camera_stations": 1
       }
     }
     ```
- [ ] **Nueva sesión `ANON_TOKEN_1` creada (`201`):** Ejecutado.
- [ ] **Cámara anónima `CAM-01` creada (`201`):** Ejecutado y guardado `ANON_CAM_ID`.
- [ ] **Caso Error (`422 ANON_PUBLIC_NOT_ALLOWED` al intentar cámara pública anónima):** Ejecutado y verificado.
- [ ] **Estado de sesión anónima (`GET /anon-sessions/current` → `200 OK` con `camera_stations: 1`):** Ejecutado y verificado.

---

## Bloque 3: Autenticación JWT, Detección de Reuso de Refresh, Perfil y Claim Anónimo (`FL-01`, `FL-02`, `FL-04`, `FL-14`, `#1`–`#6b`, `#9`)

**Situación:** El investigador decide crearse una cuenta formal (Usuario A: `investigador.a@wwf.org`). Al registrarse enviando el header `X-Anon-Token: <ANON_TOKEN_1>`, el backend le avisa en `data.anon_session` que tiene datos temporales listos para reclamar (`has_data: true`), pero **no los reclama automáticamente** hasta que el usuario confirme en el modal (`POST /anon-sessions/claim`). Además, antes de reclamar, Usuario A crea su propia cámara llamada `"CAM-01"` para verificar que al ejecutar `/claim` la cámara anónima se renombre automáticamente a `"CAM-01-2"`. También registraremos un **Usuario B** (`investigador.b@wwf.org`) para las pruebas cruzadas de privacidad DD-17 e IDOR.

### 3.1 `POST /api/v1/auth/register` — Registro de Usuario A con Hint de Sesión Anónima (`#1`)
- **Auth:** Ninguna.
- **Header opcional:** `X-Anon-Token: <ANON_TOKEN_1>`
- **Body JSON (Camino Feliz):**
  ```json
  {
    "email": "investigador.a@wwf.org",
    "password": "Fauna2026Password",
    "full_name": "Dr. Armando Rivera",
    "institution": "WWF Bolivia"
  }
  ```
- **Resultado esperado (`201 Created`):**
  - `message`: `"Cuenta creada correctamente."`
  - `data.user`: `{"id": "...", "email": "investigador.a@wwf.org", "full_name": "Dr. Armando Rivera", "institution": "WWF Bolivia", "role": "user", "is_active": true, ...}`
  - `data.tokens`: `{"access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 1800}`
  - `data.anon_session`: `{"has_data": true, "counts": {"classifications": 0, "camera_stations": 1, "projects": 0}}`
- **Pruebas de Error:**
  - **Email duplicado (`409 AUTH_EMAIL_TAKEN` — `CB-72`):** Envía el mismo body cambiando mayúsculas `"email": "INVESTIGADOR.A@wwf.org"`.
    - *Esperado:* HTTP `409`, `error.code: "AUTH_EMAIL_TAKEN"`, `message: "Ya existe una cuenta con ese correo."`.
  - **Contraseña débil (`422 AUTH_WEAK_PASSWORD`):** Envía `"email": "otro@wwf.org"` y `"password": "corta"` (o `"sololetras"`).
    - *Esperado:* HTTP `422`, `error.code: "AUTH_WEAK_PASSWORD"`, `message: "La contraseña debe tener al menos 8 caracteres, letras y números (máximo 72 bytes)."`.
- [ ] **Camino Feliz (`201 Created` Usuario A + `anon_session.has_data: true`):** Ejecutado. Guarda `USER_A_ACCESS` y `USER_A_REFRESH`.
- [ ] **Caso Error (`409 AUTH_EMAIL_TAKEN` case-insensitive):** Ejecutado y verificado.
- [ ] **Caso Error (`422 AUTH_WEAK_PASSWORD`):** Ejecutado y verificado.

### 3.2 `POST /api/v1/auth/register` — Registro de Usuario B (Para pruebas IDOR / Terceros)
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
- **Resultado esperado (`201 Created`):** Guarda `data.tokens.access_token` como **`USER_B_ACCESS`**.
- [ ] **Registro de Usuario B (`201 Created`):** Ejecutado y guardado `USER_B_ACCESS`.

### 3.3 `POST /api/v1/auth/login` — Inicio de sesión (`#2`)
- **Body JSON (Camino Feliz):**
  ```json
  {
    "email": "investigador.a@wwf.org",
    "password": "Fauna2026Password"
  }
  ```
- **Resultado esperado (`200 OK`):**
  - `message`: `"Sesión iniciada correctamente."`
  - Actualiza `USER_A_ACCESS` y `USER_A_REFRESH` con los nuevos tokens devueltos.
- **Prueba de Error (`401 AUTH_INVALID_CREDENTIALS`):**
  - Envía `"password": "PasswordIncorrecto123"`.
  - *Esperado:* HTTP `401`, `error.code: "AUTH_INVALID_CREDENTIALS"`, `message: "Correo o contraseña incorrectos."` *(Nota: no hagas más de 4 intentos fallidos seguidos con el mismo correo o activarás el rate limit `429 RATE_LIMITED` de 5 intentos/minuto por email).*
- [ ] **Camino Feliz (`200 OK`):** Ejecutado y tokens actualizados.
- [ ] **Caso Error (`401 AUTH_INVALID_CREDENTIALS`):** Ejecutado y verificado.

### 3.4 `POST /api/v1/auth/refresh` — Rotación de Refresh Token y Detección de Reuso (`#3`, `CB-78`)
- **Situación crítica de seguridad (`CB-78`):** Cuando el frontend usa un `refresh_token`, el backend lo marca como revocado y emite una pareja nueva (`access_token` + `refresh_token`). Si alguien intenta **reutilizar** el `refresh_token` viejo ya rotado, el backend detecta el robo/reuso y **revoca todas las sesiones activas del usuario**.
- **Paso 1 (Camino Feliz — Rotación):**
  - **Body JSON:** `{"refresh_token": "<USER_A_REFRESH_VIEJO>"}`
  - **Esperado (`200 OK`):** `message: "Sesión renovada."`, devuelve `data.tokens` con un `<USER_A_REFRESH_NUEVO>`.
- **Paso 2 (Prueba de Error — Reuso del token viejo `401 AUTH_TOKEN_INVALID`):**
  - Vuelve a enviar `{"refresh_token": "<USER_A_REFRESH_VIEJO>"}`.
  - **Esperado (`401 Unauthorized`):** `error.code: "AUTH_TOKEN_INVALID"`, `message: "Se detectó reutilización de sesión. Inicia sesión nuevamente."`.
- **Paso 3 (Verificar que el `<USER_A_REFRESH_NUEVO>` también quedó invalidado por la alerta de reuso):**
  - Envía `{"refresh_token": "<USER_A_REFRESH_NUEVO>"}`.
  - **Esperado (`401 Unauthorized`):** `error.code: "AUTH_TOKEN_INVALID"`.
- **Paso 4 (Re-login limpio):**
  - Vuelve a hacer `POST /api/v1/auth/login` con Usuario A, toma el nuevo `USER_A_ACCESS` y autorízalo en el botón **`Authorize`** de Swagger.
- [ ] **Camino Feliz (`200 OK` rotación de refresh token):** Ejecutado y verificado.
- [ ] **Caso Error (`401 AUTH_TOKEN_INVALID` por detección de reuso `CB-78` y revocación total):** Ejecutado y verificado.
- [ ] **Re-login de Usuario A y botón `Authorize` configurado en Swagger:** Listo.

### 3.5 `GET /api/v1/auth/me` y `PATCH /api/v1/auth/me` — Perfil del usuario (`#5`)
- **Auth:** `Bearer <USER_A_ACCESS>` (botón `Authorize`).
1. **`GET /api/v1/auth/me`:**
   - **Esperado (`200 OK`):** Datos completos de `Dr. Armando Rivera`.
   - **Prueba de Error (`401 AUTH_REQUIRED`):** Desconecta `Authorize` un momento y llama a `GET /api/v1/auth/me`. Devuelve `401 AUTH_REQUIRED`. Vuelve a conectar `Authorize` con `USER_A_ACCESS`.
2. **`PATCH /api/v1/auth/me`:**
   - **Body JSON:**
     ```json
     {
       "full_name": "Dr. Armando Rivera M.",
       "institution": "WWF Bolivia - Dirección Científica"
     }
     ```
   - **Esperado (`200 OK`):** `message: "Perfil actualizado."`, `data.full_name` e `institution` actualizados.
   - **Prueba de Error (`422 VALIDATION_ERROR`):** Envía `{"full_name": "   "}` (solo espacios) o un campo extra no permitido `{"role": "admin"}` (`extra="forbid"`). Devuelve `422 VALIDATION_ERROR`.
- [ ] **Camino Feliz (`GET /auth/me` → `200 OK` y `PATCH /auth/me` → `200 OK`):** Ejecutado y verificado.
- [ ] **Casos Error (`401 AUTH_REQUIRED` sin token y `422 VALIDATION_ERROR` con nombre vacío/campo extra):** Ejecutados y verificados.

### 3.6 `POST /api/v1/auth/me/password` — Cambio de contraseña (`#6`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Prueba de Error primero (`401 AUTH_INVALID_CREDENTIALS`):**
  - **Body JSON:** `{"current_password": "PasswordErroneo1", "new_password": "NuevaPassword2026"}`
  - **Esperado (`401 Unauthorized`):** `error.code: "AUTH_INVALID_CREDENTIALS"`, `message: "La contraseña actual es incorrecta."` *(Nota para Miguel: en este endpoint un `401` con código `AUTH_INVALID_CREDENTIALS` significa que escribió mal su contraseña actual, NO que expiró su JWT).*
- **Camino Feliz (`200 OK`):**
  - **Body JSON:** `{"current_password": "Fauna2026Password", "new_password": "Fauna2026Password"}`
  - **Esperado (`200 OK`):** `data: null`, `message: "Contraseña actualizada."`.
- [ ] **Caso Error (`401 AUTH_INVALID_CREDENTIALS` con contraseña actual incorrecta):** Ejecutado y verificado.
- [ ] **Camino Feliz (`200 OK` cambio de contraseña):** Ejecutado y verificado.

### 3.7 `POST /api/v1/auth/logout` — Cierre de sesión (`#4`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Body JSON (Camino Feliz):** `{"refresh_token": "<USER_A_REFRESH_ACTUAL>"}`
- **Resultado esperado (`200 OK`):** `data: null`, `message: "Sesión cerrada."`.
- **Prueba de Error (`401 AUTH_TOKEN_INVALID`):**
  - Envía `{"refresh_token": "token-inexistente-o-de-otro-usuario"}`.
  - **Esperado (`401 Unauthorized`):** `error.code: "AUTH_TOKEN_INVALID"`.
- *(Nota: el `access_token` JWT de Usuario A sigue funcionando hasta que cumpla sus 30 min, así que no necesitas volver a hacer login en Swagger).*
- [ ] **Camino Feliz (`200 OK` logout revoca refresh token):** Ejecutado y verificado.
- [ ] **Caso Error (`401 AUTH_TOKEN_INVALID`):** Ejecutado y verificado.

### 3.8 Endpoints de Recuperación de Contraseña por Correo (`#6b` — `FL-14`)
- **Cómo funciona hoy:** `PASSWORD_RECOVERY_ENABLED` solo apaga el **envío** (`forgot`). Validar y usar un enlace funciona siempre, para que sirva el enlace manual del admin (Bloque 11, M4-1). El correo lo envía el **worker** (job `send_reset_email`); si Redis no responde, lo envía la API como respaldo.
- **Con la recuperación apagada (`PASSWORD_RECOVERY_ENABLED=false`):**
  - `POST /api/v1/auth/password/forgot` con `{"email": "investigador.a@wwf.org"}` → **`503 EMAIL_TEMPORARILY_UNAVAILABLE`**.
  - `GET /api/v1/auth/password/reset/validate?token=cualquier-token` → **`200`** con `data.valid: false`.
  - `POST /api/v1/auth/password/reset` con `{"token": "cualquier-token", "new_password": "Fauna2026Password"}` → **`400 AUTH_RESET_TOKEN_INVALID`**.
- **Con Resend encendido en desarrollo** (ver 12.1): `forgot` responde `200` con el mensaje genérico, el worker envía el correo y el enlace lleva a `FRONTEND_BASE_URL/restablecer?token=…`.
  - Con `onboarding@resend.dev`, Resend solo entrega al correo dueño de la cuenta: registra el usuario de prueba con ese correo.
  - Copia el `token` del enlace y prueba `validate` (`valid: true`) y `reset` (`200`). Repetir `reset` con el mismo token → `400 AUTH_RESET_TOKEN_INVALID` (un solo uso).
- [ ] **Recuperación apagada:** `forgot` 503, `validate` 200 `valid:false`, `reset` 400.
- [ ] **Recuperación con Resend:** correo recibido, `validate` → `valid: true`, `reset` → 200, segundo `reset` → 400.

### 3.9 `POST /api/v1/anon-sessions/claim` — Reclamar Sesión Anónima con Renombrado Automático `-2` (`#9`, `FL-04`)
- **Situación:** Usuario A ya tiene sesión `Bearer <USER_A_ACCESS>`. Antes de reclamar su sesión anónima (`ANON_TOKEN_1`, que adentro tiene una cámara llamada `"CAM-01"`), Usuario A va a crear en su cuenta una cámara propia también llamada `"CAM-01"`. Luego llamará a `/anon-sessions/claim` enviando tanto su `Bearer` como `X-Anon-Token: <ANON_TOKEN_1>`.
1. **Paso previo:** Con `Bearer <USER_A_ACCESS>` en Swagger, ejecuta `POST /api/v1/camera-stations`:
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
   - **Esperado (`201 Created`):** Guarda este `data.id` como **`CAM_PUB_ID`**.
2. **Ejecutar `POST /api/v1/anon-sessions/claim`:**
   - **Auth:** `Bearer <USER_A_ACCESS>` + Header `X-Anon-Token: <ANON_TOKEN_1>`.
   - **Resultado esperado (`200 OK`):**
     - `message`: `"Datos asociados a tu cuenta."`
     - `data`:
       ```json
       {
         "claimed": {
           "classifications": 0,
           "camera_stations": 1,
           "projects": 0
         },
         "renamed_camera_stations": [
           {
             "id": "<ANON_CAM_ID>",
             "old_code": "CAM-01",
             "new_code": "CAM-01-2"
           }
         ]
       }
       ```
3. **Probar Idempotencia (Mismo Usuario A vuelve a llamar `POST /api/v1/anon-sessions/claim` con `<ANON_TOKEN_1>`):**
   - **Esperado (`200 OK`):** Devuelve `claimed: {classifications: 0, camera_stations: 0, projects: 0}` y `renamed_camera_stations: []`.
4. **Probar Conflicto (Usuario B intenta reclamar el mismo `<ANON_TOKEN_1>` — `409 ANON_SESSION_ALREADY_CLAIMED`):**
   - Cambia `Authorize` a `USER_B_ACCESS` y ejecuta `POST /api/v1/anon-sessions/claim` con `X-Anon-Token: <ANON_TOKEN_1>`.
   - **Esperado (`409 Conflict`):** `error.code: "ANON_SESSION_ALREADY_CLAIMED"`, `message: "Estos datos ya se asociaron a otra cuenta."`.
   - *(Vuelve a poner `USER_A_ACCESS` en `Authorize`).*
- [ ] **Camino Feliz (`200 OK` claim transfiere cámara y la renombra a `CAM-01-2`):** Ejecutado y verificado.
- [ ] **Idempotencia mismo usuario (`200 OK` con conteos en 0):** Ejecutado y verificado.
- [ ] **Caso Error (`409 ANON_SESSION_ALREADY_CLAIMED` cuando otro usuario intenta reclamarla):** Ejecutado y verificado.

---

## Bloque 4: Estaciones de Cámara Trampa, Privacidad DD-17, Cercanía (`nearby`) y Reinstalación (`redeploy`) (`FL-05`, `FL-06`, `FL-13`, `FL-15`, `#13`–`#15c`)

**Situación:** Usuario A gestiona sus estaciones de muestreo. Ya tiene `CAM-01` (pública, `CAM_PUB_ID`) y `CAM-01-2` (privada, reclamada de la sesión anónima). Crearemos una cámara privada adicional (`CAM-PRIV-01`) con coordenadas invertidas para ver el warning `CAMERA_COORDS_SUSPECT`, probaremos el bloqueo optimista `If-Match`, la detección de cámaras cercanas (`nearby`), la reinstalación (`redeploy`) y finalmente cambiaremos a **Usuario B** para certificar la regla innegociable **DD-17**: un tercero solo ve coordenadas redondeadas a 2 decimales (`location_precision: "approx_1km"`) en cámaras públicas ajenas y recibe `404 CAMERA_NOT_FOUND` en cámaras privadas ajenas.

### 4.1 `POST /api/v1/camera-stations` — Crear cámara privada con Warning de coordenadas sospechosas (`#13`, `CB-07`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Body JSON (Camino Feliz + Warning `CAMERA_COORDS_SUSPECT` por lat/lng invertidas respecto a Bolivia):**
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
- **Resultado esperado (`201 Created`):**
  - Guarda `data.id` como **`CAM_PRIV_ID`**.
  - `data.version`: `1`, `data.location_precision`: `"exact"`.
  - `meta.warnings`: contiene `[{"code": "CAMERA_COORDS_SUSPECT", "message": "Revisa las coordenadas: ¿latitud y longitud están invertidas?", "context": {"latitude": -64.9, "longitude": -16.5}}]`.
- **Pruebas de Error en `POST /api/v1/camera-stations`:**
  1. **Código duplicado case-insensitive (`409 CAMERA_CODE_TAKEN` — `CB-13`):**
     - Envía `"code": "cam-01"` (en minúsculas).
     - *Esperado:* HTTP `409`, `error.code: "CAMERA_CODE_TAKEN"`, `message: "Ya tienes una cámara con ese código."`.
  2. **Fecha con zona horaria (`422 VALIDATION_ERROR`):**
     - Envía `"deployed_at": "2026-10-10T09:00:00Z"` (con `Z` o `-04:00`).
     - *Esperado:* HTTP `422`, `error.code: "VALIDATION_ERROR"` (`"La fecha va en hora local de la cámara, sin zona horaria."`).
  3. **Inconsistencia `still_installed` vs `retrieved_at` (`422 CAMERA_INVALID_DATES` — `CB-11`/`CB-12`):**
     - Envía `"still_installed": true` junto con `"retrieved_at": "2026-11-01T17:00:00"`.
     - *Esperado:* HTTP `422`, `error.code: "CAMERA_INVALID_DATES"`, `message: "Si la cámara sigue instalada, no lleva fecha de retiro."`.
     - Envía `"still_installed": false` con `"retrieved_at": "2026-09-01T00:00:00"` (anterior a `deployed_at`).
     - *Esperado:* HTTP `422`, `error.code: "CAMERA_INVALID_DATES"`, `message: "El retiro no puede ser anterior a la colocación."`.
- [ ] **Camino Feliz (`201 Created` `CAM-PRIV-01` + warning `CAMERA_COORDS_SUSPECT`):** Ejecutado y guardado `CAM_PRIV_ID`.
- [ ] **Caso Error (`409 CAMERA_CODE_TAKEN` case-insensitive):** Ejecutado y verificado.
- [ ] **Caso Error (`422 VALIDATION_ERROR` cuando se envía timezone `Z`):** Ejecutado y verificado.
- [ ] **Caso Error (`422 CAMERA_INVALID_DATES` por fechas incoherentes):** Ejecutado y verificado.

### 4.2 `GET /api/v1/camera-stations` y `GET /api/v1/camera-stations/{camera_id}` — Exploración y Privacidad DD-17 (`#13`, `#14`)
1. **Como Dueño (`Bearer <USER_A_ACCESS>`):**
   - `GET /api/v1/camera-stations?scope=mine&view=full` → Devuelve las 3 cámaras de Usuario A con coordenadas exactas (6 decimales) y `location_precision: "exact"`.
   - `GET /api/v1/camera-stations?scope=all&view=map` → Devuelve items ligeros `CameraStationMapItem` (`id, code, name, latitude, longitude, location_precision, visibility, is_mine, still_installed, sightings, species`).
2. **Como Tercero (`Bearer <USER_B_ACCESS>` — Prueba DD-17 e IDOR):**
   - Cambia `Authorize` a **`USER_B_ACCESS`**.
   - **Paso A (`GET /api/v1/camera-stations/{CAM_PUB_ID}` — Cámara Pública de Usuario A):**
     - *Esperado (`200 OK`):* `data.latitude` y `data.longitude` vienen **redondeadas a 2 decimales** (`-14.5`, `-67.5`), `data.location_precision` es **`"approx_1km"`**, y `data.owner.is_mine` es `false`.
   - **Paso B (`GET /api/v1/camera-stations/{CAM_PRIV_ID}` — Cámara Privada de Usuario A):**
     - *Esperado (`404 Not Found` — Regla S1/CB-05):* `error.code: "CAMERA_NOT_FOUND"`, `message: "La cámara no existe o no tienes acceso a ella."` (Nunca `403`, para no revelar que el UUID existe).
   - **Paso C (`GET /api/v1/camera-stations` con `bbox` malformado):**
     - Llama con `bbox=1,2,3` (solo 3 números).
     - *Esperado (`422 VALIDATION_ERROR`):* `"bbox debe ser minLng,minLat,maxLng,maxLat."`.
   - *(Vuelve a poner `USER_A_ACCESS` en `Authorize`).*
- [ ] **Listado `view=full` y `view=map` como dueño (`200 OK`):** Ejecutado y verificado.
- [ ] **Verificación DD-17 como Usuario B (`200 OK` con `approx_1km` en pública ajena):** Ejecutado y verificado.
- [ ] **Verificación S1 como Usuario B (`404 CAMERA_NOT_FOUND` en privada ajena):** Ejecutado y verificado.
- [ ] **Caso Error (`422 VALIDATION_ERROR` en `bbox` malformado):** Ejecutado y verificado.

### 4.3 `PATCH /api/v1/camera-stations/{camera_id}` — Edición con Control de Concurrencia `If-Match` (`#14`, `CB-15`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `camera_id = <CAM_PUB_ID>`.
- **Header obligatorio:** `If-Match: 1` (o `"1"`).
- **Body JSON (Camino Feliz):**
  ```json
  {
    "name": "Cámara Principal Madidi (Actualizada)",
    "latitude": -14.512345,
    "longitude": -67.512345
  }
  ```
- **Resultado esperado (`200 OK`):**
  - `message`: `"Cámara actualizada."`
  - `data.version` sube a **`2`**.
- **Pruebas de Error:**
  1. **Versión desactualizada (`409 CONFLICT_STALE` — `CB-15`):**
     - Vuelve a enviar el mismo `PATCH` manteniendo el header `If-Match: 1` (cuando la cámara ya va por `version: 2`).
     - *Esperado:* HTTP `409`, `error.code: "CONFLICT_STALE"`, `message: "La cámara se modificó en otra ventana. Recarga para ver los cambios."`.
  2. **`If-Match` no numérico (`422 VALIDATION_ERROR`):**
     - Envía `If-Match: abc`.
     - *Esperado:* HTTP `422`, `error.code: "VALIDATION_ERROR"`, `message: "If-Match debe ser la versión del recurso."`.
  3. **Edición de cámara pública ajena (`403 FORBIDDEN`):**
     - Cambia a `USER_B_ACCESS` e intenta hacer `PATCH` a `<CAM_PUB_ID>` con `If-Match: 2`.
     - *Esperado:* HTTP `403`, `error.code: "FORBIDDEN"`, `message: "Esta cámara no es tuya."`.
     - *(Vuelve a poner `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`200 OK` con `If-Match: 1` → `version` pasa a `2`):** Ejecutado y verificado.
- [ ] **Caso Error (`409 CONFLICT_STALE` al reutilizar `If-Match: 1`):** Ejecutado y verificado.
- [ ] **Caso Error (`422 VALIDATION_ERROR` con `If-Match` inválido):** Ejecutado y verificado.
- [ ] **Caso Error (`403 FORBIDDEN` cuando Usuario B intenta editar cámara pública de Usuario A):** Ejecutado y verificado.

### 4.4 `GET /api/v1/camera-stations/nearby` — Detección de Cámaras Cercanas con Bandas de Privacidad (`#15b`, `CB-04`, `CB-05`)
- **Situación:** Consultamos qué cámaras hay a menos de 200 metros de `(-14.512345, -67.512345)`.
1. **Como Dueño (`USER_A_ACCESS`):**
   - Query params: `lat=-14.512345`, `lng=-67.512345`, `radius_m=200`.
   - **Esperado (`200 OK`):** `data.mine` incluye a `CAM-01` con `distance_m: 0.0`, `same_location: true`, `overlapping_period: true`. `data.public_others` viene vacío `[]`.
2. **Como Tercero (`USER_B_ACCESS` — Prueba `CB-04`):**
   - Cambia a `USER_B_ACCESS` y ejecuta el mismo `GET /api/v1/camera-stations/nearby?lat=-14.512345&lng=-67.512345&radius_m=200`.
   - **Esperado (`200 OK`):** `data.mine` viene vacío `[]`, y en `data.public_others` aparece `CAM-01` **sin distancia exacta ni coordenadas**, solo con `"distance_band": "<10m"` (o `"<50m"`/`"<200m"`) y los datos públicos del dueño. Las cámaras privadas de Usuario A jamás aparecen en `public_others`.
   - *(Vuelve a poner `USER_A_ACCESS`).*
- [ ] **Camino Feliz como Dueño (`200 OK` en `data.mine` con `distance_m` exacto):** Ejecutado y verificado.
- [ ] **Camino Feliz como Tercero (`200 OK` en `data.public_others` solo con `distance_band`):** Ejecutado y verificado.

### 4.5 `POST /api/v1/camera-stations/{camera_id}/redeploy` — Reinstalación en el mismo punto (`#15c`, `FL-15`, `CB-03`)
- **Situación:** El investigador retira la tarjeta de memoria/baterías de la cámara `CAM-01-2` (`ANON_CAM_ID`, instalada el `2026-10-01`) y abre un nuevo período de instalación en el mismo árbol.
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `camera_id = <ANON_CAM_ID>` (`CAM-01-2`).
- **Body JSON (Camino Feliz — dejando `code: null` para que sugiera `CAM-01-3` automáticamente):**
  ```json
  {
    "code": null,
    "deployed_at": "2026-11-05T10:00:00",
    "close_previous": true,
    "previous_retrieved_at": "2026-11-05T09:30:00",
    "observations": "Cambio de baterías y SD en el mismo punto"
  }
  ```
- **Resultado esperado (`201 Created`):**
  - `message`: `"Nueva instalación registrada."`
  - `data.camera_station`: Nueva cámara con `code: "CAM-01-3"`, `still_installed: true`, `previous_camera_station_id: "<ANON_CAM_ID>"`. Guarda su `id` como **`CAM_REDEPLOY_ID`**.
  - `data.previous`: La cámara `<ANON_CAM_ID>` ahora aparece cerrada (`still_installed: false`, `retrieved_at: "2026-11-05T09:30:00"`).
- **Prueba de Error (`422 CAMERA_INVALID_DATES`):**
  - Intenta hacer `redeploy` con `"deployed_at": "2026-08-01T00:00:00"` (anterior a la colocación de la cámara previa).
  - *Esperado:* HTTP `422`, `error.code: "CAMERA_INVALID_DATES"`, `message: "La nueva colocación no puede ser anterior a la de la cámara previa."`.
- [ ] **Camino Feliz (`201 Created` crea nueva instalación `CAM-01-3` y cierra la anterior):** Ejecutado y guardado `CAM_REDEPLOY_ID`.
- [ ] **Caso Error (`422 CAMERA_INVALID_DATES` con fecha anterior a la cámara previa):** Ejecutado y verificado.

### 4.6 `DELETE /api/v1/camera-stations/{camera_id}` — Borrado Lógico en Cascada (`#14`, `CB-21`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `camera_id = <CAM_REDEPLOY_ID>` (borramos `CAM-01-3` para mantener vivas `CAM_PUB_ID` y `CAM_PRIV_ID`).
- **Resultado esperado (`204 No Content`):** Cuerpo vacío.
- **Prueba de Error (`409 ENTITY_ALREADY_DELETED`):**
  - Vuelve a ejecutar `DELETE /api/v1/camera-stations/{CAM_REDEPLOY_ID}`.
  - *Esperado:* HTTP `409`, `error.code: "ENTITY_ALREADY_DELETED"`, `message: "La cámara ya estaba eliminada."`.
- [ ] **Camino Feliz (`204 No Content`):** Ejecutado y verificado.
- [ ] **Caso Error (`409 ENTITY_ALREADY_DELETED` al borrar dos veces):** Ejecutado y verificado.

### 4.7 `POST /api/v1/camera-stations/{camera_id}/time-offset` — Corregir la hora de la cámara (`#15d`, `CB-18`, D14)
> Hazlo después del Bloque 6, cuando la cámara ya tenga clasificaciones con fecha de `exif` o del nombre del archivo.
- **Auth:** `Bearer <USER_A_ACCESS>` (solo el dueño).
- **Path Param:** `camera_id = <CAM_PUB_ID>`.
- **Body JSON:**
  ```json
  { "offset_seconds": 3600, "from": null, "to": null, "reason": "Reloj en horario incorrecto" }
  ```
- **Resultado esperado (`200 OK`):** `data: { "updated": <n> }`, con `n` = cantidad de clasificaciones con fecha de `exif`, `container` o `filename` (las de `upload_time` no se tocan).
- **Comprobación:** `GET /api/v1/classifications/{CLASSIFICATION_ID}` muestra `captured_at` una hora después y `captured_at_original` con la fecha anterior. Si repites la corrección, `captured_at_original` conserva la primera.
- **Pruebas de Error:**
  - `offset_seconds: 0` o sin `reason` → `422 VALIDATION_ERROR`.
  - Con `Bearer <USER_B_ACCESS>`: cámara pública ajena → `403`; privada ajena → `404 CAMERA_NOT_FOUND`.
- [ ] **Camino Feliz (`200` con `updated` y `captured_at_original`):** Ejecutado y verificado.
- [ ] **Casos Error (`422`, `403`, `404`):** Ejecutado y verificado.

---

## Bloque 5: Proyectos y Asociación N:M Segura de Cámaras Propias (`FL-07`, `#16`–`#19`)

**Situación:** Usuario A crea un **Proyecto Público** llamado `"Monitoreo Jaguar Madidi 2026"` asociando inicialmente su cámara pública (`CAM_PUB_ID`). Luego asocia también su cámara privada (`CAM_PRIV_ID`). Cuando Usuario B consulta este proyecto público, se cumple `CB-20`: **dentro de un proyecto público, las cámaras privadas no se exponen ni suman para terceros**, pero el dueño sí ve ambas.

### 5.1 `POST /api/v1/projects` — Crear proyecto con cámaras iniciales (`#16`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Body JSON (Camino Feliz):**
  ```json
  {
    "name": "Monitoreo Jaguar Madidi 2026",
    "description": "Evaluación estacional con cámaras trampa",
    "visibility": "public",
    "camera_station_ids": [
      "<CAM_PUB_ID>"
    ]
  }
  ```
- **Resultado esperado (`201 Created`):**
  - `message`: `"Proyecto creado."`
  - `data`: `ProjectDetail` con `version: 1`, `camera_station_ids: ["<CAM_PUB_ID>"]` y `camera_stations: [...]`. Guarda `data.id` como **`PROJ_PUB_ID`**.
- **Prueba de Error IDOR (`403 CAMERA_NOT_OWNED` — `CB-23`):**
  - Cambia `Authorize` a **`USER_B_ACCESS`** e intenta crear un proyecto de Usuario B metiendo en `camera_station_ids` la cámara pública de Usuario A (`["<CAM_PUB_ID>"]`).
  - *Esperado (`403 Forbidden`):* `error.code: "CAMERA_NOT_OWNED"`, `message: "Solo puedes agregar tus propias cámaras al proyecto."` (Si intentara meter `<CAM_PRIV_ID>`, recibiría `404 CAMERA_NOT_FOUND`).
  - *(Vuelve a poner `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`201 Created` proyecto público creado):** Ejecutado y guardado `PROJ_PUB_ID`.
- [ ] **Caso Error IDOR (`403 CAMERA_NOT_OWNED` cuando Usuario B intenta crear proyecto con cámara pública de Usuario A):** Ejecutado y verificado.

### 5.2 `POST /api/v1/projects/{project_id}/camera-stations` — Asociar segunda cámara al proyecto (`#18`, `CB-24`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `project_id = <PROJ_PUB_ID>`.
- **Body JSON (Camino Feliz — agregamos la cámara privada `CAM_PRIV_ID`):**
  ```json
  {
    "camera_station_id": "<CAM_PRIV_ID>"
  }
  ```
- **Resultado esperado (`200 OK`):**
  - `message`: `"Cámara agregada al proyecto."`
  - `data.camera_station_ids` ahora tiene **2** cámaras (`CAM_PUB_ID` y `CAM_PRIV_ID`).
- **Prueba de Error (`409 ALREADY_ASSOCIATED` — `CB-24`):**
  - Vuelve a ejecutar el mismo `POST` con `{"camera_station_id": "<CAM_PRIV_ID>"}`.
  - *Esperado (`409 Conflict`):* `error.code: "ALREADY_ASSOCIATED"`, `message: "La cámara ya está en este proyecto."`.
- [ ] **Camino Feliz (`200 OK` cámara privada asociada al proyecto):** Ejecutado y verificado.
- [ ] **Caso Error (`409 ALREADY_ASSOCIATED` al asociar duplicada):** Ejecutado y verificado.

### 5.3 `GET /api/v1/projects` y `GET /api/v1/projects/{project_id}` — Visibilidad Diferenciada Dueño vs Tercero (`#16`, `#17`, `CB-20`)
1. **Como Dueño (`USER_A_ACCESS`):**
   - `GET /api/v1/projects/{PROJ_PUB_ID}` → `data.counts.camera_stations` es **`2`** y `data.camera_stations` lista tanto `CAM-01` (pública) como `CAM-PRIV-01` (privada).
2. **Como Tercero (`USER_B_ACCESS` — Prueba `CB-20`):**
   - Cambia `Authorize` a **`USER_B_ACCESS`** y llama a `GET /api/v1/projects/{PROJ_PUB_ID}`.
   - **Esperado (`200 OK`):** `data.counts.camera_stations` es **`1`**, `data.camera_station_ids` solo incluye `["<CAM_PUB_ID>"]` (la cámara privada de Usuario A queda completamente invisible para terceros, y la cámara pública trae coordenadas redondeadas `approx_1km`).
   - *(Vuelve a poner `USER_A_ACCESS`).*
- [ ] **Verificado como Dueño (`200 OK` ve las 2 cámaras, pública y privada):** Ejecutado y verificado.
- [ ] **Verificado como Tercero `CB-20` (`200 OK` solo ve la cámara pública con `approx_1km`):** Ejecutado y verificado.

### 5.4 `PATCH /api/v1/projects/{project_id}` — Actualizar proyecto con `If-Match` (`#17`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `project_id = <PROJ_PUB_ID>`.
- **Header obligatorio:** `If-Match: 1`.
- **Body JSON:**
  ```json
  {
    "name": "Monitoreo Jaguar Madidi 2026 - Fase I",
    "description": "Actualizado con bloqueo optimista"
  }
  ```
- **Resultado esperado (`200 OK`):** `message: "Proyecto actualizado."`, `data.version: 2`.
- **Prueba de Error (`409 CONFLICT_STALE`):**
  - Vuelve a enviar el `PATCH` con `If-Match: 1`.
  - *Esperado:* HTTP `409`, `error.code: "CONFLICT_STALE"`.
- [ ] **Camino Feliz (`200 OK` con `If-Match: 1`):** Ejecutado y verificado.
- [ ] **Caso Error (`409 CONFLICT_STALE`):** Ejecutado y verificado.

### 5.5 `DELETE /api/v1/projects/{project_id}/camera-stations/{camera_station_id}` y `DELETE /api/v1/projects/{project_id}` (`#17`, `#19`, `CB-27`)
1. **Desasociar y volver a asociar una cámara (`#19`):**
   - Ejecuta `DELETE /api/v1/projects/{PROJ_PUB_ID}/camera-stations/{ANON_CAM_ID}` (una cámara que NO está en el proyecto).
   - *Esperado (`404 CAMERA_NOT_FOUND`):* `"La cámara no está en este proyecto."`.
   - Ejecuta `DELETE /api/v1/projects/{PROJ_PUB_ID}/camera-stations/{CAM_PRIV_ID}` → HTTP `204 No Content`.
   - Vuelve a asociarla con `POST /api/v1/projects/{PROJ_PUB_ID}/camera-stations` (`{"camera_station_id": "<CAM_PRIV_ID>"}`) para que el proyecto tenga ambas cámaras en las pruebas de estadísticas del Bloque 7.
2. **Probar borrado lógico de proyecto sin borrar cámaras (`#17`, `CB-27`):**
   - Crea un proyecto temporal `POST /api/v1/projects` (`{"name": "Proyecto Temporal", "visibility": "private", "camera_station_ids": ["<CAM_PUB_ID>"]}`).
   - Bórralo con `DELETE /api/v1/projects/{ID_TEMP}` → HTTP `204 No Content`.
   - Vuelve a borrarlo → HTTP `409 ENTITY_ALREADY_DELETED`.
   - Verifica con `GET /api/v1/camera-stations/{CAM_PUB_ID}` que la cámara `CAM-01` sigue intacta (`200 OK`).
- [ ] **Desasociación (`204 No Content` y `404 CAMERA_NOT_FOUND` si no estaba):** Ejecutado y verificado.
- [ ] **Borrado lógico de proyecto (`204 No Content`, `409 ENTITY_ALREADY_DELETED` y cámaras intactas `CB-27`):** Ejecutado y verificado.

---

## Bloque 6: Lotes de Clasificación, Subida a Cola `arq`/Redis, Procesamiento con IA Fauna Real y Evidencias (`FL-08`, `FL-09`, `#21`–`#24b`, `#27`)

**Situación:** Este es el corazón del flujo multimedia (`HU-08`, `HU-09`, `HU-11`). Usuario A abre un lote (`Batch`) para su cámara pública `CAM_PUB_ID` indicando `expected_files: 4`. Sube archivos reales por `multipart/form-data`:
1. `client_index=0`: Foto real de fauna (`animal_1.jpg`) → Entra en cola (`202 Accepted`), el `fauna_worker` la toma, la envía a `ia-clasificacion-fauna` (`:8001/api/v1/detect`), guarda la taxonomía y recodifica el fotograma JPEG sin EXIF en `LocalStorage`.
2. `client_index=1`: Segunda foto real de fauna (`animal_2.jpg`, con archivo/bytes distintos a `animal_1.jpg`) → Entra en cola (`202 Accepted`) y es clasificada por la IA.
3. `client_index=2`: Video largo > 15s (`video_largo.mp4`) → Entra en cola (`202 Accepted`) con warning `VIDEO_TRUNCATED` (`F1-D10`).
4.Prueba de rechazos por ítem (`200 OK` con `status: "error"` en el `BatchItem` sin romper el lote): subir el mismo `animal_1.jpg` en otro índice (`DUPLICATE_FILE` `CB-50`) o un archivo de texto renombrado a `.jpg` (`MEDIA_UNSUPPORTED_FORMAT`).

### 6.1 `POST /api/v1/classification-batches` — Abrir Lote de Subida (`#21`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Body JSON (Camino Feliz):**
  ```json
  {
    "camera_station_id": "<CAM_PUB_ID>",
    "expected_files": 4
  }
  ```
- **Resultado esperado (`201 Created`):**
  - `message`: `"Lote creado."`
  - `data`:
    ```json
    {
      "id": "<BATCH_1_ID>",
      "camera_station_id": "<CAM_PUB_ID>",
      "camera_station_code": "CAM-01",
      "source": "web_upload",
      "status": "open",
      "expected_files": 4,
      "counts": {
        "received": 0,
        "queued": 0,
        "processing": 0,
        "done": 0,
        "failed": 0,
        "cancelled": 0
      },
      "queue": {
        "next_position": null,
        "estimated_wait_seconds": null
      },
      "created_at": "...",
      "completed_at": null,
      "items": []
    }
    ```
  - Guarda `data.id` como **`BATCH_1_ID`**.
- **Pruebas de Error:**
  - **Sin `camera_station_id` (`422 CAMERA_REQUIRED` — `D7`):** Envía `{"camera_station_id": null, "expected_files": 2}`.
    - *Esperado:* HTTP `422`, `error.code: "CAMERA_REQUIRED"`, `message: "Elige la cámara trampa donde se tomaron los archivos."`.
  - **Cámara pública ajena (`403 FORBIDDEN`):** Cambia a `USER_B_ACCESS` e intenta crear un lote en `<CAM_PUB_ID>`.
    - *Esperado:* HTTP `403`, `error.code: "FORBIDDEN"`, `message: "Solo puedes subir archivos a tus propias cámaras."`. *(Vuelve a `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`201 Created` lote `open`):** Ejecutado y guardado `BATCH_1_ID`.
- [ ] **Caso Error (`422 CAMERA_REQUIRED` sin cámara):** Ejecutado y verificado.
- [ ] **Caso Error (`403 FORBIDDEN` en cámara ajena):** Ejecutado y verificado.

### 6.2 `POST /api/v1/classification-batches/{batch_id}/files` — Subida Multipart de Archivos Reales (`#23`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `batch_id = <BATCH_1_ID>`.
1. **Subida 1 (`client_index = 0` — Foto de animal #1):**
   - `file`: Selecciona `animal_1.jpg`
   - `client_index`: `0`
   - `client_mtime`: `2026-10-15T14:20:00`
   - **Esperado (`202 Accepted`):** `message: "Archivo en cola."`, `data.status: "queued"`, `data.classification_id: "<CLS_ANIMAL_1_ID>"` (guárdalo en tu tabla), `data.queue: {"position": 1, "estimated_wait_seconds": ...}`.
2. **Subida 2 (`client_index = 1` — Foto de animal #2, en la misma ventana de 5 min para probar ráfagas luego):**
   - `file`: Selecciona `animal_2.jpg` (bytes distintos a `animal_1.jpg`)
   - `client_index`: `1`
   - `client_mtime`: `2026-10-15T14:22:00` (2 minutos después de `animal_1.jpg`)
   - **Esperado (`202 Accepted`):** `data.status: "queued"`, guarda `data.classification_id` como **`CLS_ANIMAL_2_ID`**.
3. **Subida 3 (`client_index = 2` — Prueba de Rechazo por Ítem: Duplicado SHA-256 `CB-50` o Formato Inválido):**
   - `file`: Selecciona **de nuevo el mismo archivo `animal_1.jpg`**
   - `client_index`: `2`
   - **Esperado (`200 OK` — ¡Ojo para Miguel! No es `4xx`, es `200 OK` con error dentro del `BatchItem` para no tumbar la subida en paralelo del lote):**
     - `message`: `"El archivo no se puede analizar."`
     - `data.status`: `"error"`
     - `data.classification_id`: `null`
     - `data.error`: `{"code": "DUPLICATE_FILE", "message": "Este archivo ya está en esta cámara.", "details": [{"context": {"classification_id": "<CLS_ANIMAL_1_ID>"}}]}`
   - *(Como el `client_index=2` quedó rechazado sin crear fila, puedes reutilizar `client_index=2` subiendo un archivo corrupto `falso.jpg` para ver `data.error.code: "MEDIA_UNSUPPORTED_FORMAT"`, o subir tu `video_largo.mp4` para que entre con `202 Accepted` y `warnings: [{"code": "VIDEO_TRUNCATED", ...}]`).*
4. **Prueba de Error de protocolo (`422 VALIDATION_ERROR` por `client_index` fuera de rango):**
   - Envía `client_index = 10` (mayor o igual a `expected_files: 4`).
   - *Esperado:* HTTP `422`, `error.code: "VALIDATION_ERROR"`, `message: "client_index debe ir de 0 a 3."`.
- [ ] **Camino Feliz (`202 Accepted` en `client_index=0` y `client_index=1`):** Ejecutados y guardados `CLS_ANIMAL_1_ID` y `CLS_ANIMAL_2_ID`.
- [ ] **Rechazo por ítem (`200 OK` con `data.status: "error"` y `DUPLICATE_FILE` / `MEDIA_UNSUPPORTED_FORMAT`):** Ejecutado y verificado.
- [ ] **Caso Error (`422 VALIDATION_ERROR` con `client_index >= expected_files`):** Ejecutado y verificado.

### 6.3 `POST /api/v1/classification-batches/{batch_id}/complete` y `GET /api/v1/classification-batches/{batch_id}` — Cierre de recepción y Polling con IA Real (`#22`, `#24`)
1. **Cerrar recepción de archivos (`POST /api/v1/classification-batches/{BATCH_1_ID}/complete`):**
   - **Esperado (`200 OK`):** Si el worker aún está procesando, `data.status` pasa a `"processing"`; si el worker ya terminó ambos archivos, pasa directo a `"completed"` o `"completed_with_errors"` (si dejaste el rechazo del paso 6.2).
2. **Probar subida a lote cerrado (`409 BATCH_CLOSED`):**
   - Intenta subir otro archivo a `POST /api/v1/classification-batches/{BATCH_1_ID}/files` con `client_index=3`.
   - *Esperado (`409 Conflict`):* `error.code: "BATCH_CLOSED"`, `message: "Este lote ya no recibe archivos."`.
3. **Polling del lote (`GET /api/v1/classification-batches/{BATCH_1_ID}` y `?since=`):**
   - Ejecuta `GET /api/v1/classification-batches/{BATCH_1_ID}` hasta que los ítems `0` y `1` tengan `status: "done"`.
   - Verifica que dentro de cada `BatchItem` con `status: "done"`, el campo `classification` trae el objeto `ClassificationRead` completo devuelto por la IA real (`category`, `taxonomy`, `confidence`, `alternatives`, `evidence`, `model`, `low_evidence`).
   - Prueba el parámetro incremental `?since=2099-01-01T00:00:00Z` → `data.items` viene vacío `[]` porque ningún ítem cambió después de esa fecha.
4. **Bandeja de lotes (`GET /api/v1/classification-batches?active=true`):**
   - **Esperado (`200 OK`):** Lista de lotes activos o recientes (últimos 30 min) con `items: null` (los listados nunca traen `items` para no sobrecargar la red).
- [ ] **Cierre de lote (`POST /complete` → `200 OK`):** Ejecutado y verificado.
- [ ] **Caso Error (`409 BATCH_CLOSED` al intentar subir a un lote cerrado):** Ejecutado y verificado.
- [ ] **Polling con IA Real (`GET /classification-batches/{id}` hasta `status: "done"` y prueba de `?since=`):** Ejecutado y verificado.
- [ ] **Listado de bandeja (`GET /classification-batches?active=true` con `items: null`):** Ejecutado y verificado.

### 6.4 `GET /api/v1/classifications/{classification_id}/evidence` — Descarga de Fotograma JPEG sin EXIF (`#27`)
- **Path Param:** `classification_id = <CLS_ANIMAL_1_ID>`.
1. **Como Dueño (`USER_A_ACCESS`) o Tercero (`USER_B_ACCESS`, ya que `CAM_PUB_ID` es pública):**
   - **Esperado (`200 OK`):** Respuesta binaria `image/jpeg` (Swagger muestra la imagen con el animal detectado por la IA real), header `Cache-Control: private, max-age=3600`.
2. **Prueba de Error (`404 CLASSIFICATION_NOT_FOUND`):**
   - Llama con un UUID inexistente `00000000-0000-0000-0000-000000000000`.
   - *Esperado:* HTTP `404`, envoltura JSON con `error.code: "CLASSIFICATION_NOT_FOUND"`.
- [ ] **Camino Feliz (`200 OK` imagen JPEG renderizada en Swagger):** Ejecutado y verificado.
- [ ] **Caso Error (`404 CLASSIFICATION_NOT_FOUND`):** Ejecutado y verificado.

### 6.5 Cancelación y Reintento de Ítems en Lote (`#24b` — `POST .../cancel`, `DELETE .../items/{i}`, `POST .../items/{i}/retry`)
- **Situación:** Probamos los controles de cola cuando un usuario cancela un ítem o un lote, y qué ocurre si intenta cancelar un archivo que ya terminó (`409 ITEM_NOT_CANCELLABLE` `CB-40`).
1. **Intentar cancelar un ítem que ya está `done` (`DELETE /api/v1/classification-batches/{BATCH_1_ID}/items/0`):**
   - **Esperado (`409 Conflict` — `CB-40`):** `error.code: "ITEM_NOT_CANCELLABLE"`, `message: "Este archivo ya se está analizando o terminó."`.
2. **Llamar `POST /api/v1/classification-batches/{BATCH_1_ID}/items/0/retry` sobre un ítem `done`:**
   - **Esperado (`200 OK` idempotente):** Devuelve el mismo `BatchItem` con `status: "done"` sin reencolarlo.
3. **Crear un segundo lote rápido para probar `POST /api/v1/classification-batches/{id}/cancel`:**
   - Crea un lote `POST /api/v1/classification-batches` (`{"camera_station_id": "<CAM_PUB_ID>", "expected_files": 2}`).
   - Cancélalo inmediatamente con `POST /api/v1/classification-batches/{NUEVO_BATCH_ID}/cancel`.
   - **Esperado (`200 OK`):** `message: "Lote cancelado."`, `data.status: "cancelled"`.
- [ ] **Caso Error (`409 ITEM_NOT_CANCELLABLE` al intentar borrar ítem ya procesado `CB-40`):** Ejecutado y verificado.
- [ ] **Retry idempotente sobre ítem `done` (`200 OK`):** Ejecutado y verificado.
- [ ] **Cancelación de lote (`POST /cancel` → `200 OK` con `status: "cancelled"`):** Ejecutado y verificado.

---

## Bloque 7: Consulta de Clasificaciones, Validación Científica Humana y Revisión de Ráfagas (`FL-10`, `FL-16`, `#25`, `#26`, `#28`, `#29`, `#29b`)

**Situación:** La IA ya clasificó `CLS_ANIMAL_1_ID` y `CLS_ANIMAL_2_ID`. Ahora el investigador (Usuario A) filtra sus clasificaciones, revisa las sugerencias de **ráfagas** (`/burst-candidates`, porque ambas fotos ocurrieron con 2 minutos de diferencia en la misma cámara), aplica las **6 acciones de validación humana** (`confirm`, `correct`, `correct_unlisted`, `reject`, `discard_repeat`, `reset`) verificando que **la predicción original de la IA (`taxonomy`) jamás se sobreescribe** y que cada cambio queda auditado en `validation_history`.

### 7.1 `GET /api/v1/classifications` — Listado y Filtros Avanzados (`#25`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Query Params (Camino Feliz):**
  - `camera_station_id`: `<CAM_PUB_ID>`
  - `status`: `done`
  - `category`: `animal` *(o vacío si la IA clasificó tu imagen de prueba en otra categoría)*
  - `sort`: `-captured_at`
- **Resultado esperado (`200 OK`):** Lista paginada con `CLS_ANIMAL_1_ID` y `CLS_ANIMAL_2_ID`.
- **Pruebas de Error:**
  1. **Rango de fechas invertido (`422 VALIDATION_ERROR`):**
     - `from=2026-11-10` y `to=2026-10-01`.
     - *Esperado:* HTTP `422`, `error.code: "VALIDATION_ERROR"`, `message: "La fecha inicial es posterior a la final."`.
  2. **Filtro `taxon` inexistente (`422 CATALOG_TAXON_NOT_FOUND`):**
     - `taxon=taxon-fantasma-999`.
     - *Esperado:* HTTP `422`, `error.code: "CATALOG_TAXON_NOT_FOUND"`.
  3. **Filtro `category` inválido (`422 VALIDATION_ERROR`):**
     - `category=ovni`.
     - *Esperado:* HTTP `422`, `error.code: "VALIDATION_ERROR"`.
- [ ] **Camino Feliz (`200 OK` listado filtrado):** Ejecutado y verificado.
- [ ] **Casos Error (`422` por fechas invertidas, `422 CATALOG_TAXON_NOT_FOUND` y `422` por categoría inválida):** Ejecutados y verificados.

### 7.2 `PUT /api/v1/classifications/{classification_id}/validation` — Las 6 Acciones de Validación Humana (`#28`, `CB-62..66`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `classification_id = <CLS_ANIMAL_1_ID>`.
1. **Acción 1: `confirm` (Confirmar lo que dijo la IA):**
   - **Body JSON:**
     ```json
     {
       "action": "confirm",
       "notes": "Confirmado visualmente por manchas de roseta"
     }
     ```
   - **Esperado (`200 OK`):** `data.validation.status` es `"confirmed"`, `data.validation.notes` tiene la nota, `data.effective_taxonomy` coincide con `data.taxonomy`.
2. **Acción 2: `correct` desde catálogo (`correction_source: "catalog"`):**
   - Usa un `label_id` válido del catálogo obtenido en el Bloque 1.5 (p. ej. el de *Panthera onca*).
   - **Body JSON:**
     ```json
     {
       "action": "correct",
       "label_id": "<LABEL_ID_CATALOGO>",
       "correction_source": "catalog",
       "notes": "Corregido a especie exacta del catálogo"
     }
     ```
   - **Esperado (`200 OK`):** `data.validation.status` es `"corrected"`, `data.validation.corrected_taxonomy` y `data.effective_taxonomy` tienen el nuevo taxón, mientras que **`data.taxonomy` conserva intacto lo que dijo originalmente la IA**. Además, si el archivo era `blank` o `person`, `data.category` pasa automáticamente a `"animal"`.
3. **Prueba de Error en `correct` (`422 VALIDATION_ERROR` cuando `correction_source: "alternative"` no está en `alternatives` de la IA):**
   - Envía `"action": "correct"`, `"correction_source": "alternative"`, y un `"label_id"` válido del catálogo pero que **no** figure en la lista `data.alternatives` de esa foto.
   - **Esperado (`422 Unprocessable Entity`):** `error.code: "VALIDATION_ERROR"`, `message: "Ese taxón no está entre las alternativas de la IA."`.
4. **Acción 3: `correct_unlisted` (Especie fuera del catálogo SpeciesNet — `CB-64`/`CB-65`):**
   - **Prueba de Error primero (`422 VALIDATION_ERROR` si pasas un `label_id` de rango `species`):**
     - Envía `"action": "correct_unlisted"`, `"suggested_name": "Leopardus jacobita"`, y en `"label_id"` pon un ID de rango `species`.
     - *Esperado (`422`):* `"El taxón debe ser superior a especie."`.
   - **Camino Feliz (`200 OK` sin `label_id` o con `label_id` de familia/género):**
     ```json
     {
       "action": "correct_unlisted",
       "label_id": null,
       "suggested_name": "Leopardus garleppi",
       "notes": "Gato del pajonal no listado en SpeciesNet"
     }
     ```
     - *Esperado (`200 OK`):* `data.validation.status: "corrected_unlisted"`, `data.validation.suggested_name: "Leopardus garleppi"`.
5. **Acción 4: `discard_repeat` (Marcar manualmente como repetido de otro registro de la misma cámara):**
   - **Prueba de Error primero (`422 VALIDATION_ERROR` si apunta a sí mismo):**
     - Envía `{"action": "discard_repeat", "repeat_of": "<CLS_ANIMAL_1_ID>"}`.
     - *Esperado (`422`):* `"repeat_of debe ser otro registro de la misma cámara."`.
   - **Camino Feliz (`200 OK` apuntando a `<CLS_ANIMAL_2_ID>`):**
     ```json
     {
       "action": "discard_repeat",
       "repeat_of": "<CLS_ANIMAL_2_ID>",
       "notes": "Mismo individuo 2 minutos antes"
     }
     ```
     - *Esperado (`200 OK`):* `data.validation.status: "discarded_repeat"`, `data.validation.repeat_of: "<CLS_ANIMAL_2_ID>"`.
6. **Acción 5 (`reject`) y Acción 6 (`reset`), y dejar corregida en el mismo taxón para probar Ráfagas:**
   - Envía `{"action": "reject", "notes": "Falso positivo"}` → `data.validation.status: "rejected"`.
   - Envía `{"action": "reset"}` → `data.validation.status: "unvalidated"`, `validated_at: null`.
   - Finalmente, aplica `{"action": "correct", "label_id": "<LABEL_ID_CATALOGO>", "correction_source": "catalog"}` **tanto a `CLS_ANIMAL_1_ID` como a `CLS_ANIMAL_2_ID`** (con el mismo `<LABEL_ID_CATALOGO>`) para garantizar que ambos tengan exactamente la misma taxonomía efectiva y formen una ráfaga en el paso 7.5.
- [ ] **Acción `confirm` (`200 OK`):** Ejecutada y verificada.
- [ ] **Acción `correct` (`200 OK` conserva `taxonomy` de IA y actualiza `effective_taxonomy`):** Ejecutada y verificada.
- [ ] **Caso Error en `correct` (`422` cuando `alternative` no pertenece a `alternatives`):** Ejecutado y verificado.
- [ ] **Acción `correct_unlisted` (`200 OK` + error `422` si `rank == species`):** Ejecutada y verificada.
- [ ] **Acción `discard_repeat` (`200 OK` + error `422` si apunta a sí mismo):** Ejecutada y verificada.
- [ ] **Acciones `reject` y `reset` (`200 OK`), y ambas clasificaciones alineadas al mismo `<LABEL_ID_CATALOGO>`:** Ejecutado y verificado.

### 7.3 `GET /api/v1/classifications/{classification_id}?include=validation_history` — Historial de Validación (`#26`)
1. **Como Dueño (`USER_A_ACCESS`):**
   - Llama a `GET /api/v1/classifications/{CLS_ANIMAL_1_ID}?include=validation_history`.
   - **Esperado (`200 OK`):** `data.validation_history` trae la lista cronológica de todas las acciones que acabas de ejecutar (`confirm`, `correct`, `correct_unlisted`, `discard_repeat`, `reject`, `reset`, `correct`), cada una con `{"at": "...", "by": "<USER_A_ID>", "action": "...", "values": {...}, "notes": "..."}`.
2. **Como Tercero (`USER_B_ACCESS` — Privacidad del historial):**
   - Cambia a `USER_B_ACCESS` y llama al mismo `GET /api/v1/classifications/{CLS_ANIMAL_1_ID}?include=validation_history`.
   - **Esperado (`200 OK`):** Como la cámara es pública, Usuario B ve la clasificación, pero **`data.validation_history` viene en `null`** (el historial nombra a quien validó y solo lo ve el dueño).
   - *(Vuelve a poner `USER_A_ACCESS`).*
- [ ] **Historial completo visible para el dueño (`200 OK` con array `validation_history`):** Ejecutado y verificado.
- [ ] **Historial oculto para terceros (`200 OK` con `validation_history: null`):** Ejecutado y verificado.

### 7.4 `POST /api/v1/classifications/validation-batch` — Validación Masiva con Protección IDOR (`#29`, `CB-67`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Situación:** Enviamos en un solo lote un ID propio (`CLS_ANIMAL_1_ID`) y un UUID inexistente o ajeno (`00000000-0000-0000-0000-000000000099`). Por `CB-67`, lo ajeno o inexistente no aborta el lote ni revela si existe: va a `skipped` con `CLASSIFICATION_NOT_FOUND`.
- **Body JSON:**
  ```json
  {
    "ids": [
      "<CLS_ANIMAL_1_ID>",
      "00000000-0000-0000-0000-000000000099"
    ],
    "action": "confirm",
    "notes": "Confirmación por lote"
  }
  ```
  *(Nota: recuerda volver a aplicar `PUT /validation` con `action: "correct"` y `<LABEL_ID_CATALOGO>` a `<CLS_ANIMAL_1_ID>` después de esta prueba si `CLS_ANIMAL_1_ID` y `CLS_ANIMAL_2_ID` tenían especies distintas de la IA).*
- **Resultado esperado (`200 OK`):**
  ```json
  {
    "updated": 1,
    "skipped": [
      {
        "id": "00000000-0000-0000-0000-000000000099",
        "code": "CLASSIFICATION_NOT_FOUND"
      }
    ]
  }
  ```
- [ ] **Camino Feliz + `CB-67` (`200 OK` con `updated: 1` y `skipped: 1`):** Ejecutado y verificado.

### 7.5 Revisión de Ráfagas: `GET /burst-candidates`, `POST /repeat-batch` y `POST /repeat-batch/dismiss` (`#29b`, `FL-16`, `CB-60..60d`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
1. **Consultar candidatos a ráfaga (`GET /api/v1/classifications/burst-candidates`):**
   - **Prueba de Error primero (`422 VALIDATION_ERROR` si no envías ni cámara ni proyecto, o si envías ambos):**
     - Llama sin parámetros → HTTP `422`, `"Indica una cámara o un proyecto (solo uno)."`.
   - **Camino Feliz:** Llama con `camera_station_id=<CAM_PUB_ID>&window_minutes=10`.
   - **Esperado (`200 OK`):** Devuelve un array con un `BurstGroup` que agrupa `CLS_ANIMAL_1_ID` y `CLS_ANIMAL_2_ID` (misma cámara, mismo taxón efectivo, diferencia de 2 minutos ≤ ventana de 10 min), indicando `suggested_keep_id` y `group_key`. Copia `group_key` como **`BURST_GROUP_KEY`**.
2. **Probar `POST /api/v1/classifications/repeat-batch/dismiss` (Descartar sugerencia y conservar todos):**
   - **Body JSON:**
     ```json
     {
       "group_key": "<BURST_GROUP_KEY>",
       "window_minutes": 10
     }
     ```
   - **Esperado (`200 OK`):** `data: {"dismissed": 2}`. Si vuelves a llamar a `GET /burst-candidates?camera_station_id=<CAM_PUB_ID>&window_minutes=10&include_reviewed=false`, ya no aparece; con `include_reviewed=true` vuelve a aparecer.
3. **Probar `POST /api/v1/classifications/repeat-batch` (Conservar uno y descartar repetidos — `CB-60d`):**
   - **Prueba de Error primero (`422 REPEAT_KEEP_REQUIRED` — `CB-60d`):**
     - Envía `{"keep_ids": [], "discard_ids": ["<CLS_ANIMAL_2_ID>"]}`.
     - *Esperado (`422`):* `error.code: "REPEAT_KEEP_REQUIRED"`, `message: "Conserva al menos un registro. Para conservar todos, descarta la sugerencia."`.
   - **Prueba de Error (`422 VALIDATION_ERROR` por intersección):**
     - Envía el mismo ID en `keep_ids` y `discard_ids`.
     - *Esperado (`422`):* `"Un registro no puede conservarse y descartarse a la vez."`.
   - **Camino Feliz (`200 OK`):**
     ```json
     {
       "keep_ids": ["<CLS_ANIMAL_1_ID>"],
       "discard_ids": ["<CLS_ANIMAL_2_ID>"],
       "notes": "Ráfaga revisada: conservamos la toma más nítida"
     }
     ```
     - *Esperado (`200 OK`):* `data: {"kept": 1, "discarded": 1}`. `<CLS_ANIMAL_2_ID>` queda en estado `discarded_repeat` apuntando a `<CLS_ANIMAL_1_ID>`.
- [ ] **Candidatos a ráfaga (`GET /burst-candidates` → `200 OK` + error `422` sin alcance):** Ejecutado y verificado.
- [ ] **Dismiss de ráfaga (`POST /repeat-batch/dismiss` → `200 OK`):** Ejecutado y verificado.
- [ ] **Resolución de ráfaga (`POST /repeat-batch` → `200 OK` + error `422 REPEAT_KEEP_REQUIRED`):** Ejecutado y verificado.

### 7.6 `PATCH /api/v1/classifications/{classification_id}` — Mover Clasificación a otra Cámara Propia (`#26`, `CB-51`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Situación:** Movemos temporalmente `CLS_ANIMAL_2_ID` a la cámara privada `CAM_PRIV_ID` (para que la cámara privada también tenga datos en las pruebas de estadísticas del Bloque 8).
- **Path Param:** `classification_id = <CLS_ANIMAL_2_ID>`.
- **Body JSON:**
  ```json
  {
    "camera_station_id": "<CAM_PRIV_ID>"
  }
  ```
- **Resultado esperado (`200 OK`):** `message: "Clasificación movida"`, `data.camera_station_id: "<CAM_PRIV_ID>"`.
  - *(Además, haz un `PUT /api/v1/classifications/{CLS_ANIMAL_2_ID}/validation` con `{"action": "confirm"}` para que cuente como avistamiento activo en la cámara privada `<CAM_PRIV_ID>`).*
- [ ] **Camino Feliz (`200 OK` clasificación movida a `CAM_PRIV_ID` y confirmada):** Ejecutado y verificado.

---

## Bloque 8: Estadísticas Ecológicas y Exportación de Reportes Científicos Excel y PDF (`FL-11`, `FL-12`, `#15`, `#20`, `#31`)

**Situación:** Ahora el proyecto público `PROJ_PUB_ID` tiene **2 cámaras**:
- `CAM_PUB_ID` (Pública): con 1 avistamiento confirmado (`CLS_ANIMAL_1_ID`).
- `CAM_PRIV_ID` (Privada): con 1 avistamiento confirmado (`CLS_ANIMAL_2_ID`).
Verificaremos que los números de `/stats`, `/reports/excel` y `/reports/pdf` salen de `stats_service.compute`, y que cuando consulta **Usuario A (Dueño)** suma **2 avistamientos**, pero cuando consulta **Usuario B (Tercero)** sobre el mismo proyecto público solo suma **1 avistamiento** (excluyendo la cámara privada `CB-20`) y redondea las coordenadas en la hoja *Clasificaciones* del Excel (`DD-17`).

### 8.1 `GET /api/v1/camera-stations/{camera_id}/stats` — Estadísticas por Cámara (`#15`)
1. **Como Dueño (`USER_A_ACCESS`) en `<CAM_PUB_ID>`:**
   - **Esperado (`200 OK`):** `data.scope: "camera_station"`, `data.totals.sightings: 1`, secciones `totals, richness, non_animal, by_species, by_genus, by_family, unidentified_to_species, by_month, by_hour, effort` pobladas (`by_camera` es `null` cuando `scope == "camera_station"`).
   - Prueba filtro `?sections=totals,effort` → Solo vienen pobladas `totals` y `effort`; las demás secciones vienen en `null`.
2. **Pruebas de Error:**
   - `?sections=totals,clima_lunar` → HTTP `422`, `error.code: "VALIDATION_ERROR"`, `"Sección de estadísticas desconocida."`.
   - Cambia a **`USER_B_ACCESS`** y pide `GET /api/v1/camera-stations/{CAM_PRIV_ID}/stats` → HTTP `404`, `error.code: "CAMERA_NOT_FOUND"`. *(Vuelve a `USER_A_ACCESS`).*
- [ ] **Camino Feliz (`200 OK` completo y con `?sections=totals,effort`):** Ejecutado y verificado.
- [ ] **Casos Error (`422` por sección desconocida y `404 CAMERA_NOT_FOUND` en cámara privada ajena):** Ejecutados y verificados.

### 8.2 `GET /api/v1/projects/{project_id}/stats` — Estadísticas por Proyecto y Exclusión de Privadas a Terceros (`#20`, `CB-20`)
1. **Como Dueño (`USER_A_ACCESS`) en `<PROJ_PUB_ID>`:**
   - **Esperado (`200 OK`):** `data.totals.sightings` es **`2`**, y `data.by_camera` lista las **2 cámaras** (`CAM-01` con 1 avistamiento y `CAM-PRIV-01` con 1 avistamiento).
2. **Como Tercero (`USER_B_ACCESS` — Prueba `CB-20`):**
   - Cambia a **`USER_B_ACCESS`** y llama a `GET /api/v1/projects/{PROJ_PUB_ID}/stats`.
   - **Esperado (`200 OK`):** `data.totals.sightings` es **`1`**, y `data.by_camera` **solo lista `CAM-01`** (los datos de la cámara privada de Usuario A no se filtran ni siquiera agregados en los totales del proyecto público).
   - *(Vuelve a poner `USER_A_ACCESS`).*
- [ ] **Stats de proyecto como Dueño (`200 OK` suma las 2 cámaras = 2 avistamientos):** Ejecutado y verificado.
- [ ] **Stats de proyecto como Tercero `CB-20` (`200 OK` suma solo la cámara pública = 1 avistamiento):** Ejecutado y verificado.

### 8.3 `GET /api/v1/reports/excel` y `GET /api/v1/reports/pdf` — Exportación Científica (`#31`, `FL-12`)
1. **Descargar Excel como Tercero (`USER_B_ACCESS`) para certificar DD-17 en Excel:**
   - Con `USER_B_ACCESS`, llama a `GET /api/v1/reports/excel?project_id=<PROJ_PUB_ID>`.
   - **Esperado (`200 OK`):** Descarga archivo binario `WWM_Monitoreo-Jaguar-Madidi-2026-Fase-I_<AAAAMMDD>.xlsx`.
   - **Verificación física al abrir el `.xlsx`:**
     - Tiene las **5 hojas oficiales**: `Resumen`, `Por especie`, `Por género`, `Por familia`, `Clasificaciones`.
     - En la hoja `Clasificaciones`, solo aparece el archivo de `CAM-01` y sus columnas `Latitud` y `Longitud` están **redondeadas a 2 decimales** (`-14.51`, `-67.51`).
2. **Descargar PDF como Dueño (`USER_A_ACCESS`):**
   - Cambia a `USER_A_ACCESS` y llama a `GET /api/v1/reports/pdf?project_id=<PROJ_PUB_ID>`.
   - **Esperado (`200 OK`):** Descarga archivo `WWM_...pdf` con portada, totales (2 avistamientos), gráficos de barras y `request_id` en el pie de página.
3. **Pruebas de Error en `/reports/excel` y `/reports/pdf`:**
   - **Sin cámara ni proyecto (`422 VALIDATION_ERROR`):** Llama a `GET /api/v1/reports/excel` sin parámetros → HTTP `422`, `"Indica una cámara o un proyecto (solo uno)."`.
   - **Filtro sin resultados (`404 REPORT_EMPTY`):** Llama con `project_id=<PROJ_PUB_ID>&from=2020-01-01&to=2020-01-02` → HTTP `404`, envoltura JSON con `error.code: "REPORT_EMPTY"`, `message: "No hay clasificaciones para esos filtros."`.
- [ ] **Excel `.xlsx` descargado y verificado (5 hojas + coordenadas redondeadas a terceros DD-17):** Ejecutado y verificado.
- [ ] **PDF `.pdf` descargado y verificado:** Ejecutado y verificado.
- [ ] **Casos Error (`422` sin alcance y `404 REPORT_EMPTY` cuando no hay filas):** Ejecutados y verificados.

---

## Bloque 9: Importación Segura de Paquetes de Escritorio `.wwm.zip` (`FL-23`, `#32`–`#35`, `CB-80..87`)

**Situación:** El investigador procesó cientos de fotos en campo sin internet usando la app de escritorio (`ia-clasificacion-fauna/desktop`), que exportó un archivo `.wwm.zip` (`manifest.json` + `classifications.jsonl` + `evidence/<sha256>.jpg`). Ahora en la web sube ese paquete en dos fases:
1. **Vista previa (`POST /api/v1/imports/desktop`):** Valida estructura, checksum SHA-256, taxones y fotogramas sin escribir clasificaciones en la BD, guardando el `.zip` por 1 hora.
2. **Confirmación (`POST /api/v1/imports/{import_id}/confirm`)** o **Cancelación (`DELETE /api/v1/imports/{import_id}`)**.

> [!TIP]
> **Fixtures listos en el repositorio para esta prueba:**
> En la carpeta `tests/fixtures/package/` tienes paquetes reales `.wwm.zip` listos para seleccionar en Swagger:
> - `tests/fixtures/package/sample_valid.wwm.zip` (paquete válido completo)
> - `tests/fixtures/package/invalid_checksum.wwm.zip` (JSONL adulterado)
> - `tests/fixtures/package/invalid_zip_slip.wwm.zip` (intento de path traversal `../`)
> - `tests/fixtures/package/unsupported_version.wwm.zip` (`format_version: "2.0"`)

### 9.1 `POST /api/v1/imports/desktop` — Subir Paquete y Generar Vista Previa (`#32`)
- **Auth:** `Bearer <USER_A_ACCESS>` *(Obligatorio usuario con cuenta; sesiones anónimas dan `401 AUTH_REQUIRED`)*.
1. **Pruebas de Error de Seguridad e Integridad primero:**
   - **Sin cámara ni `create_camera=true` (`422 VALIDATION_ERROR`):** Sube `sample_valid.wwm.zip` dejando `camera_station_id` vacío y `create_camera=false`.
     - *Esperado (`422`):* `"Indica una cámara propia o create_camera=true (solo uno)."`.
   - **Paquete con Checksum adulterado (`422 IMPORT_CHECKSUM_MISMATCH`):** Sube `invalid_checksum.wwm.zip` con `camera_station_id=<CAM_PUB_ID>`.
     - *Esperado (`422`):* `error.code: "IMPORT_CHECKSUM_MISMATCH"`.
   - **Paquete con Zip Slip (`422 IMPORT_INVALID_PACKAGE`):** Sube `invalid_zip_slip.wwm.zip` con `camera_station_id=<CAM_PUB_ID>`.
     - *Esperado (`422`):* `error.code: "IMPORT_INVALID_PACKAGE"`.
   - **Versión no soportada (`422 IMPORT_UNSUPPORTED_VERSION`):** Sube `unsupported_version.wwm.zip` con `camera_station_id=<CAM_PUB_ID>`.
     - *Esperado (`422`):* `error.code: "IMPORT_UNSUPPORTED_VERSION"`.
2. **Camino Feliz (`201 Created` con `sample_valid.wwm.zip`):**
   - `package`: Selecciona `tests/fixtures/package/sample_valid.wwm.zip`
   - `camera_station_id`: `<CAM_PUB_ID>`
   - `create_camera`: `false`
   - **Resultado esperado (`201 Created`):**
     - `message`: `"Vista previa lista"`
     - `data`: `ImportPreview` con `import_id` (guárdalo como **`IMPORT_PREVIEW_ID`**), `status: "preview"`, `expires_at` (+1 hora), `counts: {"lines": ..., "new": ..., "duplicates": ..., "invalid": ..., "outside_deployment_range": ..., "by_category": {...}}` y `issues: [...]`.
- [ ] **Casos Error de integridad (`422 IMPORT_CHECKSUM_MISMATCH`, `IMPORT_INVALID_PACKAGE`, `IMPORT_UNSUPPORTED_VERSION`):** Ejecutados y verificados.
- [ ] **Camino Feliz (`201 Created` vista previa de `sample_valid.wwm.zip`):** Ejecutado y guardado `IMPORT_PREVIEW_ID`.

### 9.2 `DELETE /api/v1/imports/{import_id}` — Cancelar una Vista Previa (`#34`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Situación:** Probamos cancelar la vista previa `<IMPORT_PREVIEW_ID>` antes de confirmar, verificando que borra el temporal y luego creamos una nueva vista previa para confirmarla en el paso 9.3.
- **Path Param:** `import_id = <IMPORT_PREVIEW_ID>`.
- **Resultado esperado (`204 No Content`):** Vista previa cancelada y `.zip` temporal eliminado.
- **Prueba de Error (`404 IMPORT_NOT_FOUND`):**
  - Vuelve a ejecutar `DELETE /api/v1/imports/{IMPORT_PREVIEW_ID}` (que ya está en `status: "cancelled"`).
  - *Esperado:* HTTP `404`, `error.code: "IMPORT_NOT_FOUND"`.
- **Re-crear vista previa para el paso 9.3:**
  - Vuelve a ejecutar `POST /api/v1/imports/desktop` con `sample_valid.wwm.zip` y `camera_station_id=<CAM_PUB_ID>`, y actualiza **`IMPORT_PREVIEW_ID`** con el nuevo `import_id`.
- [ ] **Cancelación de vista previa (`204 No Content` y `404 IMPORT_NOT_FOUND` al repetir):** Ejecutado y verificado.
- [ ] **Nueva vista previa creada para confirmar:** Listo (`IMPORT_PREVIEW_ID` actualizado).

### 9.3 `POST /api/v1/imports/{import_id}/confirm` y `GET /api/v1/imports/{import_id}` — Confirmar en el worker y seguir el estado (`#33`, `CB-82`, D10)
> Desde el 21/11/2026 (D10) la confirmación **no importa dentro del request**: responde `202` y el worker `arq` hace el trabajo. El worker tiene que estar corriendo (`docker compose ps` muestra `fauna_worker`).
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `import_id = <IMPORT_PREVIEW_ID>`.
- **Body JSON (Camino Feliz):**
  ```json
  {
    "include_warnings": true,
    "camera": null
  }
  ```
- **Resultado esperado (`202 Accepted`):** `message: "Importación en curso"` y `data.status: "processing"`.
- **Seguimiento:** repite `GET /api/v1/imports/{IMPORT_PREVIEW_ID}` cada 1–2 s hasta que `status` deje de ser `processing`. *Esperado:*
  ```json
  {
    "import_id": "<IMPORT_PREVIEW_ID>",
    "status": "completed",
    "camera_station_id": "<CAM_PUB_ID>",
    "camera_code": "CAM-01",
    "result": { "batch_id": "<BATCH_DESKTOP_ID>", "imported": 3, "skipped_duplicates": 0, "skipped_invalid": 0 },
    "error": null
  }
  ```
  Si algo falla en el worker, `status` queda en `"failed"` y `error` trae `{code, message}` (por ejemplo `IMPORT_PREVIEW_EXPIRED` si el zip ya no está).
- **Pruebas de Error:**
  1. Vuelve a ejecutar `POST /api/v1/imports/{IMPORT_PREVIEW_ID}/confirm` sobre la misma importación (en curso o terminada).
     - *Esperado (`409 Conflict`):* `error.code: "IMPORT_ALREADY_IMPORTED"`, `message: "Esta importación ya se confirmó."`.
  2. Intenta volver a subir el mismo `sample_valid.wwm.zip` en la misma cámara `<CAM_PUB_ID>` en `POST /api/v1/imports/desktop`.
     - *Esperado (`409 Conflict` — `CB-82`):* `error.code: "IMPORT_ALREADY_IMPORTED"`, `message: "Este paquete ya se importó en esa cámara."`, con `details[0].context.import_id == "<IMPORT_PREVIEW_ID>"`.
  3. Con Redis apagado (`docker compose stop redis`), confirma otra vista previa.
     - *Esperado (`503`):* `error.code: "QUEUE_UNAVAILABLE"`; la vista previa sigue en `preview` y se puede confirmar después.
- [ ] **Camino Feliz (`202` → `completed`, fotogramas recodificados y lote `desktop_import` creado):** Ejecutado y verificado.
- [ ] **Caso Error (`409 IMPORT_ALREADY_IMPORTED` al re-confirmar o re-subir el mismo paquete `CB-82`):** Ejecutado y verificado.
- [ ] **Caso Error (`503 QUEUE_UNAVAILABLE` sin Redis):** Ejecutado y verificado.

### 9.4 `GET /api/v1/imports` — Historial de Importaciones de Escritorio (`#35`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Query Params:** `camera_station_id=<CAM_PUB_ID>`, `page=1`, `page_size=50`.
- **Resultado esperado (`200 OK`):**
  - Lista paginada con las importaciones de Usuario A (la `cancelled` del paso 9.2 y la `completed` del paso 9.3, con `imported`, `camera_code: "CAM-01"` y `package_created_at`).
- [ ] **Camino Feliz (`200 OK` historial de importaciones):** Ejecutado y verificado.

---

## Bloque 10: Borrado Lógico de Clasificación Individual y Cierre de Bitácora (`#26`)

### 10.1 `DELETE /api/v1/classifications/{classification_id}` — Borrado Lógico de Clasificación (`#26`)
- **Auth:** `Bearer <USER_A_ACCESS>`.
- **Path Param:** `classification_id = <CLS_ANIMAL_2_ID>`.
- **Resultado esperado (`204 No Content`):** Cuerpo vacío.
- **Verificación posterior (`404 CLASSIFICATION_NOT_FOUND`):**
  - Llama a `GET /api/v1/classifications/{CLS_ANIMAL_2_ID}` o intenta volver a hacer `DELETE /api/v1/classifications/{CLS_ANIMAL_2_ID}`.
  - *Esperado:* HTTP `404`, `error.code: "CLASSIFICATION_NOT_FOUND"`, `message: "No encontramos esa clasificación."`.
- [ ] **Camino Feliz (`204 No Content` borrado lógico de clasificación):** Ejecutado y verificado.
- [ ] **Caso Error (`404 CLASSIFICATION_NOT_FOUND` al consultar o volver a borrar):** Ejecutado y verificado.

---

## Bloque 11: Panel Admin (`HU-15a`, `HU-15b` — `FL-40..46`, `#36`–`#44`)

**Situación:** Con los datos de los bloques anteriores, el administrador revisa la plataforma. Regla de oro: el admin ve lo **anónimo** y lo **público**; lo **privado** solo aparece como **conteo**, y pedirlo por id responde **404** (`CB-96`). Toda acción que cambia algo exige `reason` y queda en la auditoría.

### 11.0 Crear la cuenta admin por CLI y entrar (`CB-99`)
```powershell
docker compose exec -e WWF_ADMIN_PASSWORD='Admin2026Fauna' api python -m app.cli create-admin --email admin@wwf.org
```
- **Esperado:** `{"result": "created", "user_id": "…"}`. La contraseña nunca se imprime. Repetirlo con un correo que ya existe → `"promoted"`, sin tocar su contraseña.
- Entra con `POST /api/v1/auth/login` (`admin@wwf.org` / `Admin2026Fauna`) y guarda `ADMIN_ACCESS`.
- [ ] **Admin creado y `ADMIN_ACCESS` guardado.**

### 11.1 `GET /api/v1/admin/stats` — Estadísticas de la plataforma (`#36`)
- **Con `USER_A_ACCESS`:** `403 ADMIN_REQUIRED`. **Sin token:** `401`.
- **Con `ADMIN_ACCESS` (`scope=all`):**
  - `content.camera_stations.private` ≥ 1: la cámara `CAM_PRIV_ID` cuenta, pero solo como número.
  - `fauna.by_species` **no** incluye especies que solo están en `CAM_PRIV_ID`.
  - `fauna_map[*].latitude`/`longitude` con 2 decimales (~1 km).
  - `model_feedback` refleja las validaciones del Bloque 7 (solo de lo público y anónimo).
- [ ] **403 sin rol admin.**
- [ ] **200 con privados solo como conteo y fauna sin privados.**

### 11.2 `GET /api/v1/admin/camera-stations` — Explorar cámaras (`#37`)
- **Esperado:**
  - `CAM_PUB_ID` con coordenadas redondeadas y `location_precision: "approx_1km"`;
  - la cámara anónima (`ANON_CAM_ID`, si no fue reclamada) con coordenadas **exactas** y `owner.display_name: "Anónimo #xxxx"`;
  - `CAM_PRIV_ID` **no aparece**.
- Prueba los filtros `scope=public`, `scope=anonymous`, `q=CAM` e `include_deleted=true`.
- [ ] **Lista sin privadas, públicas redondeadas y anónimas exactas.**

### 11.3 `GET /api/v1/admin/classifications` y `/admin/classifications/{id}/evidence` (`#38`)
- La lista solo trae clasificaciones de cámaras públicas o anónimas, con `owner_type`, `is_deleted` y `deleted_reason`. Filtros: `status=done|error|all`, `camera_station_id`.
- **Evidencia de `CLS_ANIMAL_1_ID`** (cámara pública) → `200 image/jpeg`.
- **Evidencia de una clasificación de `CAM_PRIV_ID`** → **`404 CLASSIFICATION_NOT_FOUND`**.
- [ ] **Evidencia pública 200 y privada 404.**

### 11.4 `GET /api/v1/admin/anon-sessions` — Sesiones anónimas (`#38`)
- **Esperado:** cada sesión con `label: "Anónimo #xxxx"` (nunca el token), `status`, `counts` y `retained`. La sesión del Bloque 2 aparece como `claimed`. Guarda un `ANON_SESSION_ID`.
- [ ] **Lista sin tokens.**

### 11.5 Borrado lógico y restauración (`#39`)
1. `POST /api/v1/admin/classifications/{CLS_ANIMAL_1_ID}/delete` con `{}` → **`422 DELETE_REASON_REQUIRED`**.
2. Mismo endpoint con `{"reason": "Prueba de bitácora"}` → `200` con `deleted: {"classifications": 1, …}`.
3. Repetir el paso 2 → **`409 ENTITY_ALREADY_DELETED`**.
4. `POST /api/v1/admin/camera-stations/{CAM_PUB_ID}/delete` con `{"reason": "Cascada"}` → `200` con la cámara y sus clasificaciones vivas.
5. `POST /api/v1/admin/camera-stations/{CAM_PUB_ID}/restore` con `{}` → `200`. **Restaura solo lo del paso 4:** `CLS_ANIMAL_1_ID`, borrada en el paso 2, sigue borrada.
6. `POST /api/v1/admin/classifications/{CLS_ANIMAL_1_ID}/restore` → `200`. Repetirlo → **`409 ENTITY_NOT_DELETED`**.
7. `POST /api/v1/admin/camera-stations/{CAM_PRIV_ID}/delete` con motivo → **`404`** (privada).
- [ ] **Motivo obligatorio, 409 por repetir, cascada y restauración parcial, privada 404.**

### 11.6 `POST /api/v1/admin/delete-batch` (`#39`)
- **Body:** `{"entity": "classifications", "ids": ["<CLS_ANIMAL_2_ID>", "<id de una clasificación privada>"], "reason": "Limpieza"}`.
- **Esperado:** `deleted` cuenta las borradas y `skipped` trae cada id saltado con su código: `CLASSIFICATION_NOT_FOUND` para la privada y `ENTITY_ALREADY_DELETED` si ya estaba borrada (por ejemplo, `CLS_ANIMAL_2_ID` tras el Bloque 10). Después restaura lo que quieras conservar.
- [ ] **Lote con `skipped` por ítem.**

### 11.7 Usuarios (`#40`)
1. `GET /api/v1/admin/users?q=investigador` → usuarios con `counts`. Guarda `USER_B_ID`.
2. `POST /api/v1/admin/users/{tu propio id}/deactivate` con motivo → **`409 CANNOT_DEACTIVATE_SELF`**.
3. `POST /api/v1/admin/users/{USER_B_ID}/deactivate` con `{"reason": "Prueba"}` → `200` con `is_active: false`.
4. Con `USER_B_ACCESS`, `GET /api/v1/auth/me` → **`403 ACCOUNT_DISABLED`**. Su refresh token quedó revocado.
5. `POST /api/v1/admin/users/{USER_B_ID}/reactivate` → `is_active: true`. Usuario B vuelve a entrar con login.
- [ ] **Autodesactivación bloqueada, desactivar corta el acceso, reactivar lo devuelve.**

### 11.8 `POST /api/v1/admin/users/{USER_B_ID}/password-reset-link` (`#40`, `CB-76`)
- **Body:** `{"reason": "Sin acceso al correo"}`.
- **Esperado:** `reset_url` (`…/restablecer?token=…`) y `expires_at`. El enlace se muestra **una sola vez**, y en la auditoría solo queda el vencimiento.
- Prueba el token con `GET /api/v1/auth/password/reset/validate` → `valid: true`. Funciona aunque la recuperación por correo esté apagada.
- [ ] **Enlace generado y válido; el token no aparece en `audit-log` ni en los logs.**

### 11.9 `GET` y `PUT /api/v1/admin/settings` (`#41`, `CB-43`)
- `GET` → `anon_data_retention.value: true`.
- `PUT` con `{"anon_data_retention": "no", "reason": "x x x"}` → **`422 SETTING_INVALID`**.
- `PUT` con `{"anon_data_retention": false}` → **`422 DELETE_REASON_REQUIRED`**.
- `PUT` con `{"anon_data_retention": false, "reason": "Prueba de bitácora"}` → `value: false` y `updated_by: "admin@wwf.org"`. Solo afecta lo que se cree desde ahora: una sesión anónima nueva nace con `anon_retain: false`, y las anteriores no cambian.
- Vuelve a dejarlo en `true` con otro `PUT`.
- [ ] **Validación, motivo obligatorio y cambio auditado.**

### 11.10 `GET /api/v1/admin/audit-log` (`#42`)
- Prueba los filtros `action=soft_delete`, `action=update_setting`, `entity_type=users`, `from` y `to`.
- **Esperado:** cada acción de 11.5 a 11.9 con `reason`, `old_value`/`new_value` y `request_id`.
- [ ] **Auditoría completa.**

### 11.11 `GET /api/v1/admin/queue` (`#43`, `FL-45`)
- **Con el worker arriba:** `workers.alive: true`, `concurrency`, `busy`, `queued`, `processing`, `avg_processing_seconds` (tiempo real de la IA), `last_hour` y `email` con los topes.
- **Detén el worker** (`docker compose stop worker`), espera unos 40 s y repite → `workers.alive: false`. Vuelve a levantarlo.
- Para ver `by_owner`, sube un lote de varios archivos (Bloque 6) y consulta mientras se procesa.
- [ ] **Cola y latido del worker.**

### 11.12 `GET /api/v1/admin/unlisted-suggestions` (`#44`, `CB-65`)
- Necesita una clasificación con `correct_unlisted` en una cámara pública (Bloque 7.2, acción 3). Si la acción se reemplazó después, repítela sobre otra clasificación de `CAM_PUB_ID`.
- **Esperado:** el nombre agrupado sin tildes ni mayúsculas (`"leopardus jacobita"`), `count`, `parent_taxon` y `classification_ids`.
- [ ] **Sugerencia agrupada.**

### 11.13 `GET /api/v1/admin/reports/excel` (`#42`)
- **Esperado:** descarga `WWM_admin_all_AAAAMMDD.xlsx` con 6 hojas: *Plataforma*, *Fauna por especie*, *Por género*, *Por familia*, *Clasificaciones* y *Sugerencias*.
- En *Clasificaciones* no hay ninguna fila de `CAM_PRIV_ID`, y las anónimas salen como `Anónimo #xxxx`.
- En `audit-log` aparece `action: "export"`.
- [ ] **Excel sin privados y auditado.**

---

## Bloque 12: Operación en desarrollo (`HU-04`, `HU-16`, `T1`, `T2`)

### 12.1 Correo real con Resend
- **En tu `.env`** (nunca en Git):
  - `PASSWORD_RECOVERY_ENABLED=true`;
  - `EMAIL_PROVIDER="resend"`;
  - `RESEND_API_KEY="re_…"`;
  - `EMAIL_FROM="onboarding@resend.dev"`;
  - `FRONTEND_BASE_URL="http://localhost:5173"`.

  Reinicia la API y el worker: `docker compose up -d --force-recreate api worker`.
- **Prueba de conexión:** `docker compose exec api python -m app.cli send-test-email --to <correo-de-tu-cuenta-resend>` → `{"result": "sent", "provider": "resend", "provider_id": "…"}` y el correo llega.
- **Flujo completo:** registra un usuario con ese mismo correo y sigue el 3.8 con Resend encendido.
- **En el log del worker** (`docker compose logs worker`) aparece `send_reset_email('<id>')`, solo con un id, sin el correo ni la IP.
- [ ] **Correo de prueba recibido.**
- [ ] **Recuperación por correo de punta a punta.**

### 12.2 Límites de intentos compartidos (Redis)
- Haz 11 logins seguidos con contraseña incorrecta usando correos distintos: los 10 primeros → `401`, el 11.º → **`429 RATE_LIMITED`**. El límite es por IP y vale para todos los procesos de la API.
- Haz 6 logins seguidos al mismo correo → el 6.º → `429` (5 por minuto por correo).
- [ ] **Límites por IP y por correo.**

### 12.3 Semilla E2E
```powershell
docker compose exec -e WWF_E2E_PASSWORD='E2e-Password1' api python -m app.cli seed-e2e
```
- **Esperado:** `{"status": "seeded", "users": 3, "camera_stations": 2, "classifications": 30}`. Repetirlo → `"already_seeded"`. Carga datos en la base de desarrollo: `admin@e2e.example.com`, `ana@e2e.example.com` y `beto@e2e.example.com`.
- [ ] **Semilla cargada e idempotente.**

### 12.4 Respaldo y restauración (`FL-32`)
- **Requisitos:**
  - bash (Git Bash o WSL) y python;
  - `pg_dump`, `pg_restore` y `psql` de la **misma versión mayor que el servidor**. Si no están en el `PATH`, define `PG_BIN` (por ejemplo, `PG_BIN="/c/Program Files/PostgreSQL/16/bin"`). Los scripts verifican la versión y se detienen si no coincide.
  - una base vacía para restaurar: `createdb -h localhost -p 5433 -U postgres wwf_restore_test`.
```bash
DATABASE_URL="postgresql+asyncpg://postgres:<pass>@localhost:5433/faunadb" STORAGE_LOCAL_PATH="./uploads/evidence" scripts/backup.sh backups/
RESTORE_DATABASE_URL="postgresql://postgres:<pass>@localhost:5433/wwf_restore_test" scripts/restore_test.sh backups/wwm-AAAAMMDDTHHMMSSZ
```
- **Esperado:** `Respaldo listo: …`, y después `Restauración OK …: alembic 0003, N fotogramas, filas iguales.`
- Con `RESTORE_DATABASE_URL` apuntando a `faunadb` → se niega.
- [ ] **Respaldo y restauración probados.**

---

## Resumen de Certificación para Merge (`develop` → `main`)

| Bloque | Dominio / Flujos (`FL-xx`) | Endpoints Cubiertos | Estado Físico |
| :--- | :--- | :---: | :---: |
| **Bloque 1** | Salud, Config Pública y Catálogo SpeciesNet (`FL-10`) | `/`, `#11`, `#12`, `#30` (6 endpoints) | `[ ]` |
| **Bloque 2** | Sesiones Anónimas y Límites sin Cuenta (`FL-03`) | `#7`, `#8`, `#10` (3 endpoints) | `[ ]` |
| **Bloque 3** | Auth JWT, Reuso Refresh, Perfil, Reset y Claim (`FL-01..04`, `FL-14`) | `#1`–`#6b`, `#9` (11 endpoints) | `[ ]` |
| **Bloque 4** | Cámaras Trampa, Privacidad DD-17, `nearby` y `redeploy` (`FL-05..06`, `FL-13`, `FL-15`) | `#13`, `#14`, `#15b`, `#15c`, `#15d` (8 endpoints) | `[ ]` |
| **Bloque 5** | Proyectos y Asociación N:M Segura (`FL-07`) | `#16`–`#19` (7 endpoints) | `[ ]` |
| **Bloque 6** | Lotes, Subida a Cola `arq`/Redis, Worker IA Real y Evidencias (`FL-08..09`) | `#21`–`#24b`, `#27` (9 endpoints) | `[ ]` |
| **Bloque 7** | Clasificaciones, Validación Humana (6 acciones) y Ráfagas (`FL-10`, `FL-16`) | `#25`, `#26`, `#28`, `#29`, `#29b` (9 endpoints) | `[ ]` |
| **Bloque 8** | Estadísticas Ecológicas y Reportes Excel (5 hojas) / PDF (`FL-11`, `FL-12`) | `#15`, `#20`, `#31` (4 endpoints) | `[ ]` |
| **Bloque 9** | Importación de Paquetes de Escritorio `.wwm.zip` (`FL-23`) | `#32`–`#35` + `GET /imports/{id}` (5 endpoints) | `[ ]` |
| **Bloque 10** | Borrado Lógico de Clasificaciones (`FL-10`) | `#26 DELETE` (1 endpoint) | `[ ]` |
| **Bloque 11** | Panel Admin: stats, explorar, borrado/restauración, usuarios, settings, auditoría, cola, sugerencias y Excel (`FL-40..46`) | `#36`–`#44` (18 endpoints) | `[ ]` |
| **Bloque 12** | Operación en desarrollo: Resend, límites en Redis, `seed-e2e`, respaldo/restauración | CLI + scripts | `[ ]` |
| **TOTAL** | **100 % del backlog en `develop` (M0–M4)** | **80 rutas (método + ruta) + CLI** | `[ ]` |
