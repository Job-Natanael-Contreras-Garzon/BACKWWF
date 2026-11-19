---
title: "12 - Guía de Rutina: Implementar con Agentes de Código y Aprender (modo junior)"
date: 2026-11-17
project: BACKWWF
version: "1.1.0"
tags: [guia, rutina, agentes, aprendizaje, junior, docker, env, wwf]
---

# 12. Guía de Rutina: implementar paso a paso con agentes y aprender en el camino

> [!NOTE]
> Fuentes: [[10_Backlog_Teamwork_WWF]] (qué construir) · [[11_Teamwork_Todolist_WWF]] (en qué orden y qué archivos toca cada ticket) · [[DEFINITION_OF_DONE]] (cuándo está terminado).

## 0. La idea en una frase

**1 ticket = 1 ciclo corto de 10 pasos.** El agente escribe el código, pero **antes** te explica qué va a hacer, **durante** te cuenta cada paso, y **después** te hace preguntas para comprobar que lo entendiste. Un ticket no se cierra hasta que puedas explicarlo con tus palabras.

Tu rol no es "copiar lo que sale", es **dirigir y revisar**: tú decides el ticket, apruebas el plan, lees el diff y cierras el ticket. El agente es tu compañero senior que programa y enseña.

---

## 1. Preparación e Infraestructura Real en Docker (hazla una sola vez)

### 1.1 Topología real en desarrollo (2 contenedores Docker + PostgreSQL)

En tu entorno local actual corren **2 contenedores Docker** y la base de datos PostgreSQL en el host:

| Componente | Nombre / Imagen | Puerto | Cómo se comunica |
| :--- | :--- | :--- | :--- |
| **API Backend** | `fauna_api` (`fauna-monitoring-api:local`) | `0.0.0.0:8000->8000` | Expone FastAPI con `--reload`. Lee su config de `.env`. |
| **Servicio IA** | `wwf-wildlife-api` (`wwf-wildlife-detection:latest`) | `0.0.0.0:8081->8000` | Desde `fauna_api`: `http://host.docker.internal:8081` (desde host: `http://localhost:8081`). |
| **Base de datos** | PostgreSQL (`faunadb` en tu PC) | `5433` | Desde `fauna_api`: `postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@host.docker.internal:5433/faunadb`. |

> [!TIP]
> **¿Por qué ves `host.docker.internal`?** Porque dentro de un contenedor Docker, `localhost` apunta *al propio contenedor*, no a tu máquina Windows. `host.docker.internal` es el puente especial de Docker Desktop para llegar a PostgreSQL (`5433`) o al otro contenedor expuesto (`8081`).

### 1.2 Cómo funcionan las 2 configuraciones (`development` vs `production`) con Variables de Entorno

Una regla de oro que verás desde el **primer ticket (`BUG-01`)** es que **el código fuente es uno solo, pero tiene 2 configuraciones distintas según el entorno**:

- **No se escriben secretos en el código** (ni contraseñas en `check_db.py`, ni `digitalocean.yaml`, ni claves por defecto en `app/core/config.py`).
- Todo se lee desde **variables de entorno** a través de una única clase `Settings` (`app/core/config.py`):
  - **`ENVIRONMENT=development` (tu Docker local):** usa un archivo `.env` en tu computadora (que **nunca** se sube a Git). Apunta a `faunadb` en `host.docker.internal:5433`, a `wwf-wildlife-api` en `http://host.docker.internal:8081`, usa claves JWT propias de desarrollo (≥ 32 bytes) y permite `http://localhost:5173` / `3000` en CORS.
  - **`ENVIRONMENT=production` (servidor real / PaaS):** las variables se cargan en el panel secreto del servidor (`type: SECRET`). Apunta a PostgreSQL remoto (ej. Aiven con `?ssl=require`) y a la IA de producción con **contraseñas y claves JWT completamente distintas** a las de desarrollo. Si falta una clave, mide < 32 bytes o usa un placeholder, `Settings` aborta el arranque con `CRITICAL config.invalid` y **nunca** abre CORS a `localhost`.

