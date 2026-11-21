# Guía de desarrollo: cómo se implementa cada tarea

> Documento interno · CETERIS404 · v1 — 08/11/2026
> **Obligatoria para los tres** (Diego, Job, Miguel). Define **un único flujo** para llevar una tarea del plan a producción: especificarla como historia de usuario, descomponerla en unidades de trabajo, probarla e integrarla. También fija los estándares de código, los patrones, las prácticas de seguridad y los criterios de revisión.
> **Complementa a:** [ESTANDARES_BACKEND_IA.md](ESTANDARES_BACKEND_IA.md), que define la arquitectura, el formato de respuesta, los errores y los logs. Aquí no se repite: se enlaza.
> **Plantillas listas para copiar:** [plantillas/](plantillas/) (historia de usuario, PR, bug).

---

## Índice

1. [El ciclo de una tarea](#1-el-ciclo-de-una-tarea)
2. [Paso 1 · Especificar la tarea como historia de usuario](#2-paso-1--especificar-la-tarea-como-historia-de-usuario)
3. [Paso 2 · Descomponer en unidades de trabajo](#3-paso-2--descomponer-en-unidades-de-trabajo)
4. [Paso 3 · Pruebas: qué, cómo y cuánto](#4-paso-3--pruebas-qué-cómo-y-cuánto)
5. [Paso 4 · Implementar: principios de clean code](#5-paso-4--implementar-principios-de-clean-code)
6. [Estándares y patrones del backend y la IA (Python)](#6-estándares-y-patrones-del-backend-y-la-ia-python)
7. [Estándares y patrones del frontend (React)](#7-estándares-y-patrones-del-frontend-react)
8. [Seguridad: reglas de codificación](#8-seguridad-reglas-de-codificación)
9. [Paso 5 · Git, PR y revisión](#9-paso-5--git-pr-y-revisión)
10. [Definición de listo (DoR) y de terminado (DoD)](#10-definición-de-listo-dor-y-de-terminado-dod)
11. [Ejemplo completo: de la tarea al PR](#11-ejemplo-completo-de-la-tarea-al-pr)

---

## 1. El ciclo de una tarea

```
 ┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────┐   ┌──────────────┐
 │ 1. Especif. │──▶│ 2. Revisión  │──▶│ 3. Unidades  │──▶│ 4. Tests  │──▶│ 5. Implemen- │
 │   HU (spec) │   │   (DoR)      │   │   de trabajo │   │  primero  │   │    tación    │
 └─────────────┘   └──────────────┘   └──────────────┘   └───────────┘   └──────┬───────┘
                                                                                 │
 ┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────┐           │
 │ 10. Cierre  │◀──│ 9. Verific.  │◀──│ 8. Merge a   │◀──│ 7. Review │◀──── 6. PR ┘
 │   (DoD)     │   │  en el hito  │   │   develop    │   │ + CI      │
 └─────────────┘   └──────────────┘   └──────────────┘   └───────────┘
```

| Paso | Qué se hace | Quién | Resultado | Tiempo orientativo |
|---|---|---|---|---|
| 1 | Escribir la HU a partir de la tarea del plan (§2) | El dueño de la tarea | `docs/specs/HU-<ID>.md` en el repo | 30–60 min |
| 2 | Revisar la HU contra el contrato y los flujos; aprobarla | Diego (y la contraparte, si toca su contrato) | Comentario "Aprobada" en el PR de la spec, o un ✅ en el canal | < 1 día |
| 3 | Partir la HU en unidades de trabajo (§3) | El dueño | La lista de UT en la misma HU | 15–30 min |
| 4 | Escribir los tests de los criterios de aceptación **antes** o **junto** con el código (§4) | El dueño | Tests en rojo que describen la HU | — |
| 5 | Implementar unidad por unidad, siguiendo §5–§8 | El dueño | Commits pequeños, uno o más por UT | — |
| 6 | Abrir el PR con la plantilla | El dueño | PR enlazado a la HU | — |
| 7 | CI en verde + revisión de código (§9) | El revisor | Aprobación | < 1 día hábil |
| 8 | *Squash merge* a `develop` | El dueño | — | — |
| 9 | Probar el flujo en el hito semanal (H1–H6, [DEPENDENCIAS](tareas/DEPENDENCIAS.md#2-hitos-de-integración)) | El equipo | Flujo verificado de punta a punta | — |
| 10 | Marcar la HU como terminada (DoD, §10) | El dueño | Estado `Terminada` en la HU | — |

**Reglas:**
- **No se escribe código de producción sin una HU aprobada.** Las excepciones son los *hotfix* de seguridad (por ejemplo BE-51), que se especifican después, el mismo día.
- **Una tarea del plan = una HU**, salvo que sea grande (más de 3 días): entonces se parte en varias HU (`HU-BE-13a`, `HU-BE-13b`), cada una entregable por sí sola.
- Si al implementar se descubre que el contrato está mal o incompleto, **se detiene**, se corrige el contrato (con la aprobación de Diego), se avisa a la contraparte y luego se sigue.

---

## 2. Paso 1 · Especificar la tarea como historia de usuario

### 2.1 Dónde vive
- En **cada repo**, en `docs/specs/HU-<ID-de-la-tarea>-<slug>.md` (por ejemplo `BACKWWF/docs/specs/HU-BE-13-subida-por-archivo.md`).
- Se versiona con el código: la HU se sube en el **primer PR** de la tarea (o en un PR de solo spec si se quiere aprobar antes).
- El estado se lleva en la cabecera de la HU: `Borrador → Aprobada → En curso → En revisión → Terminada`.

### 2.2 Formato
Plantilla completa: [plantillas/PLANTILLA_HU.md](plantillas/PLANTILLA_HU.md). Las partes obligatorias son:

| Sección | Contenido | Ejemplo |
|---|---|---|
| **Historia** | `Como <rol>, quiero <acción>, para <beneficio>`. El rol es un actor real (investigador, visitante anónimo, admin, investigador de campo) o, en las historias técnicas, "el equipo" o "el sistema". | *Como investigador, quiero subir 20 videos y seguir navegando, para no perder tiempo esperando el análisis.* |
| **Origen** | El ID de la tarea del plan, los flujos (FL/FD), los casos borde (CB) y las secciones del contrato | BE-13 · FL-08 · FD F1 · CB-30…36 · API §7 |
| **Alcance** | Qué entra y, **explícitamente, qué no** | "No incluye el worker (BE-61)" |
| **Dependencias** | ⛔ Lo que necesita, 🔁 el sustituto y ➡️ qué desbloquea (copiado de la tarea y ajustado) | ⛔ BE-60 · 🔁 `ia-fake` · ➡️ FE-15 |
| **Criterios de aceptación** | En **Gherkin** (`Dado / Cuando / Entonces`), numerados como `CA-1`, `CA-2`… Se parte de los criterios de la tarea y se agregan los que surjan. **Cada CA se convierte en al menos un test.** | Ver §2.3 |
| **Diseño técnico** | Los archivos o módulos que se crean o tocan, las firmas de las funciones principales, los cambios en la BD y las variables de entorno | `UploadService.accept_file(owner, batch_id, upload) -> BatchItem` |
| **Unidades de trabajo** | La lista de UT (§3) | UT-1 … UT-6 |
| **Plan de pruebas** | La tabla CA → test (unitario, integración, e2e), con el nombre del test | `CA-3 → test_upload_rejects_duration_over_limit` |
| **Riesgos y preguntas** | Lo que no está claro, con un responsable de resolverlo | "¿Límite del proxy de 240 s? → Diego" |

### 2.3 Cómo escribir buenos criterios de aceptación
- **Uno por comportamiento**, observable desde afuera (respuesta HTTP, pantalla, fila en la BD, archivo, log).
- **Con datos concretos**: no "un video largo", sino "un video de 16 s".
- **Cubren:**
  - el **camino feliz**;
  - **cada error** del contrato para ese endpoint o pantalla;
  - los **casos borde** CB-xx asignados;
  - **permisos** (dueño, otro usuario, anónimo, admin);
  - lo **no funcional** que aplique (tiempo, memoria, sin datos sensibles en los logs).
- Formato:
```gherkin
CA-3 · Video que supera 15 s (truncamiento F1-D10)
  Dado ana, dueña de CAM01, con un lote abierto
  Cuando sube "largo.mp4" de 16,2 s
  Entonces la respuesta es 202 (entra a cola)
    Y al completar, el resultado incluye warning VIDEO_TRUNCATED (truncated_at_seconds = 15.0)
    Y no queda ningún archivo temporal en TMP_UPLOAD_PATH
```

### 2.4 Historias técnicas
Las tareas STD-xx, BE-60, IA-22 y similares también se escriben como HU: `Como equipo de desarrollo, quiero <x>, para <y>`. Sus criterios son verificables igual (por ejemplo: "`grep … ` → 0", "el CI falla si…").

### 2.5 Criterios para aprobar una HU (los revisa Diego)
- [ ] Todos los endpoints, campos y códigos que menciona existen en el contrato, con el mismo nombre.
- [ ] Están todos los CB-xx asignados a la tarea.
- [ ] Cada CA es verificable y tiene su test en el plan de pruebas.
- [ ] Las dependencias están claras, con su sustituto.
- [ ] El "fuera de alcance" está escrito.

---

## 3. Paso 2 · Descomponer en unidades de trabajo

Una **unidad de trabajo (UT)** es el paso mínimo que deja el código **compilando y con tests en verde**.

| Regla | Valor |
|---|---|
| Tamaño | De **2 a 6 horas**. Si es más grande, se parte. |
| Cambio | Idealmente ≤ 300 líneas (sin contar los tests). |
| Tests | Cada UT incluye **sus** tests. No hay una UT de "escribir los tests al final". |
| Commit | Uno o más commits por UT, con el ID: `feat(upload): validar duración del video [BE-13/UT-3]`. |
| Orden | De adentro hacia afuera: modelo → repositorio → servicio → endpoint → (front) servicio → store → componente → pantalla. |
| Nombre | `UT-<n>` dentro de la HU, con su descripción, los CA que cubre y una estimación en horas. |

**Tipos de UT habituales:**

| Back / IA | Front |
|---|---|
| Migración + modelo | Tipos y servicio (`services/xxx.js`) con MSW del contrato |
| Schema Pydantic (entrada y salida) | Hook de datos (`useXxx`) |
| Repositorio + tests de consultas | Store (si hay estado de cliente) |
| Servicio (caso de uso) + tests unitarios | Componente de presentación + test |
| Endpoint (router) + tests de integración | Contenedor o pantalla + test |
| Integración externa (IA, storage, email, cola) + tests con *fakes* | Conexión con el back real + prueba e2e |
| Job o *worker* + tests | Mensajes de error y estados vacíos |

**Ejemplo de lista de UT** (en la HU):
```
| UT | Descripción | CA | Estimación |
|----|-------------|----|-----------|
| UT-1 | Migración: classification_batches + columnas queue en classifications | — | 3 h |
| UT-2 | MediaValidator (extensión, firma, tamaño en streaming, ffprobe) + unit tests | CA-3, CA-4 | 5 h |
| UT-3 | UploadService.accept_file (temporal + sha256 + duplicados + fila queued) | CA-2, CA-5 | 6 h |
| UT-4 | Endpoints POST /classification-batches y /files + integración | CA-1, CA-2 | 4 h |
| UT-5 | GET ?active / ?since + cancel / retry | CA-9…13 | 5 h |
| UT-6 | Límites QUEUE_* y Redis caído | CA-6…8 | 3 h |
```

---

## 4. Paso 3 · Pruebas: qué, cómo y cuánto

### 4.1 Pirámide

```
          ▲  E2E (Playwright): un recorrido por flujo FD marcado (e2e)       ~30 escenarios
         ▲▲  Integración: API + Postgres + Redis + ia-fake                   ~1 por CA del back
       ▲▲▲▲  Unitarios: servicios, validadores, utilidades, hooks, componentes   la mayoría
```

### 4.2 Qué prueba cada nivel

| Nivel | Back / IA | Front | Herramientas |
|---|---|---|---|
| **Unitario** | Servicios con repositorios y adaptadores **falsos** (la IA, el storage, la cola, el email); validadores; cálculos de stats; el pipeline de la IA con frames sintéticos | Utilidades (`formatTimestamp`, `errorMessages`), hooks, stores, componentes aislados | `pytest`, `pytest-asyncio` · `vitest`, `@testing-library/react` |
| **Integración** | El endpoint real contra Postgres y Redis reales (contenedores de test) y `ia-fake`; verifica el HTTP, la envoltura, la BD y los logs | La pantalla completa con **MSW** sirviendo los JSON del contrato | `httpx.AsyncClient` + `testcontainers` (o el servicio en CI) · `vitest` + `msw` |
| **Contrato** | El schema del back es igual al de la IA (`contract.py`, `package.py`); el OpenAPI es igual a API §15 | Los mocks de MSW validan contra los ejemplos del contrato | Test de igualdad de schemas |
| **E2E** | — | El navegador real contra el stack completo (`docker-compose.dev.yml` con `ia-fake`): los criterios **(e2e)** de TAREAS_FRONTEND | **Playwright** |
| **Precisión (IA)** | `eval.py` sobre el set etiquetado | — | IA-10 / IA-17 |

### 4.3 Reglas
- **Nombres:** `test_<comportamiento>` en inglés y en *snake_case* (`test_upload_rejects_duration_over_limit`); en el front, `it('rechaza videos de más de 15 s')`. Cada test lleva **el ID del CA** en un comentario o *docstring*: `"""BE-13 CA-3"""`.
- **Estructura Arrange / Act / Assert**, un comportamiento por test.
- **Datos:** *factories* (`tests/factories.py`, `src/test/factories.js`) con los personajes comunes (`ana`, `luis`, `admin`, `anon1`, `CAM01`, `CAM02`, `QN-A`, `P1`). Nada de depender de datos que dejó otro test.
- **Qué se simula y qué no:**
  - unitario: todo lo externo (IA, storage, cola, email, reloj);
  - integración: **no** se simulan la BD ni Redis, sí la IA (`ia-fake`) y el email (`console`).
- **El tiempo** se controla con un reloj inyectable (`Clock` en el back, `vi.useFakeTimers` en el front). Prohibido `sleep` en los tests, salvo en e2e con espera por condición.
- **Cobertura mínima:**
  - back: `services/` ≥ 80 %, total ≥ 70 %;
  - IA: `wwm_pipeline` ≥ 70 %;
  - front: `utils`, `hooks` y `stores` ≥ 70 %; los componentes, por los CA.

  La cobertura no sustituye a los CA: un CA sin test = HU no terminada.
- **Tests inestables (*flaky*):** se arreglan o se marcan `skip` con un *issue* en menos de 24 h. Nunca se reintentan en silencio.
- **Bugs:** todo bug corregido trae un test que fallaba antes del arreglo.

### 4.4 E2E (Playwright)
- La carpeta es `Front-WWF/e2e/` y hay **un archivo por bloque** de FD (`b-anonimo.spec.ts`, `f-subida.spec.ts`…).
- Corre contra `docker compose -f docker-compose.dev.yml up` con `ia-fake` y datos semilla (`make seed-e2e`, que lo provee Job).
- Archivos de prueba en `e2e/fixtures/media/`, nombrados según las reglas de `ia-fake` (`jaguar.mp4`, `vacio_blank.jpg`, `lento_slow.mp4`…).
- Corre en CI sobre `develop` cada noche y antes de cada hito. En el hito H6 corre también como *smoke* contra producción, con una cuenta de prueba.

---

## 5. Paso 4 · Implementar: principios de clean code

Aplican a los tres repos:

| Principio | Regla concreta |
|---|---|
| **Nombres que explican** | Variables y funciones dicen qué son o hacen: `accept_file`, no `process`. Booleanos como pregunta: `is_owner`, `has_evidence`. Sin abreviaturas raras. El código va en **inglés**; los textos al usuario, en **español**. |
| **Funciones pequeñas y de una sola cosa** | Guía: ≤ 30 líneas y ≤ 4 parámetros (si son más, un objeto). Un nivel de abstracción por función. |
| **Responsabilidad única** | Un módulo o clase tiene un solo motivo para cambiar: el router no valida negocio, el servicio no arma HTTP, el componente no llama a axios. |
| **Retorno temprano** | Se validan los casos de error al inicio y se sale; sin `if` anidados de más de 2 niveles. |
| **Sin valores mágicos** | Los estados, categorías y códigos van en `Enum` o constantes; los umbrales, en la configuración. |
| **Errores explícitos** | Nunca `except: pass` ni `catch {}` vacío. Los errores se lanzan con su código (`AppError`) y se manejan en un solo lugar. |
| **Sin duplicación…** | La lógica de negocio vive en un solo lugar (las stats en `StatsService`, la ubicación en `serialize_location`)… |
| **…pero sin abstraer de más** | Regla de tres: se abstrae a la tercera repetición, no antes. **YAGNI**: no se construye "por si acaso". |
| **Inmutabilidad** | Se prefiere crear nuevos objetos en vez de mutar los que llegan como parámetro (sobre todo en el estado de React). |
| **Comentarios** | Solo para el **por qué** no evidente. El **qué** lo dice el código. Sin código comentado (para eso está Git). |
| **Formato automático** | `ruff format` y Prettier; no se discute el estilo en la revisión. |
| **La regla del boy scout** | Si se toca un archivo, se deja un poco mejor (sin mezclar refactors grandes con la tarea). |

---

## 6. Estándares y patrones del backend y la IA (Python)

> La arquitectura por capas, la envoltura, los errores, los logs, la configuración y el storage están en [ESTANDARES_BACKEND_IA.md §2–§9](ESTANDARES_BACKEND_IA.md). Aquí van los **patrones** y las **reglas de implementación**.

### 6.1 Patrones que se usan (y dónde)

| Patrón | Para qué | Dónde |
|---|---|---|
| **Capas** (router → servicio → repositorio) | Separar HTTP, negocio y datos | Todo el back |
| **Servicio de caso de uso** | Una clase por grupo de casos de uso, con métodos que son acciones (`accept_file`, `claim`, `redeploy`) | `app/services/` |
| **Repositorio** | Encapsular las consultas SQLAlchemy con métodos con nombre (`list_visible_to`, `find_by_sha256`) | `app/repositories/` |
| **Unidad de trabajo** | Una transacción por caso de uso; el *commit* lo hace el servicio al final | `async with uow:` en los servicios |
| **Inyección de dependencias** | Recibir repositorios y adaptadores por constructor o `Depends`, para poder probar con *fakes* | Servicios, routers |
| **Adaptador** | Aislar los sistemas externos y traducir sus errores | `integrations/ai_client.py`, `storage/`, `email/`, `queue.py` |
| **Estrategia** | Implementaciones intercambiables por configuración | `StorageBackend` (local/S3), `EmailProvider` (resend/console/smtp) |
| **DTO** (Pydantic) | Contratos de entrada y salida separados del modelo de la BD | `app/schemas/` (`XxxCreate`, `XxxUpdate`, `XxxRead`) |
| **Política** (*policy object*) | Reglas de permisos en un solo lugar | `app/services/policies.py`: `can_view(viewer, resource)`, `can_edit(...)`, `serialize_location(...)` |
| **Pipeline** | Etapas puras y componibles | `wwm_pipeline` (`sampling → detection → classification → aggregation → evidence`) |
| **Idempotencia** | Que un trabajo repetido no duplique efectos | El *worker* (BE-61), la asociación (BE-01), la importación (BE-40) |

**Patrones que NO se usan** (para no complicar): *event sourcing*, CQRS, microservicios adicionales, un ORM genérico propio, herencia profunda de servicios.

### 6.2 Esqueleto de una funcionalidad completa (referencia)
```python
# schemas/camera_station.py — DTO de entrada (las reglas del contrato API §1.5)
class CameraStationCreate(BaseModel):
    code: constr(strip_whitespace=True, min_length=1, max_length=50)
    latitude: confloat(ge=-90, le=90)
    longitude: confloat(ge=-180, le=180)
    deployed_at: datetime
    still_installed: bool
    retrieved_at: datetime | None = None
    observations: constr(max_length=2000) | None = None
    visibility: Visibility = Visibility.PRIVATE
    project_id: UUID | None = None

    @model_validator(mode="after")
    def _dates(self) -> "CameraStationCreate":
        if self.still_installed and self.retrieved_at:
            raise ValueError("retrieved_at debe ser null si sigue instalada")
        return self

# api/v1/camera_stations.py — router: solo HTTP
@router.post("/camera-stations", status_code=201, response_model=ApiResponse[CameraStationRead])
async def create_camera(body: CameraStationCreate,
                        owner: Owner = Depends(get_owner),
                        service: CameraStationService = Depends(get_camera_service),
                        _f=Depends(flow("FL-05"))):
    camera, warnings = await service.create(owner, body)
    return ok(camera, message="Cámara registrada", warnings=warnings)

# services/camera_station_service.py — negocio, sin FastAPI
class CameraStationService:
    def __init__(self, uow: UnitOfWork, cameras: CameraRepository, projects: ProjectRepository, clock: Clock): ...

    async def create(self, owner: Owner, data: CameraStationCreate) -> tuple[CameraStationRead, list[Warning]]:
        if owner.is_anonymous and data.visibility is Visibility.PUBLIC:
            raise AnonPublicNotAllowed()
        self._validate_dates(data)                           # CAMERA_INVALID_DATES
        async with self.uow:
            if await self.cameras.code_exists(owner, data.code):
                raise CameraCodeTaken(context={"code": data.code})
            camera = await self.cameras.add(owner, data)
            if data.project_id:
                await self._associate(owner, camera, data.project_id)
            await self.uow.commit()
        return to_read(camera, viewer=owner), detect_coord_warnings(data)
```

### 6.3 Reglas de implementación
- **Async:** todo I/O de red o BD es `async`; lo pesado en CPU o el I/O bloqueante (Pillow, ffprobe, openpyxl, el zip) va con `await asyncio.to_thread(...)` o al *worker*.
- **SQL:** solo el ORM o `text()` **con parámetros**; prohibido armar SQL con *f-strings*. Las consultas de listados siempre llevan paginación y los filtros de visibilidad del repositorio.
- **Transacciones:** una por caso de uso; nunca un `commit` dentro de un bucle; las operaciones en cascada (asociar, borrar, importar), en una sola transacción.
- **N+1:** prohibido. Los conteos y las relaciones se cargan con `selectinload` o con consultas agregadas. Los tests de los listados verifican la cantidad de consultas.
- **Tipos:** *type hints* en todo lo público; `mypy` estricto en `core/` y `services/`.
- **Fechas:** siempre `datetime` con zona en el servidor (UTC). Para `captured_at`, la hora local sin zona, según el contrato. El "ahora" viene de un `Clock` inyectable.
- **Configuración:** solo por `Settings` (STD §8), nunca `os.environ`.
- **Logs:** con `log_step()` y eventos con nombre (STD §7); nunca `print`.
- **Migraciones:** toda modificación de la BD va con Alembic, con un `downgrade` funcional y revisada en el PR.
- **IA y escritorio:** `wwm_pipeline` es Python puro, sin estado global (los modelos se inyectan) y determinista en los tests (semillas fijas); la UI de Tkinter nunca se toca desde un hilo de trabajo.

---

## 7. Estándares y patrones del frontend (React)

### 7.1 Estructura por funcionalidad
```
src/
├── app/                 # router, layouts, providers, error boundary
├── services/            # apiClient + un servicio por recurso (contrato API_BACK_FRONT)
├── features/
│   ├── cameras/         # components/, hooks/, CameraFormModal.jsx, …
│   ├── upload/          # UploadWidget, UploadTray, useUploadStore
│   ├── classifications/ # ResultsGallery, ValidationDeck, …
│   ├── stats/           # StatsPanel
│   ├── projects/ · auth/ · admin/ · imports/
├── components/ui/       # botones, modales, tablas, toasts (sin lógica de negocio)
├── hooks/               # hooks genéricos (useDebounce, useEvidence…)
├── store/               # solo estado de cliente: auth, config, upload
├── utils/               # formatTimestamp, errorMessages, enums…
├── mocks/               # MSW (solo en desarrollo y tests; fuera del build)
└── test/                # factories, setup
```

### 7.2 Patrones

| Patrón | Regla |
|---|---|
| **Servicios por recurso** | `services/cameraStationService.js` expone funciones con el nombre del contrato (`listCameraStations(params)`, `createCameraStation(body)`) y usa **solo** `apiClient`. |
| **Estado del servidor ≠ estado del cliente** | Los datos que vienen del back (listas, detalles, stats) se manejan con **TanStack Query** (`@tanstack/react-query` v5): caché, reintentos, *polling* e invalidación. **Zustand** queda solo para el estado propio del cliente: sesión, configuración y `UploadManager`. No se copian datos del servidor en Zustand. |
| **Hooks de datos** | Un hook por consulta o mutación (`useCameraStations(filters)`, `useCreateCameraStation()`), con las claves de caché centralizadas en `services/queryKeys.js`. |
| **Contenedor / presentación** | Las pantallas (contenedores) obtienen los datos con hooks y los pasan a componentes de presentación, que solo reciben *props* y emiten eventos (fáciles de probar). |
| **Formularios** | `react-hook-form` + `zod`, con esquemas que reflejan las reglas del contrato (por ejemplo, `cameraStationSchema` con las reglas de API §1.5). Los errores del back (`error.details`) se mapean a los campos con `setError`. |
| **Estados de pantalla** | Cada pantalla con datos usa `<AsyncState loading error empty>`: skeleton, `ErrorNotice` con `request_id` y vacío con acción. |
| **Composición** | Se prefiere componer componentes pequeños a hacer componentes con muchas *props* booleanas. Si un componente pasa de 200 líneas, se parte. |

### 7.3 Reglas de implementación
- **Sin lógica de negocio crítica en el front:** los permisos, las estadísticas y la ubicación los decide el back. El front solo **oculta** lo que no se puede hacer (y aun así maneja el 403 o 404).
- **Textos:** todos en español, centralizados por funcionalidad (`features/x/texts.js`), sin mezclarlos con la lógica.
- **Accesibilidad:** cada control tiene su `label`; los modales atrapan el foco y cierran con `Esc`; los atajos de teclado (`C`, `N`, `Z`) no se disparan mientras se escribe en un campo; contraste AA; los íconos solos llevan `aria-label`.
- **Rendimiento:** listas largas paginadas o virtualizadas; imágenes con *lazy loading*; `useMemo` y `useCallback` solo donde se mide un problema; nada de *polling* con la pestaña oculta a la misma frecuencia.
- **URLs:** los filtros de las listas y el panel abierto se reflejan en la URL (`/?camera=<id>&tab=stats&from=…`), así se puede recargar o compartir.
- **Sin `console.log`** (ESLint), sin `dangerouslySetInnerHTML`, sin claves ni URLs en el código.

---

## 8. Seguridad: reglas de codificación

Cada regla tiene su punto en la lista de revisión del PR (§9.3).

| # | Riesgo (OWASP) | Regla en este proyecto | Dónde |
|---|---|---|---|
| S1 | Control de acceso roto / IDOR (A01) | **Toda** consulta por ID pasa por los filtros de visibilidad del repositorio (`visible_to`, `owned_by`, `admin_visible`). Lo ajeno privado → **404**. Hay un test IDOR por endpoint (BE-23). | Back |
| S2 | Exposición de datos (A01/A04) | Las coordenadas exactas solo van al dueño (`serialize_location`, DD-17). Los schemas de salida son explícitos: nunca se devuelve el modelo de la BD entero. | Back |
| S3 | Inyección (A03) | Solo el ORM o SQL con parámetros. Ningún valor del usuario en comandos del sistema: `ffprobe` y `ffmpeg` se llaman con una **lista** de argumentos (`subprocess.run([...])`, sin `shell=True`). | Back, IA |
| S4 | XSS (A03) | React escapa por defecto; prohibido `dangerouslySetInnerHTML`. Los textos libres (`observations`, `suggested_name`, `notes`) se muestran como texto. En el PDF y el Excel se escapan; en el Excel, las celdas que empiezan con `=`, `+`, `-` o `@` llevan un apóstrofo (para evitar la inyección de fórmulas). | Front, back (reportes) |
| S5 | Fallas criptográficas (A02) | Contraseñas con bcrypt (*cost* 12); los tokens (anónimo, recuperación, *refresh*) se guardan como **hash**; los secretos de 32 bytes o más con `secrets`; comparaciones con `hmac.compare_digest`. | Back, IA |
| S6 | Autenticación (A07) | Rotación del *refresh* con detección de reutilización; *rate limit* en el login y en la recuperación; mensajes que no revelan si la cuenta existe; `must_change_password` para el admin. | Back |
| S7 | Subida de archivos | Validación de la **firma binaria**, no solo la extensión; tamaño máximo en *streaming*; los nombres de los temporales los genera el servidor (nunca se usa el nombre del usuario como ruta); límites de píxeles (Pillow `MAX_IMAGE_PIXELS`); el fotograma se **re-codifica** antes de guardarlo. | Back, IA |
| S8 | Paquetes zip | Las validaciones de PKG §5: tamaño comprimido y descomprimido, número de entradas, rutas permitidas (sin `..` ni absolutas), sin *symlinks*, checksum. | Back (BE-40) |
| S9 | Configuración insegura (A05) | CORS solo para el dominio; cabeceras de seguridad; sin *stack traces* en producción; `/docs` deshabilitado en producción; la IA y Redis sin puerto publicado. | Back, infra |
| S10 | Componentes vulnerables (A06) | Versiones fijadas; `pip-audit` y `npm audit` en CI (fallan con una vulnerabilidad alta); Dependabot activado. | Los tres repos |
| S11 | Registro y monitoreo (A09) | Los logs de STD §7 **sin** datos sensibles; las acciones de admin en la auditoría; los errores con `request_id`. | Back, IA |
| S12 | SSRF (A10) | El back solo llama a URLs de la configuración (IA, Resend); nunca a URLs que mande el usuario. | Back |
| S13 | Secretos | Nunca en el repo: `.env` en `.gitignore`, `gitleaks` en *pre-commit* y en CI; las claves del front son públicas por naturaleza (Maps), así que van **restringidas por dominio**. | Los tres |
| S14 | Privacidad | Correos enmascarados en los logs; el anónimo se identifica solo por el prefijo del hash; el admin nunca ve contenido privado (BE-52). | Back |

**Si se detecta una vulnerabilidad:** se avisa a Diego por privado (no en un *issue* público), se corrige en una rama `fix/sec-…` con prioridad máxima y se agrega un test que la cubra.

---

## 9. Paso 5 · Git, PR y revisión

### 9.1 Ramas y commits
- `main` es lo estable (lo que se despliega), con *tags* `vX.Y.Z`. `develop` es la integración diaria; se protege y solo recibe PR.
- **Ramas:** `feature/<ID>-<slug>` (por ejemplo `feature/BE-13-subida-por-archivo`), `fix/<ID>-<slug>` y `fix/sec-<slug>` para seguridad.
- **Commits:** *Conventional Commits* con el ID: `feat(upload): encolar archivo válido [BE-13/UT-3]`. Los tipos son `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`.
- La rama se actualiza con `develop` (*rebase*) antes de pedir revisión.

### 9.2 Pull requests
- **Tamaño:** como guía, ≤ 400 líneas cambiadas sin contar los tests. Si una HU es más grande, va en varios PR (por UT o grupos de UT), cada uno con los tests en verde.
- **Plantilla:** [plantillas/PLANTILLA_PR.md](plantillas/PLANTILLA_PR.md), que se copia a `.github/pull_request_template.md` en cada repo.
- **Revisor:** al menos **1 aprobación**:
  - en el back, revisa Miguel o Diego; en el front, Job o Diego; en la IA, Job o Miguel;
  - si el PR **cambia el contrato, el catálogo de errores o la seguridad**, la aprobación de **Diego** es obligatoria.
- **Merge:** *squash merge* con el título del PR, y la rama se borra.
- **Tiempo de revisión:** como máximo 1 día hábil. Si se bloquea, se avisa en el canal.

### 9.3 Lista de revisión (el revisor la recorre)
**Funcional**
- [ ] Cumple **todos** los CA de la HU y cada uno tiene su test.
- [ ] Respeta el contrato (nombres, tipos, códigos de error, envoltura).
- [ ] Cubre los CB-xx asignados.

**Código**
- [ ] Las capas se respetan (STD §2 / §7.1); no hay lógica de negocio en el router ni en el componente.
- [ ] Los nombres son claros; las funciones, cortas; no hay duplicación ni código muerto o comentado.
- [ ] Los errores van con su código del catálogo; no hay `except` ni `catch` vacíos.
- [ ] No hay N+1; los listados están paginados.
- [ ] Los logs llevan `flow` y `event`, sin datos sensibles.

**Seguridad (§8)**
- [ ] Permisos verificados en el back (S1) y la ubicación según DD-17 (S2).
- [ ] Ninguna entrada del usuario llega a SQL, a la *shell* ni a rutas de archivo (S3, S7).
- [ ] No hay secretos ni datos sensibles en el código ni en los logs (S13, S14).

**Pruebas y entrega**
- [ ] CI en verde (lint, tipos, tests, build, auditoría de dependencias).
- [ ] La cobertura no baja de los mínimos de §4.3.
- [ ] `.env.example`, la migración y la documentación están actualizados si aplica.

---

## 10. Definición de listo (DoR) y de terminado (DoD)

**Una HU está lista para empezar (DoR) cuando:**
- [ ] Está escrita con la plantilla y **aprobada** (§2.5).
- [ ] Sus dependencias ⛔ están disponibles **o** tiene un sustituto 🔁 definido.
- [ ] Está partida en UT de 6 h o menos.
- [ ] Está asignada a una semana y a un hito.

**Una HU está terminada (DoD) cuando:**
- [ ] Todos sus CA pasan, con tests automatizados (y los e2e, si los marcó).
- [ ] Está fusionada en `develop` con CI en verde y la revisión aprobada.
- [ ] Se verificó **contra lo real** (no solo contra el sustituto) en el hito que corresponde.
- [ ] Cumple STD §13 (envoltura, códigos, logs, configuración).
- [ ] El contrato y los documentos se actualizaron si hubo cambios, y la contraparte está avisada.
- [ ] El estado en la HU dice `Terminada`, con el enlace al PR.

---

## 11. Ejemplo completo: de la tarea al PR

**Tarea:** BE-13 (lotes y subida por archivo), de [TAREAS_BACKEND](tareas/TAREAS_BACKEND.md#be-13--lotes-y-subida-por-archivo).

1. **Job crea `BACKWWF/docs/specs/HU-BE-13-subida-por-archivo.md`** con la plantilla:
   - *Historia:* "Como investigador, quiero subir mis videos a una cámara y recibir confirmación inmediata de que quedaron en cola, para seguir usando la plataforma mientras se analizan."
   - *Origen:* BE-13 · FL-08, FL-09 · FD F1 · CB-30…36, 40, 50, 51, 54 · API §7.1–7.8.
   - *Fuera de alcance:* el procesamiento con la IA (BE-61) y el *reaper* (BE-61).
   - *Dependencias:* ⛔ BE-04, BE-05, BE-21, BE-60 · 🔁 `ia-fake` · ➡️ FE-22, FE-15, FE-23, FE-52.
   - *CA-1 a CA-14:* los criterios de la tarea, en Gherkin.
   - *UT-1 a UT-6:* la tabla de §3.
   - *Plan de pruebas:* CA-1 → `test_create_batch_requires_camera`, CA-2 → `test_upload_valid_file_returns_202_queued_fast`, …
2. **Diego la revisa** con la lista de §2.5 y la aprueba.
3. **Job trabaja UT por UT**, cada una con sus tests y su commit: `feat(upload): MediaValidator con ffprobe [BE-13/UT-2]`.
4. **Abre el PR** `feat: lotes y subida por archivo [BE-13]` con la plantilla, enlazando la HU y marcando la lista de revisión.
5. **Miguel lo revisa** (es el contrato que él consume) y lo aprueba; el CI está en verde; *squash merge*.
6. **En el hito H2**, Miguel conecta FE-22 y FE-15 contra el back real con `ia-fake`; si algo no coincide con el contrato, se abre un `fix` contra la HU.
7. **Job marca la HU como `Terminada`** con el enlace al PR.
