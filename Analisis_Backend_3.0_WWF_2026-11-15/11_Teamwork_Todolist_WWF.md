---
title: "11 - To-Do List de Ejecución para Antigravity /teamwork (M0–M4)"
date: 2026-11-16
project: BACKWWF
version: "1.0.0 TDR"
tags: [teamwork, antigravity, todolist, swarm, ponytail, wwf]
---

# 11. To-Do List Maestro para `/teamwork` (`BACKWWF` M0–M4)

> [!NOTE]
> Backlog completo: [[10_Backlog_Teamwork_WWF]] · Matriz `FL/CB`: [[09_Matriz_Flujos_y_Casos_Borde]] · DoD Único: [[DEFINITION_OF_DONE]]

Este checklist está diseñado para ejecutarse por **oleadas (*Waves*)** con el comando **`/teamwork`** de Antigravity (o en sesiones individuales con modelo local 9B). Cada tarea delimita explícitamente **los archivos que posee** para que varios agentes puedan trabajar en paralelo sin pisarse el mismo archivo.

**Reglas para cada agente / worker:**
1. Cargar antes de programar: `.agents/skills/ponytail/SKILL.md`, `wwf-backend-standards`, `wwf-api-contracts`, `wwf-flows-and-edge-cases` y `wwf-dev-workflow`.
2. Construir desde los contratos (`skills`), **no** copiando código legacy (el código actual solo indica qué borrar).
3. Código mínimo funcional (Ponytail), sin stubs S3 ni mocks silenciosos, y verificado contra PostgreSQL/Redis/IA reales según [[DEFINITION_OF_DONE]].

---

## Milestone 0 — Saneamiento, Walking Skeleton IA y Cimientos

### Oleada 0A (Secuencial — Bloqueante inicial)
- [ ] **[BUG-01] Purga y rotación de secretos expuestos y configuración estricta** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: Ninguna`
  - **Scope / Archivos:** `digitalocean.yaml`, `check_db.py`, `app/services/species_data_service.py`, `app/core/config.py`, `app/services/video_service.py`, `.env.example`, `.pre-commit-config.yaml` (`gitleaks`).
  - **Objetivo:** Cero secretos en código, `Settings` único que falla con `CRITICAL` si `SECRET_KEY`/`REFRESH_SECRET_KEY` < 32 bytes, `localhost` en CORS solo en `development`, `ffprobe` desde `PATH`.
  - **Spec:** [[10_Backlog_Teamwork_WWF]] (`BUG-01`) · **Verificación:** `test_settings_rejects_weak_jwt_secrets_in_production`.

### Oleada 0B (Paralelizable en `/teamwork`: 3 agentes en archivos disjuntos tras `BUG-01`)
- [ ] **[BUG-02] Cierre de brechas BOLA/IDOR y eliminación de routers legacy sin autenticación** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01]`
  - **Scope / Archivos:** `app/main.py` (desmontar routers), eliminar `app/api/v1/{videos,species,individuals,reports,ai_router,media_files,users}.py` y corregir validación de propiedad en `app/services/project_service.py` si aplica en transición.
  - **Objetivo:** Retirar rutas legacy expuestas y cerrar BOLA/IDOR (`CB-23`).
  - **Spec:** [[10_Backlog_Teamwork_WWF]] (`BUG-02`) · **Verificación:** `test_legacy_routes_removed_and_idor_blocked`.

- [ ] **[BUG-03] Eliminación de bloqueo del Event Loop y fuga de errores 500** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01]`
  - **Scope / Archivos:** `app/main.py` (solo `global_exception_handler` 500 sin `str(exc)`), `app/services/media_service.py` (quitar `shutil.copyfileobj` síncrono mientras se migra a `HU-08`).
  - **Objetivo:** Cero `shutil.copyfileobj` síncrono en corrutinas `async def` y respuesta 500 genérica (`INTERNAL_ERROR`).
  - **Spec:** [[10_Backlog_Teamwork_WWF]] (`BUG-03`) · **Verificación:** `test_500_handler_hides_internal_exception_details`.

- [ ] **[SPIKE-01] Walking Skeleton: Llamada real a `POST /api/v1/detect` sin cola ni storage** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01]`
  - **Scope / Archivos:** `app/integrations/ai_contract.py`, `app/integrations/ai_client.py`, `scripts/verify_ai_spike.py`.
  - **Objetivo:** Validar en días 2–5 el contrato real `API_IA_BACK.md` (puertos, `X-API-Key`, `timeout=180s`, JSON `DetectResponse` y Pillow sobre `image_base64`) contra `ia-deteccion` o `ia-fake`.
  - **Spec:** [[10_Backlog_Teamwork_WWF]] (`SPIKE-01`) · **Verificación:** Ejecución real con 1 imagen + 1 video.

