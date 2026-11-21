---
title: "13C - Protocolo de IA Fauna Real (:8001), Operación (Bloque 12) y Certificación Final"
date: 2026-11-21
project: BACKWWF
version: "2.0.0"
status: active
tags: [testing, ia-real, operacion, redis, resend, backup, certificacion, wwf]
---

# 13C. Protocolo de IA Fauna Real (`:8001`), Operación (Bloque 12) y Certificación Final

> [!NOTE]
> **Paneles compañeros:**
> - Tabla de tokens, IDs y registro de hallazgos con `request_id`: **`[[13A_Hoja_Tokens_IDs_y_Arranque]]`**.
> - Secuencia paso a paso de los 80 endpoints en Swagger (Bloques 1 al 11): **`[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]`**.

---

## 1. Lo que SOLO se puede certificar con la IA Fauna Real (`:8001`)

Los tests automatizados del repositorio usan `ia-fake`; durante el **Bloque 6** de `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]`, comprueba y registra aquí estos 7 puntos físicos contra el contenedor real `ia-clasificacion-fauna` (`wwm-ia:latest` en `:8001`):

### 1.1 Tiempos Reales de Inferencia y Latido del Worker (`AI_TIMEOUT_SECONDS = 180`)
- **Qué medir:**
  - Tiempo total de 1 foto (`animal_1.jpg`): **`________ s`**
  - Tiempo total de 1 video de 15 s (`video_15s.mp4`): **`________ s`**
- **Qué comprobar:**
  - Mientras el video se procesa en la IA, el worker envía un latido a PostgreSQL cada **30 s** (`WORKER_HEARTBEAT_SECONDS = 30`, actualizando `classifications.heartbeat_at`) para que el *Reaper* (`FL-33`, umbral 10 min) nunca lo devuelva a la cola por error (`CB-38`).
  - Si un video supera `180 s` (`AI_TIMEOUT_SECONDS = 180.0`, mayor que el corte de `150 s` de la IA), el ítem pasa a `status: "error"` con `error.code: "AI_TIMEOUT"` y **conserva su archivo temporal** en `TMP_UPLOAD_PATH` para poder reintentarlo con `POST /api/v1/classification-batches/{batch_id}/items/{client_index}/retry`.
- [ ] **Tiempos reales medidos y latido del worker verificado.**

### 1.2 Arranque en Frío (`AI_NOT_READY` + Reintentos a los 5 s y 30 s — `CB-37`)
- **Acción física:**
  1. Reinicia el contenedor de la IA real:
     ```powershell
     docker restart <nombre_contenedor_ia>
     ```
  2. Inmediatamente (mientras `GET http://localhost:8001/api/v1/health` responde `503` con `"status": "loading"`), sube una foto nueva a un lote abierto en Swagger.
- **Resultado esperado:**
  - La IA responde `503 IA_MODEL_NOT_READY` → `ai_client` lo traduce a `AI_NOT_READY`.
  - En `docker compose logs worker` aparece `classification.ai_call.retry` (`error_code: "AI_NOT_READY"`).
  - El worker espera **5 s** (primer reintento) y, si sigue cargando, **30 s** (segundo reintento) (`WORKER_RETRY_DELAYS = "5,30"`).
  - Cuando la IA termina de cargar el modelo, el archivo se clasifica y pasa a **`status: "done"`** sin fallar.
- [ ] **Arranque en frío (`AI_NOT_READY` → reintentos 5 s / 30 s → `done`) verificado.**

### 1.3 Resultados Reales por Categoría y Paridad con los 3538 Taxones
- **Qué comprobar en el JSON de `GET /api/v1/classification-batches/{BATCH_1_ID}`:**
  - **Foto vacía (`vacia_blank.jpg`):** `category: "blank"`, `taxonomy: null`, `evidence: null`.
  - **Persona / Vehículo (`persona.jpg`, `vehiculo.jpg`):** `category: "person"` o `"vehicle"`, **`taxonomy: null`**, pero **`evidence` sí viene poblado** (con `url`, `bbox`, `width`, `height`).
  - **Fauna (`animal_1.jpg`, `animal_2.jpg`):** `category: "animal"`, y tanto `taxonomy.label_id` como todos los `alternatives[i].label_id` existen en el catálogo de **3538 taxones** (`GET /api/v1/catalog/species/{label_id}` responde `200 OK`), lo que permite que en el **Bloque 7.2** la acción `correct` con `correction_source: "alternative"` funcione sin dar `CATALOG_TAXON_NOT_FOUND`.
