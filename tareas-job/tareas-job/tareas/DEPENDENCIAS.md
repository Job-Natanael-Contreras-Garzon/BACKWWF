# Dependencias entre tareas e hitos de integración

> Documento interno · CETERIS404 · v1 — 08/11/2026
> **Para qué sirve:** saber, antes de empezar una tarea, **qué necesita del otro** (un endpoint, algo que la IA ya haga, un archivo) y **con qué se puede avanzar mientras tanto**, para que nadie quede bloqueado.
> **Notación en las tareas:**
> - ⛔ **Bloqueante:** sin esto no se puede **terminar** la tarea. Puede empezarse con el sustituto indicado.
> - 🔁 **Sustituto:** con qué se avanza mientras tanto (fixture, IA simulada, MSW).
> - ➡️ **Desbloquea:** qué tareas de otros esperan esta.

---

## 1. Sustitutos para no bloquearse

| Mientras no exista… | Se usa… | Lo prepara | Disponible |
|---|---|---|---|
| La IA nueva (IA-13/14/15/20) | **`ia-fake`** (✅ lista en `ia-clasificacion-fauna/fake/`, puerto **`8001`**): contenedor FastAPI mínimo que implementa `POST /api/v1/detect`, `/health` y `/catalog` según [API_IA_BACK](../contratos/API_IA_BACK.md) y responde con los **fixtures** de IA §2.2/§2.4. Elige la respuesta según el nombre del archivo: `*_blank*` → `blank`, `*_person*` → `person`, `*_vehicle*` → `vehicle`, `*_toolong*` → `200` truncado a `15.0 s` (`F1-D10`), `*_error_decode*` → 422, `*_slow*` → espera 60 s, `*_timeout*` → 504; cualquier otro → animal. Incluye fotograma JPEG en base64. | Diego (con IA-21) | ✅ **Listo** |
| El catálogo real (IA-19) | `speciesnet_catalog.json` (**3538 taxones**, ✅ listo) y `speciesnet_catalog.sample.json` (**558 taxones**) | Diego (con IA-19) | ✅ **Listo** |
| Un paquete real de escritorio (DS-17) | `sample.wwm.zip` válido + inválidos (`zip slip`, checksum alterado, versión 2.0, JPG corrupto, taxón inexistente, sin manifest, sin evidencia en animal) en `tests/fixtures/package/` | Diego (con IA-21 / `tools/make_sample_packages.py`) | ✅ **Listo** |
| Los endpoints del back | **MSW** (*Mock Service Worker*) en el front, **solo en desarrollo** (`src/mocks/`, excluido del build), con los JSON de ejemplo de [API_BACK_FRONT](../contratos/API_BACK_FRONT.md) | Miguel | S1 en adelante |
| El back levantado | `docker compose -f docker-compose.dev.yml up`: `backend` + `worker` + `redis` + `db` + `ia-fake` (o `ia` real con `--profile ia`) | Job (BE-60), Diego (`ia-fake`) | S2 |

**Regla:** un sustituto **nunca** llega a producción. Las pruebas de aceptación finales se hacen contra lo real.

---

## 2. Hitos de integración

Al final de cada semana se integra en `develop` y se prueba el flujo del hito **de punta a punta** (front real → back real → IA real o `ia-fake`). Si un hito no se cumple, se informa en el canal del equipo con lo que falta.

