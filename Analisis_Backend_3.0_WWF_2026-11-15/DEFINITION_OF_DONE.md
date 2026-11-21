---
title: "Definition of Done (DoD) Único — BACKWWF"
date: 2026-11-20
project: BACKWWF
version: "1.2.0 TDR"
tags: [dod, workflow, qa, pr, docker, env, wwf]
---

# Definition of Done (DoD) Único (`BACKWWF`)

> [!NOTE]
> Regla de proceso: ningún ticket repite este documento; todos lo enlazan como `[[DEFINITION_OF_DONE]]`.

## 1. Criterio de Código Ejecutable (Antes de pedir Review)
- [ ] **Verificación contra infraestructura real (Docker):** El endpoint/worker corre y responde dentro del entorno real activo (`fauna_api` en `:8000`, servicio IA `ia-clasificacion-fauna` / `ia-fake` en `:8001` (el contenedor viejo `wwf-wildlife-api:8081` no cuenta), PostgreSQL `faunadb` en `:5433` vía `host.docker.internal:5433`, Redis y el worker `arq` cuando aplique), no solo contra mocks en memoria.
- [ ] **Gestión de secretos y doble entorno (`development` vs `production`):** Cero credenciales, contraseñas, API keys ni URLs privadas hardcodeadas en código, scripts (`check_db.py`, `app/cli.py seed-e2e`) o manifiestos (`docker-compose.yml`; no hay manifiestos de producción hasta que el cliente elija la plataforma, D1). Toda configuración sensible se lee exclusivamente desde variables de entorno mediante `Settings` (`app/core/config.py`), soportando perfiles separados para `ENVIRONMENT=development` y `ENVIRONMENT=production` con credenciales, hosts y políticas de CORS distintas por entorno.
- [ ] **Contrato IA (si el ticket habla con la IA o importa paquetes):** usa la copia sin editar de `app/integrations/ia_contract/` (sha256 igual al commit de `SOURCE.md`; solo se copian archivos de la lista MIT de la IA, lo demás se replica con el mismo comportamiento, D2), traduce errores con la tabla "Contrato IA vigente" de [[10_Backlog_Teamwork_WWF]], prueba con los fixtures oficiales de `tests/fixtures/` y nunca completa datos que la IA no devolvió (DD-4).
- [ ] **Código mínimo funcional (Ponytail):** Sin wrappers especulativos, sin código comentado muerto, sin librerías nuevas innecesarias y sin stubs "para después" (ej. solo `LocalStorage` detrás de `StorageBackend`).
- [ ] **Estándares `ESTANDARES_BACKEND_IA.md`:** Envoltura `ApiResponse`, errores con código estable `AppError` (sin `HTTPException` libre ni stack traces en 500), logs JSON con `request_id`/`flow`/`step` sin datos sensibles y sin `print()`.

## 2. Cobertura de Pruebas por Nivel de Riesgo
- [ ] **Nivel 1 — Automatizado obligatorio (bloquea merge):** Tests unitarios/integración para **seguridad, privacidad e integridad de datos** (IDOR/BOLA, DD-17, secretos y rechazo de claves débiles en `Settings`, bloqueos optimistas `If-Match`, duplicados SHA-256, unicidad de cámara, Zip Slip/Bomb).
- [ ] **Nivel 2 — Un test parametrizado por grupo:** Casos borde similares agrupados con `@pytest.mark.parametrize` (validación de formatos, cola/reaper, ráfagas, importación).
- [ ] **Nivel 3 — Verificación manual con nota en PR:** Casos cosméticos o de baja probabilidad (`verificado a mano: ver CB-xx` en la descripción del PR).
- [ ] **Bugs:** Todo `BUG` incluye al menos 1 test que falla antes del arreglo y pasa después.

## 3. Quality Gate y CI
- [ ] `ruff check`, `ruff format --check` y `mypy --strict` (sobre todo `app/` salvo `db/session.py`) en verde.
- [ ] `pytest` en verde (cobertura `services/` ≥ 80%, global ≥ 70%) y `pip-audit` sin vulnerabilidades altas.
- [ ] `.env.example` (con plantilla documentada para `development` y `production` usando placeholders, **nunca** secretos reales) y migración Alembic (`upgrade` + `downgrade` + `alembic check` sin diferencias) actualizados si aplica; dependencias nuevas con versión fijada, licencia compatible (MIT/BSD/Apache) y `pip-audit` limpio; `gitleaks` sin credenciales en archivos rastreados por Git.

## 4. Flujo de Revisión y Desbloqueo a Front
- [ ] **Aviso temprano a Miguel (Front):** Si el ticket desbloquea trabajo en `Front-WWF`, avisar **al abrir el PR** (no al cerrarlo) para integración paralela contra el contrato.
- [ ] **Revisión obligatoria de Diego:** Solo en tickets marcados como `Revisión obligatoria: Diego` (seguridad, privacidad DD-17 o contrato externo IA: `BUG-01..04`, `SPIKE-01`, `HU-01`, `HU-02`, `HU-05`, `HU-06`, `HU-11`, `HU-15a`, `HU-16`).
- [ ] **Revisión asíncrona:** El resto de los tickets se fusiona a `develop` con CI verde sin esperar aprobación previa de Diego (revisión asíncrona posterior).
- [ ] **Checklist de PR (`PLANTILLA_PR.md`):** Completado y fusionado vía *squash merge*.
