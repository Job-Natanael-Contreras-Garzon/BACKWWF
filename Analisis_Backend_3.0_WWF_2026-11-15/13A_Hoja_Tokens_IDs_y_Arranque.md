---
title: "13A - Panel Fijo: Arranque desde 0, Hoja de Tokens/IDs y Registro de Hallazgos"
date: 2026-11-21
project: BACKWWF
version: "2.0.0"
status: active
tags: [testing, swagger, tokens, setup, bitacora, wwf]
---

# 13A. Panel Fijo: Arranque desde 0, Hoja de Tokens/IDs y Hallazgos (`BACKWWF`)

> [!TIP]
> **Cómo usar este archivo (Vista Dividida en Obsidian / VS Code):**
> Mantén **`13A`** fijo en una pestaña lateral mientras avanzas por **`[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]`** y **`[[13C_Protocolo_IA_Real_Operacion_y_Certificacion]]`**. Así puedes copiar y pegar tus `access_token`, `anon_token`, UUIDs y `request_id` sin hacer *scroll*.

---

## 1. Secuencia para Destruir y Levantar Contenedores desde Cero (PowerShell)

### Paso 1.1: Destruir contenedores actuales y limpiar cola Redis
```powershell
# 1. Bajar Backend, Worker y volumen de Redis
cd "c:\Users\contr\Documents\Repositorios de Git\INNOVAHACK\BACKWWF"
docker compose down -v --remove-orphans

# 2. Bajar contenedor IA real (sin -v para conservar los ~505 MB de modelos en el volumen 'models')
cd "c:\Users\contr\Documents\Repositorios de Git\INNOVAHACK\ia-clasificacion-fauna"
docker compose down --remove-orphans

# 3. Eliminar cualquier contenedor suelto de ia-fake o IA vieja (:8081)
docker rm -f ia-fake wwf-wildlife-api 2>$null
docker ps
```

### Paso 1.2: Levantar `ia-clasificacion-fauna` real en `:8001` y esperar carga de modelos
```powershell
cd "c:\Users\contr\Documents\Repositorios de Git\INNOVAHACK\ia-clasificacion-fauna"
# (Solo si el volumen 'models' está vacío): docker compose run --rm ia python tools/fetch_models.py
docker compose up -d --build --force-recreate

# Comprobar que ya cargó MegaDetector + SpeciesNet (debe responder {"status":"ok", ...})
curl.exe http://localhost:8001/api/v1/health
```

### Paso 1.3: Levantar `BACKWWF` (`fauna_api`, `fauna_worker`, `fauna_redis`)
> Verifica antes en tu `.env` de `BACKWWF` que `AI_SERVICE_URL="http://host.docker.internal:8001"` y `AI_API_KEY` coincida con la de la IA (`dev-key` en desarrollo).

```powershell
cd "c:\Users\contr\Documents\Repositorios de Git\INNOVAHACK\BACKWWF"

# (Opcional) Limpiar temporales y fotogramas locales de pruebas anteriores
Remove-Item -Recurse -Force .\uploads\tmp\*, .\uploads\evidence\* -ErrorAction SilentlyContinue

docker compose up -d --build --force-recreate
docker ps
```

### Paso 1.4: Respaldar `faunadb`, aplicar migraciones hasta `0003` y crear Admin
```powershell
cd "c:\Users\contr\Documents\Repositorios de Git\INNOVAHACK\BACKWWF"

# (Opcional si quieres empezar con las 15 tablas en blanco; si antes quieres backup corre scripts/backup.sh en Git Bash):
docker compose exec -T api alembic downgrade base

# Subir esquema a 0003 y verificar
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
# Esperado: 0003 (head)

# Crear cuenta de Administrador para el Bloque 11
docker compose exec -e WWF_ADMIN_PASSWORD=Admin2026Fauna -T api python -m app.cli create-admin --email admin@wwf.org --full-name "Administrador WWF"

# Verificar Readiness general (database: ok, ai: ok, storage: ok)
curl.exe http://localhost:8000/api/v1/health/ready
```

- [x] **IA Real en `:8001` respondiendo `status: "ok"` (`MDv5a` + `speciesnet-4.0.2a` cargados en 17.4 s)**
- [x] **Migración Alembic en `0003 (head)`**
- [x] **Contenedores `fauna_api`, `fauna_worker` y `fauna_redis` arriba (`Up`)**
- [x] **Admin `admin@wwf.org` creado (`c4f9d76e-7ac1-41b7-9095-815713930c8d`, pass: `AdminFauna2026Password`)**

---

## 2. Batería de Archivos para Tener a Mano

- [ ] **Fotos reales para IA (Bloque 6):**
  - `animal_1.jpg` y `animal_2.jpg` (2 fotos distintas con un animal claro → `category: "animal"`).
  - `vacia_blank.jpg` (vegetación sin animales → `category: "blank"`, `evidence: null`).
  - `persona.jpg` y `vehiculo.jpg` (`category: "person" | "vehicle"`, `taxonomy: null`, con `evidence`).
  - `foto.heic` y `falso.jpg` (texto renombrado a `.jpg` → rechazo limpio `200 OK` con `status: "error"`).
- [ ] **Videos reales para IA (Bloque 6):**
  - `video_15s.mp4` (≤ 15 s, para medir inferencia y latido del worker).
  - `video_largo.mp4` (> 16 s, para verificar truncado a `15.0 s` y warning `VIDEO_TRUNCATED`).
  - Un `.avi`, un `.mkv` y un `.flv` válidos (aceptados por `formats.py`).