### Oleada 0C (Secuencial tras Oleada 0B)
- [ ] **[HU-01] Infraestructura Core estándar y `LocalStorage` (sin stub S3)** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-01], [BUG-03], [SPIKE-01]`
  - **Scope / Archivos:** `app/core/{responses,errors,logging,middleware}.py`, `app/api/v1/router.py`, `app/integrations/storage/{base,local}.py`, `app/main.py`, `pyproject.toml` (`ruff`, `mypy`).
  - **Objetivo:** `ApiResponse`, `AppError`, logs JSON con `X-Request-ID`/`flow`/`step`, middlewares de seguridad, `StorageBackend` + `LocalStorage` (sin `s3.py`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (envoltura estándar `apiClient.js`).

### Oleada 0D (Paralelo parcial tras `HU-01`)
- [ ] **[HU-02] Esquema canónico PostgreSQL, migración inicial Alembic y repositorios + UoW** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-02], [HU-01]`
  - **Scope / Archivos:** `app/models/*.py`, `app/db/uow.py`, `app/repositories/*.py`, `app/services/policies.py`, `migrations/versions/0001_canonical_schema.py`.
  - **Objetivo:** Esquema completo `FLUJOS_SISTEMA.md §3`, índices únicos parciales (`CB-13`, `CB-50`), `upgrade`/`downgrade` limpios, repositorios sin `commit()` y sin `lazy="selectin"` en cascada.

- [ ] **[BUG-04] Eliminación de `timeout=2.0`, mock de *Panthera onca* y `ai_router.py`** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [BUG-02], [SPIKE-01], [HU-01]`
  - **Scope / Archivos:** Eliminar `app/services/ai_service.py` y `app/api/v1/ai_router.py` (reemplazados por `ai_client.py`).
  - **Objetivo:** Cero mocks silenciosos (DD-4); fallo de IA se traduce a `AI_TIMEOUT`/`AI_UNAVAILABLE`.

---

## Milestone 1 — Núcleo: Auth, Sesiones Anónimas, Cámaras y Proyectos

### Oleada 1A (Secuencial tras `HU-02`)
- [ ] **[HU-03] Autenticación JWT completa, rotación/reuso de refresh tokens, perfil y sistema** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-02]`
  - **Scope / Archivos:** `app/api/v1/{auth,config,health}.py`, `app/services/auth_service.py`, `app/repositories/{user,token}_repo.py`, `app/schemas/auth.py`.
  - **Objetivo:** Endpoints `#1–#6`, `#11`, `#12` (`register`, `login` con rate limit, `refresh` con rotación, `logout`, `GET/PATCH /me`, `me/password`, `/config/public`, `/health`, `/health/ready`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-01`..`FE-04`).

### Oleada 1B (Paralelizable tras `HU-03`: 2 agentes)
- [ ] **[HU-05] Sesiones anónimas temporales, `claim` atómico y cron `FL-30`** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [HU-03]`
  - **Scope / Archivos:** `app/api/v1/anon_sessions.py`, `app/services/anon_session_service.py`, `app/repositories/anon_session_repo.py`, `app/worker/cron_anon.py`.
  - **Objetivo:** Endpoints `#7–#10` (`POST /anon-sessions`, `/current`, `/claim` renombrando `-2`, `/close`) y cron horario `FL-30` (`anon_retain`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`AnonBanner`, `ClaimDialog`).

- [ ] **[HU-04] Recuperación de contraseña por correo (Resend) *(Condicional / Diferible)*** · `Prioridad: Low` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-03]`
  - **Scope / Archivos:** `app/services/password_reset_service.py`, `app/integrations/email/`, `app/worker/send_email_job.py`.
  - **Objetivo:** Endpoint `#6b` (`forgot`, `validate`, `reset`) con límites y cuotas Resend; confirmar con WWF si entra en fecha de hackathon (si no, usar enlace manual de `HU-15a`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-14`).