> [!IMPORTANT]
> Por eso **`BUG-01` es obligatorio antes de construir nada**: purga las credenciales heredadas del hackathon y blinda `Settings` para que un agente jamás mezcle ni filtre secretos entre `development` y `production`.

### 1.3 Inicializar y poblar `faunadb` en Docker (PowerShell)

`.dockerignore` excluye `seed_db.py`, `seed_massive.py` y `check_db.py` de la imagen Docker (para mantenerla limpia), pero **sí incluye `migrations/`**. Por eso, en PowerShell enviamos los scripts por entrada estándar (`stdin`) al contenedor `fauna_api`:

```powershell
# 1) Crear las tablas actuales en faunadb
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

# 2) Verificar las 10 tablas en pg_tables
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
# Salida esperada: ['anon_sessions', 'camera_stations', 'individuals', 'media_files', 'project_stations', 'projects', 'reports', 'species', 'users', 'videos']

# 3) Poblar la BD con seed_db.py (crea admin@wwf.org / wwf123456, 1 proyecto, 3 cámaras + N:M y ~87 detecciones en media_files/videos/species)
Get-Content .\seed_db.py -Raw | docker compose exec -T api python -

# 4) Verificar los conteos por tabla
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
# Salida esperada tras corrida limpia: users: 1, projects: 1, camera_stations: 3, project_stations: 3, media_files: 87, videos: 87, species: 87
```

### 1.4 Reglas de trabajo, Skills y Modo Mentor

1. **Entorno real corriendo** (lo exige el DoD §1): `fauna_api` (`:8000`), `wwf-wildlife-api` (`:8081`), PostgreSQL `faunadb` (`:5433`) y Redis (cuando aplique desde `HU-08`). Sin esto, nada se puede dar por "hecho".
2. **Rama de trabajo:** `develop` como base; una rama por ticket (`feat/hu-03-auth`, `fix/bug-01-secretos`).
3. **Skills a mano** (carpeta `.agents/skills` o `Analisis_Backend_3.0_WWF_2026-11-15/skills_compactas`): `wwf-backend-standards`, `wwf-api-contracts`, `wwf-flows-and-edge-cases`, `wwf-dev-workflow` y `ponytail`. Todo agente las carga **antes** de escribir código.
4. **Exclusión de edición:** la carpeta `tareas-job/` es solo referencia normativa; **nunca la edites**.
5. **Cuaderno de aprendizaje:** crea `Bitacora_Aprendizaje.md` (plantilla en §6) y un `Glosario.md` vacío. Aquí vive lo que vas aprendiendo.
6. **Instrucción permanente "modo mentor"** (pégala al iniciar cada sesión con el agente, o guárdala en el archivo de instrucciones del proyecto):

```text
MODO MENTOR (activo en toda la sesión)
Soy desarrollador junior. Trabajamos en BACKWWF (FastAPI + PostgreSQL + Redis/arq en Docker).
Reglas para ti:
1. Antes de tocar código: explícame el objetivo del ticket en lenguaje simple y con una analogía.
2. Trabaja en pasos pequeños. Antes de cada paso dime: QUÉ vas a hacer, POR QUÉ, y QUÉ concepto aplica.
3. Después de cada paso, resume en 2-3 líneas lo que cambió y qué archivo tocaste.
4. Cuando uses un concepto nuevo (ej. UnitOfWork, IDOR, If-Match, idempotencia, Settings por entorno), defínelo en 2 líneas y dame un ejemplo del propio proyecto.
5. No avances al siguiente paso hasta que yo diga "sigue". Si hay dos formas de hacerlo, muéstrame ambas y recomienda una.
6. Al final del ticket hazme 3 preguntas de repaso y corrígeme sin dar la respuesta de inmediato.
7. Respeta DEFINITION_OF_DONE.md, la separación development/production por variables de entorno y el principio Ponytail: mínimo código funcional, sin stubs "para después".
```

