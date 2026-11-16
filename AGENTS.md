# Backend API - Monitoreo de Fauna Silvestre WWF

FastAPI backend para gestión de proyectos de cámaras trampa, video multimedia y análisis IA.

## 🚀 Commands Exactos

### Development (venv requerido)
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

# Run a single test file
pytest tests/test_phase3_soft_delete_and_nm_stress.py

# Tests require no database/connection - in-memory FastAPI client
```

### Database & Migrations
```bash
# Initialize DB schema (dev only, creates all tables)
python check_db.py  # Verify schema if needed

# Run alembic migrations (prod workflow)
alembic upgrade head

# Create migration file
alembic revision --autogenerate -m "your_message"
```

### Data Seeding
```bash
# Small seed: ~100 detections across 3 stations
python seed_db.py

# Mass seed: ~4500 records with burst events
python seed_massive.py
```

## 🏗 Architecture Overview

**Directory Structure:**
- `app/api/v1/` – API routers (auth, users, projects, camera_stations, videos, species, individuals, reports, ai)
- `app/services/` – Business logic for video processing, AI integration, user/project/station/media services
- `app/db/` – Database session management (`engine`, `async_session_maker`)
- `app/models/` – SQLAlchemy declarative models (base.py registers all in its `__all__`)
- `app/schemas/` – Pydantic V2 schemas for request/response validation
- `app/crud/` - CRUD operations using SelectInLoader for async compatibility
- `app/interfaces/` – Service layer contracts/interfaces
- `app/core/` – Config, security (JWT), enums

**Entry Point:** `app/main:app`

## 🔑 Key Quirks & Notes

### SQLAlchemy with AsyncPG
**Critical:** The project uses `lazy='selectin'` in all bidirectional relationships to avoid `MissingGreenletError`. Avoid standard lazy loading.

```python
# Example (do not use naive lazy loading)
rel = ForeignKeyColumn(rel=Relationship, lazy='selectin')  # Must be used everywhere
```

### FastAPI Lifespan Context Manager
The database pool is created/destroyed in `app/main.py` using an async context manager. Never remove the `@asynccontextmanager` decorator or it will leak connections.

### JWT Configuration (in .env)
- Default keys are placeholders - change them in production `.env`
- Access tokens expire in **30 minutes**
- Refresh tokens expire in **7 days**
- Tokens require header: `Authorization: Bearer <access_token>`

### CORS
Default allowed origins include frontend dev URLs. Production should restrict via `.env`.

### AI Service External Dependency
External AI inference service is called at `AI_SERVICE_URL=http://localhost:8081`. Set appropriately in production.

### Database Connection Format
```
postgresql+asyncpg://user:password@host:port/dbname?ssl=require
```
Always use async connection patterns with `async with engine.connect()`.

## 🐳 Deployment (Koyeb / Docker)

**Dockerfile stages:** Multi-stage build using Python 3.11-slim with builder stage for pip wheels.

**Production command (2 workers):**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      --workers 2 --loop uvloop --no-access-log
```

**Koyeb config:** `koyeb.yml` exposes port 8000, health-checks `/health`.

**Docker layers to exclude (in .dockerignore):**
- `requirements.txt` is copied to build cache for better layer reuse.
- `.env` is excluded; use env vars at deploy time.
- `migrations/`, `seed_*.py`, `uploads/` must be mounted or ignored appropriately.

## 📂 Important Files by Purpose

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app + lifespan DB dispose |
| `app/core/config.py` | Settings + JWT keys + DATABASE_URL |
| `app/db/session.py` | Async session factory & engine |
| `migrations/env.py` | Alembic async migrations setup |
| `requirements.txt` | All Python dependencies |
| `Dockerfile` | Multi-stage build (builder caches pip wheels) |
| `koyeb.yml` | Koyeb deployment manifest |
| `pytest.ini` | Pytest asyncio config |
| `.env.example` | Required env vars list |

## ⚠️ Common Pitfalls

- Forgetting the `--reload` flag during development causes hot-reload to not work.
- Using `lazy='joined'` instead of `'selectin'` breaks async SQLAlchemy.
- Missing DB dispose in lifespan leaks connection pools on shutdown.
- Running tests without an env requires no real database - they mock routes.
- JWT secrets must be changed before production deployment (default is weak).

## 📜 API Endpoints Summary

All endpoints live under `/api/v1`:

- `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/me` – Authentication
- `/users` – User CRUD
- `/projects`, `/camera_stations` – Project and station management
- `/videos`, `/media_files`, `/species`, `/individuals` – Multimedia & detections
- `/reports` – Aggregated reports
- `/ai/` (see `app/api/v1/ai_router.py`) – AI processing websockets/routes

**Docs:** Serve at `http://localhost:8000/docs` (Swagger) and `/redoc`.

## 🔐 Security Notes

- Always set strong `SECRET_KEY` and `REFRESH_SECRET_KEY` via `.env`.
- Production Docker excludes `.env`; inject secrets at runtime or mount secure volumes.
- Default JWT keys are examples – change immediately before deployment.
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

