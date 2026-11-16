---
title: "Definition of Done (DoD) Único — BACKWWF"
date: 2026-11-16
project: BACKWWF
version: "1.0.0 TDR"
tags: [dod, workflow, qa, pr, wwf]
---

# Definition of Done (DoD) Único (`BACKWWF`)

> [!NOTE]
> Regla de proceso: ningún ticket repite este documento; todos lo enlazan como `[[DEFINITION_OF_DONE]]`.

## 1. Criterio de Código Ejecutable (Antes de pedir Review)
- [ ] **Verificación contra infraestructura real:** El endpoint/worker corre y responde contra **PostgreSQL real** (y **Redis / `ia-deteccion`** donde aplique), no solo contra mocks en memoria.
- [ ] **Código mínimo funcional (Ponytail):** Sin wrappers especulativos, sin código comentado muerto, sin librerías nuevas innecesarias y sin stubs "para después" (ej. solo `LocalStorage` detrás de `StorageBackend`).
- [ ] **Estándares `ESTANDARES_BACKEND_IA.md`:** Envoltura `ApiResponse`, errores con código estable `AppError` (sin `HTTPException` libre ni stack traces en 500), logs JSON con `request_id`/`flow`/`step` sin datos sensibles y sin `print()`.

## 2. Cobertura de Pruebas por Nivel de Riesgo
- [ ] **Nivel 1 — Automatizado obligatorio (bloquea merge):** Tests unitarios/integración para **seguridad, privacidad e integridad de datos** (IDOR/BOLA, DD-17, secretos, bloqueos optimistas `If-Match`, duplicados SHA-256, unicidad de cámara, Zip Slip/Bomb).
- [ ] **Nivel 2 — Un test parametrizado por grupo:** Casos borde similares agrupados con `@pytest.mark.parametrize` (validación de formatos, cola/reaper, ráfagas, importación).
- [ ] **Nivel 3 — Verificación manual con nota en PR:** Casos cosméticos o de baja probabilidad (`verificado a mano: ver CB-xx` en la descripción del PR).
- [ ] **Bugs:** Todo `BUG` incluye al menos 1 test que falla antes del arreglo y pasa después.

## 3. Quality Gate y CI
- [ ] `ruff check`, `ruff format --check` y `mypy` (estricto en `core/` y `services/`) en verde.
- [ ] `pytest` en verde (cobertura `services/` ≥ 80%, global ≥ 70%) y `pip-audit` sin vulnerabilidades altas.
- [ ] `.env.example` y migración Alembic (`upgrade` + `downgrade`) actualizados si aplica.

## 4. Flujo de Revisión y Desbloqueo a Front
- [ ] **Aviso temprano a Miguel (Front):** Si el ticket desbloquea trabajo en `Front-WWF`, avisar **al abrir el PR** (no al cerrarlo) para integración paralela contra el contrato.
- [ ] **Revisión obligatoria de Diego:** Solo en tickets marcados como `Revisión obligatoria: Diego` (seguridad, privacidad DD-17 o contrato externo IA: `BUG-01..04`, `SPIKE-01`, `HU-01`, `HU-02`, `HU-05`, `HU-06`, `HU-11`, `HU-15a`, `HU-16`).
- [ ] **Revisión asíncrona:** El resto de los tickets se fusiona a `develop` con CI verde sin esperar aprobación previa de Diego (revisión asíncrona posterior).
- [ ] **Checklist de PR (`PLANTILLA_PR.md`):** Completado y fusionado vía *squash merge*.