| Hito | Fin de | Qué debe funcionar de punta a punta | Entregan |
|---|---|---|---|
| **H1 · Bases** | S1 | Contratos aprobados por los tres; `ia-fake` + fixtures + catálogo de muestra publicados; el back responde con la envoltura y los errores estándar; registro, login y `/auth/me`; BE-51 cerrado; la línea base de la IA medida. | Diego: IA-21, `ia-fake`, IA-10 · Job: STD-07/01/03, BE-51, BE-14 · Miguel: FE-50, SEC-01/02 |
| **H2 · Sesión y cámaras** | S2 | El front en `/api/v1`; anónimo (crear sesión, aviso) y login; el mapa con cámaras reales (con redondeo para ajenas); registrar una cámara con clic; crear proyectos y asociar; la cola levanta (`redis` + `worker`) y un archivo pasa de `queued` a `done` **con `ia-fake`**. | Job: BE-11, BE-01, BE-02, BE-07, BE-08, BE-15, BE-23, BE-60, BE-13, BE-61 (base) · Miguel: FE-09, FE-13, FE-28, FE-01, FE-02, FE-14, FE-20 · Diego: IA-13/14/15/20 |
| **H3 · Clasificar y validar** | S3 | Subir 20 archivos con la bandeja navegando por la app, **con la IA real**; los resultados con fotograma y `mm:ss`; validar y corregir (alternativas, catálogo, no catalogado); asociar los datos anónimos; cámaras cercanas y reinstalación. **Entrega del Producto 1** (escritorio). | Job: BE-04, BE-05, BE-10, BE-16, BE-22, BE-25, BE-61, BE-63, BE-64, BE-27 · Miguel: FE-11, FE-15, FE-17, FE-21…24, FE-06, FE-27, FE-08 · Diego: IA-17, IA-19, DS-* |
| **H4 · Estadísticas** | S4 | Stats por cámara y proyecto (pantalla = Excel); ráfagas; recuperar la contraseña; APIs de admin. | Job: BE-09, BE-26, BE-66, BE-62, BE-53…57, BE-65 · Miguel: FE-25, FE-26, FE-33, FE-18, FE-16, FE-03, FE-04 |
| **H5 · Completo** | S5 | PDF; importar el paquete de escritorio (también creando la cámara); panel admin; todo dockerizado; los tests por flujo en verde. | Job: BE-26b, BE-40, BE-35 · Miguel: FE-07, FE-32, FE-60, FE-30 · Diego: DEP-01 |
| **H6 · Producción** | S6 | Desplegado en el servidor de WWF con HTTPS; e2e (DEP-04) sin bloqueantes; manuales; entrega del Producto 2. | Todos |

---

## 3. Matriz: el front necesita del back

Columna **"Integrar"**: la semana en que el front deja MSW y prueba contra el back real.

| Tarea front | Necesita del back (endpoint) | Tarea back | Integrar |
|---|---|---|---|
| FE-50 `apiClient` | La envoltura `{status,data,message,error,meta}` y `X-Request-ID` | STD-01, STD-04 | S1–S2 |
| FE-51 Mensajes de error | El catálogo de códigos estable | STD-03 | S2 |
| FE-09 Rutas `/api/v1` | El prefijo y las rutas nuevas | **BE-11** (misma semana) | S2 |
| FE-13 Configuración | `GET /config/public` | BE-15 | S2 |
| FE-28 Login, registro, perfil | `/auth/*` | BE-14 | S2 |
| FE-01, FE-02, FE-34 Anónimo | `/anon-sessions*`, `data_retention` | BE-01, BE-58 | S2 |
| FE-11 Asociar los datos | `POST /anon-sessions/claim`, `/close`; `anon_session` en el login | BE-01, BE-14 | S3 |
| FE-14 Mapa | `GET /camera-stations?view=map&bbox` (con redondeo) | BE-07 | S2 |
| FE-20, FE-21 Cámaras | `POST/PATCH/DELETE /camera-stations`, `If-Match` | BE-07, BE-63 | S2–S3 |
| FE-17 Cercanas y reinstalación | `/camera-stations/nearby`, `/redeploy`, `meta.warnings` | BE-63 | S3 |
| FE-27, FE-08 Proyectos | `/projects*`, `/projects/{id}/camera-stations` | BE-08 | S3 |
| FE-22, FE-15, FE-23, FE-52 Subida y bandeja | `/classification-batches*` (202 `queued`, posición, `?active`, `cancel`, `retry`) | BE-13, BE-61 | S3 |
| FE-24 Galería | `GET /classifications` con filtros | BE-16 | S3 |
| FE-06 Fotogramas | `GET /classifications/{id}/evidence` | BE-05 | S3 |
| FE-25 Validación | `PUT …/validation`, `validation-batch`, `/catalog/species` | BE-10, BE-24, BE-25 | S3–S4 |
| FE-18 Ráfagas | `/burst-candidates`, `/repeat-batch` | BE-66 | S4 |
| FE-26, FE-33 Estadísticas | `/camera-stations/{id}/stats`, `/projects/{id}/stats` | BE-09 | S4 |
| FE-07 Descargas | `/reports/excel` (S4), `/reports/pdf` (S5) | BE-26, BE-26b | S4–S5 |
| FE-16 Recuperar contraseña | `/auth/password/*` | BE-62 | S4 |
| FE-32 Importar | `/imports/*` | BE-40 | S5 |
| FE-60 Admin | `/admin/*` | BE-50, BE-52…58, BE-65 | S4–S5 |

