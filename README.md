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

`docker compose up -d --build` levanta los **3 procesos del backend**. La IA y PostgreSQL corren aparte:

| Componente | Servicio en `docker-compose.yml` | Puerto | Rol |
| :--- | :--- | :--- | :--- |
| `fauna_api` | `api` | `8000` | API FastAPI (`app.main:app`, con `--reload` en desarrollo). |
| `fauna_worker` | `worker` | — | Worker `arq`: clasifica con la IA, confirma importaciones de escritorio y corre los crons (reaper, limpieza, purga anónima). |
| `fauna_redis` | `redis` | `6379` | Cola de avisos para el worker (la BD es la fuente de verdad). |
| Servicio IA (`../ia-clasificacion-fauna`) | aparte | `8001` | IA real o `ia-fake` con el contrato `1.0.0` (`/api/v1/detect`, `/health`, `/catalog`). |
| PostgreSQL (`faunadb`) | aparte, en el host | `5433` | Base de desarrollo, accesible desde Docker vía `host.docker.internal:5433`. |

```text
Front (:5173) ──▶ api (:8000) ──▶ PostgreSQL host.docker.internal:5433/faunadb
                     │  ▲
                     ▼  │
                  Redis ──▶ worker ──▶ IA (http://host.docker.internal:8001)
```

**Producción:** no hay manifiestos de una plataforma concreta; el cliente la elige al cerrar el proyecto. Cualquiera sirve si corre estos mismos 3 procesos (api, worker y Redis) con las variables de entorno de `.env.example`.

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

## 🗄️ Base de Datos: Migraciones con Alembic

El esquema lo crea **solo Alembic** (`migrations/versions/`). Ya no existen `create_all`, `seed_db.py` ni `seed_massive.py`.

```powershell
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current        # esperado: 0002 (head)
```

- `0001` crea el esquema canónico y **borra las tablas del hackathon** si existen. Antes de aplicarla en una base con datos reales, hacer un respaldo.
- `0002` (aditiva) suma la importación en el worker y la corrección de hora de cámaras.
- Al tocar modelos: `alembic revision --autogenerate`, revisar el archivo y comprobar con `alembic upgrade head`, `alembic downgrade -1` y `alembic check` (sin diferencias).

Los datos de prueba vuelven con `python -m app.cli seed-e2e` (HU-16). Mientras tanto, cada test crea los suyos.

Comandos útiles del CLI (`python -m app.cli <comando>`): `purge-anon`, `reaper`, `cleanup` y `sync-catalog`.

---

## 🚀 Ejecución Local (Sin Docker) y Pruebas

```powershell
# Activar entorno virtual (Windows)
.\app\venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Iniciar la API y, en otra terminal, el worker (necesita Redis en REDIS_URL)
uvicorn app.main:app --reload
arq app.worker.main.WorkerSettings

# Pruebas: TEST_DATABASE_URL debe apuntar a una base descartable (nunca a faunadb)
pytest
ruff check . ; ruff format --check . ; mypy
```

- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check:** [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health) y `/api/v1/health/ready`

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

## 🛡️ Operación: admin, respaldos, semilla E2E y CI

**Cuenta admin (CB-99).** La contraseña llega por variable de entorno o se pide por teclado; nunca va en la línea de comandos ni se imprime:

```bash
WWF_ADMIN_PASSWORD='…' python -m app.cli create-admin --email admin@wwf.org
WWF_ADMIN_PASSWORD='…' python -m app.cli reset-admin-password --email admin@wwf.org  # revoca sus sesiones
```

**Respaldos (FL-32).** Funcionan con cualquier PostgreSQL (Aiven, Docker o local). Las credenciales se pasan como variables `PG*`, no como argumentos:

```bash
DATABASE_URL=… STORAGE_LOCAL_PATH=/data/evidence scripts/backup.sh backups/
RESTORE_DATABASE_URL=postgresql://…/wwf_restore_test scripts/restore_test.sh backups/wwm-AAAAMMDDTHHMMSSZ
```

- `backup.sh` deja `db.dump`, `evidence.tar.gz`, `MANIFEST` (versión de Alembic, filas por tabla y cantidad de fotogramas) y `SHA256SUMS`. Borra los respaldos con más de `BACKUP_KEEP_DAYS` días (14 por defecto).
- `restore_test.sh` restaura en una base **descartable** y compara el resultado con el `MANIFEST`. Se niega a restaurar sobre `DATABASE_URL` o sobre `faunadb`.
- Necesitan `pg_dump`, `pg_restore` y `psql` de la versión 16.
- `backups/` está en `.gitignore`.

**Semilla E2E (DEP-04).** `WWF_E2E_PASSWORD='…' python -m app.cli seed-e2e` carga datos fijos para Playwright:

- un admin (`admin@e2e.example.com`) y dos investigadores (`ana@…` y `beto@…`);
- una cámara pública y una privada, y un proyecto;
- 30 clasificaciones con fotograma.

Es idempotente y no corre en producción.

**CI.** `.github/workflows/ci.yml` corre el mismo gate del DoD en cada PR a `develop` o `main`:

- gitleaks;
- `ruff`;
- `mypy --strict`;
- `pip-audit`;
- `alembic check` con `downgrade base` y `upgrade` de nuevo;
- todos los tests, incluidas la matriz IDOR (`tests/security`) y los contratos (`tests/contracts`);
- un respaldo y una restauración reales.

Las herramientas están en `requirements-dev.txt`. Para comparar los contratos contra el repo de la IA, define en GitHub la variable `IA_REPO` (`owner/ia-clasificacion-fauna`) y, si el repo es privado, el secreto `IA_REPO_TOKEN`.

## 📚 Documentación y Plan de Construcción con Agentes

- [Documentación técnica del proyecto](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/docs/README.md)
- [Esquema de base de datos y seeding](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/docs/base_de_datos/README.md)
- [Backlog Teamwork M0–M4](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/10_Backlog_Teamwork_WWF.md)
- [To-Do List `/teamwork`](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/11_Teamwork_Todolist_WWF.md)
- [Guía de rutina con agentes](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/12_Guia_Rutina_Implementacion_con_Agentes.md)
- [Definition of Done Único](file:///c:/Users/contr/Documents/Repositorios%20de%20Git/INNOVAHACK/BACKWWF/Analisis_Backend_3.0_WWF_2026-11-15/DEFINITION_OF_DONE.md)
