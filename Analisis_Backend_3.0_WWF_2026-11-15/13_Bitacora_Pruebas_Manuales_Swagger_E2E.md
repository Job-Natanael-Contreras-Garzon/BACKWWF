---
title: "13 - Índice Maestro de la Bitácora Física E2E en Swagger con IA Real (Vista Multi-Panel)"
date: 2026-11-21
project: BACKWWF
version: "2.0.0"
status: active
tags: [testing, swagger, e2e, bitacora, index, wwf]
---

# 13. Índice Maestro: Bitácora Física E2E en Swagger con IA Real (`BACKWWF`)

Para trabajar cómodamente en **vista dividida (multi-panel)** sin tener que hacer *scroll* arriba y abajo durante las pruebas en Swagger (`http://localhost:8000/docs`), la bitácora está dividida en **3 archivos complementarios**:

1. **Panel Izquierdo (Fijo) — [[13A_Hoja_Tokens_IDs_y_Arranque]]**
   - Comandos en PowerShell para destruir contenedores y levantarlos desde cero (`ia-clasificacion-fauna :8001` + `BACKWWF :8000` + migración `0003` + `create-admin`).
   - Checklist de archivos multimedia y paquetes `.wwm.zip` (`tests/fixtures/package/`).
   - **Tabla editable de Tokens y UUIDs** (`ANON_TOKEN_1`, `USER_A_ACCESS`, `USER_B_ACCESS`, `ADMIN_ACCESS`, `CAM_PUB_ID`, `CAM_PRIV_ID`, `PROJ_PUB_ID`, `BATCH_1_ID`, `CLS_ANIMAL_1_ID`, etc.) lista para copiar y pegar.
   - **Tabla de Registro de Hallazgos con `request_id`** (`meta.request_id` o `w-<hex10>`) para buscar cualquier error en los logs.

2. **Panel Central (Ejecución Lineal en Swagger) — [[13B_Guia_Secuencia_Swagger_Bloques_1_al_11]]**
   - Envoltura estándar `ApiResponse` para el frontend (Miguel).
   - **Secuencia paso a paso de los Bloques 1 al 11 (las 80 rutas HTTP operativas en `main`):**
     - **Bloque 1:** Sistema, `/health/ready`, `/config/public` y Catálogo SpeciesNet (`3538` taxones).
     - **Bloque 2:** Sesiones Anónimas (`ANON_TOKEN_1` y `ANON_TOKEN_2`).
     - **Bloque 3:** Auth JWT, Detección de Reuso de Refresh (`CB-78`), Perfil, Reset y Claim con renombrado `-2`.
     - **Bloque 4:** Cámaras Trampa, Privacidad DD-17, `nearby`, `redeploy` y `time-offset` (`#15d`).
     - **Bloque 5:** Proyectos y Asociación N:M Segura (`CB-20`, `CB-23`).
     - **Bloque 6:** Lotes, Subida a Cola `arq`/Redis, Procesamiento con IA Real y `/evidence`.
     - **Bloque 7:** Consulta de Clasificaciones, Validación Humana (6 acciones) y Ráfagas (`FL-16`).
     - **Bloque 8:** Estadísticas Ecológicas SQL y Reportes Científicos Excel (5 hojas) y PDF (`reportlab`).
     - **Bloque 9:** Importación Asíncrona de Paquetes de Escritorio `.wwm.zip` (`202` + `GET /imports/{id}`).
     - **Bloque 10:** Borrado Lógico de Clasificaciones.
     - **Bloque 11:** Panel Admin Completo (`#36`–`#44`: `AdminScope`, `CB-96`, moderación, usuarios, `password-reset-link`, settings, `/admin/queue`, `/admin/unlisted-suggestions`, Excel global de 6 hojas y `audit-log`).

3. **Panel Derecho (IA Real, Operación CLI y Scorecard) — [[13C_Protocolo_IA_Real_Operacion_y_Certificacion]]**
   - **Protocolo de lo que SOLO se ve con la IA Fauna Real (`:8001`):** tiempos reales foto vs video 15 s, latido del worker vs `AI_TIMEOUT_SECONDS=180`, arranque en frío (`AI_NOT_READY` a los 5 s y 30 s), resultados reales (`blank`, `person`/`vehicle` sin taxonomía, `animal` en los 3538 taxones), truncado de videos largos (`VIDEO_TRUNCATED`), formatos (`.heic` rechazado, `.avi`/`.mkv`/`.flv` aceptados), trazabilidad `w-<hex10>` en logs de Back e IA, y prueba de carga de ~50 archivos con 2 dueños en `/admin/queue` + `docker stats`.
   - **Bloque 12 (Operación en desarrollo):** Correo real con Resend en el worker (`T2`), límites de intentos compartidos en Redis (`T1`, `429 RATE_LIMITED`), crons CLI (`sync-catalog`, `reaper`, `cleanup`, `purge-anon`, `reset-admin-password`), semilla `seed-e2e` y respaldo/restauración (`scripts/backup.sh` + `scripts/restore_test.sh`).
   - **Scorecard de Certificación Final (Bloques 0 al 12).**