- [ ] **Paquetes de escritorio en `tests/fixtures/package/` (Bloque 9):**
  - Válidos: `sample_valid.wwm.zip`, `sample_valid_no_camera.wwm.zip`.
  - Inválidos: `invalid_checksum.wwm.zip`, `invalid_zip_slip.wwm.zip`, `invalid_version_2.wwm.zip`, `invalid_corrupt_jpg.wwm.zip`, `invalid_no_manifest.wwm.zip`, `invalid_unknown_taxon.wwm.zip`.

---

## 3. Hoja de Tokens y UUIDs (Copiar y Pegar durante la Prueba)

> [!WARNING]
> **Regla de Oro en Swagger (`http://localhost:8000/docs`):**
> En `get_owner` (`app/api/deps.py`), el header **`Authorization: Bearer` siempre tiene prioridad sobre `X-Anon-Token`**. Cuando pruebes sesiones anónimas puras (Bloque 2), haz clic en **`Authorize` → `Logout`**.

| Variable | Dónde se obtiene | Valor actual (Pegar aquí) |
| :--- | :--- | :--- |
| `LABEL_ID_CATALOGO` | **Bloque 1.5** (`GET /catalog/species?q=Jaguar`) | `` |
| `ANON_TOKEN_1` | **Bloque 2.3** (`POST /anon-sessions` — se reclama en 3.9) | `` |
| `ANON_CAM_ID` | **Bloque 2.3** (`POST /camera-stations` anónima `CAM-01` → `CAM-01-2`) | `` |
| `ANON_TOKEN_2` | **Bloque 2.4** (`POST /anon-sessions` — NO reclamar; para Admin) | `` |
| `ANON_CAM_2_ID` | **Bloque 2.4** (`POST /camera-stations` anónima `CAM-ANON-02`) | `` |
| `ANON_SESSION_2_ID` | **Bloque 11.4** (`GET /admin/anon-sessions` — UUID de sesión #2) | `` |
| `USER_A_ID` | **Bloque 3.1** (`POST /auth/register` — `investigador.a@wwf.org`) | `` |
| `USER_A_ACCESS` | **Bloque 3.1 / 3.4** (`access_token` Investigador A — TTL 30m) | `` |
| `USER_A_REFRESH` | **Bloque 3.1 / 3.4** (`refresh_token` Investigador A) | `` |
| `USER_B_ID` | **Bloque 3.2** (`POST /auth/register` — `investigador.b@wwf.org`) | `` |
| `USER_B_ACCESS` | **Bloque 3.2** (`access_token` Investigador B — Tercero / IDOR) | `` |
| `ADMIN_ID` | **Bloque 11.0** (`POST /auth/login` — `admin@wwf.org`) | `c4f9d76e-7ac1-41b7-9095-815713930c8d` |
| `ADMIN_ACCESS` | **Bloque 11.0** (`access_token` Admin — **¡TTL 15 min!**) | `` |
| `RESET_TOKEN_MANUAL` | **Bloque 11.8** (`token` de `reset_url` generado por el Admin) | `` |
| `CAM_PUB_ID` | **Bloque 3.9** (`POST /camera-stations` pública `CAM-01` de Usuario A) | `` |
| `CAM_PRIV_ID` | **Bloque 4.1** (`POST /camera-stations` privada `CAM-PRIV-01` de Usuario A) | `` |
| `CAM_REDEPLOY_ID` | **Bloque 4.5** (`POST /camera-stations/{id}/redeploy` `CAM-01-3`) | `` |
| `PROJ_PUB_ID` | **Bloque 5.1** (`POST /projects` público de Usuario A) | `` |
| `BATCH_1_ID` | **Bloque 6.1** (`POST /classification-batches` en `CAM_PUB_ID`) | `` |
| `CLS_ANIMAL_1_ID` | **Bloque 6.2** (`classification_id` de `animal_1.jpg` en `CAM_PUB_ID`) | `` |
| `CLS_ANIMAL_2_ID` | **Bloque 6.2** (`classification_id` de `animal_2.jpg` en `CAM_PUB_ID`) | `` |
| `CLS_PRIV_ID` | **Bloque 10.1** (Clasificación dentro de `CAM_PRIV_ID` para prueba `CB-96`) | `` |
| `BURST_GROUP_KEY` | **Bloque 7.5** (`group_key` de `GET /classifications/burst-candidates`) | `` |
| `IMPORT_PREVIEW_ID` | **Bloque 9.1 / 9.2** (`import_id` de `POST /imports/desktop`) | `` |

---

## 4. Registro de Hallazgos, Tiempos y Errores por `request_id`

- **Petición HTTP en Swagger:** copia `meta.request_id` del JSON (o el header `X-Request-ID`).
- **Job del worker hacia la IA:** usa `w-<primeros 10 hex de classification_id>` (ej. `w-a1b2c3d4e5`).
- **Comando para buscar un `request_id` en los logs:**
  ```powershell
  docker compose logs api worker | Select-String "<REQUEST_ID>"
  ```

| # | Bloque / Paso | Endpoint o Archivo Probado | HTTP / `error.code` | `request_id` (`meta.request_id` o `w-<hex10>`) | Observación / Tiempo medido | Estado |
| :-: | :--- | :--- | :--- | :--- | :--- | :---: |
| 1 | | | | | | `[ ]` |
| 2 | | | | | | `[ ]` |
| 3 | | | | | | `[ ]` |
| 4 | | | | | | `[ ]` |
| 5 | | | | | | `[ ]` |
| 6 | | | | | | `[ ]` |
| 7 | | | | | | `[ ]` |
| 8 | | | | | | `[ ]` |