- [ ] **Resultados reales (`blank`, `person`/`vehicle` sin taxonomía, `animal` con taxones válidos en el catálogo de 3538) verificados.**

### 1.4 Truncado de Videos Largos (`> 15 s` — `F1-D10`)
- **Qué comprobar con `video_largo.mp4` (> 16 s):**
  - El archivo NO es rechazado: termina en `status: "done"`.
  - En `warnings` de la clasificación viene:
    ```json
    [
      {
        "code": "VIDEO_TRUNCATED",
        "message": "Se analizaron los primeros 15 s del video.",
        "context": { "truncated_at_seconds": 15.0 }
      }
    ]
    ```
  - El fotograma elegido por la IA (`evidence.timestamp_seconds`) cae entre **`0.0` y `15.0`** segundos (`evidence.timestamp_label` entre `"00:00"` y `"00:15"`).
- [ ] **Video largo truncado a `15.0 s` con warning `VIDEO_TRUNCATED` y fotograma dentro del rango `[0, 15]` verificado.**

### 1.5 Formatos Reales (`formats.py`)
- **`.heic` (`foto.heic`):** Se rechaza limpio al subir (`200 OK` en `/files` con `BatchItem.status: "error"`, `error.code: "MEDIA_UNSUPPORTED_FORMAT"`, mensaje indicando convertir a JPEG hasta `IA-16`).
- **`.avi`, `.mkv` y `.flv`:** Pasan la validación de extensión y firma binaria (`202 Accepted`) y son procesados por la IA real.
- [ ] **Rechazo limpio de `.heic` y aceptación/procesamiento de `.avi`, `.mkv`, `.flv` verificados.**

### 1.6 Trazabilidad Extremo a Extremo por `request_id`
- Toma el UUID de `CLS_ANIMAL_1_ID` (ej. `a1b2c3d4-e5f6-...`). El worker forma el `request_id` como **`w-<primeros 10 hex>`** (ej. `w-a1b2c3d4e5`) y lo envía a la IA en el header `X-Request-ID`.
- Ejecuta en PowerShell:
  ```powershell
  docker compose logs worker | Select-String "w-"
  docker logs <nombre_contenedor_ia> | Select-String "w-"
  ```
- **Esperado:** El mismo `w-<hex10>` aparece tanto en los logs JSON del `fauna_worker` como en los logs de `ia-clasificacion-fauna`.
- [ ] **Mismo `request_id` (`w-<hex10>`) confirmado en logs del backend/worker y de la IA.**

### 1.7 Prueba de Carga (~50 archivos con 2 dueños distintos) y Cola Justa (`CB-30`)
- **Escenario:**
  1. Con **Usuario A**, abre un lote para 25 archivos y empieza a subirlos.
  2. Al mismo tiempo, con **Usuario B** (en una cámara creada por Usuario B), abre un lote para 25 archivos y súbelos.
  3. Con **`ADMIN_ACCESS`**, consulta repetidamente `GET /api/v1/admin/queue` (`#43`) mientras corre `docker stats` en una terminal:
     ```powershell
     docker stats
     ```
- **Qué comprobar y registrar:**
  - En `GET /api/v1/admin/queue`: `by_owner` muestra los archivos en espera de ambos investigadores y la cola justa (`QUEUE_PER_OWNER_INFLIGHT = 2`, `WORKER_CONCURRENCY = 2`) alterna entre Usuario A y Usuario B sin que el primero bloquee al segundo.
  - **Métricas observadas bajo carga:**
    - `avg_processing_seconds` reportado en `/admin/queue`: **`________ s`**
    - Pico de CPU del contenedor de IA (`docker stats`): **`________ %`**
    - Pico de RAM del contenedor de IA (`docker stats`, límite `6g`): **`________ GB`**
    - ¿Conviene mantener `WORKER_CONCURRENCY=2` / `QUEUE_WORKERS=1` o ajustarlos?: **`____________________`**
- [ ] **Prueba de carga de ~50 archivos con 2 dueños, cola justa en `/admin/queue` y monitoreo de CPU/RAM completados.**

---

## 2. Bloque 12: Operación en Desarrollo, Límites Redis, Resend y Backups (`HU-04`, `HU-16`, `T1`, `T2`, `FL-30..33`)