## 4. Matriz: el back necesita de la IA y del escritorio

| Tarea back | Necesita | De | Sustituto mientras tanto | Integrar con lo real |
|---|---|---|---|---|
| BE-03 Cliente de la IA | `contract.py` (schema) + `ia-fake` `:8001` | ✅ IA-21 (`contract.py` listo; realinear `ai_contract.py` de PR #4) | — (es la base) | S1 |
| BE-04, BE-05, BE-61 Guardado y worker | Que `/detect` devuelva **una respuesta por archivo** con taxonomía completa, `evidence.image_base64`, `timestamp_seconds`, `low_evidence`, `truncated_at_seconds` y `capture` (sin `geofence`) | ✅ IA-13, IA-14, IA-15, IA-20 listos | `ia-fake` | S3 |
| BE-21 Formatos | Que la IA decodifique los formatos de `formats.py` base (`IA-16` pendiente para HEIC/TIF/extra) | 🚧 `formats.py` listo; `IA-16` pendiente | `ia-fake` | S3 |
| BE-22 `captured_at` | `capture` en la respuesta | ✅ IA-20 listo | Fixtures con `capture` | S3 |
| BE-25 Catálogo | `speciesnet_catalog.json` completo (`3538` taxones) + `GET /api/v1/catalog` con `ETag` | ✅ IA-19 listo | `speciesnet_catalog.sample.json` (`558`) | S3 |
| BE-29 Salud | `GET /api/v1/health` de la IA (`max_file_mb: 300.0`, 4 estados) | ✅ IA-18 listo | `ia-fake` | S3 |
| BE-03 / SEC-05 API key | `X-API-Key` obligatoria en la IA (`AI_API_KEY` en prod, `dev-key` en dev) | ✅ IA-30 lista | `ia-fake` (`dev-key`) | S3 |
| BE-40 Importación | `package.py` + `package_validator.py` + un paquete real (`evidence` solo en `animal`, `F2-D2`/`F2-D9`) | ✅ IA-21, DS-17 listos | `sample.wwm.zip` + inválidos | S5 |
| DEP-03 Capacidad | Los tiempos reales por archivo | ⏳ IA-17 (pendiente) | — | S3 |

## 5. Lo que el back necesita del front

| Tarea back | Necesita | De | Cuándo |
|---|---|---|---|
| BE-11 Prefijo | Que FE-09 cambie las rutas **en la misma semana**, para no dejar el `develop` roto | Miguel | S2 |
| BE-13 `client_mtime` | Que el front envíe `File.lastModified` | Miguel (FE-15) | S3 |
| BE-35 Tests e2e | El guion de pruebas por pantalla | Miguel (DEP-04) | S6 |

## 6. Ruta crítica

```
IA-21 (S1) ─▶ BE-03 ─▶ BE-04/05 ─▶ BE-13 ─▶ BE-61 ─▶ FE-15/22/24 ─▶ FE-25 ─▶ FE-26 ─▶ FE-07
   │                                  ▲
   └─▶ ia-fake ───────────────────────┘ (permite avanzar sin la IA real hasta S3)
IA-13/14/15/20 (S2) ─▶ integración real (S3) ─▶ IA-17 (medición) ─▶ DEP-05 (Producto 1)
BE-14/BE-01 (S1–S2) ─▶ FE-28/FE-01 ─▶ FE-11
BE-09 (S3–S4) ─▶ BE-26/26b ─▶ FE-07 · BE-53 ─▶ FE-60
```
Si se atrasa algo de la ruta crítica, se avisa el mismo día.