---

## 2. Orden de trabajo recomendado (para aprender, no solo para terminar)

El To-Do [[11_Teamwork_Todolist_WWF]] está pensado para `/teamwork` con varios agentes en paralelo. **Como junior, te conviene ir en serie** (un ticket a la vez) al menos hasta terminar M1. Así ves el sistema crecer y no te llegan 3 diffs a la vez que no puedes revisar. Cuando ya domines el ciclo, activa el paralelo en las oleadas marcadas "Paralelizable".

| Etapa | Tickets (en orden) | Qué aprenderás | Revisión |
|---|---|---|---|
| **M0 · Limpieza** | `BUG-01` → `BUG-02` → `BUG-03` | Gestión de secretos, config estricta, IDOR/BOLA, event loop async, errores 500 seguros | Diego (obligatoria) |
| **M0 · Contrato IA** | `SPIKE-01` | Cliente HTTP async (`httpx`), contrato Pydantic, "walking skeleton" | Diego |
| **M0 · Cimientos** | `HU-01` → `HU-02` → `BUG-04` | Capas, `ApiResponse`/`AppError`, logs JSON, `StorageBackend`, ORM, Alembic, UoW | Diego |
| **M1 · Núcleo** | `HU-03` → `HU-05` → `HU-06` → `HU-07` (`HU-04` queda condicional) | JWT y rotación de refresh, sesiones anónimas, privacidad DD-17, bloqueo optimista `If-Match` | `HU-05`, `HU-06`: Diego; resto asíncrona |
| **M2 · Cola** | `HU-08` → `HU-09` | Subida en streaming, SHA-256 y duplicados, Redis/`arq`, cola justa, crons | Asíncrona (CI verde) |
| **M3 · IA real** | `HU-11` → `HU-13` → `HU-12` → `HU-10` → `HU-14` | Workers, evidencia, estadísticas, ráfagas, Zip Slip/Bomb, reportes Excel/PDF | `HU-11`: Diego; resto asíncrona |
| **M4 · Cierre** | `HU-15a` → `HU-16` → `HU-15b` | Roles/admin, matriz IDOR, backups, CI gate | `HU-15a`, `HU-16`: Diego |

Regla de oro del orden: **no empieces un ticket si no están cerradas sus dependencias** (campo `Depende de:` en el To-Do).

---

## 3. La rutina de 10 pasos por ticket

> Tiempo orientativo para un ticket mediano: 2–4 sesiones de 60–90 min. No es una carrera.

### Paso 1 · Elegir y abrir el ticket (5 min)
- Toma el siguiente ticket sin marcar en [[11_Teamwork_Todolist_WWF]] cuyas dependencias estén cerradas.
- Lee tú mismo, **sin agente**, su ficha en [[10_Backlog_Teamwork_WWF]]: Historia, Alcance (incluye / no incluye), Criterios de aceptación y Unidades de trabajo (UT).
- Anota en la bitácora: *"Esto creo que hay que construir: ..."* (2–3 líneas). Servirá para comparar con la explicación del agente.

### Paso 2 · Briefing: que el agente te lo explique (10 min)
Prompt:
```text
Vamos a trabajar el ticket [HU-XX] de 10_Backlog_Teamwork_WWF.md.
Carga primero las skills wwf-backend-standards, wwf-api-contracts, wwf-flows-and-edge-cases, wwf-dev-workflow y ponytail.
Todavía NO escribas código. Explícame:
1. Qué problema resuelve este ticket, con una analogía.
2. Qué conceptos nuevos necesito saber (defínelos corto).
3. Qué archivos toca (campo Scope/Archivos del To-Do) y qué NO debe tocar (recuerda: nunca tocar tareas-job/).
4. Qué variables de entorno usa (¿cambia algo entre development y production?) y confirma que no hay secretos hardcodeados.
5. Qué casos borde (CB-xx) y flujos (FL-xx) aplican y por qué importan.
```
Luego **tú explicas de vuelta** con tus palabras: *"Entonces el ticket hace X para que Y, y lo más peligroso es Z"*. Si el agente corrige algo, eso es aprendizaje: anótalo.

