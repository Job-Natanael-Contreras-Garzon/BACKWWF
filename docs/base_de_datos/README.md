---
title: "Base de Datos y Seeding en Docker — BACKWWF"
date: 2026-11-17
project: BACKWWF
version: "4.0.0 -> 1.0.0 TDR"
tags: [database, postgresql, alembic, seed, docker, wwf]
---

# Base de Datos, Tablas Actuales y Seeding (`faunadb`)

> [!NOTE]
> Índice general: [[../README]] | Refactor a esquema canónico: [[../../Analisis_Backend_3.0_WWF_2026-11-15/10_Backlog_Teamwork_WWF]] (`HU-02`)

---

## 1. Conexión por Entorno

La cadena de conexión se lee exclusivamente desde la variable de entorno `DATABASE_URL` definida en `Settings` (`app/core/config.py`):

- **Desarrollo (`ENVIRONMENT=development`, Docker `fauna_api`):**
  `postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@host.docker.internal:5433/faunadb`
- **Producción (`ENVIRONMENT=production`, PostgreSQL gestionado):**
  `postgresql+asyncpg://<PROD_USER>:<PROD_PASSWORD>@<PROD_HOST>:<PORT>/<PROD_DB>?ssl=require`

---

## 2. Tablas Activas en `faunadb` (Estado Actual)

Tras ejecutar `Base.metadata.create_all` dentro del contenedor `fauna_api`, PostgreSQL crea las siguientes **10 tablas** en el esquema `public`:

1. `users`: Usuarios registrados (autenticación `bcrypt` + JWT).
2. `anon_sessions`: Sesiones temporales anónimas (`is_claimed`, `claimed_by_user_id`).
3. `projects`: Proyectos de investigación (`status` público/privado).
4. `camera_stations`: Estaciones de cámaras trampa (`station_code`, coordenadas, estado).
5. `project_stations`: Relación N:M entre proyectos y estaciones de cámara.
6. `media_files`: Registros multimedia unificados (video/imagen).
7. `videos`: Tabla multimedia legacy mantenida temporalmente en sincronía con `media_files`.
8. `species`: Detecciones taxonómicas (`family`, `genus`, `scientific_name`, `common_name`, `confidence_score`, `is_verified`).
9. `individuals`: Ejemplares identificados.
10. `reports`: Reportes almacenados.

> [!IMPORTANT]
> **Transición hacia Alembic (`HU-02`):** En el Milestone 0 (`HU-02`), las tablas `videos`, `media_files` y `species` convergen hacia el esquema canónico (`classification_batches`, `classifications`, `desktop_imports`, `refresh_tokens`, `admin_audit_log`, etc.) gestionado exclusivamente con migraciones Alembic (`migrations/` ya está incluido en el build de Docker al haberse removido de `.dockerignore`).

---

## 3. Cambios Aplicados en `seed_db.py` y Flujo en Docker

El script [seed_db.py](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/seed_db.py) fue actualizado respecto a la versión inicial del MVP con las siguientes mejoras:

1. **Usuario fijo con contraseña real (`bcrypt`):** Busca o crea `admin@wwf.org` con contraseña hasheada `wwf123456` (`Dr. Jane Goodall`, `institucion="WWF"`, `is_active=True`) usando `get_password_hash`.
2. **Proyecto y relación N:M (`project_stations`):** Crea el proyecto `Monitoreo de Fauna - Amazonia 2026` y asocia las 3 estaciones (`CAM-01`, `CAM-02`, `CAM-03`) tanto por `project_id`/`user_id` como mediante filas explícitas en `project_stations` (`ProjectStation`). Si las estaciones ya existen por `station_code`, las reutiliza.
3. **Sincronía `media_files` + `videos` + `species`:** Genera **60 eventos base** + **ráfagas dependientes** (< 30 minutos, 30 % de probabilidad con 1 a 3 clips extra), creando rutas locales `/uploads/videos/...` y poblando simultáneamente `MediaFile`, `Video` y `Species`.
4. **Taxonomía completa en `species`:** Cada detección incluye `family`, `genus`, `scientific_name` y `common_name` (ej. *Felidae* / *Panthera* / *Panthera onca* / *Jaguar*), `confidence_score` de 4 decimales y fechas UTC (`timezone.utc`).

### Ejecución desde PowerShell (inyectando `stdin` al contenedor)

```powershell
# 1. Crear tablas
@'
import asyncio
import app.models
from app.db.session import engine
from app.models.base import Base

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Tablas creadas correctamente en faunadb.")

asyncio.run(init_db())
'@ | docker compose exec -T api python -

# 2. Poblar con seed_db.py
Get-Content .\seed_db.py -Raw | docker compose exec -T api python -

# 3. Verificar conteos reales
@'
import asyncio
from sqlalchemy import text
from app.db.session import engine

async def verify():
    tables = ["users", "projects", "camera_stations", "project_stations", "media_files", "videos", "species"]
    async with engine.connect() as conn:
        for t in tables:
            count = (await conn.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
            print(f"{t}: {count} filas")
    await engine.dispose()

asyncio.run(verify())
'@ | docker compose exec -T api python -
```

Resultado verificado tras corrida limpia:
- `users`: 1 fila (`admin@wwf.org` / `wwf123456`)
- `projects`: 1 fila
- `camera_stations`: 3 filas (`CAM-01`, `CAM-02`, `CAM-03`)
- `project_stations`: 3 filas
- `media_files`: ~87 filas (60 eventos base + ráfagas)
- `videos`: ~87 filas
- `species`: ~87 filas
