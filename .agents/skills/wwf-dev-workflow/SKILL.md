---
name: wwf-dev-workflow
description: Flujo de desarrollo ajustado M0-M4 para Job/Diego/Miguel: walking skeleton, DoD único, revisión selectiva y reglas Ponytail.
---

# Flujo de Desarrollo Ajustado (`BACKWWF`)

Equipo: **Job** (Backend), **Diego** (Tech Lead / IA), **Miguel** (Frontend). Objetivo: máxima velocidad con código funcional real y cero burocracia repetitiva.

## 1. Orden de Ejecución (M0 → M4)
1. **M0 Día 1–5 (Urgente):** `BUG-01..03` ✅ cerrados (PR #1–#3) + **`SPIKE-01` Walking Skeleton**: PR #4 v0 fusionada; falta realinear `ai_contract.py` al `contract.py` final de `ia-clasificacion-fauna` (`:8001`, sin `geofence`, con `low_evidence` y `truncated_at_seconds`).
2. **M0 Día 6–10:** `HU-01` (`Core` estándar + **solo `LocalStorage`** detrás de `StorageBackend`, sin stub S3) + `HU-02` (esquema canónico + Alembic + repositorios/UoW).
3. **M1:** `HU-03` (Auth), `HU-05` (Sesiones anónimas + `FL-30`), `HU-06` (Cámaras + DD-17), `HU-07` (Proyectos). *(`HU-04` Resend es condicional tras confirmar con WWF).*
4. **M2:** `HU-08` (Lotes + cola justa `arq`), `HU-09` (Cancel/retry + crons `FL-31/33`).
5. **M3 & M3–4:** `BUG-04` + `HU-11` (Worker IA + `/evidence`), `HU-12` (Validación + ráfagas), `HU-13` (Catálogo + Stats), `HU-10` (Import `.wwm.zip` en M3–4).
6. **M4:** `HU-14` (Excel/PDF), `HU-15a` (Admin MVP), **`HU-16` (Prioridad High: Matriz IDOR + Backups `FL-32` + CI Gate)**, y `HU-15b` (Admin extensión post-demo).

## 2. Reglas de Especificación y Código (Ponytail + Claude/LLM)
- **Especificación mínima por ticket:** Endpoints exactos, códigos de error `AppError` y Gherkin **solo** para seguridad/privacidad; el resto en bullets de 1 línea. Sin estimaciones de horas.
- **Construye desde las skills y contratos, NO desde el código legacy:** El código actual de `BACKWWF` solo sirve para identificar qué borrar y qué datos migrar.
- **No inventes wrappers ni stubs "para luego":** Escribe el cambio mínimo completo que pasa los checks.

## 3. Verificación, Revisión y Desbloqueo a Miguel
- **Ticket listo = endpoint corriendo contra PostgreSQL real** (y Redis/`ia-clasificacion-fauna`/`ia-fake` `:8001` cuando aplique), nunca solo contra mocks en memoria.
- **Revisión obligatoria de Diego** (bloquea merge): **solo** en `BUG-01..04`, `SPIKE-01`, `HU-01`, `HU-02`, `HU-05`, `HU-06`, `HU-11`, `HU-15a`, `HU-16`.
- **Revisión asíncrona:** El resto (`HU-03`, `04`, `07`, `08`, `09`, `10`, `12`, `13`, `14`, `15b`) se fusiona a `develop` con CI verde (`ruff`, `mypy`, `pytest`, `pip-audit`).
- **Aviso temprano a Miguel:** Cuando un PR desbloquee trabajo del front (`Desbloquea Front`), avisar a Miguel **al abrir el PR**, no al cerrarlo.
- **DoD único:** Todo ticket referencia `DEFINITION_OF_DONE.md`.