### 12.1 Correo Real con Resend y Encolado en el Worker (`HU-04`, `T2`)
- **Configuración en `.env` local** (nunca en Git):
  - `PASSWORD_RECOVERY_ENABLED=true`
  - `EMAIL_PROVIDER="resend"`
  - `RESEND_API_KEY="re_..."`
  - `EMAIL_FROM="onboarding@resend.dev"` *(con este remitente de prueba, Resend entrega al correo dueño de la cuenta Resend)*
  - `FRONTEND_BASE_URL="http://localhost:5173"`
  - Reiniciar API y worker: `docker compose up -d --force-recreate api worker`
- **Prueba 1 — Conexión directa por CLI:**
  ```powershell
  docker compose exec -T api python -m app.cli send-test-email --to <correo-de-tu-cuenta-resend>
  ```
  - *Esperado:* `{"result": "sent", "provider": "resend", "provider_id": "..."}` y recepción del correo en bandeja.
- **Prueba 2 — Flujo completo `FL-14` por el worker (`T2`):**
  - Registra un usuario con ese correo, llama a `POST /api/v1/auth/password/forgot` (`200 OK`), verifica en `docker compose logs worker` que corrió el job `send_reset_email` (sin imprimir el correo ni la IP en texto plano) y usa el enlace recibido en `/reset/validate` y `/reset`.
  - *(Al terminar, si no dejarás Resend activo, vuelve a poner `PASSWORD_RECOVERY_ENABLED=false`).*
- [ ] **Correo de prueba `send-test-email` recibido.**
- [ ] **Recuperación `FL-14` procesada por el worker (`send_reset_email`) de punta a punta.**

### 12.2 Límites de Intentos Compartidos en Redis (`T1`)
- En `POST /api/v1/auth/login`:
  1. Haz **6 logins seguidos** con contraseña errónea al **mismo correo** (`investigador.a@wwf.org`): los 5 primeros responden `401 AUTH_INVALID_CREDENTIALS` y el **6.º responde `429 RATE_LIMITED`** (límite de 5/min por correo en Redis).
  2. Haz **11 logins seguidos** con contraseña errónea usando **correos distintos** (`test1@wwf.org` .. `test11@wwf.org`): los 10 primeros responden `401` y el **11.º responde `429 RATE_LIMITED`** (límite de 10/min por IP en Redis).
- [ ] **Rate limits en Redis por correo (5/min → `429`) y por IP (10/min → `429`) verificados.**

### 12.3 Crons CLI (`sync-catalog`, `reaper`, `cleanup`, `purge-anon`) y `reset-admin-password`
```powershell
# 1. Sincronizar catálogo con la IA real en :8001 (ETag / 304 Not Modified)
docker compose exec -T api python -m app.cli sync-catalog

# 2. Ejecutar crons de mantenimiento de forma manual e idempotente
docker compose exec -T api python -m app.cli reaper
docker compose exec -T api python -m app.cli cleanup
docker compose exec -T api python -m app.cli purge-anon

# 3. Recuperar contraseña del Admin por CLI (revoca sus sesiones activas, CB-99)
docker compose exec -e WWF_ADMIN_PASSWORD=Admin2026Fauna -T api python -m app.cli reset-admin-password --email admin@wwf.org
```
- [ ] **`sync-catalog`, `reaper`, `cleanup`, `purge-anon` y `reset-admin-password` ejecutados con salida JSON limpia.**

### 12.4 Semilla E2E para Frontend / Playwright (`seed-e2e` — `HU-16`)
```powershell
docker compose exec -e WWF_E2E_PASSWORD=E2e-Password1 -T api python -m app.cli seed-e2e
```
- **Esperado:** `{"status": "seeded", "users": 3, "camera_stations": 2, "classifications": 30}` (y si lo repites responde `"already_seeded"`). Crea `admin@e2e.example.com`, `ana@e2e.example.com` y `beto@e2e.example.com` listos para que Miguel corra Playwright.
- [ ] **Semilla `seed-e2e` cargada e idempotente.**

