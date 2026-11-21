---
name: wwf-flows-and-edge-cases
description: Mapa compacto de flujos FL-xx y clasificación por riesgo de casos borde CB-xx (qué testear siempre vs parametrizar vs verificar a mano).
---

# Flujos (`FL-xx`) y Matriz de Riesgo (`CB-xx`)

Usa esta guía para no olvidar reglas funcionales ni malgastar tiempo escribiendo tests triviales.

## 1. Mapa Rápido de Flujos (`FL-xx`)
- **Acceso (`FL-01..04, FL-14`):** Registro/login/rotación refresh (`FL-01, 02`); sesión anónima con hash SHA-256 en `sessionStorage`, TTL 24h, `anon_retain` copiado al crear cada fila (`FL-03`); `claim` atómico renombrando colisiones `-2` (`FL-04`); reset email Resend condicional o enlace manual admin (`FL-14`).
- **Cámaras y Proyectos (`FL-05..07, FL-13, FL-15`):** Alta con mapa y `nearby` (`FL-05`); edición `If-Match`, retiro, borrado lógico cascada y `time-offset` (`FL-06`); reinstalación `redeploy` (`FL-15`); proyectos N:M solo con cámaras propias (`FL-07`); exploración pública con DD-17 (`FL-13`).
- **Clasificación y Cola (`FL-08..09`):** Subida `202` a `TMP_UPLOAD_PATH` + cola justa Redis/`arq` (`QUEUE_PER_OWNER_INFLIGHT=2`, `FL-08`); polling `?since=`, cancelación y retry si temporal vive (`FL-09`).
- **Validación y Reportes (`FL-10..12, FL-16`):** Confirmar/corregir/rechazar/unlisted + historial (`FL-10`); ráfagas `burst-candidates` y `repeat-batch` (`FL-16`); stats SQL sin APIs de clima (`FL-11`); Excel 5 hojas + PDF con DD-17 (`FL-12`).
- **Escritorio (`FL-20..23`):** `FL-20..22` ya corren en `ia-clasificacion-fauna/desktop` (`evidence` solo en `animal` por `F2-D2`/`F2-D9`); el Back implementa `FL-23` (`POST /imports/desktop` preview 1h + `/confirm`).
- **Crons y Backups (`FL-30..33`):** `FL-30` vence anónimos y purga `anon_retain=false`; `FL-31` limpia temporales/huérfanos; `FL-32` scripts `pg_dump`+evidencias; `FL-33` *Reaper* cola cada 5 min.
- **Admin (`FL-40..46`):** `AdminScope` nunca ve privado (`404`); MVP (`FL-40..44`: stats, explorar, borrar/restaurar con `reason`, usuarios, `anon_data_retention`) + extensión post-demo (`FL-45` cola, `FL-46` unlisted, Excel global).

## 2. Qué Probar Según Nivel de Riesgo (`CB-01..99`)

### 🔴 Nivel 1: Automatizar SIEMPRE (bloquean merge)
*Fallo = fuga de datos privados, IDOR o corrupción de BD.*
- **Privacidad / DD-17:** `CB-04/05/05b` (`nearby` con bandas `<10m/<50m/<200m`, privadas ocultas, coords redondeadas 2 decimales), `CB-20/20b` (privada excluida de stats/proyecto público; anónimo no publica), `CB-96` (admin recibe `404` en privado).
- **IDOR / Auth / Tokens:** `CB-23` (no asociar cámara ajena), `CB-44` (usuario desactivado cancela `queued`), `CB-67` (`validation-batch` omite IDs ajenos), `CB-72/73/74/75/78` (email duplicado, no enumeración en forgot, invalidación de resets, reuso/revocación de refresh tokens), `CB-98/99` (no auto-desactivarse, CLI reset admin).
- **Integridad / No Mock:** `CB-13/14` (`code` único case-insensitive por dueño), `CB-15` (`If-Match` -> `409 CONFLICT_STALE`), `CB-37` (error IA nunca inventa Jaguar; worker reintenta 5 s/30 s `AI_UNAVAILABLE`/`AI_TIMEOUT`/`IA_BUSY` y luego `error`; `ai_client` reintenta 1 vez `IA_INTERNAL`), `CB-50/51/52/54/55` (deduplicación SHA-256 misma cámara / otra cámara / importación), `CB-82` (`IMPORT_ALREADY_IMPORTED`), `CB-97` (borrar sesión anónima cancela `queued`) y Zip Slip/Bomb en `.wwm.zip`.

### 🟡 Nivel 2: Un Test Parametrizado por Grupo (`@pytest.mark.parametrize`)
- **Validación cámara:** `CB-01/02/06` (`nearby`), `CB-03` (`redeploy`), `CB-08/11/12` (rango coords y fechas), `CB-18` (`time-offset`), `CB-21/24/27`.
- **Cola / Crons:** `CB-30..43` (cola justa, límites `429`/`503`, Redis caído, reaper 10m/24h, cancel `409`, retry `410`, claim/retención anónima).
- **Archivos / Validación / Stats:** `CB-56..59` (video > 15 s + 0,5 s de tolerancia truncado a 15.0 s + warning `VIDEO_TRUNCATED` `F1-D10`, magic bytes, formatos `ia_contract/formats.py` y rechazo explícito `.heic` hasta `IA-16`, >100 MP (`too_many_pixels`) -> `MEDIA_TOO_LARGE`, corrupto); traducción de errores IA parametrizada con `httpx.MockTransport` y los fixtures `tests/fixtures/ai/*.json`, `CB-60..60d` (ráfagas y `REPEAT_KEEP_REQUIRED`), `CB-61..68` (genus rank, blank->animal, `correct_unlisted`, historial), `CB-80..87` (preview/confirm import, `LINE_INVALID`, `EVIDENCE_MISSING`).

### 🟢 Nivel 3: Verificación Manual con Nota en PR (sin test unitario/integración dedicado)
*Comentar `"verificado a mano: ver CB-xx"` en el PR:*
- `CB-07` (warning `CAMERA_COORDS_SUSPECT`), `CB-09` (warning mover >50m), `CB-10` (múltiples cámaras mismo punto en mapa), `CB-16` (subir a cámara retirada), `CB-19` (recalcular `trap_days`), `CB-22/25/26` (proyecto vacío, nombres repetidos, N:M), `CB-53` (mismo nombre distinto SHA-256), `CB-70/71` (dos pestañas anónimas), `CB-90..95` (reglas locales escritorio; solo test contrato UTF-8 largo en `HU-16`).