### Paso 3 · Plan por unidades de trabajo (10 min)
Cada ticket ya trae UT (UT-1, UT-2…). Pide el plan sobre eso:
```text
Propón el plan de implementación siguiendo las UT del ticket.
Para cada UT dime: archivos a crear/editar, orden de los pasos, y cómo vamos a probarla.
Marca qué parte es "seguridad/privacidad/integridad" (Nivel 1 de pruebas del DoD, bloquea merge).
No escribas código todavía.
```
Aprueba, recorta o cambia el plan. Si algo te parece demasiado grande, pide dividirlo (Ponytail: cambio mínimo completo).

### Paso 4 · Test primero (rojo) (15–20 min)
El DoD pide que los `BUG` tengan un test que **falla antes y pasa después**, y los de seguridad/privacidad son Nivel 1 (bloquean merge). Por eso empezamos por el test:
```text
UT-1: escribe primero SOLO los tests (los del criterio de aceptación; en BUG, el test nombrado en el ticket).
Explícame qué verifica cada test y por qué debe fallar ahora.
Ejecútalos y muéstrame que fallan por la razón correcta.
```
**Concepto que repasas aquí:** TDD (rojo → verde → refactor), qué es un test de integración vs unitario, `pytest.mark.parametrize` para casos borde similares (Nivel 2).

### Paso 5 · Implementar en pasos pequeños, con explicación (el grueso)
Por cada UT, repite este mini-ciclo:
```text
Implementa solo el paso 1 de la UT-1. Antes: qué vas a hacer y por qué.
Después: resumen de 2-3 líneas y qué concepto aplicaste. Luego espera mi "sigue".
```
Cosas que **debes mirar tú** en cada diff (checklist rápido de lectura):
- ¿Toca solo los archivos del `Scope`? Si toca otros, pregunta por qué.
- ¿Toda credencial, URL o clave viene de `Settings` (variables de entorno) y funciona tanto en `development` como en `production`? Si ves contraseñas, API keys, DSN o `os.getenv` fuera de `app/core/config.py` → rechazar.
- ¿El router es "fino" (ruta + schema + dependencias → 1 servicio)? La lógica va en `services/`, las consultas en `repositories/`, y **solo el servicio hace `commit`**.
- ¿Los errores son `AppError` con código estable (no `HTTPException` suelto)? ¿Las respuestas usan `ApiResponse`?
- ¿Hay `print()`, código comentado, librerías nuevas o stubs "para después"? → rechazar.
- ¿Algún dato sensible (email, token, coordenadas exactas ajenas) puede acabar en logs o respuestas?

Si no entiendes una línea: **detén al agente** con *"explícame esta función línea por línea como si fuera mi primer día"*. Es lo más valioso de todo el flujo.

### Paso 6 · Verificar contra infraestructura real en Docker (15 min)
El DoD §1 es claro: no basta con mocks. Pide al agente que **lo ejecute de verdad** contra los contenedores activos (`fauna_api` `:8000`, servicio IA `ia-clasificacion-fauna` / `ia-fake` en `:8001` —o transitoriamente `wwf-wildlife-api:8081`—, PostgreSQL `faunadb` `:5433`) y te enseñe la evidencia:
```text
Levanta/verifica los contenedores Docker y ejecuta el flujo completo del ticket contra faunadb real (y la IA / ia-fake :8001 o Redis si aplica).
Muéstrame las peticiones (curl o httpx) y las respuestas, y revisa en los logs que salen request_id, flow y step sin datos sensibles.
Si el ticket toca BD: ejecuta dentro de fauna_api:
  docker compose exec -T api alembic upgrade head
  docker compose exec -T api alembic downgrade base
  docker compose exec -T api alembic upgrade head
```
Mira tú mismo una respuesta real: ¿viene en la envoltura `{status, data, message, error, meta}`? ¿El error trae un código estable?