### Oleada 1C (Secuencial tras `HU-05`)
- [ ] **[HU-06] Cámaras trampa, privacidad DD-17, `nearby`, `redeploy` y `time-offset`** · `Prioridad: High` · `Revisión: Obligatoria Diego` · `Depende de: [HU-05]`
  - **Scope / Archivos:** `app/api/v1/camera_stations.py`, `app/services/camera_station_service.py`, `app/repositories/camera_repo.py`, `app/schemas/camera_station.py`.
  - **Objetivo:** Endpoints `#13`, `#14`, `#15b`, `#15c`, `#15d` (`If-Match`, `serialize_location` DD-17, `CB-01..CB-21`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (Mapa, `CameraFormModal`, `NearbyCamerasDialog`).

### Oleada 1D (Paralelizable tras `HU-06`: 2 agentes en dominios disjuntos)
- [ ] **[HU-07] Gestión de proyectos y asociación N:M segura de cámaras propias** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-06]`
  - **Scope / Archivos:** `app/api/v1/projects.py`, `app/services/project_service.py`, `app/repositories/project_repo.py`, `app/schemas/project.py`.
  - **Objetivo:** Endpoints `#16–#19` (privacidad independiente, `If-Match`, `CAMERA_NOT_OWNED` `CB-23`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-10`).

- [ ] **[HU-08] Creación de lotes y subida no bloqueante a cola justa Redis/`arq`** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-06]`
  - **Scope / Archivos:** `app/api/v1/batches.py`, `app/services/{batch_service,media_validator}.py`, `app/integrations/queue.py`, `app/worker/dispatcher.py`.
  - **Objetivo:** Endpoints `#21`, `#23`, `#24` (`aiofiles`, `python-magic`, Pillow pixels, `ffprobe ≤ 15.5s`, SHA-256 deduplicado `CB-50..54`, dispatcher justo `CB-30`).
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
  - **Objetivo:** Endpoint `#27` + worker real conectado a `ai_client.py` (reintentos `IA_BUSY`, Pillow sin EXIF, borrado temporal en `finally`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (resultados reales y fotogramas).

### Oleada 3B (Secuencial tras `HU-07` y `HU-11`)
- [ ] **[HU-13] Catálogo SpeciesNet en RAM y estadísticas ecológicas oficiales** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-06], [HU-07], [HU-11]`
  - **Scope / Archivos:** `app/api/v1/catalog.py`, `app/services/{catalog_service,stats_service}.py`, `app/repositories/stats_repo.py`, `app/schemas/stats.py`.
  - **Objetivo:** Endpoints `#15`, `#20`, `#30` (`/catalog/species*`, `/camera-stations/{id}/stats`, `/projects/{id}/stats`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-25`, `FE-26`).

### Oleada 3C (Paralelizable tras `HU-13`: 3 agentes en módulos disjuntos)
- [ ] **[HU-12] Consulta de clasificaciones, validación humana y revisión de ráfagas** · `Prioridad: High` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-11], [HU-13]`
  - **Scope / Archivos:** `app/api/v1/classifications.py` (resto de rutas), `app/services/{classification_service,burst_service}.py`, `app/repositories/classification_repo.py`.
  - **Objetivo:** Endpoints `#25`, `#26`, `#28`, `#29`, `#29b` (`CB-51`, `CB-60..67`).
  - **Desbloquea Front:** Avisar a Miguel al abrir PR (`FE-24`, `FE-25`).

- [ ] **[HU-10] *(Milestone 3–4)* Importación segura de paquetes `.wwm.zip` de escritorio** · `Prioridad: Medium` · `Revisión: Asíncrona (CI verde)` · `Depende de: [HU-08], [HU-13]`
  - **Scope / Archivos:** `app/api/v1/imports.py`, `app/services/import_service.py`, `app/integrations/package_contract.py`, `app/worker/import_job.py`.
  - **Objetivo:** Endpoints `#32–#35` (Zip Slip/Bomb, checksum, Pillow, `create_camera`, `import_job` `CB-80..87`).
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
  - **Objetivo:** Certificar 0 brechas IDOR en los 44 contratos, paridad con `ia-deteccion` (`FL-20..22`, `CB-90..95`), backup/restore `FL-32`, `pip-audit` y `seed-e2e`.
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
