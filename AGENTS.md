# Backend API - Monitoreo de Fauna Silvestre WWF

FastAPI backend para gestión de proyectos de cámaras trampa, video multimedia y análisis IA.

## 🚀 Commands Exactos

### Docker Development Topology (Actual)
En desarrollo corren los servicios de API, IA y PostgreSQL en el host:
- `fauna_api` (`fauna-monitoring-api:local`) en `0.0.0.0:8000->8000/tcp` con `--reload`
- Servicio IA objetivo (`../ia-clasificacion-fauna`): `ia` (`api/`) o `ia-fake` (`fake/`) en `:8001` (`X-API-Key: dev-key` en dev; `wwf-wildlife-api:8081` queda como contenedor legado transitorio hasta migrar `ai_contract.py` de `SPIKE-01`)
- PostgreSQL en el host (`faunadb` puerto `5433`, accesible desde Docker vía `host.docker.internal:5433`)

```powershell
# Levantar API en modo desarrollo
docker compose up -d --build

# Ver contenedores y estado
docker ps
```

### Development (venv local alternativo)
```bash
# Activate environment
.\app\venv\Scripts\Activate.ps1  # Windows
source app/venv/bin/activate      # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Start dev server with auto-reload
uvicorn app.main:app --reload
```

### Testing
```bash
# Run all tests (asyncio_mode = auto configured in pytest.ini)
pytest

# Run inside Docker container
docker compose exec -T api pytest

# Run a single test file
pytest tests/test_phase3_soft_delete_and_nm_stress.py
```

### Database, Migrations & Seeding (Docker PowerShell)
`.dockerignore` excluye `seed_db.py`, `seed_massive.py` y `check_db.py` de la imagen, pero **incluye `migrations/`**. Para inicializar, verificar o poblar en Docker usar `stdin` (`docker compose exec -T api python -`):

```powershell
# 1. Crear tablas en faunadb
@'
import asyncio, app.models
from app.db.session import engine
from app.models.base import Base
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
asyncio.run(init_db())
'@ | docker compose exec -T api python -

# 2. Verificar las 10 tablas en pg_tables
@'
import asyncio
from sqlalchemy import text
from app.db.session import engine
async def check():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"))
        print([r[0] for r in res.fetchall()])
    await engine.dispose()
asyncio.run(check())
'@ | docker compose exec -T api python -

# 3. Poblar BD con seed_db.py (crea admin@wwf.org / wwf123456, 1 proyecto, 3 estaciones + N:M, ~87 detecciones en media_files/videos/species)
Get-Content .\seed_db.py -Raw | docker compose exec -T api python -

# 4. Run alembic migrations (workflow objetivo)
alembic upgrade head
alembic revision --autogenerate -m "your_message"
```

## 🏗 Architecture Overview

**Directory Structure:**
- `app/api/v1/` – API routers (auth, users, projects, camera_stations, videos, species, individuals, reports, ai)
- `app/services/` – Business logic for video processing, AI integration, user/project/station/media services
- `app/db/` – Database session management (`engine`, `async_session_maker`)
- `app/models/` – SQLAlchemy declarative models (`base.py` defines `Base`, `BaseEntity`)
- `app/schemas/` – Pydantic V2 schemas for request/response validation
- `app/crud/` - CRUD operations
- `app/interfaces/` – Service layer contracts/interfaces
- `app/core/` – Config, security (JWT), enums
- `Analisis_Backend_3.0_WWF_2026-11-15/` – Auditoría, backlog M0–M4 (`10_Backlog_Teamwork_WWF.md`), todolist (`11_Teamwork_Todolist_WWF.md`), rutina (`12_Guia_Rutina_Implementacion_con_Agentes.md`) y `DEFINITION_OF_DONE.md`
- **Exclusión crítica:** `tareas-job/` es solo lectura de referencia normativa; **nunca editar ni crear archivos dentro de `tareas-job/`**.

**Entry Point:** `app/main:app`

## 🔑 Key Quirks & Notes

### SQLAlchemy with AsyncPG
**Critical:** The project currently uses `lazy='selectin'` in relationships to avoid `MissingGreenletError` (nota: en el refactor `HU-02` se reemplazará por carga explícita en repositorios).

### FastAPI Lifespan Context Manager
The database pool is created/destroyed in `app/main.py` using `@asynccontextmanager`. Never remove it or it will leak connections.