### Paso 7 · Quality gate (5 min)
Estos son los comandos del DoD §3 (puedes correrlos en local o dentro del contenedor con `docker compose exec -T api <comando>`). Pide que los ejecute y te explique cualquier fallo:
```bash
ruff check .
ruff format --check .
mypy app/core app/services      # estricto en core/ y services/
pytest --cov=app                # services/ >= 80%, global >= 70%
pip-audit                       # sin vulnerabilidades altas
# Alternativa dentro de Docker:
docker compose exec -T api pytest --cov=app
```
Si algo falla, **pide que te explique el error antes de arreglarlo**. Cada error de `mypy` es una mini-lección de tipos.

### Paso 8 · Auto-revisión y lectura del diff (10–15 min)
```text
Ejecuta /ponytail-review sobre el diff completo.
Luego revisa tu propio trabajo contra DEFINITION_OF_DONE.md punto por punto y dime qué casilla NO puedes marcar todavía y por qué.
```
Después **tú lees el diff completo una vez**, de arriba abajo. Comprueba la regla: *"¿podría explicárselo a Diego en 2 minutos?"*

### Paso 9 · PR, aviso y revisión (10 min)
- Abre el PR con `PLANTILLA_PR.md` completada. Si hubo casos de Nivel 3, anota `verificado a mano: ver CB-xx`.
- **Si el ticket dice `Desbloquea Front`:** avisa a **Miguel al abrir el PR**, no al cerrarlo (así integra en paralelo contra el contrato).
- **Si la revisión es "Obligatoria: Diego"** (`BUG-01..04`, `SPIKE-01`, `HU-01`, `HU-02`, `HU-05`, `HU-06`, `HU-11`, `HU-15a`, `HU-16`): espera su aprobación. Si no, con CI verde se fusiona (*squash merge*) y Diego revisa después.
- Los comentarios de revisión también son material de aprendizaje: pídele al agente *"explícame por qué Diego tiene razón en este comentario"*.

### Paso 10 · Cierre de aprendizaje (10 min, no te lo saltes)
```text
Cerramos el ticket [HU-XX]. Hazme 3 preguntas de repaso sobre lo que implementamos (una de concepto, una de seguridad/riesgo, una de "qué pasaría si...").
Espera mi respuesta a cada una y corrígeme sin darme la solución antes de que lo intente.
Luego dame: (a) 5 términos nuevos para mi Glosario con definición corta, (b) un error típico que un junior comete en este tema, (c) qué debería repasar mañana.
```
Marca `[x]` en [[11_Teamwork_Todolist_WWF]], completa la bitácora (§6) y copia los términos al Glosario.

---

## 4. Conceptos clave por ticket (tu mapa de repaso)

