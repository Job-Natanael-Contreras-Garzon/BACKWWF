# Backend - Sistema de Monitoreo de Fauna (Cámaras Trampa e IA)

API RESTful asíncrona desarrollada con **FastAPI** para la gestión de proyectos de monitoreo de fauna silvestre, estaciones de cámaras trampa, ingesta multimedia y procesamiento con Inteligencia Artificial.

---

## 🛠 Stack Tecnológico

- **Framework Core:** [FastAPI](https://fastapi.tiangolo.com/) (servidor ASGI Uvicorn).
- **ORM y Base de Datos:** [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/) asíncrono + PostgreSQL (`asyncpg`).
- **Migraciones:** Alembic (configuración asíncrona en `migrations/env.py`).
- **Validación y Configuración:** [Pydantic V2](https://docs.pydantic.dev/latest/) + `pydantic-settings`.
- **Procesamiento Multimedia:** `ffmpeg` / `ffprobe` (incluido en `Dockerfile`).
- **Documentación Interactiva:** Swagger UI (`/docs`) y ReDoc (`/redoc`).

---

## 🐳 Arquitectura en Modo Desarrollo (Docker)

En el entorno local de desarrollo operan **2 contenedores Docker** conectados a PostgreSQL en el host:

| Componente / Contenedor | Imagen / Servicio | Puerto | Rol |
| :--- | :--- | :--- | :--- |
| `fauna_api` (`api` en `docker-compose.yml`) | `fauna-monitoring-api:local` | `0.0.0.0:8000->8000` | API FastAPI con `--reload` (`app.main:app`). |
| Servicio IA objetivo (`../ia-clasificacion-fauna`) | `ia` (`api/`) o `ia-fake` (`fake/`) | `0.0.0.0:8001->8001` | Microservicio IA real / simulado alineado al contrato v2 (`POST /api/v1/detect`, `/health`, `/catalog`). |
| `wwf-wildlife-api` *(legado transitorio)* | `wwf-wildlife-detection:latest` | `0.0.0.0:8081->8000` | Contenedor previo aún activo mientras se migra el cliente hacia `:8001`. |
| PostgreSQL (`faunadb`) | Servicio PostgreSQL del host | `5433` | Base de datos de desarrollo accesible desde Docker vía `host.docker.internal:5433`. |

```text
Host / Frontend (:5173, :3000) ──▶ fauna_api (:8000) ──▶ PostgreSQL host.docker.internal:5433/faunadb
                                          │
                                          └──▶ ia / ia-fake (http://host.docker.internal:8001 o http://ia:8001)
```

> **Nota sobre `.dockerignore`:** La imagen Docker excluye `seed_db.py`, `seed_massive.py` y `check_db.py` para mantener liviano el contenedor, pero **sí incluye `migrations/`** para poder ejecutar migraciones dentro del contenedor.

---

## 🔐 Variables de Entorno: Desarrollo vs Producción

Toda la configuración sensible se inyecta exclusivamente por **variables de entorno** (`.env` en desarrollo local, nunca versionado en Git; secretos encriptados del PaaS en producción). Nunca se deben escribir credenciales, URLs privadas ni claves JWT en texto plano dentro del código fuente, scripts o manifiestos (`docker-compose.yml`, `check_db.py`).

Ambos entornos comparten la misma estructura en `Settings` (`app/core/config.py`), pero mantienen **credenciales, hosts y políticas independientes**:

| Variable | `ENVIRONMENT=development` (Local / Docker) | `ENVIRONMENT=production` (Servidor / PaaS) |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@host.docker.internal:5433/faunadb` | `postgresql+asyncpg://<PROD_USER>:<PROD_PASSWORD>@<PROD_HOST>:<PORT>/<PROD_DB>?ssl=require` |
| `AI_SERVICE_URL` | `http://host.docker.internal:8001` (`../ia-clasificacion-fauna` o `ia-fake`; legado transitorio `:8081`) | URL interna o privada del servicio de IA productivo (`http://ia:8001`) |
| `AI_API_KEY` | `dev-key` (aceptada por `ia-clasificacion-fauna` en dev) | Clave secreta exclusiva de producción (obligatoria) |
| `SECRET_KEY` / `REFRESH_SECRET_KEY` | Claves distintas de desarrollo (≥ 32 bytes) en `.env` | Claves criptográficas únicas de producción (≥ 32 bytes), distintas a las de dev |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Dominio real del frontend productivo (sin `localhost`) |

Consulta [.env.example](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/.env.example) como plantilla base (usa siempre placeholders, jamás secretos reales).

---

## 🗄️ Inicialización y Poblado de Base de Datos en Docker (PowerShell)

Como `seed_db.py` está excluido de la imagen en `.dockerignore`, las tareas de inicialización, inspección y poblado se ejecutan inyectando el script por entrada estándar (`stdin`) hacia el contenedor `fauna_api` (`docker compose exec -T api python -`):

### 1. Crear las tablas en `faunadb`

```powershell
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
```

### 2. Verificar las tablas creadas en `pg_tables`

```powershell
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
```

Salida esperada (10 tablas):
```text
['anon_sessions', 'camera_stations', 'individuals', 'media_files', 'project_stations', 'projects', 'reports', 'species', 'users', 'videos']
```

### 3. Ejecutar el seeder actualizado (`seed_db.py`)

```powershell
Get-Content .\seed_db.py -Raw | docker compose exec -T api python -
```

**Qué genera `seed_db.py`:**
- Crea o recupera el usuario de prueba `admin@wwf.org` / `wwf123456` (`Dr. Jane Goodall`, contraseña hasheada con `bcrypt`, `is_active=True`).
- Crea el proyecto público `Monitoreo de Fauna - Amazonia 2026`.
- Crea o reutiliza 3 estaciones de cámaras trampa (`CAM-01`, `CAM-02`, `CAM-03`) asignadas al usuario y las vincula en la tabla intermedia N:M `project_stations`.
- Genera **60 eventos base + ráfagas dependientes (< 30 min)** (aprox. **87 registros** en total), poblando sincronizadamente `media_files`, `videos` y `species` con taxonomía completa (`family`, `genus`, `scientific_name`, `common_name`).

### 4. Verificar el conteo de filas por tabla

```powershell
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

Salida de referencia tras una corrida limpia:
```text
users: 1 filas
projects: 1 filas
camera_stations: 3 filas
project_stations: 3 filas
media_files: 87 filas
videos: 87 filas
species: 87 filas
```

---

## 🚀 Ejecución Local (Sin Docker) y Pruebas

```powershell
# Activar entorno virtual (Windows)
.\app\venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Iniciar servidor de desarrollo
uvicorn app.main:app --reload

# Ejecutar pruebas automatizadas
pytest
```

- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 🎨 Reportes: diseño de WWF

Los reportes Excel y PDF (`GET /api/v1/reports/excel|pdf`, HU-14) se arman con `openpyxl` y `reportlab`. Los números salen de `app/services/stats_service.py`, así que cambiar el diseño nunca cambia los datos.

**Todo el diseño del PDF vive en un solo archivo: `app/reports/brand.py`.** Para aplicar la identidad de WWF:

1. **Logo:** copiar el archivo a `app/reports/assets/wwf_logo.png` (PNG o JPG, fondo transparente si es posible). Se dibuja arriba a la izquierda de la portada con el ancho de `logo_width_cm` (4 cm por defecto). Si el archivo no está, la portada sale sin logo.
2. **Colores:** cambiar `primary` (barras y línea de los encabezados), `primary_light` (fondo de los encabezados de tabla), `text` y `muted` (texto secundario y pie). Van en hex, por ejemplo `"#000000"`.
3. **Tipografía:** por defecto se usa Helvetica, que no necesita archivos. Para usar la de WWF:
   - copiar los `.ttf` a `app/reports/assets/`;
   - declararlos en `font_files`, por ejemplo `(("WWFSans", "WWFSans-Regular.ttf"), ("WWFSans-Bold", "WWFSans-Bold.ttf"))`;
   - poner `font="WWFSans"` y `font_bold="WWFSans-Bold"`.
4. **Textos fijos:** `title` (título de la portada) y `organization` (por ejemplo "WWF Bolivia", que aparece en el pie de cada página).

La estructura (qué secciones hay y en qué orden) está en `app/reports/pdf.py`. El Excel no tiene logo: sus hojas y columnas las fija el contrato §11 (`app/services/report_service.py`).

Para revisar el resultado:

```bash
pytest tests/test_hu14_reports.py   # verifica estructura, pie y request_id
```

Después, descargar un PDF real desde `/api/v1/reports/pdf?camera_station_id=…`.

**Licencias:** `reportlab` es BSD y `openpyxl` es MIT. El logo y las fuentes de WWF tienen sus propias condiciones de uso: hay que confirmar con WWF que pueden versionarse en el repositorio. Si no pueden, dejarlos fuera de Git y montarlos en `app/reports/assets/` al desplegar.

## 📚 Documentación y Plan de Construcción con Agentes

- [Documentación técnica del proyecto](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/docs/README.md)
- [Esquema de base de datos y seeding](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/docs/base_de_datos/README.md)
- [Backlog Teamwork M0–M4](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/10_Backlog_Teamwork_WWF.md)
- [To-Do List `/teamwork`](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/11_Teamwork_Todolist_WWF.md)
- [Guía de rutina con agentes](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/12_Guia_Rutina_Implementacion_con_Agentes.md)
- [Definition of Done Único](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/DEFINITION_OF_DONE.md)