### Environment Profiles (`development` vs `production`)
- Toda credencial, URL y secreto (`DATABASE_URL`, `SECRET_KEY`, `REFRESH_SECRET_KEY`, `AI_SERVICE_URL`, `AI_API_KEY`, `ALLOWED_ORIGINS`) se inyecta **únicamente por variables de entorno** leídas por `Settings` (`app/core/config.py`).
- **Dos configuraciones independientes con estructura compartida:**
  - `ENVIRONMENT=development`: `.env` local (no versionado), conecta a `host.docker.internal:5433/faunadb` y a `http://host.docker.internal:8001` (`../ia-clasificacion-fauna` / `ia-fake` con `AI_API_KEY=dev-key`; legado transitorio `:8081`), permite `localhost:5173`/`3000` en CORS y usa claves JWT de desarrollo (≥ 32 bytes).
  - `ENVIRONMENT=production`: variables secretas encriptadas en el PaaS (PostgreSQL remoto con `?ssl=require`, IA productiva en red interna `http://ia:8001` con `AI_API_KEY` obligatoria, claves JWT únicas criptográficas ≥ 32 bytes), CORS estricto sin `localhost`.
- **Prohibido:** hardcodear contraseñas o API keys en código, `check_db.py`, `seed_db.py` o manifiestos (`docker-compose.yml`).

### JWT Configuration
- Access tokens expire in **30 minutes**; Refresh tokens expire in **7 days** (`Authorization: Bearer <access_token>`).

### AI Service External Dependency
- Objetivo alineado (`../ia-clasificacion-fauna`): `AI_SERVICE_URL=http://host.docker.internal:8001` (o `http://ia:8001` en compose; `http://localhost:8001` desde el host) con `X-API-Key: dev-key` en desarrollo. Contenedor previo `wwf-wildlife-api:8081` queda como referencia transitoria hasta realinear `SPIKE-01` (PR #4).
- Estado actual de `develop`: fusionados PR #1 (`BUG-01`), PR #2 (`BUG-02`), PR #3 (`BUG-03`) y PR #4 (`SPIKE-01` v0 pendiente de realineación al `contract.py` final `:8001`).

## 🐳 Deployment & Docker

- **Multi-stage Dockerfile:** Python 3.11-slim with builder stage for pip wheels and `ffmpeg` + `curl` in runtime.
- **Production command:** `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --loop uvloop --no-access-log`
- **`.dockerignore`:** excluye `.env`, `uploads/`, `seed_db.py`, `seed_massive.py`, `check_db.py` (mantiene `migrations/`).

## 🔐 Security Notes

- Rotar y purgar cualquier secreto heredado antes de producir (`BUG-01`).
- Never commit `.env` or real credentials to Git or documentation.
- User `is_deleted` soft-delete flag is used; avoid permanent hard deletes in prod code.

---

## Ponytail (Lazy Senior Dev Mode — `DietrichGebert/ponytail`)

You are a lazy senior developer. The best code is the code never written. You solve the whole problem with the least new code. End your reply with one or two lines: what you skipped or did not check, and any risk the user must know.

### Before you write
Read the task and the code it touches. List every place your change must reach: callers, tests, fixtures, config, exports. Check what your change could break for users: data it would destroy or expose, callers that stop working. That is scope. Extra features are not.

### The smallest complete change
Take the first option that fully works:
1. Does it need to exist? Skip features, options and flexibility nobody asked for, and name them in one line. A vague request ("build me X") gets the smallest version that does the core job.
2. Already in this codebase (a helper, component, service, pattern)? Use it the way the surrounding code does.
3. Standard library or a platform feature? Use it, unless the project has its own.
4. An installed dependency? Use it. Never add a dependency for a few lines.
5. Can it be one line a reader gets at a glance? One line.
6. Otherwise: the minimum code that works.

- Be lazy about the solution, never about the change itself: finish every part the task needs, including callers, tests and fixtures your change breaks.
- No abstraction, wrapper, type conversion, option, config, boilerplate or "for later" code nobody asked for (e.g. no S3 stubs while deploying on local storage). Deletion beats addition.
- The shortest working diff wins. Comment only the why the code cannot show, in one line.
- Bug fix: grep every caller before editing, then fix the root cause once in shared code.
- Lazy code without its check is unfinished: new non-trivial logic leaves one small test or assert-based self-check.
- Shortcut with a known limit gets: `shortcut: <the limit>, <when to upgrade>`.

**Never cut:** validation at trust boundaries, error handling that prevents data loss, security (IDOR, DD-17, secrets), accessibility, or anything explicitly requested.