| Ticket | Conceptos que debes dominar al cerrarlo | Pregunta de autoevaluación |
|---|---|---|
| `BUG-01` | Secretos en variables de entorno (`development` `.env` con `host.docker.internal` vs `production` en PaaS `type: SECRET`), `pydantic-settings`, fallar al arrancar, `gitleaks`, purga en `check_db.py`/`digitalocean.yaml` | ¿Por qué desarrollo y producción usan la misma clase `Settings` pero credenciales distintas, y por qué no basta borrar el secreto del último commit? |
| `BUG-02` | BOLA/IDOR, autorización por dueño, retirar superficie de ataque | ¿Cómo prueba un test que A no puede tocar lo de B? |
| `BUG-03` | Event loop, `async` vs bloqueante, I/O en chunks, no filtrar `str(exc)` | ¿Qué le pasa a todos los usuarios si una corrutina se bloquea? |
| `SPIKE-01` | `httpx.AsyncClient`, timeouts, contrato Pydantic, walking skeleton | ¿Por qué validar el contrato real antes de construir la cola? |
| `HU-01` | Capas, `ApiResponse`, `AppError`, middleware, contextvars, protocolo `StorageBackend` | ¿Qué gano con un `Protocol` en vez de una clase concreta? |
| `HU-02` | ORM, migraciones, índices únicos parciales, `UnitOfWork`, `commit` solo en servicio | ¿Por qué un repositorio nunca hace `commit`? |
| `BUG-04` | Eliminar mocks silenciosos, traducir fallos externos a `AI_TIMEOUT`/`AI_UNAVAILABLE` | ¿Por qué un mock que devuelve "jaguar" es peor que un error? |
| `HU-03` | JWT, refresh token rotatorio, detección de reuso, rate limit, hash de passwords | ¿Qué hacemos si llega un refresh token ya usado? |
| `HU-05` | Token anónimo guardado como hash, transacción atómica, idempotencia, cron | ¿Qué significa que `claim` sea idempotente? |
| `HU-06` | Privacidad DD-17 (coordenadas aproximadas), `If-Match`/`409`, borrado lógico | ¿Qué devuelve el sistema si Luis pide la cámara privada de Ana y por qué? |
| `HU-07` | Relación N:M, validar propiedad antes de asociar, filtros de privacidad | ¿Por qué `CAMERA_NOT_OWNED` es 403 y no 404? |
| `HU-08` | Streaming de subida, `python-magic`, SHA-256, cola justa con Redis/`arq` | ¿Cómo evitamos que un usuario sature la cola? |
| `HU-09` | Polling con `?since=`, cancelación, reintentos, *reaper* | ¿Qué trabajo huérfano limpia el reaper y por qué? |
| `HU-11` | Worker `arq`, reintentos, limpieza en `finally`, entrega protegida de evidencia | ¿Por qué se borra el temporal en `finally`? |
| `HU-12`/`13`/`14` | Agregaciones SQL, validación humana, ráfagas, escape de fórmulas Excel | ¿Qué es la inyección de fórmulas en Excel? |
| `HU-10` | Zip Slip, Zip Bomb, checksum, importación en job | ¿Cómo se explota un Zip Slip? |
| `HU-15a`/`16` | Roles, auditoría, matriz IDOR, backup/restore, CI como compuerta | ¿Qué prueba una matriz IDOR que un test suelto no? |

---

## 5. Rutina diaria y semanal

**Sesión diaria (≈ 90 min):**
1. *(5 min)* Repaso relámpago: pide al agente 2 preguntas sobre lo que cerraste ayer.
2. *(60–70 min)* Avanza pasos 4–7 del ticket en curso.
3. *(10–15 min)* Pasos 8–10: revisión, PR y bitácora, aunque el ticket no esté terminado (anota en qué paso quedaste y qué sigue).

**Fin de semana o viernes (≈ 45 min):**
- Relee la bitácora de la semana y reescribe 3 conceptos **sin mirar**.
- Pide al agente un mini examen de 10 preguntas mezcladas de los tickets cerrados.
- Elige el concepto que peor te salió y pide un ejercicio práctico pequeño (no solo teoría).

**Antes de abrir un PR:** si no puedes explicar en voz alta qué hace cada archivo que cambió, no abras el PR todavía.

---

## 6. Plantilla de bitácora (copia y pega por ticket)

```markdown
## [HU-XX] Título — fecha
**Mi idea inicial:** (lo que creí que había que hacer antes del briefing)
**Lo que realmente hace:** (con mis palabras, 3-4 líneas)
**Conceptos nuevos:** (término → definición corta)
**Decisiones y por qué:** (ej. "usamos Protocol y no S3 porque Ponytail/YAGNI")
**Error que cometí o que el agente corrigió:**
**Comandos que corrí y su resultado:** ruff / mypy / pytest / pip-audit / alembic
**Preguntas de repaso (y mi respuesta):**
**Para repasar mañana:**
```