### 12.5 Respaldo y Prueba de Restauración (`FL-32` — `scripts/backup.sh` y `scripts/restore_test.sh`)
- **Requisitos en Git Bash / WSL:** `pg_dump`, `pg_restore` y `psql` de la misma versión mayor que PostgreSQL (`16`; si no están en el `PATH`, exportar `PG_BIN="/c/Program Files/PostgreSQL/16/bin"`), y crear una BD vacía descartable `wwf_restore_test`:
  ```bash
  createdb -h localhost -p 5433 -U postgres wwf_restore_test
  DATABASE_URL="postgresql+asyncpg://postgres:<pass>@localhost:5433/faunadb" STORAGE_LOCAL_PATH="./uploads/evidence" scripts/backup.sh backups/
  RESTORE_DATABASE_URL="postgresql://postgres:<pass>@localhost:5433/wwf_restore_test" scripts/restore_test.sh backups/wwm-<AAAAMMDDTHHMMSSZ>
  ```
- **Esperado:** `Respaldo listo: ...` y luego `Restauración OK en localhost:5433/wwf_restore_test: alembic 0003, <N> fotogramas, filas iguales.` (Si apuntas `RESTORE_DATABASE_URL` a `faunadb`, se niega con código `2`).
- [ ] **Respaldo `backup.sh` y restauración verificada `restore_test.sh` (`alembic 0003`) completados.**

---

## 3. Scorecard de Certificación Final (`main` 100% Verificado para Frontend)

| Bloque | Dominio / Flujos (`FL-xx`) | Rutas / Comandos Cubiertos | Archivo Guía | Estado Físico |
| :--- | :--- | :---: | :---: | :---: |
| **Bloque 0** | Preparación desde cero: IA Real `:8001`, Alembic `0003` y Admin CLI | 4 pasos de arranque | `[[13A_Hoja_Tokens_IDs_y_Arranque]]` | `[ ]` |
| **Bloque 1** | Salud (`/health/ready`), Config Pública y Catálogo SpeciesNet (`FL-10`) | `/`, `#11`, `#12`, `#30` (6 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 2** | Sesiones Anónimas y Límites sin Cuenta (`FL-03`) | `#7`, `#8`, `#10` (3 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 3** | Auth JWT, Reuso Refresh `CB-78`, Perfil, Reset y Claim `-2` (`FL-01..04`, `FL-14`) | `#1`–`#6b`, `#9` (11 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 4** | Cámaras, Privacidad DD-17, `nearby`, `redeploy` y `time-offset` (`FL-05..06`, `FL-13`, `FL-15`) | `#13`, `#14`, `#15b`, `#15c`, `#15d` (8 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 5** | Proyectos y Asociación N:M Segura (`FL-07`, `CB-20`, `CB-23`) | `#16`–`#19` (7 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 6** | **Lotes, Cola `arq`/Redis, IA Fauna Real (`:8001`), Formatos, Carga y `/evidence`** (`FL-08..09`) | `#21`–`#24b`, `#27` (9 rutas + 7 pruebas IA real) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` + `13C §1` | `[ ]` |
| **Bloque 7** | Clasificaciones, Validación Humana (6 acciones) y Ráfagas (`FL-10`, `FL-16`) | `#25`, `#26`, `#28`, `#29`, `#29b` (9 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 8** | Estadísticas Ecológicas SQL y Reportes Excel (5 hojas) / PDF `reportlab` (`FL-11`, `FL-12`) | `#15`, `#20`, `#31` (4 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 9** | Importación Asíncrona de Paquetes de Escritorio `.wwm.zip` (`FL-23`, D2, D10) | `#32`–`#35` + `GET /imports/{id}` (5 rutas) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 10** | Borrado Lógico de Clasificaciones (`FL-10`) | `#26 DELETE` (1 ruta) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 11** | **Panel Admin:** `AdminScope`, Moderación, Usuarios, Reset Link, Settings, Cola, Sugerencias y Excel Global (`FL-40..46`) | `#36`–`#44` (18 rutas con las 4 entidades) | `[[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]` | `[ ]` |
| **Bloque 12** | **Operación:** Resend en worker (`T2`), Rate limit Redis (`T1`), CLI Crons, `seed-e2e` y `backup.sh`/`restore_test.sh` (`FL-30..33`) | 8 comandos CLI + 2 scripts | `13C §2` | `[ ]` |
| **TOTAL** | **100 % del Backlog (`M0–M4` + `T1/T2`) en `main` (`0003`)** | **80 rutas (método + ruta) + CLI + Scripts** | **`13A` + `13B` + `13C`** | `[ ]` |
