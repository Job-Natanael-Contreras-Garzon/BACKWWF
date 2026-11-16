# Flujos del sistema

> Documento interno · CETERIS404 · v1 — 07/11/2026
> **Qué es:** la definición funcional de todo lo que el sistema hace y permite, flujo por flujo, con los componentes que intervienen, lo que se guarda y los errores esperados.
> **Relación con otros documentos:** las decisiones DD-* están en [PLAN_IMPLEMENTACION_TDR.md §2](PLAN_IMPLEMENTACION_TDR.md#2-decisiones-de-diseño-que-rigen-todo-el-plan); los formatos de respuesta, códigos de error y logs, en [ESTANDARES_BACKEND_IA.md](ESTANDARES_BACKEND_IA.md). Cada flujo tiene un ID `FL-xx` que **se escribe en los logs** (campo `flow`) para saber en qué flujo ocurrió un fallo.

---

## Índice

1. [Actores](#1-actores)
2. [Mapa de flujos](#2-mapa-de-flujos)
3. [Modelo de datos objetivo](#3-modelo-de-datos-objetivo)
4. [Flujos de acceso y sesión](#4-flujos-de-acceso-y-sesión)
5. [Flujos de cámaras y proyectos](#5-flujos-de-cámaras-y-proyectos)
6. [Flujos de clasificación (web)](#6-flujos-de-clasificación-web)
7. [Flujos de validación, estadísticas y reportes](#7-flujos-de-validación-estadísticas-y-reportes)
8. [Flujos de la app de escritorio](#8-flujos-de-la-app-de-escritorio)
9. [Sincronización escritorio → web](#9-sincronización-escritorio--web)
10. [Tareas programadas del sistema](#10-tareas-programadas-del-sistema)
11. [Flujos del administrador](#11-flujos-del-administrador)
12. [Máquinas de estado](#12-máquinas-de-estado)
13. [Puntos a confirmar con WWF](#13-puntos-a-confirmar-con-wwf)

---

## 1. Actores

| Actor | Descripción | Puede |
|---|---|---|
| **Visitante anónimo** | Usa la web sin cuenta. Recibe una credencial temporal que vive solo mientras el navegador esté abierto. | Clasificar archivos, registrar cámaras y proyectos **privados** temporales, ver sus resultados, y asociarlos a una cuenta si se registra o inicia sesión en esa misma sesión. |
| **Investigador** | Usuario con cuenta. | Todo lo anterior de forma permanente, además de marcar contenido como público, validar, exportar e importar paquetes de escritorio. |
| **Visitante de contenido público** | Cualquiera, con o sin sesión. | Ver en el mapa las cámaras y proyectos públicos y sus estadísticas. |
| **Investigador de campo** | Usa la app de escritorio, normalmente sin internet. | Clasificar carpetas localmente y exportar un paquete de sincronización. |
| **Administrador** | **Una sola cuenta** con `role=admin`, creada solo por comando en el servidor (no por registro). Es un extra que da CETERIS404. | Ver estadísticas globales de la plataforma; ver y analizar los datos **anónimos** y **públicos**; de lo **privado**, solo conteos (§11.1); aplicar y revertir borrados lógicos; desactivar usuarios; **activar o desactivar la retención de datos anónimos** (FL-44). |
| **Sistema** | Tareas automáticas del servidor. | Vencer sesiones anónimas inactivas (y eliminar sus datos solo si se crearon con la retención desactivada), limpiar temporales, hacer backups. |

---

## 2. Mapa de flujos

| ID | Flujo | Actor | Componentes | Prioridad |
|---|---|---|---|---|
| FL-01 | Registro de cuenta | Anónimo | Front · Back | P0 |
| FL-02 | Inicio y cierre de sesión, renovación del token | Investigador | Front · Back | P0 |
| FL-03 | Inicio de una sesión anónima | Anónimo | Front · Back | P0 |
| FL-04 | Asociación de los datos anónimos a una cuenta | Anónimo → Investigador | Front · Back | P0 |
| FL-05 | Registro de una cámara con clic en el mapa | Anónimo / Investigador | Front · Back | P0 |
| FL-06 | Edición, retiro y eliminación de una cámara | Dueño | Front · Back | P1 |
| FL-07 | Creación de un proyecto y asociación de cámaras | Anónimo / Investigador | Front · Back | P0 |
| FL-08 | Carga y clasificación de archivos | Anónimo / Investigador | Front · Back · IA | P0 |
| FL-09 | Seguimiento de un lote en segundo plano | Anónimo / Investigador | Front · Back | P1 |
| FL-10 | Validación y corrección de clasificaciones | Investigador | Front · Back | P0 |
| FL-11 | Consulta de estadísticas (cámara o proyecto) | Todos según visibilidad | Front · Back | P0 |
| FL-12 | Exportación a Excel y PDF | Dueño o público | Front · Back | P0 |
| FL-13 | Exploración del contenido público | Todos | Front · Back | P1 |
| FL-14 | Recuperación de contraseña por correo (Resend) | Investigador | Front · Back · Worker | P1 |
| FL-15 | Reinstalación de una cámara en el mismo punto | Dueño | Front · Back | P1 |
| FL-16 | Revisión de ráfagas: descartar registros repetidos del mismo animal | Dueño | Front · Back | P1 |
| FL-20 | Escritorio: primer inicio y descarga del modelo | Investigador de campo | Escritorio | P0 |
| FL-21 | Escritorio: clasificación de una carpeta | Investigador de campo | Escritorio (pipeline IA) | P0 |
| FL-22 | Escritorio: exportación del paquete de sincronización | Investigador de campo | Escritorio | P1 |
| FL-23 | Web: importación de un paquete de escritorio | Investigador | Front · Back | P1 |
| FL-30 | Vencimiento de sesiones anónimas inactivas (los datos se conservan según la retención) | Sistema | Back | P0 |
| FL-31 | Limpieza de temporales y archivos huérfanos | Sistema | Back · IA | P1 |
| FL-32 | Backup de la base y de los fotogramas | Sistema | Infra | P0 |
| FL-33 | *Reaper* de la cola (recupera ítems colgados o perdidos) | Sistema | Back · Worker | P0 |
| FL-40 | Panel de estadísticas globales | Administrador | Front · Back | P1 |
| FL-41 | Exploración y análisis de datos anónimos y públicos | Administrador | Front · Back | P1 |
| FL-42 | Borrado lógico y restauración | Administrador | Front · Back | P1 |
| FL-43 | Gestión de usuarios (desactivar o reactivar) | Administrador | Front · Back | P1 |
| FL-44 | Configuración de la retención de datos anónimos | Administrador | Front · Back | P1 |
| FL-45 | Monitor de la cola y del envío de correos | Administrador | Front · Back | P1 |
| FL-46 | Sugerencias de especies no catalogadas y desempeño del modelo | Administrador | Front · Back | P1 |

> **Casos borde** de todos los flujos: [flujos/CASOS_BORDE.md](flujos/CASOS_BORDE.md) (CB-xx).

> **Alcance:** FL-40 a FL-44 (administrador) **no están en el TDR**. Es un extra que CETERIS404 entrega sin costo, con un único administrador.
>
> **Alcance:** FL-22 y FL-23 (sincronización) **no están en el TDR**. El TDR (§3.4) dice que la app de escritorio "solo realiza la clasificación y no proporciona estadísticas", y el paquete respeta eso: lleva **registros**, no estadísticas, que las calcula la web al importar. Conviene presentarlo a WWF como un valor agregado para que no se lea como cambio de alcance (§13, D6).

---

## 3. Modelo de datos objetivo

Es la base para todos los flujos. Reemplaza el esquema actual (`species` como tabla de detecciones, `videos`, `individuals`, `colaborators`), y la migración inicial de Alembic se escribe ya con este esquema.

| Tabla | Campos principales | Notas |
|---|---|---|
| `users` | `id`, `email`, `password_hash`, `full_name`, `institution`, **`role`** (`user`/`admin`), `is_active`, `created_at`, `last_login_at` | El rol no se puede asignar por la API pública. |
| `anon_sessions` | `id`, `token_hash`, `created_at`, `last_activity_at`, `expires_at`, `status` (`active`/`claimed`/`expired`), `claimed_by_user_id`, `claimed_at` | Se guarda el **hash** del token, nunca el token. `expired` = el token ya no sirve, pero **los datos se conservan**. |
| `admin_audit_log` | `id`, `admin_user_id`, `action` (`soft_delete`/`restore`/`deactivate_user`/`reactivate_user`/`export`/`update_setting`), `entity_type`, `entity_id`, `old_value`, `new_value`, `reason`, `created_at`, `request_id` | Toda acción del administrador queda registrada; la tabla es de solo inserción. |
| `system_settings` | `key`, `value` (JSON), `updated_by`, `updated_at` | Configuración que cambia el admin **en caliente**, sin reiniciar ni tocar el `.env`. Primera clave: `anon_data_retention` (por defecto `true`). |
| `anon_purge_runs` | `id`, `run_at`, `sessions`, `classifications`, `camera_stations`, `projects`, `frames` | Conteos de cada ejecución de FL-30 que eliminó datos, sin ningún dato personal ni taxonómico. Permite que el panel informe cuánto se eliminó por la configuración. |
| `camera_stations` | `id`, **dueño**, `code`, `name`, `latitude`, `longitude`, `deployed_at`, `retrieved_at`, `still_installed`, `observations`, `visibility`, `previous_camera_station_id`, `version` | `code` es único por dueño sin distinguir mayúsculas, entre las no borradas. `version` sirve para el bloqueo optimista (CB-15). |
| `password_reset_tokens` | `id`, `user_id`, `token_hash`, `expires_at`, `used_at`, `created_at`, `request_ip_hash` | Un solo uso, 30 min; al crear uno se invalidan los anteriores. |
| `email_log` | `id`, `type` (`password_reset`), `to_hash`, `status` (`queued`/`sent`/`failed`/`skipped_limit`), `provider_id`, `created_at` | Conteo de la cuota y auditoría. No guarda el correo en claro. |
| `projects` | `id`, **dueño**, `name`, `description`, `visibility` | Individual, sin colaboradores. |
| `project_camera_stations` | `project_id`, `camera_station_id` | Solo cámaras del mismo dueño. |
| `classification_batches` | `id`, **dueño**, `camera_station_id`, `source` (`web`/`desktop_import`), `status`, `total`, `done`, `failed`, `created_at` | Un envío de N archivos. |
| `classifications` | Ver detalle abajo | **Una fila por archivo** (DD-1). |
| `desktop_imports` | `id`, **dueño**, `camera_station_id`, `package_sha256`, `manifest` (JSON), `status`, `counts`, `created_at` | Auditoría de FL-23. |

**Dueño:** cada recurso tiene `owner_user_id` **o** `anon_session_id`, nunca los dos ni ninguno (`CHECK` en la BD). Asociar los datos a una cuenta (FL-04) es pasar de uno al otro.

**Retención anónima por registro:** cada fila creada por una sesión anónima (`camera_stations`, `projects`, `classification_batches`, `classifications`) guarda `anon_retain` (`true`/`false`), que copia el valor de `anon_data_retention` **en el momento de su creación**. Así, un cambio de la configuración solo afecta a los datos que se creen desde ese momento (FL-44). En filas de usuarios el campo es `NULL`.

**Borrado lógico** (ya existe en `BaseEntity`: `is_deleted`, `deleted_at`). Se agregan `deleted_by` (usuario o admin) y `deleted_reason`, en todas las tablas de contenido (`camera_stations`, `projects`, `classifications`, `classification_batches`, `desktop_imports`). Nunca se borra físicamente desde la aplicación. **Única excepción:** los datos anónimos creados con la retención desactivada (`anon_retain = false`), que FL-30 elimina físicamente al vencer la sesión porque, por configuración, no debían guardarse. Lo borrado no aparece en listados, estadísticas ni exportaciones; solo el administrador puede verlo con el filtro `include_deleted` y restaurarlo.

**`classifications`:**

| Grupo | Campos |
|---|---|
| Origen | `batch_id`, dueño, `camera_station_id` (obligatorio, D7), `source` (`web`/`desktop`), `file_name`, `file_sha256`, `file_size_bytes`, `media_type`, `duration_seconds` |
| Fecha de captura | `captured_at`, `captured_at_source` (`exif`/`container`/`filename`/`client_mtime`/`upload_time`) |
| Resultado de la IA | `category` (`animal`/`person`/`vehicle`/`blank`), `class`, `order`, `family`, `genus`, `species`, `scientific_name`, `common_name`, `rank`, `confidence`, `label_raw`, `frames_analyzed` |
| Evidencia (DD-3) | `evidence_key` (ruta en el *storage*), `evidence_frame_index`, `evidence_timestamp_seconds` (minuto y segundo del video), `evidence_bbox` |
| Trazabilidad del modelo | `model_detector`, `model_classifier`, `geofence`, `sampling` |
| Procesamiento | `status` (`queued`/`processing`/`done`/`error`/`cancelled`), `error_code`, `warnings` (JSONB), `tmp_key` (ruta del temporal mientras está en cola), `queued_at`, `started_at`, `finished_at`, `heartbeat_at`, `attempts` |
| Validación | `validation_status` (`unvalidated`/`confirmed`/`corrected`/`corrected_unlisted`/`rejected`/`discarded_repeat`), `repeat_of`, `burst_reviewed_at`, `correction_source` (`alternative`/`catalog`/`unlisted`), `corrected_*` (taxonomía), `suggested_name`, `validated_by`, `validated_at`, `validation_notes`, `validation_history` (JSONB) |

- **Índice único `(camera_station_id, file_sha256)`** entre las filas `queued`, `processing` y `done` no borradas: el mismo archivo no se cuenta dos veces aunque se suba de nuevo o llegue también por un paquete de escritorio. Además, se busca el mismo `sha256` en **otras cámaras del dueño** (CB-51).
- **Taxonomía efectiva** para estadísticas y exportaciones: la corregida si existe; si no, la de la IA. Las filas `rejected` y `discarded_repeat` no cuentan como avistamiento.

---

## 4. Flujos de acceso y sesión

### FL-03 · Inicio de una sesión anónima

**Regla (DD-2):** sin sesión **sí se guarda** en la BD, bajo una credencial anónima temporal. Si el usuario cierra el navegador, pierde la credencial y ya no puede acceder a esos datos; no hay forma de recuperarla. Lo que pasa después con los datos depende de la configuración **`anon_data_retention`** (FL-44), vigente cuando se creó cada registro:
- **`true` (por defecto):** los datos **no se eliminan**. Quedan como datos anónimos para las estadísticas generales, visibles solo para el administrador (FL-41), que puede aplicarles un borrado lógico (FL-42).
- **`false`:** los datos existen solo mientras dura la sesión. Al vencer o al elegir "No asociar", se eliminan físicamente junto con sus fotogramas (FL-30). Es el comportamiento literal del TDR §3.1.

En ambos casos, si el usuario asocia la sesión a su cuenta (FL-04), los datos se conservan como suyos.

1. **Front:** la primera vez que el visitante hace una acción que guarda algo (clasificar, crear una cámara o un proyecto), y no tiene sesión ni token anónimo, llama a `POST /api/v1/anon-sessions`.
2. **Back:** genera un token aleatorio (`secrets.token_urlsafe(32)`), guarda solo su hash SHA-256 con `expires_at = ahora + ANON_SESSION_TTL_HOURS` (24 h por defecto) y devuelve `{anon_token, expires_at, data_retention}`. `data_retention` es el valor actual de la configuración, para que el front muestre el aviso correcto.
3. **Front:** guarda el token en **`sessionStorage`**. Sobrevive a F5 en la misma pestaña y se borra al cerrar la pestaña o el navegador. Lo envía en cada petición como `X-Anon-Token`.
4. **Back:** con cada petición válida actualiza `last_activity_at` y extiende `expires_at` (vencimiento por inactividad).
5. **Front:** muestra un aviso fijo: *"Estás trabajando sin cuenta. Perderás el acceso a tus resultados al cerrar el navegador. Inicia sesión o regístrate para conservarlos."*
6. **Aviso de uso de datos**, que se muestra antes de la primera clasificación anónima y se acepta una vez por sesión. El texto depende de `data_retention`:
   - **Con retención:** *"Los archivos que clasifiques sin cuenta no se guardan, pero sí sus resultados (especie, fotograma de evidencia, fecha y ubicación de la cámara, si la registras). Se conservan de forma anónima para generar estadísticas de la plataforma."* Como los datos se retienen y el usuario no los puede borrar, este aviso es necesario.
   - **Sin retención:** *"Tus resultados se eliminarán al cerrar el navegador, salvo que inicies sesión o te registres."* Solo informa; no hace falta aceptarlo.

**Reglas y límites:**
- El token **nunca** va en la URL ni en los logs.
- El contenido anónimo es **siempre privado**: no se puede marcar como público. Así se evita que alguien publique contenido en el mapa sin cuenta.
- Límites por sesión anónima, configurables: `ANON_MAX_FILES` (por ejemplo 50), `ANON_MAX_CAMERAS` (por ejemplo 5) y *rate limit* por IP para crear sesiones.
- Si el token vence o no existe → `401 ANON_SESSION_EXPIRED`. El front lo borra y avisa que los datos anteriores ya no están disponibles.

**Errores:** `ANON_SESSION_EXPIRED`, `ANON_LIMIT_REACHED`, `RATE_LIMITED`.

### FL-01 · Registro de cuenta

1. **Front:** formulario con nombre, correo, contraseña e institución → `POST /api/v1/auth/register`. Si hay un token anónimo, lo envía en `X-Anon-Token`.
2. **Back:** valida (correo único, contraseña de 8 caracteres o más), crea el usuario y devuelve `access_token` y `refresh_token`.
3. Si había token anónimo con datos → **FL-04**.

**Errores:** `AUTH_EMAIL_TAKEN` (409), `VALIDATION_ERROR` (422), `RATE_LIMITED`.

### FL-02 · Inicio y cierre de sesión, renovación del token

1. **Login:** `POST /api/v1/auth/login` → tokens. Si hay token anónimo con datos → FL-04.
2. **Recarga de página:** el front llama a `GET /api/v1/auth/me` para restaurar el usuario. Si el *access token* venció, el interceptor llama a `POST /api/v1/auth/refresh` una sola vez y reintenta.
3. **Logout:** `POST /api/v1/auth/logout` (invalida el *refresh token* si se implementa la lista de revocación) y el front borra todo el estado.

**Errores:** `AUTH_INVALID_CREDENTIALS` (401, el mismo mensaje si falla el correo o la contraseña), `AUTH_TOKEN_EXPIRED` (401), `AUTH_TOKEN_INVALID` (401).

### FL-04 · Asociación de los datos anónimos a una cuenta

**Mejora propuesta frente al flujo actual:** la asociación se **confirma** explícitamente y es **atómica**.

1. **Front:** tras el registro o el login, si existe `X-Anon-Token`, llama a `GET /api/v1/anon-sessions/current` → `{classifications: 12, camera_stations: 1, projects: 0}`.
2. Si hay datos, muestra *"Tienes 12 clasificaciones y 1 cámara de esta sesión. ¿Asociarlas a tu cuenta?"* con las opciones **Asociar** y **No asociar**.
   - La confirmación evita que, en una computadora compartida, los datos de otra persona terminen en la cuenta equivocada.
3. **Asociar:** `POST /api/v1/anon-sessions/claim` con `Authorization: Bearer` y `X-Anon-Token`. El back, **en una sola transacción**:
   1. pasa `anon_session_id` → `owner_user_id` en todas las tablas;
   2. resuelve los choques de `code` de cámara (agrega el sufijo `-2` y lo informa);
   3. marca la sesión como `claimed`.
4. **No asociar:** `POST /api/v1/anon-sessions/current/close` → la sesión pasa a `expired` de inmediato, igual que FL-30. Los datos quedan como anónimos y no se borran.
5. El front borra el token de `sessionStorage` en ambos casos.

**Idempotencia:** reclamar una sesión ya reclamada por el mismo usuario devuelve 200 sin cambios; si la reclamó otro usuario → `409 ANON_SESSION_ALREADY_CLAIMED`.

**Errores:** `ANON_SESSION_EXPIRED`, `ANON_SESSION_ALREADY_CLAIMED`.

### FL-14 · Recuperación de contraseña
**Proveedor:** Resend, detrás de una interfaz `EmailProvider` (cambiable por SMTP). Su plan gratuito permite **100 correos al día y 3000 al mes**; el sistema se pone topes **menores** (`EMAIL_DAILY_CAP=80`, `EMAIL_MONTHLY_CAP=2500`) para no llegar nunca al límite del proveedor.

1. `/recuperar` → el usuario escribe su correo → `POST /api/v1/auth/password/forgot`.
2. **Back**, siempre en el mismo tiempo y con la misma respuesta genérica:
   1. aplica los límites por correo (3 por hora, 5 por día) y por IP (10 por hora), con contadores en Redis;
   2. si el usuario existe, está activo y no se superó ningún límite, crea el token (32 bytes, hash en la BD, 30 min, invalida los anteriores) y **encola** el envío;
   3. si se alcanzó el **tope global**, responde `503 EMAIL_TEMPORARILY_UNAVAILABLE` a todos.
3. **Worker:** envía el correo (plantilla en español con el enlace `https://<dominio>/restablecer?token=…`) por Resend y registra `email_log`. Si Resend responde 429 o 5xx, reintenta 2 veces y luego marca `failed`.
4. `/restablecer?token=` → `GET …/reset/validate` → formulario → `POST …/reset` → revoca todos los *refresh tokens* → "Contraseña actualizada".
5. **Respaldo sin correo:** el admin genera un enlace manual (`POST /admin/users/{id}/password-reset-link`), que queda en la auditoría.

**Requisito:** un dominio verificado en Resend (DNS SPF y DKIM, SEC-12), que depende del dominio de WWF (SEC-07).
**Casos borde:** CB-73 a CB-78.

---

## 5. Flujos de cámaras y proyectos

### FL-05 · Registro de una cámara con clic en el mapa
1. **Front:** el botón "Colocar cámara" activa el modo de colocación; el clic en el mapa precarga la latitud y la longitud (editables).
2. Formulario:
   - código o nombre;
   - fecha y hora de colocación;
   - "sigue instalada" o fecha y hora de retiro;
   - observaciones;
   - pública o privada (deshabilitado para el anónimo). Al elegir **pública** se muestra la advertencia de DD-17 (FD D3).
3. **Cercanía:** antes de guardar, el front consulta `GET /api/v1/camera-stations/nearby` y, si hay cámaras propias o públicas a menos de 30 m, muestra las opciones de CB-01…CB-06:
   - otra cámara en el mismo punto;
   - reinstalación (FL-15);
   - abrir la existente.

   Nunca se informa la existencia de cámaras privadas ajenas.
4. `POST /api/v1/camera-stations` → el back valida:
   - coordenadas en rango;
   - `retrieved_at ≥ deployed_at`;
   - `code` único por dueño.
5. La cámara aparece en el mapa; las privadas solo las ve su dueño. Las advertencias (`CAMERA_COORDS_SUSPECT`) llegan en `meta.warnings`. **No se restringe la ubicación a Bolivia**; el mapa arranca centrado en Santa Cruz.

### FL-15 · Reinstalación en el mismo punto
`POST /api/v1/camera-stations/{id}/redeploy`:
- crea una cámara **nueva** con la misma ubicación, el mismo nombre, la misma visibilidad y los mismos proyectos, un código nuevo (`CAM01-2`) y `previous_camera_station_id`;
- opcionalmente cierra la anterior con su fecha de retiro.

Cada periodo conserva sus clasificaciones, el esfuerzo (días-cámara) se calcula bien y el proyecto suma ambas (CB-03).

**Errores:** `CAMERA_CODE_TAKEN` (409), `CAMERA_INVALID_DATES` (422), `VALIDATION_ERROR`.

### FL-06 · Edición, retiro y eliminación de una cámara
- **Editar:** `PATCH /api/v1/camera-stations/{id}` (solo el dueño).
- **Retirar:** el mismo PATCH con `retrieved_at` y `still_installed=false`.
- **Eliminar:** `DELETE` es un borrado lógico (`deleted_by` = el dueño). El modal de confirmación indica cuántas clasificaciones tiene. La cámara y sus clasificaciones quedan ocultas para el usuario y fuera de las estadísticas; no se borran físicamente ni se purgan sus fotogramas. Solo el administrador las ve con `include_deleted`. Los datos de una cámara privada borrada siguen siendo privados también para el administrador (§11.1).
- **Visibilidad:** el dueño puede cambiar en cualquier momento entre pública y privada (`PATCH {visibility}`), y lo mismo con un proyecto. El cambio afecta de inmediato a lo que ven los demás y el administrador.

**Errores:** `CAMERA_NOT_FOUND` (404), `FORBIDDEN` (403).

### FL-07 · Creación de un proyecto y asociación de cámaras
1. `POST /api/v1/projects` con nombre, descripción y visibilidad.
2. **Asociar cámaras existentes:** el selector muestra solo las cámaras propias → `POST /api/v1/projects/{id}/camera-stations` `{camera_station_id}`.
3. **Crear una cámara dentro del proyecto:** FL-05 con `project_id` preseleccionado; el back crea la cámara y la asociación en una transacción.
4. **Desasociar:** `DELETE /api/v1/projects/{id}/camera-stations/{camera_station_id}`. La cámara sigue existiendo.
5. La visibilidad del proyecto y la de la cámara son **independientes** (TDR §3.1).

**Errores:** `PROJECT_NOT_FOUND`, `CAMERA_NOT_OWNED` (403), `ALREADY_ASSOCIATED` (409).

---

## 6. Flujos de clasificación (web)

### FL-08 · Carga y clasificación de archivos

**Reglas:**
- Una clasificación por archivo (DD-1).
- Los archivos originales se procesan en un temporal y se **borran** (DD-3); solo se guardan el registro y el fotograma de evidencia comprimido, en el *storage* local.

```
Front ──multipart──▶ Back ──(1 archivo)──▶ IA
  │                    │ valida, calcula sha256, temporal    │ muestreo → MegaDetector → SpeciesNet + geofence
  │                    │                                     │ → votación → taxonomía → fotograma
  │                    ◀───────── JSON (contrato IA) ──────┘
  │                    │ guarda el fotograma en el storage (JPEG) y la fila en classifications
  │                    │ borra el temporal (finally)
  ◀── resultado por archivo ──┘
```

1. **Front:**
   - selección múltiple de archivos y una **cámara registrada obligatoria** para todos, también para el anónimo (TDR §3.1, D7);
   - validación previa en el cliente: extensión (formatos comunes de cámaras trampa, foto y video; API §4.1), peso y, cuando el navegador puede leerla, `video.duration ≤ 15 s` (el resto lo valida el back);
   - envía `lastModified` de cada archivo.
2. `POST /api/v1/classification-batches` `{camera_station_id, expected_files}` → crea el lote. Luego el front sube **un archivo por petición**, 3 en paralelo, con `POST /api/v1/classification-batches/{id}/files` (`file`, `client_index`, `client_mtime`), y al final llama a `POST …/complete`. El detalle está en [API §7](contratos/API_BACK_FRONT.md#7-clasificación-lotes-cola-y-archivos).
3. **Back API, por archivo** (rápido, sin llamar a la IA):
   1. autoriza: el dueño del lote;
   2. valida la firma, el peso y la duración (`ffprobe`);
   3. calcula el `sha256`; si es un duplicado (CB-50, CB-51), devuelve el ítem en `error` y no encola;
   4. guarda el archivo en el **temporal compartido** (`TMP_UPLOAD_PATH`);
   5. crea la fila con `status=queued` y `anon_retain` (si es anónimo);
   6. encola el trabajo en **Redis** (`arq`) respetando la cola justa;
   7. responde **202** con `queue.position` y `estimated_wait_seconds`.
4. **Worker, por trabajo:**
   1. marca la fila `processing` y actualiza `heartbeat_at` cada 30 s;
   2. llama a la IA (`X-API-Key`, `X-Request-ID`, `X-Flow`), con 2 reintentos en errores transitorios;
   3. guarda el fotograma con `StorageBackend.put()` y la fila `done`. Si falla, la fila queda en `error` con su `error_code`, **sin inventar datos** (DD-4);
   4. borra el temporal;
   5. libera el turno del dueño, y el despachador pasa el siguiente trabajo por *round-robin*.

   El dueño se toma **del lote al escribir** (CB-41).
5. **Front:**
   - el `UploadManager` global sigue la cola por *polling* (`GET /classification-batches?active=true` cada 3 s, o 15 s con la pestaña oculta);
   - la bandeja `UploadTray` se ve en todas las pantallas, y el usuario **sigue navegando** (CB-31);
   - al terminar, notificación y galería. Cada tarjeta muestra el fotograma, la especie común y la científica, el género, la familia, la confianza, el `rank` y el **minuto y segundo** (`evidence.timestamp_label`). Las clases no animales van aparte (DD-9).
6. Un lote que nadie cierra queda `incomplete` al cabo de 1 h sin archivos nuevos.

**Capacidad:** cada *worker* atiende una réplica de la IA, que procesa un archivo a la vez. Para más capacidad se agregan pares *worker* + IA (escala horizontal), sin cambiar el código (DEP-03).

**Fecha de captura** (`captured_at`), en este orden de prioridad:
1. EXIF `DateTimeOriginal`;
2. `creation_time` del contenedor del video;
3. fecha en el nombre del archivo;
4. `lastModified` del cliente;
5. hora de subida.

La fuente queda en `captured_at_source`. La extracción vive en el pipeline común de la IA, de modo que la app de escritorio use la misma lógica.

**Errores por archivo:**
- `MEDIA_UNSUPPORTED_FORMAT` (415);
- `MEDIA_TOO_LARGE` (413);
- `MEDIA_DURATION_EXCEEDED` (422);
- `MEDIA_DECODE_FAILED` (422);
- `DUPLICATE_FILE`;
- `AI_UNAVAILABLE` (502);
- `AI_TIMEOUT` (504);
- `STORAGE_WRITE_FAILED` (500).

### FL-09 · Cola: seguimiento, cancelación y reintentos
1. **Seguimiento:** `GET /api/v1/classification-batches?active=true` (bandeja) y `GET /api/v1/classification-batches/{id}?since=` (detalle). La posición y la espera estimada se recalculan en cada consulta.
2. **Cancelar:** `POST …/cancel` (todo lo que está en cola) o `DELETE …/items/{i}` (uno). Lo que ya está `processing` termina.
3. **Reintentar:** `POST …/items/{i}/retry` si el temporal sigue disponible (24 h); si no, hay que volver a subir el archivo.
4. **F5 o cerrar la pestaña:** lo que ya estaba en cola **se sigue procesando** en el servidor (CB-33). Con sesión, se ve al volver; si es anónimo y cerró el navegador, ya no puede verlo.
5. **Límites:** `QUEUE_MAX_PENDING_PER_USER` (500) → `QUEUE_USER_LIMIT`; la cola global llena o el disco temporal al 85 % → `QUEUE_FULL`; Redis caído → `QUEUE_UNAVAILABLE`, mientras el resto del sistema sigue funcionando (CB-34…CB-36).

---

## 7. Flujos de validación, estadísticas y reportes

### FL-10 · Validación y corrección
1. **Front:** la tabla o galería de clasificaciones de una cámara o proyecto tiene filtros:
   - `validation_status`;
   - especie;
   - fecha;
   - confianza menor que X (para revisar primero las dudosas).
2. **Por archivo:** `PUT /api/v1/classifications/{id}/validation`, con estas acciones:
   - **confirmar** → `confirmed`;
   - **corregir**, después de pulsar "No es esta especie", con cuatro opciones:
     1. una de las `alternatives` (hasta 2) → `correct` con `correction_source=alternative`;
     2. **Buscar otra especie** en el catálogo → `correct` con `correction_source=catalog`;
     3. **No está en el catálogo** → `correct_unlisted` con `suggested_name` (texto libre) y, opcionalmente, el taxón superior conocido. Cuenta en ese nivel y queda registrado para futuras mejoras (FL-46, CB-65);
     4. **No hay ningún animal** → `reject`.

     La taxonomía corregida siempre sale **del catálogo**; el texto libre solo se guarda como sugerencia;
   - **rechazar** (no hay animal) → `rejected`;
   - **deshacer** → `reset` (vuelve a `unvalidated`);
   - además, notas opcionales.
3. **En lote:** `POST /api/v1/classifications/validation-batch` `{ids[], action}`, solo para confirmar, rechazar o deshacer.
4. **Back:** valida la corrección contra el catálogo de SpeciesNet y registra `validated_by` y `validated_at`. Un anónimo puede validar, y su validación se conserva si asocia la sesión a una cuenta.

**Errores:** `CLASSIFICATION_NOT_FOUND`, `FORBIDDEN`, `CATALOG_TAXON_NOT_FOUND` (422).

### FL-16 · Ráfagas: registros repetidos del mismo animal
**Regla (D10, opción A):** cada archivo con el animal cuenta como un avistamiento. Muchas cámaras toman varias fotos o videos por disparo; el investigador decide si ese conjunto cuenta como uno o como varios.
1. El sistema **sugiere** grupos: misma cámara, misma especie efectiva, capturas a ≤ `BURST_WINDOW_MINUTES` (5 min, ajustable por el usuario) entre sí. `GET /api/v1/classifications/burst-candidates`.
2. Por cada grupo, el investigador elige:
   - **Conservar todos** (`dismiss`): siguen contando N y el grupo deja de sugerirse;
   - **Dejar uno**: el de mayor confianza viene marcado por defecto, pero puede elegir otro;
   - **Elegir cuáles dejar**: casillas por archivo.

   → `POST /api/v1/classifications/repeat-batch`.
3. Los descartados pasan a `discarded_repeat` con `repeat_of`: **no cuentan como avistamientos**, pero no se borran, conservan su fotograma y su taxonomía, y **no** se consideran errores de la IA. Se puede deshacer (`reset`).
4. También se puede marcar uno suelto desde su detalle (`discard_repeat`).
5. Las estadísticas, el Excel y el PDF informan `discarded_repeat`, y el Excel marca en cada fila si cuenta como avistamiento.

### FL-11 · Estadísticas
`GET /api/v1/camera-stations/{id}/stats` · `GET /api/v1/projects/{id}/stats` · filtros `from`, `to`, `only_validated`, `source` (`web`/`desktop`).

**Definición:** **avistamiento** = un archivo clasificado con `category=animal` y que no está `rejected`. Se usa la taxonomía efectiva.

| Estadística | Nivel | Fuente |
|---|---|---|
| Avistamientos por **especie, género y familia** (conteo y %) | **TDR — obligatorio** | taxonomía efectiva |
| Totales: archivos procesados, con fauna, sin fauna, con error | Complementaria (P0) | `classifications` |
| Riqueza: número de especies, géneros y familias distintos | Complementaria (P0) | taxonomía |
| Clases no animales: personas, vehículos, vacíos | Complementaria (P0) | `category` |
| Estado de validación: validados, corregidos, rechazados, pendientes; **% de correcciones**, que mide el acierto real de la IA | Complementaria (P1) | `validation_status` |
| Por cámara dentro del proyecto: avistamientos y especies por cámara (matriz cámara × especie) | Complementaria (P1) | `camera_station_id` |
| Distribución temporal: por mes y por **hora del día** (patrón de actividad) | Complementaria (P1) | `captured_at`; excluye `upload_time` |
| Primera y última fecha de registro por especie; confianza media por especie | Complementaria (P2) | — |
| Esfuerzo de muestreo: días-cámara (colocación → retiro) y avistamientos por cada 100 días-cámara | Complementaria (P2) | `deployed_at`, `retrieved_at` |

No hay estadísticas que dependan de servicios externos (clima): se descarta VisualCrossing.

### FL-12 · Exportación a Excel y PDF
**Recomendación (DD-6): ambos se generan en el back.** Ver la justificación en el plan §2.

1. **Front:** los botones "Excel" y "PDF" en cámara y proyecto aplican los filtros activos.
2. `GET /api/v1/reports/excel?camera_station_id=|project_id=&only_validated=&from=&to=` y `GET /api/v1/reports/pdf?...`.
3. **Back:**
   1. autoriza;
   2. obtiene **un solo dataset** con el mismo servicio que FL-11;
   3. genera el archivo en memoria;
   4. responde con `Content-Disposition: attachment`.
4. **Excel:**
   - *Resumen*: alcance, filtros, fecha de generación, versión del modelo y totales;
   - *Por especie*, *Por género* y *Por familia*;
   - *Clasificaciones*: archivo, cámara, coordenadas, fecha de captura y su fuente, minuto:segundo del fotograma, taxonomía de la IA, taxonomía validada, confianza, estado de validación, notas y origen.
5. **PDF:** la misma información con gráficos (barras por especie, género y familia) y una tabla; el pie lleva el `request_id` y la fecha.

**Errores:** `REPORT_EMPTY` (sin datos con esos filtros; se responde 200 con un archivo que lo indica, o 404, según se acuerde con el front), `FORBIDDEN`.

### FL-13 · Exploración del contenido público
1. Sin sesión, o con sesión mirando contenido ajeno, el mapa carga `GET /api/v1/camera-stations?visibility=public` y `GET /api/v1/projects?visibility=public`.
2. Se ven las estadísticas y los fotogramas de lo público. Las coordenadas de las cámaras ajenas se muestran **redondeadas a ~1 km** (DD-17); solo el dueño ve la ubicación exacta.
3. Las mutaciones sobre contenido ajeno responden `403`.

---

## 8. Flujos de la app de escritorio

### FL-20 · Primer inicio y descarga del modelo
1. Al abrir, la app verifica `%LOCALAPPDATA%\WWM\models` (pesos de MegaDetector, SpeciesNet y el código de YOLOv5 empaquetado).
2. Si falta algo:
   - una pantalla de descarga con progreso;
   - verificación del tamaño y el hash;
   - reintento y reanudación.
3. Al terminar queda marcado `models.ok` con versiones y hashes; desde entonces **no usa la red**.
4. **Errores** que se muestran con un mensaje claro y quedan en el log:
   - `NETWORK_UNAVAILABLE`;
   - `DOWNLOAD_INTEGRITY_FAILED`;
   - `DISK_SPACE_LOW`.

### FL-21 · Clasificación de una carpeta
1. El usuario elige la carpeta de origen (no recursiva), la de destino y la opción **copiar** o **mover**. Opcional: **código de cámara**, que se usa en FL-22 para emparejarla en la web.
2. Por cada archivo, con el **pipeline común** en modo precisión:
   1. calcula el `sha256`;
   2. obtiene la fecha de captura;
   3. clasifica: muestreo denso, votación y taxonomía.
3. **Con especie:**
   1. copia o mueve el archivo a `destino/<Nombre científico (común)>/`;
   2. escribe al lado `<NOMBRE>_fotograma.jpg`: el fotograma completo con el recuadro y una etiqueta con especie, confianza y **minuto:segundo**;
   3. antes de mover, verifica la copia por tamaño y hash.
4. **Sin especie, persona, vehículo o vacío:** el archivo **queda en el origen** (TDR §3.4).
5. Cada resultado se agrega a `destino/_wwm/clasificaciones.jsonl` (registro local, base del paquete).
6. Botón *Detener*: termina el archivo en curso y deja el registro consistente; se puede **reanudar**, y los archivos ya procesados, reconocidos por su hash, se saltan.
7. Al terminar: un resumen en pantalla con cantidades procesadas, clasificadas, sin especie y con error. Es un conteo de la tarea, no una estadística de fauna.

---

## 9. Sincronización escritorio → web

**Objetivo:** que el investigador de campo no tenga que subir los videos a la web. La app exporta un paquete liviano con los **registros y los fotogramas de evidencia**, y la web lo importa y guarda los datos como si se hubieran clasificado allí.

### FL-22 · Exportación del paquete (escritorio)
1. **Botón "Exportar para la web"** al terminar una clasificación, o desde el menú sobre una carpeta de destino ya procesada.
2. Genera `WWM_<codigo-camara>_<AAAAMMDD-HHMM>.wwm.zip` con `manifest.json` (con los datos **opcionales** de la cámara: código, nombre, coordenadas, fechas y observaciones), `classifications.jsonl` (con la taxonomía completa, familia incluida, y todos los datos que registra la web) y `evidence/<sha256>.jpg`. **El formato normativo, con todos los campos, está en [contratos/PAQUETE_ESCRITORIO.md](contratos/PAQUETE_ESCRITORIO.md).**

**Reglas:**
- **No incluye estadísticas** (TDR §3.4): solo registros. Las estadísticas las calcula la web.
- **No incluye los videos ni las imágenes originales.** Para 340 archivos el paquete pesa unos 10 MB (≈100 KB por fotograma con animal).
- Usa los mismos campos que la respuesta de la IA ([API_IA_BACK.md](contratos/API_IA_BACK.md)), así la web reutiliza su código de guardado.

### FL-23 · Importación del paquete (web)
1. **Front**, con sesión obligatoria: botón "Importar desde escritorio" en una cámara, o en el mapa. Si el `code` del paquete coincide con una cámara propia, se sugiere; si no, el usuario elige una o **crea la cámara con los datos del paquete** (`create_camera=true`), y puede completar en el mapa lo que falte.
2. **Vista previa:** `POST /api/v1/imports/desktop` (multipart con el `.zip` y `camera_station_id`). El back valida y responde sin escribir nada:
   `{new: 320, duplicates: 12, invalid: 8, outside_deployment_range: 3, warnings: [...]}`.
3. **Confirmación:** el usuario revisa y confirma → `POST /api/v1/imports/{id}/confirm` (la vista previa deja el paquete en un temporal con un TTL de 1 h).
4. **Back**, en una transacción por bloques:
   1. crea `desktop_imports` y un `classification_batch` con `source=desktop_import`;
   2. guarda las filas con `source=desktop`;
   3. **re-codifica** cada fotograma con Pillow antes de guardarlo en el *storage*;
   4. salta los duplicados por `(camera_station_id, file_sha256)`.
5. Las clasificaciones importadas quedan `unvalidated` y entran a FL-10 y FL-11 igual que las de la web. Los filtros permiten separar `source=web` y `source=desktop`.

**Validaciones de seguridad del paquete:**

| Riesgo | Control |
|---|---|
| Zip bomb o paquete enorme | Tamaño máximo comprimido (`IMPORT_MAX_MB`, por ejemplo 200 MB) y descomprimido; número máximo de entradas. |
| *Zip slip* (rutas `../`) | Solo se aceptan `manifest.json`, `classifications.jsonl` y `evidence/<sha256>.jpg`; cualquier otra ruta → rechazo. |
| Imágenes maliciosas o con metadatos | Se abre cada JPG con Pillow, se valida que sea imagen y se **re-codifica** (elimina EXIF y cualquier contenido extra). |
| Datos alterados o corruptos | Hash del `jsonl` contra el manifiesto; esquema validado con Pydantic línea por línea; `format_version` soportada. |
| Taxonomía inventada | Cada taxón se valida contra el catálogo de SpeciesNet; si no existe → línea inválida. |
| Fechas incoherentes | `captured_at` fuera del rango colocación–retiro de la cámara → advertencia, no rechazo. |
| Doble importación | El índice único `(camera_station_id, file_sha256)` y el `package_sha256` en `desktop_imports` lo avisan en la vista previa. |

**Errores:**
- `IMPORT_INVALID_PACKAGE` (422);
- `IMPORT_UNSUPPORTED_VERSION` (422);
- `IMPORT_TOO_LARGE` (413);
- `IMPORT_CHECKSUM_MISMATCH` (422);
- `IMPORT_ALREADY_IMPORTED` (409, con la opción de continuar solo con lo nuevo);
- `CAMERA_NOT_OWNED` (403).

---

## 10. Tareas programadas del sistema

| ID | Tarea | Frecuencia | Qué hace |
|---|---|---|---|
| FL-30 | Vencimiento de sesiones anónimas | Cada hora | Las sesiones `active` con `expires_at < ahora` pasan a `expired` y el token deja de funcionar. Luego, para las sesiones `expired` (también las cerradas con "No asociar"):<br>• filas con `anon_retain = true` → **se conservan**;<br>• filas con `anon_retain = false` → se **eliminan físicamente**, con sus fotogramas en el storage.<br>Deja un log con conteos (`retained`, `purged`), nunca con tokens. |
| FL-31 | Limpieza de temporales | Cada hora y al arrancar | Borra los temporales del back y de la IA con más de 1 h, los paquetes de vista previa vencidos y los fotogramas **huérfanos**, es decir, sin fila en `classifications` por un fallo de escritura. **No toca** los fotogramas de registros borrados lógicamente. |
| FL-32 | Backup | Diario | `pg_dump` de la BD + copia del volumen de fotogramas; retención de 7 diarios y 4 semanales; prueba de restauración documentada. |

| FL-33 | *Reaper* de la cola | Cada 5 min | Vuelve a `queued` los ítems `processing` sin `heartbeat_at` por más de 10 min (con un máximo de 3 intentos; después `error`); re-encola los `queued` que no están en Redis (por ejemplo, si Redis se reinició); marca `PROCESSING_EXPIRED` los de más de 24 h y borra su temporal. |

Se implementan como **tareas cron de `arq`**, en el mismo *worker* que procesa la cola, con ejecución única. Registran `flow=FL-3x` en los logs.

**Crecimiento del storage:** como, con la retención activa, nada se borra físicamente, los fotogramas crecen sin límite (~100 KB por clasificación con animal; 100 000 clasificaciones ≈ 10 GB). Es manejable en disco y es la razón principal para dejar listo el paso a S3 (DD-3). El panel del administrador muestra el uso del storage (FL-40).

---

## 11. Flujos del administrador

### 11.1 Matriz de privacidad: qué ve el administrador

| Contenido | Registros (fotogramas, especies, coordenadas, fechas) | Estadísticas taxonómicas | Conteos |
|---|---|---|---|
| **Anónimo** (de cualquier sesión, activa o vencida) | ✅ Sí | ✅ Sí | ✅ Sí |
| **Público** de usuarios | ✅ Sí (como cualquier visitante) | ✅ Sí | ✅ Sí |
| **Privado** de usuarios | ❌ No | ❌ No | ✅ Solo cuántas cámaras y proyectos privados hay (por usuario y en total) |
| **Usuarios** | Nombre, correo, institución, fecha de alta, último acceso, estado | — | ✅ Total, activos, nuevos por mes |

**Reglas:**
- La regla se aplica **en el back**, en un único `AdminScope` (filtro `visibility = public OR anon_session_id IS NOT NULL`) que usan todos los endpoints `/admin/*`. No basta con ocultarlo en el front.
- Los datos privados **no entran** en las estadísticas globales del administrador, ni siquiera agregados. Así se respeta la elección del usuario: si una cámara es privada, sus especies y su ubicación no salen de su cuenta.
- Si un usuario cambia una cámara de pública a privada, desaparece del alcance del administrador desde ese momento, salvo en los conteos.
- Los datos anónimos asociados a una cuenta (FL-04) dejan de ser anónimos y pasan a seguir la visibilidad que elija el usuario (privada por defecto).
- El administrador **no puede** cambiar la visibilidad de contenido ajeno ni editar clasificaciones. Solo puede borrarlas lógicamente y restaurarlas.

### FL-40 · Panel de estadísticas globales
`GET /api/v1/admin/stats?from=&to=&include_deleted=false`. La respuesta tiene cuatro bloques:

1. **Usuarios:**
   - total, activos, desactivados y nuevos por mes;
   - usuarios con al menos una clasificación.
2. **Sesiones anónimas:**
   - total, activas, asociadas a una cuenta y vencidas;
   - **tasa de conversión** (anónimo → cuenta), clasificaciones por sesión.
3. **Contenido, con conteos de todo:**
   - cámaras y proyectos por visibilidad (`public` / `private` / `anonymous`) y borrados;
   - archivos procesados por origen (`web` / `desktop`);
   - errores por `error_code`;
   - uso del storage en GB.
4. **Fauna, solo con datos anónimos y públicos:**
   - las mismas estadísticas que FL-11 (especie, género, familia, riqueza, por mes y por hora);
   - un mapa de calor de las cámaras públicas y anónimas;
   - un filtro por alcance: `anonymous`, `public` o ambos.

Exportación: `GET /api/v1/admin/reports/excel?…` con el mismo alcance. Queda registrada en `admin_audit_log`.

### FL-41 · Exploración de datos anónimos y públicos
1. `GET /api/v1/admin/classifications?scope=anonymous|public&anon_session_id=&from=&to=&taxon=&include_deleted=&page=` y `GET /api/v1/admin/camera-stations?scope=…`.
2. Una vista de tabla y mapa con el detalle de cada registro, incluido el fotograma (`GET /api/v1/admin/classifications/{id}/evidence`, que aplica la misma regla de §11.1).
3. Las sesiones anónimas se muestran como `Anónimo #a91f` (prefijo del hash), sin IP ni datos identificables.
4. Pedir un recurso privado → **404** (no se revela su existencia).

### FL-42 · Borrado lógico y restauración
1. **Borrar:** `POST /api/v1/admin/{entity}/{id}/delete` con `{reason}` (obligatorio). Las entidades son `classifications`, `camera-stations`, `projects` y `anon-sessions` (en cascada sobre todo lo de esa sesión).
   - Sobre contenido **anónimo o público**: permitido.
   - Sobre contenido **privado**: no se puede seleccionar, porque el administrador no lo ve. Si hay que retirar la cuenta completa, se usa FL-43.
2. **Borrado en lote:** `POST /api/v1/admin/delete-batch` `{entity, ids[], reason}`, por ejemplo para spam o archivos de prueba.
3. **Restaurar:** `POST /api/v1/admin/{entity}/{id}/restore`. La restauración en cascada solo devuelve los registros que se borraron en la misma operación (se identifica por `deleted_at` + `deleted_by`).
4. **Efectos:** lo borrado desaparece de los listados, las estadísticas (de usuarios y globales) y las exportaciones. Con `include_deleted=true` el administrador lo sigue viendo, marcado.
5. Cada acción se registra en `admin_audit_log` y en los logs (`event=admin.soft_delete.completed`).

### FL-43 · Gestión de usuarios
1. `GET /api/v1/admin/users?q=&status=&page=` → los datos de la cuenta y los **conteos** de su contenido (cámaras públicas y privadas, proyectos, clasificaciones), sin el contenido privado.
2. **Desactivar:** `POST /api/v1/admin/users/{id}/deactivate` `{reason}`. El usuario no puede iniciar sesión, se revocan sus *refresh tokens* y su contenido **público** deja de mostrarse. No se borra nada.
3. **Reactivar:** `POST /api/v1/admin/users/{id}/reactivate`.
4. El administrador no puede desactivarse a sí mismo.

### FL-44 · Configuración de la retención de datos anónimos
1. **Pantalla "Configuración"** del panel, con el interruptor *"Guardar los datos de usuarios sin sesión"*. Por defecto está **activado**.
2. `GET /api/v1/admin/settings` → `{anon_data_retention: true, updated_by, updated_at}`. Para cambiarlo: `PUT /api/v1/admin/settings` `{anon_data_retention: false, reason}`.
3. **Efecto solo hacia adelante:**
   - el nuevo valor se aplica a los registros anónimos que se **creen desde ese momento**, porque cada fila guarda `anon_retain` al crearse;
   - **los datos anteriores nunca se eliminan ni cambian** por modificar este valor;
   - en una sesión anónima abierta durante el cambio, lo creado antes conserva el valor anterior y lo creado después usa el nuevo.
4. Las sesiones nuevas reciben el valor vigente en `data_retention` (FL-03), y el front muestra el aviso que corresponde. Una sesión abierta antes del cambio ve el aviso nuevo en su siguiente `GET /anon-sessions/current`.
5. El cambio queda en `admin_audit_log` (`update_setting`, con el valor anterior y el nuevo) y en los logs (`event=admin.setting.updated`).
6. **Panel:** muestra el historial de cambios del interruptor y, en FL-40, cuántos registros anónimos se conservaron y cuántos se eliminaron por la configuración.

### FL-45 · Monitor de la cola y del correo
`GET /api/v1/admin/queue`: *workers* activos, ítems en cola y en proceso, tiempo medio, antigüedad del más viejo, pendientes por dueño, resultados de la última hora y uso de la cuota de correo (diaria y mensual). Si el ítem más viejo lleva más de 30 min en cola, el panel lo marca en rojo.

### FL-46 · Desempeño del modelo y especies no catalogadas
- `model_feedback` en `GET /admin/stats`:
  - % confirmadas;
  - % corregidas con una alternativa;
  - % corregidas desde el catálogo;
  - % no catalogadas;
  - % rechazadas;
  - las confusiones más frecuentes (predicho → corregido).
- `GET /api/v1/admin/unlisted-suggestions`: los nombres sugeridos, agrupados.

Es la base objetiva para futuras mejoras del modelo, fuera del TDR. Solo usa datos anónimos y públicos.

### Cuenta de administrador
- **Habrá un único administrador.**
- No se crea desde la web, sino con un comando en el servidor: `python -m app.cli create-admin --email …` (la contraseña se pide por consola). El comando falla si ya existe un administrador.
- `python -m app.cli reset-admin-password` permite cambiar la contraseña; `--transfer-to <email>` pasa el rol a otra cuenta.
- **Seguridad:**
  - contraseña de 12 caracteres o más;
  - *rate limit* más estricto en el login;
  - *access token* corto (15 min);
  - todas las rutas `/api/v1/admin/*` exigen `require_role("admin")`;
  - recomendado: restringir `/api/v1/admin/*` por IP en el proxy, o agregar un segundo factor (TOTP) en una fase posterior.

---

## 12. Máquinas de estado

**Sesión anónima:**
```
active ──(claim)──▶ claimed (los datos pasan a la cuenta)
  │
  └──(vence por inactividad / "no asociar")──▶ expired (el token no sirve)
                                                 ├─ filas anon_retain=true  → se conservan (visibles para el admin)
                                                 └─ filas anon_retain=false → se eliminan físicamente (FL-30)
```

**Contenido (cualquier entidad):**
```
activo ──(dueño o admin: delete)──▶ borrado lógico ──(admin: restore)──▶ activo
```

**Clasificación (procesamiento):**
```
(subida) ──▶ queued ──▶ processing ──▶ done
               │  ▲          │
               │  └─(reaper)─┤ (sin latido > 10 min)
               │             └──▶ error (AI_TIMEOUT, MEDIA_DECODE_FAILED, PROCESSING_EXPIRED…) ──(retry)──▶ queued
               └──(cancel)──▶ cancelled
```

**Clasificación (validación):**
```
unvalidated ──▶ confirmed
     │    ├───▶ corrected (corrected_* poblado; correction_source = alternative | catalog)
     │    └───▶ corrected_unlisted (suggested_name; taxón superior opcional)
     ├────────▶ rejected (la IA se equivocó: no hay animal; no cuenta)
     └────────▶ discarded_repeat (mismo animal que otro registro de la ráfaga; no cuenta, no es error de la IA)
 (cualquier estado validado puede volver a editarse; se registra quién y cuándo)
```

**Lote:**
```
processing ──▶ completed | completed_with_errors | failed
```

---

## 13. Puntos a confirmar con WWF

**Estado al 07/11/2026:** todas las decisiones de alcance están tomadas. Solo queda **informar** a WWF de lo que amplía o ajusta el TDR.

| # | Tema | Estado |
|---|---|---|
| D1 | Se guarda el fotograma de evidencia, pero no los videos | ✅ Decidido (DD-3). **Informar.** |
| D2 | Ubicación de las cámaras públicas | ✅ Decidido: redondeada a ~1 km para quien no es dueño, con una advertencia antes de publicar (DD-17). |
| D3 | Columnas del Excel | ✅ Aprobadas por Diego (08/11/2026): [API §11](contratos/API_BACK_FRONT.md#11-reportes-excel-y-pdf). |
| D4 | Formatos y peso | ✅ Decidido: formatos comunes de cámaras trampa, foto y video, para cualquier biólogo; 300 MB (DD-18). Validación de la IA con los **videos de prueba que ya se entregaron** (IA-10). |
| D5 | Datos anónimos conservados para estadísticas (configurable) | ✅ Decidido (DD-2). **Informar**, junto con el texto del aviso de uso de datos. |
| D6 | Sincronización escritorio → web | ✅ Decidido (DD-10). **Informar** como valor agregado. |
| D7 | Subir siempre a una cámara registrada | ✅ Decidido: también para el anónimo (TDR §3.1). |
| D8 | Estadísticas complementarias | ✅ Decidido (DD-5). **Informar.** |
| D10 | Ráfagas | ✅ Decidido (DD-16, FL-16). |
| D11 | Región | ✅ Decidido: sin restricción; el mapa arranca en Santa Cruz. |