---

## 7. Cuándo (y cómo) pasar a `/teamwork` en paralelo

Cuando hayas cerrado al menos un ticket completo por el ciclo de 10 pasos y te sientas cómodo leyendo diffs:

1. Usa solo las oleadas marcadas **Paralelizable** (0B, 1B, 1D, 3C, 4B). Cada ticket posee archivos disjuntos, por eso no se pisan.
2. Mantén el modo mentor: pide que **cada agente deje un resumen de 5 líneas** (qué hizo, qué concepto aplicó, qué riesgo vio) en la descripción del PR.
3. Revisa los PR **uno por uno**, no en bloque. Si tu capacidad de revisión es el cuello de botella, baja a 2 agentes.
4. Prompt base (el del To-Do) con una línea extra de aprendizaje:

```text
/teamwork Toma las tareas pendientes de la siguiente oleada en 11_Teamwork_Todolist_WWF.md.
Respeta el Scope/Archivos de cada ticket y NO edites ni crees archivos en tareas-job/.
Cada agente carga las skills wwf-* y ponytail, respeta la separación development/production por variables de entorno en Settings, y cumple DEFINITION_OF_DONE.md.
Cada agente debe dejar en su PR un "Resumen para aprender": qué hizo, qué conceptos aplicó (definidos en 2 líneas) y qué riesgos vio.
Marca [x] en el To-Do y ejecuta /ponytail-review al terminar cada ticket.
```

---

## 8. Reglas para no perderte (anti-trampas)

- **No aceptes código que no puedas explicar.** Pregunta hasta entenderlo, o pide una versión más simple.
- **Un ticket a la vez** hasta dominar el ciclo. El paralelo viene después.
- **Nunca marques `[x]` sin evidencia** (comandos ejecutados, respuestas reales en Docker, CI verde).
- **Mocks no cuentan como terminado:** el DoD exige PostgreSQL (`faunadb`) / `ia-clasificacion-fauna` o `ia-fake` (`:8001`, legado `:8081`) / Redis reales.
- **Cero secretos en código o manifiestos:** todo lo sensible va en variables de entorno (`.env` local para `development` y secretos del servidor para `production`), nunca hardcodeado.
- **Carpeta `tareas-job/` intocable:** es solo lectura de referencia; ningún agente debe editarla.
- **Si el agente inventa algo fuera del contrato**, vuelve a las skills (`wwf-api-contracts`, `wwf-flows-and-edge-cases`) y pide que cite de dónde sale cada endpoint o error.
- **Seguridad primero:** en `BUG-*`, `HU-05`, `HU-06`, `HU-11`, `HU-16` baja el ritmo y revisa doble; son los que Diego revisa por una razón.
- **Duda de negocio** (ej. si `HU-04` entra en la fecha del demo): no la resuelvas con el agente, pregúntala a Diego/WWF.

---

## 9. Checklist de cierre de ticket (imprímelo mentalmente)

- [ ] Corre contra PostgreSQL (y Redis / IA) reales, con evidencia
- [ ] Tests de Nivel 1 pasan; bugs con test rojo→verde
- [ ] `ruff check`, `ruff format --check`, `mypy`, `pytest`, `pip-audit` en verde
- [ ] `.env.example` y migración Alembic (`upgrade` + `downgrade`) al día si aplica
- [ ] `/ponytail-review` hecho y diff leído por mí
- [ ] PR con `PLANTILLA_PR.md`; Miguel avisado al abrir (si desbloquea Front); Diego aprobó (si es obligatoria)
- [ ] Bitácora + glosario actualizados; respondí las 3 preguntas de repaso
- [ ] Casilla `[x]` en [[11_Teamwork_Todolist_WWF]]
