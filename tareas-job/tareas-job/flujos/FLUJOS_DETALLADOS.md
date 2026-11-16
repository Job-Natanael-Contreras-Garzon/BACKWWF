# Flujos detallados del sistema

> Documento interno · CETERIS404 · v1 — 07/11/2026
> **Qué es:** cada recorrido del usuario paso a paso: qué ve, qué hace, qué llamada se dispara, qué responde el sistema y qué se muestra después. Sirve para implementar, para probar (cada flujo es un caso e2e) y para escribir el manual de usuario.
> **Relación:** las reglas de negocio y el modelo de datos están en [FLUJOS_SISTEMA.md](../FLUJOS_SISTEMA.md); los endpoints y los JSON, en [contratos/API_BACK_FRONT.md](../contratos/API_BACK_FRONT.md) (citado como **API §n**); la IA, en [contratos/API_IA_BACK.md](../contratos/API_IA_BACK.md); el paquete, en [contratos/PAQUETE_ESCRITORIO.md](../contratos/PAQUETE_ESCRITORIO.md).
> **Notación:** cada flujo indica su ID de sistema (`FL-xx`), que es el valor de `flow` en los logs. Los casos borde (`CB-xx`) están en [CASOS_BORDE.md](CASOS_BORDE.md).

---

## Índice

0. [Mapa de pantallas](#0-mapa-de-pantallas)
1. [A · Comunes](#a--comunes)
2. [B · Usuario sin sesión](#b--usuario-sin-sesión)
3. [C · Cuenta: registro, login y sesión](#c--cuenta-registro-login-y-sesión)
4. [D · Cámaras trampa](#d--cámaras-trampa)
5. [E · Proyectos](#e--proyectos)
6. [F · Subir y clasificar videos e imágenes](#f--subir-y-clasificar-videos-e-imágenes)
7. [G · Validación](#g--validación)
8. [H · Estadísticas y reportes](#h--estadísticas-y-reportes)
9. [I · App de escritorio y sincronización con la web](#i--app-de-escritorio-y-sincronización-con-la-web)
10. [J · Administrador](#j--administrador)
11. [Mensajes de error en pantalla](#k--mensajes-de-error-en-pantalla)

---

## 0. Mapa de pantallas

| Pantalla / componente | Ruta o contexto | Hoy en el front | Qué hace |
|---|---|---|---|
| **Mapa principal** | `/` | `MainMapLayout`, `FullScreenMap` | Mapa con marcadores de cámaras (propias y públicas), barra superior y FAB. |
| Barra superior | `/` | (parcial) | Logo; **"Iniciar sesión / Registrarse"** o **menú de usuario** (nombre, Mi perfil, Cerrar sesión, *Panel admin* si es admin). |
| **`AnonBanner`** | `/` sin sesión | ❌ nuevo | Franja fija: "Trabajas sin cuenta…" con el botón "Crear cuenta". |
| **`DataNoticeModal`** | Primera acción anónima | ❌ nuevo | Aviso de uso de datos según `data_retention`. |
| **FAB** (`CreationFAB`) | `/` | ✅ | **Colocar cámara** · **Nuevo proyecto** · **Clasificar archivos** · **Importar desde escritorio** (este último solo con sesión). |
| `FilterPanel` | `/` | ✅ | Filtros del mapa: mías / públicas / todas, instaladas, búsqueda. |
| **Panel de cámara** | `/?camera=<id>` | `CameraDataModal` (rehacer) | Pestañas: **Datos** · **Clasificaciones** · **Estadísticas** · **Validación** · **Importaciones**. |
| **Panel de proyecto** | `/?project=<id>` | `ProjectGiantModal` (rehacer) | Pestañas: **Resumen** · **Cámaras** · **Estadísticas** · **Clasificaciones**. |
| Lista "Mis proyectos" | `/` | `ProjectListModal` | Proyectos propios y públicos. |
| **`CameraFormModal`** | Colocar o editar cámara | `CreateStationModal` (rehacer) | Formulario de cámara (API §1.5). |
| `ProjectFormModal` | Nuevo o editar proyecto | `CreateProjectModal` | Formulario de proyecto. |
| **`UploadWidget`** | Clasificar | ✅ (sin montar) | Selección de archivos y validación previa; entrega los archivos al `UploadManager`. |
| **`UploadTray`** | **Todas las pantallas** | ❌ nuevo | Bandeja flotante (abajo a la derecha) del `UploadManager` global: lotes activos, subiendo, en cola (posición y espera), analizando, listos y con error. Permite cancelar y reintentar. Sigue funcionando al navegar. |
| **`NearbyCamerasDialog`** | Al colocar o mover una cámara | ❌ nuevo | Cámaras cercanas y opciones de CB-01…CB-06. |
| (formatos) | — | — | Formatos aceptados: [API §4.1](../contratos/API_BACK_FRONT.md#41-get-configpublic). |
| **`ResultsGallery`** | Tras clasificar o en la pestaña Clasificaciones | ❌ nuevo | Tarjetas por archivo con fotograma, taxonomía, `mm:ss` y estado. |
| **`ValidationDeck`** | Pestaña Validación | ✅ (estático) | Revisión de una en una: confirmar, corregir o rechazar. |
| **`ImportDesktopModal`** | Importar desde escritorio | ❌ nuevo | Subir el `.wwm.zip`, vista previa y confirmación. |
| **`ClaimDialog`** | Tras el login o registro con datos anónimos | ❌ nuevo | "¿Asociar N clasificaciones…?". |
| Login / Registro / Recuperar | `/login`, `/registro`, `/recuperar`, `/restablecer?token=` | `AuthLayout` | Formularios. |
| Perfil | `/perfil` | ❌ nuevo | Nombre, institución, cambio de contraseña. |
| **Panel admin** | `/admin/*` | `UserManagerModal` (se reemplaza) | Resumen, Fauna, Explorar, Sesiones anónimas, Usuarios, Configuración, Auditoría. |

**Estados comunes que toda pantalla con datos debe manejar:** *cargando* (skeleton), *vacío* (mensaje + acción sugerida), *error* (mensaje del catálogo + "Código de referencia: `<request_id>`" + Reintentar). Nunca se muestran datos de ejemplo.

---

## A · Comunes

### A1 · Arranque de la aplicación
| # | Front | Llamada | Resultado |
|---|---|---|---|
| 1 | Carga la SPA | `GET /config/public` (API §4.1) | Guarda en memoria los límites, los formatos y `anon_data_retention`. Si falla, muestra una pantalla de error con Reintentar, porque sin configuración no se puede validar nada. |
| 2 | ¿Hay un `refresh_token` en `localStorage`? | `POST /auth/refresh` → `GET /auth/me` | Si hay sesión → modo **usuario** (C3). Si falla → borra los tokens y pasa a modo **visitante**. |
| 3 | Sin sesión: ¿hay `anon_token` en `sessionStorage`? | `GET /anon-sessions/current` (API §3.2) | Si es válida → modo **anónimo** con datos (B5). Si da 401 → borra el token y pasa a modo **visitante**. |
| 4 | Carga el mapa, **centrado en Santa Cruz** (`config.map.default_center`, zoom 8). Si el usuario tiene cámaras, en las visitas siguientes se centra en ellas. | `GET /camera-stations?scope=all&view=map&bbox=…` (API §5.1) | Marcadores: los propios en un color y los públicos ajenos en otro. Se recarga al mover el mapa, con *debounce* de 400 ms. |

**Aceptación:** con la API caída, el usuario ve un error con código de referencia, nunca datos inventados.

---

## B · Usuario sin sesión

### B1 · Primera visita: explorar lo público · FL-13
| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | Abre el sitio | Mapa + `AnonBanner` | A1 | Ve solo las cámaras **públicas**. |
| 2 | Hace clic en un marcador público | Panel de cámara en solo lectura (pestañas Datos, Clasificaciones y Estadísticas) | `GET /camera-stations/{id}` · `GET /camera-stations/{id}/stats` · `GET /classifications?camera_station_id=` | Ve los datos de la cámara, sus estadísticas y las clasificaciones con fotograma (`GET …/evidence`). |
| 3 | Abre un proyecto público | Panel de proyecto en solo lectura | `GET /projects/{id}` · `GET /projects/{id}/stats` | Ve las estadísticas agregadas de sus cámaras públicas. |
| 4 | Descarga un reporte | Botones Excel y PDF | `GET /reports/excel?…` | Descarga lo público. |

No se crea sesión anónima solo por mirar.

### B2 · Clasificar como anónimo · FL-03 + FL-05 + FL-08
**Regla (D7):** también sin cuenta se sube **a una cámara registrada** (TDR §3.1). La única diferencia con un usuario es que la cámara es temporal y siempre privada.
**Precondición:** visitante, sin token anónimo.

| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | FAB → **Clasificar archivos** | — | — | — |
| 2 | — | Como no hay token, lo crea | `POST /anon-sessions` (API §3.1) | Guarda `anon_token` en `sessionStorage` y `data_retention` en el store. |
| 3 | — | Muestra `DataNoticeModal` | — | **Con retención:** debe aceptarlo para seguir. **Sin retención:** aviso informativo. |
| 4 | — | ¿Tiene cámaras en esta sesión? **No** → "Para clasificar, primero registra la cámara trampa donde se tomaron los archivos", con el botón **Colocar cámara** → B3 pasos 1–3 → vuelve aquí con la cámara preseleccionada. **Sí** → selector de cámara (obligatorio). | `GET /camera-stations?scope=mine` | — |
| 5 | Elige los archivos | Validación local: extensión según `config.media` (formatos comunes de cámaras trampa, foto y video), peso ≤ `max_file_mb` y duración ≤ 15 s cuando el navegador puede leerla | — | Los inválidos se marcan en rojo con su motivo y no se envían. |
| 6 | Pulsa **Clasificar** | Crea el lote y entrega los archivos al `UploadManager` | `POST /classification-batches` `{camera_station_id, expected_files:3}` | `Batch` con `status:open`. La `UploadTray` aparece. |
| 7 | — | Envía los archivos, 3 en paralelo: *Subiendo n %* → **En cola (posición 4 · ~3 min)** | `POST /classification-batches/{id}/files` (API §7.2) | **202** `queued` en segundos; los inválidos o duplicados vuelven con **200** `error`. |
| 8 | **Sigue usando la app** | La `UploadTray` muestra el progreso; *polling* cada 3 s | `GET /classification-batches?active=true` | *Analizando* → ✅ / ⚠️. |
| 9 | — | Al enviar todo | `POST /classification-batches/{id}/complete` | — |
| 10 | — | Toast "3 archivos analizados · 2 con fauna" con **Ver resultados** | `GET /classification-batches/{id}` | — |
| 11 | Ve los resultados | `ResultsGallery` en la pestaña Clasificaciones de la cámara | `GET /classifications/{id}/evidence` (*blob*) | El fotograma, la especie común y la científica, el género, la familia, la confianza, el `rank` y el **mm:ss**. Lo que no tiene fauna va aparte. |

### B3 · Registrar una cámara como anónimo y clasificar en ella · FL-05 + FL-08
| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | FAB → **Colocar cámara** | El cursor pasa a modo colocación con el aviso "Haz clic en el mapa" | — | Crea la sesión anónima si no existe (B2 pasos 2 y 3). |
| 2 | Hace clic en el mapa | Abre `CameraFormModal` con la latitud y la longitud precargadas (editables) | — | El campo "Pública" está **deshabilitado** con el *tooltip* "Regístrate para publicar". |
| 3 | Completa código, colocación, "sigue instalada" y observaciones | Validación local (fechas, campos obligatorios) | `POST /camera-stations` | La cámara aparece en el mapa como propia. |
| 5 | En el panel de la cámara, **Clasificar archivos** | `UploadWidget` con la cámara preseleccionada | B2 pasos 5–11 | Los resultados aparecen en la pestaña **Clasificaciones**. |

**Errores:** `CAMERA_CODE_TAKEN`, `CAMERA_INVALID_DATES`, `ANON_LIMIT_REACHED` (5 cámaras).

### B4 · Crear un proyecto como anónimo · FL-07
Igual que E1–E3, pero la visibilidad es siempre privada. Si intenta publicarlo → el control está deshabilitado (y el back responde `ANON_PUBLIC_NOT_ALLOWED`).

### B5 · Volver con F5 en la misma pestaña · FL-03
| # | Front | Llamada | Resultado |
|---|---|---|---|
| 1 | A1 paso 3 | `GET /anon-sessions/current` | Recupera `counts` y `data_retention`. |
| 2 | Recarga el mapa | `GET /camera-stations?scope=all&view=map` | Aparecen sus cámaras anónimas. |
| 3 | Reconstruye la `UploadTray` | `GET /classification-batches?active=true` | Los ítems en cola o en proceso siguen avanzando. Los que no se llegaron a **enviar** se marcan "No enviado: vuelve a seleccionarlo" (CB-32). |

### B6 · Cerrar el navegador
No hay llamada. `sessionStorage` desaparece. Al volver, A1 no encuentra token → modo visitante.
- Con `anon_retain = true`: los datos quedan en la BD como anónimos, visibles solo para el admin.
- Con `anon_retain = false`: FL-30 los elimina al vencer la sesión, a las 24 h.

### B7 · Registrarse y asociar los datos · FL-01 + FL-04
| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | "Crear cuenta" en `AnonBanner` | `/registro` | — | — |
| 2 | Completa el formulario | Validación local (correo, contraseña de 8 caracteres o más con letra y número) | `POST /auth/register` + `X-Anon-Token` (API §2.1) | Tokens + `anon_session.has_data = true`, con sus conteos. |
| 3 | — | Guarda los tokens y abre **`ClaimDialog`**: "Tienes 12 clasificaciones y 1 cámara de esta sesión. ¿Asociarlas a tu cuenta?" | — | — |
| 4a | **Asociar** | — | `POST /anon-sessions/claim` (API §3.3) | Toast "12 clasificaciones y 1 cámara asociadas". Si hay `renamed_camera_stations`: "Tu cámara CAM01 pasó a llamarse CAM01-2 porque ya tenías ese código". |
| 4b | **No asociar** | Confirmación: "No podrás recuperarlas" | `POST /anon-sessions/current/close` | — |
| 5 | — | Borra `anon_token`, oculta `AnonBanner` y recarga el mapa | `GET /camera-stations?…` | Pasa a modo usuario. Lo asociado queda **privado** por defecto; puede publicarlo después (D3). |

**Aceptación:** con "Asociar", las clasificaciones, las validaciones y las cámaras aparecen en la cuenta; con "No asociar", ya no aparecen en ninguna parte para el usuario.

### B8 · Iniciar sesión con datos anónimos · FL-02 + FL-04
Igual que B7, pero desde `/login` con `POST /auth/login`. Si la sesión anónima no tiene datos (`has_data:false`), no se muestra `ClaimDialog` y se cierra la sesión anónima sin preguntar.

### B9 · Límite anónimo alcanzado · FL-03
| Situación | Respuesta | Front |
|---|---|---|
| Crear un lote que supera `max_files` | `ANON_LIMIT_REACHED` en `POST /classification-batches` | Modal: "Sin cuenta puedes clasificar hasta 50 archivos. Te quedan 8. Crea una cuenta gratis para seguir", con los botones **Crear cuenta** y **Clasificar solo 8**. |
| La sexta cámara | `ANON_LIMIT_REACHED` | Igual, con el límite de cámaras. |
| El token venció (más de 24 h de inactividad con la pestaña abierta) | `ANON_SESSION_EXPIRED` | Borra el token: "Tu sesión sin cuenta expiró; sus datos ya no están disponibles". Al volver a guardar algo, crea una sesión nueva. |

---

## C · Cuenta: registro, login y sesión

### C1 · Registro sin datos anónimos · FL-01
| # | Front | Llamada | Resultado |
|---|---|---|---|
| 1 | `/registro`: nombre, correo, contraseña, confirmación, institución (opcional) | — | La validación local muestra los errores por campo. |
| 2 | Enviar | `POST /auth/register` | 201 → guarda los tokens (§C3) → redirige a `/` con el toast "Bienvenida, Ana". |
| — | Error `AUTH_EMAIL_TAKEN` | — | Error en el campo correo, con el enlace "¿Ya tienes cuenta? Inicia sesión". |
| — | Error `VALIDATION_ERROR` | — | Muestra `error.details[]` en cada campo. |

### C2 · Login · FL-02
| # | Front | Llamada | Resultado |
|---|---|---|---|
| 1 | `/login`: correo y contraseña | `POST /auth/login` | 200 → tokens. Si es admin (`user.role=admin`), el menú muestra "Panel admin". |
| — | `AUTH_INVALID_CREDENTIALS` | — | "Correo o contraseña incorrectos" (sin decir cuál de los dos). |
| — | `ACCOUNT_DISABLED` | — | "Tu cuenta está desactivada. Contacta al administrador." |
| — | `RATE_LIMITED` | — | "Demasiados intentos. Espera un minuto." Se desactiva el botón durante 60 s. |

### C3 · Mantener la sesión · FL-02
- **Almacenamiento:** `access_token` **en memoria** (store, sin `persist`) y `refresh_token` en `localStorage` (FE-40).
- **Al recargar:** A1 paso 2.
- **Cuando vence el access:** el interceptor recibe 401 `AUTH_TOKEN_EXPIRED` → hace **un solo** `POST /auth/refresh` (las peticiones concurrentes esperan esa misma promesa) → reintenta la original. Si el refresh falla → logout local y "Tu sesión expiró", con redirección a `/login?next=<ruta>`.

### C4 · Cerrar sesión · FL-02
Menú → **Cerrar sesión** → `POST /auth/logout {refresh_token}` → borra los tokens y los stores → vuelve a `/` en modo visitante. Si la llamada falla, igual limpia todo lo local.

### C5 · Perfil y contraseña · FL-02
`/perfil`: `GET /auth/me` → editar el nombre y la institución → `PATCH /auth/me`. Cambiar la contraseña → `POST /auth/me/password` → "Contraseña actualizada; se cerraron tus otras sesiones".

### C6 · Recuperar la contraseña · FL-14
| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | En `/login`, "¿Olvidaste tu contraseña?" | `/recuperar`: campo de correo | — | — |
| 2 | Enviar | — | `POST /auth/password/forgot` | Siempre: "Si el correo está registrado, recibirás un enlace en unos minutos. Revisa también la carpeta de spam." El botón queda deshabilitado 60 s. |
| — | `EMAIL_TEMPORARILY_UNAVAILABLE` | "No podemos enviar correos en este momento. Intenta mañana o contacta al administrador." | — | — |
| 3 | Abre el enlace del correo | `/restablecer?token=…` | `GET /auth/password/reset/validate` | Si es válido: formulario con "Restableciendo la contraseña de a\*\*\*@wwf.org.bo". Si no: "El enlace venció o ya se usó", con **Pedir otro**. |
| 4 | Escribe la nueva contraseña dos veces | Validación local | `POST /auth/password/reset` | "Contraseña actualizada" → `/login`. Las demás sesiones se cierran. |

---

## D · Cámaras trampa

### D1 · Registrar una cámara con clic en el mapa · FL-05
**Precondición:** usuario (o anónimo, con B3).

| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | FAB → **Colocar cámara** | Modo colocación: cursor en cruz y aviso "Haz clic donde está la cámara · Esc para cancelar" | — | — |
| 2 | Hace clic | Marcador temporal + `CameraFormModal` | — | La latitud y la longitud se precargan con 6 decimales y se pueden editar o pegar desde un GPS. |
| 3 | Completa los campos | Campos del API §1.5:<br>• **Código** (obligatorio);<br>• Nombre;<br>• **Fecha y hora de colocación** (`datetime-local`);<br>• **¿Sigue instalada?** (interruptor; si está apagado, pide la **fecha y hora de retiro**);<br>• **Observaciones**;<br>• **Pública / Privada** (por defecto privada). | — | Validación local: retiro ≥ colocación. |
| 4 | Guardar | **Primero** verifica la cercanía | `GET /camera-stations/nearby?lat=&lng=&radius_m=30&deployed_at=&retrieved_at=` (API §5.7) | Si no hay nada cerca → paso 5. Si hay → `NearbyCamerasDialog` (paso 4b). |
| 4b | Elige una opción | Muestra "Tienes **CAM01** a 12 m (instalada desde el 01/03/2026)" y, si existen, "Hay 1 cámara pública de otro investigador a 8 m". Opciones: **Es otra cámara en el mismo punto** (sigue al paso 5) · **Reinstalé CAM01** (D5) · **Abrir CAM01** (cancela). | — | CB-01…CB-06 |
| 5 | — | — | `POST /camera-stations` | 201 → el marcador pasa a definitivo y se abre el panel de la cámara con "Clasificar archivos" destacado. Si `meta.warnings` trae `CAMERA_COORDS_SUSPECT`, se muestra "¿Latitud y longitud invertidas?", con el botón **Intercambiar** (CB-07). Las ubicaciones fuera de Bolivia son válidas y no generan aviso. |
| — | `CAMERA_CODE_TAKEN` | — | — | Error en el campo código: "Ya tienes una cámara con ese código". |

### D2 · Editar o retirar una cámara · FL-06
Panel de la cámara → pestaña **Datos** → **Editar** (solo si `owner.is_mine`) → `CameraFormModal` precargado → `PATCH /camera-stations/{id}`.
- **Retirar:** el atajo "Marcar como retirada" abre un selector de fecha y hora → `PATCH {still_installed:false, retrieved_at}`.
- **Mover la ubicación:** el botón "Reubicar en el mapa" vuelve al modo colocación → `PATCH {latitude, longitude}`.

### D3 · Cambiar la visibilidad · FL-06
Interruptor **Pública / Privada** en la pestaña Datos (y la opción "Pública" al crear la cámara o el proyecto) → **advertencia antes de publicar** (DD-17):
> **¿Hacer pública esta cámara?** Cualquier persona podrá ver:
> - su **ubicación aproximada** (~1 km; la exacta solo la ves tú);
> - las especies registradas, sus estadísticas y los **fotogramas de evidencia**.
>
> Ten en cuenta que los fotogramas pueden mostrar referencias del lugar. Si registra especies sensibles (por ejemplo, jaguar), evalúa si conviene mantenerla privada.
>
> [Cancelar] [Hacer pública]

→ `PATCH {visibility}`. Un anónimo ve el interruptor deshabilitado.

### D4 · Eliminar una cámara · FL-06
**Eliminar** → `ConfirmDeleteModal`: "Se ocultarán la cámara y sus 120 clasificaciones. Esta acción no se puede deshacer desde tu cuenta" → `DELETE /camera-stations/{id}` → 204 → desaparece del mapa y de sus proyectos.

### D5 · Reinstalar una cámara en el mismo punto · FL-15
Desde `NearbyCamerasDialog` ("Reinstalé CAM01") o desde la pestaña Datos → **Nueva instalación en este punto**:
1. Un modal muestra el código sugerido `CAM01-2` (editable), la nueva fecha y hora de colocación, observaciones y la casilla "Marcar CAM01 como retirada el …" (marcada si sigue instalada).
2. `POST /camera-stations/{id}/redeploy` (API §5.8).
3. Se abre el panel de la cámara nueva, con el aviso "Instalación anterior: CAM01 (01/03 – 02/05)" enlazado. La cámara nueva ya está en los mismos proyectos.

### D6 · Corregir la hora de la cámara (P2) · CB-18
Pestaña Datos → **Corregir la hora de la cámara** → indicar el desfase ("+1 h", o "la foto que dice 2000-01-01 00:00 fue el 2026-03-01 08:30") y el rango → `POST /camera-stations/{id}/time-offset` → "Se corrigieron 118 fechas".

---

## E · Proyectos

### E1 · Crear un proyecto · FL-07
| # | Front | Llamada | Resultado |
|---|---|---|---|
| 1 | FAB → **Nuevo proyecto** → `ProjectFormModal`: nombre, descripción, Pública/Privada y el selector múltiple "Cámaras a incluir" (solo las propias: `GET /camera-stations?scope=mine`) | — | — |
| 2 | Guardar | `POST /projects` (API §6.2) | 201 `ProjectDetail` → abre el panel del proyecto, en la pestaña Cámaras. |

### E2 · Asociar una cámara existente · FL-07
Panel del proyecto → **Cámaras** → **+ Asociar cámara existente** → lista de las cámaras propias no asociadas → elegir → `POST /projects/{id}/camera-stations {camera_station_id}` → se actualiza la lista y el mapa resalta las cámaras del proyecto.
**Errores:** `ALREADY_ASSOCIATED` (no debería pasar, porque el selector filtra), `CAMERA_NOT_OWNED`.

### E3 · Crear una cámara dentro del proyecto · FL-07
Panel del proyecto → **+ Registrar nueva cámara** → D1, pero el `CameraFormModal` lleva el `project_id` → `POST /camera-stations {…, project_id}` → la cámara queda creada **y** asociada.

### E4 · Quitar una cámara del proyecto · FL-07
En la lista de cámaras → **Quitar del proyecto** → confirmación: "La cámara no se borra" → `DELETE /projects/{id}/camera-stations/{cid}`.

### E5 · Editar o cambiar la visibilidad · FL-07
**Editar** → `PATCH /projects/{id}`. Al hacerlo **público**, la advertencia de D3 adaptada al proyecto: "Los demás verán la ubicación aproximada de sus cámaras públicas, sus especies, estadísticas y fotogramas. Las cámaras privadas del proyecto seguirán privadas".

### E6 · Eliminar un proyecto · FL-07
`DELETE /projects/{id}` → confirmación: "Las cámaras no se eliminan".

---

## F · Subir y clasificar videos e imágenes

### F1 · Subir archivos a una cámara · FL-08 + FL-09
**Precondición:** usuario con al menos una cámara. Si no tiene, el widget propone "Registra primero una cámara" (D1).

| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | Desde el panel de la cámara, o el FAB → **Clasificar archivos** | `UploadWidget`: selector de cámara **obligatorio** (preseleccionado si viene del panel) + zona de arrastre | — | — |
| 2 | Arrastra 20 archivos | Validación local por archivo (formato, peso, duración); los inválidos se muestran pero no se envían | — | — |
| 3 | **Clasificar** | El widget se cierra y entrega el trabajo al `UploadManager` | `POST /classification-batches {camera_station_id, expected_files:18}` | La `UploadTray` muestra "CAM01 · 0 de 18". |
| 4 | **Navega libremente** (otra cámara, estadísticas, un proyecto) | El `UploadManager` envía 3 archivos en paralelo; la bandeja muestra *Subiendo n %* | `POST /classification-batches/{id}/files` × 18 | Cada archivo responde en segundos con **202** `queued` (posición y espera) o **200** `error` (inválido o duplicado). Mientras haya bytes subiendo, el aviso de `beforeunload` está activo (CB-32). |
| 5 | — | Cuando se envió todo: "Ya puedes cerrar la página; el análisis continúa en el servidor" | `POST /classification-batches/{id}/complete` | — |
| 6 | — | *Polling* de la bandeja | `GET /classification-batches?active=true` cada 3 s | "CAM01 · 11 listos · 5 en cola (~4 min) · 1 analizando · 1 con error". |
| 7 | — | Al terminar: toast y notificación del navegador (si dio permiso) "CAM01: 18 archivos analizados" | — | Acciones: **Ver resultados**, **Validar ahora** (G1) y **Reintentar los fallidos**. |

**Acciones en la bandeja:**
- **Cancelar lo que está en cola** → `POST …/cancel`; cancelar uno → `DELETE …/items/{i}` (CB-40).
- **Reintentar** un ítem con error de IA → `POST …/items/{i}/retry`; con `RETRY_FILE_UNAVAILABLE`, pide volver a seleccionar el archivo.
- Si el usuario llega a su tope (`QUEUE_USER_LIMIT`), el `UploadManager` **pausa** el envío y lo reanuda solo cuando bajan los pendientes (CB-34). Con `QUEUE_FULL` o `QUEUE_UNAVAILABLE`, reintenta con *backoff* (1, 2 y 5 min) y lo indica en la bandeja.

**Errores por archivo** (la tarjeta muestra el mensaje del catálogo, §K):

| `error.code` | Tarjeta | Acción ofrecida |
|---|---|---|
| `MEDIA_DURATION_EXCEEDED` | "Dura 16,2 s; máximo 15 s" | Ninguna (el archivo no es válido) |
| `MEDIA_UNSUPPORTED_FORMAT` / `MEDIA_TOO_LARGE` / `MEDIA_DECODE_FAILED` | Mensaje específico | Ninguna |
| `DUPLICATE_FILE` | "Ya estaba clasificado en esta cámara" | **Ver clasificación** |
| `DUPLICATE_FILE_OTHER_CAMERA` | "Ya está clasificado en CAM02" | **Mover a esta cámara** (`PATCH /classifications/{id}`) · **Ignorar** |
| `AI_TIMEOUT` / `AI_UNAVAILABLE` / `AI_NOT_READY` / `AI_BAD_RESPONSE` / `STORAGE_WRITE_FAILED` | "No se pudo analizar. Código de referencia: …" | **Reintentar** |
| `PROCESSING_EXPIRED` | "Estuvo demasiado tiempo en espera" | Volver a subirlo |
| `CANCELLED_BY_USER` | "Cancelado" | Volver a encolar (si el temporal existe) |

### F2 · Ver los resultados de una cámara · FL-08
Panel de la cámara → **Clasificaciones** → `GET /classifications?camera_station_id=…&page=1&page_size=24&sort=-captured_at` → `ResultsGallery` paginada.
- **Filtros:** categoría, especie (autocompletado del catálogo filtrado a las especies presentes), estado de validación, fechas, confianza menor que X y origen (web o escritorio).
- **Detalle:** clic en una tarjeta → modal con el fotograma grande y el recuadro (dibujado con `bbox` sobre el JPEG), `mm:ss` ("Detectado en el segundo 00:07"), las alternativas (top 2–3), los metadatos del archivo, `captured_at` y su fuente ("Fecha tomada del nombre del archivo"), el modelo, y los botones de validación (G).

### F3 · Historial de subidas · FL-08
Pestaña **Clasificaciones** → "Historial de subidas" → `GET /classification-batches?camera_station_id=` → lista con fecha, cantidades y estado. Clic → `GET /classification-batches/{id}`.

### F4 · Borrar una clasificación · FL-08
En el detalle → **Eliminar** → `DELETE /classifications/{id}`, que deja de contar en las estadísticas.

---

## G · Validación

### G1 · Revisar de una en una · FL-10
| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | Pestaña **Validación** de la cámara (o del proyecto) | `ValidationDeck`: carga las pendientes ordenadas por **confianza ascendente**, para revisar primero las dudosas | `GET /classifications?camera_station_id=&status=done&validation_status=unvalidated&category=animal,person,vehicle&sort=confidence&page_size=50` | Tarjeta grande con el fotograma y la **especie de mayor confianza** ("Jaguar · *Panthera onca* · 94 %"). Contador: "Pendientes: 39". |
| 2 | **✓ Correcto** (atajo `C`) | — | `PUT /classifications/{id}/validation {action:"confirm"}` | Pasa a la siguiente. |
| 3 | **✗ No es esta especie** (atajo `N`) | Despliega las opciones:<br>**a.** las alternativas (hasta 2) como botones con su %, por ejemplo "Puma · 3 %" y "Ocelote · 1 %";<br>**b.** **Buscar otra especie…** (autocompletado del catálogo, `GET /catalog/species?q=`);<br>**c.** **No está en el catálogo**;<br>**d.** **No hay ningún animal**. | — | — |
| 3a | Elige una alternativa | — | `PUT … {action:"correct", label_id, correction_source:"alternative"}` | "Corregido: Puma concolor". |
| 3b | Busca y elige otra | — | `PUT … {action:"correct", label_id, correction_source:"catalog"}` | Ídem. |
| 3c | No está en el catálogo | Campo **"¿Qué especie es?"** (texto libre, obligatorio, por ejemplo "Leopardus colocolo") + "¿Conoces el género o la familia?" (autocompletado opcional del catálogo, solo taxones superiores) + notas | `PUT … {action:"correct_unlisted", suggested_name, label_id?}` | "Registrado como especie no catalogada". Cuenta en el género o familia indicados, o en "No identificados". Queda como sugerencia para futuras mejoras (CB-65). |
| 3d | No hay ningún animal | Notas opcionales ("viento", "lluvia") | `PUT … {action:"reject"}` | Deja de contar en las estadísticas. |
| 4 | **Deshacer** la última acción (atajo `Z`) | — | `PUT … {action:"reset"}` | — |

En la tarjeta del detalle se ve el historial de validación ("Corregido por Ana el 07/11: Puma → Jaguar").

### G2 · Validar en lote · FL-10
En `ResultsGallery`, el modo selección (casillas) → **Confirmar seleccionadas** o **Rechazar seleccionadas** → `POST /classifications/validation-batch` → "48 confirmadas".

### G3 · Corregir algo que la IA marcó como "vacío"
En los filtros de la galería, `category=blank` → el detalle **no tiene fotograma**. Como el archivo original ya no está, la única corrección posible es "Marcar como animal" con una especie del catálogo (`action:"correct"`, que cambia `category` a `animal`). Se muestra el aviso: "Sin fotograma de evidencia: la corrección se basa en tu conocimiento del archivo".

### G4 · Revisar ráfagas (registros repetidos) · FL-16
| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | Pestaña **Validación** → sub-pestaña **Ráfagas**; también aparece el aviso "Hay 7 posibles ráfagas" en la pestaña Clasificaciones | Selector "Agrupar capturas a menos de **5** min" (1–60) | `GET /classifications/burst-candidates?camera_station_id=&window_minutes=5` | Lista de grupos: "Jaguar · 3 archivos · 04:22–04:23 (52 s)", con las miniaturas lado a lado. |
| 2 | Abre un grupo | Muestra los fotogramas grandes en fila, con la confianza y la hora de cada uno; el de mayor confianza viene marcado como **Conservar** | — | — |
| 3a | **Dejar solo el marcado** | — | `POST /classifications/repeat-batch {keep_ids:[k91], discard_ids:[k92,k93]}` | "Se conservó 1; 2 marcados como repetidos". Las estadísticas pasan de 3 a 1 jaguar. |
| 3b | **Elegir cuáles dejar** (casillas) | — | `POST /classifications/repeat-batch {keep_ids:[…], discard_ids:[…]}` | — |
| 3c | **Conservar todos** (son animales distintos, por ejemplo una madre con su cría) | — | `POST /classifications/repeat-batch/dismiss {group_key}` | El grupo deja de sugerirse; siguen contando 3. |
| 4 | Deshacer | En el detalle de un repetido: "Repetido de IMG_001 · **Volver a contar**" | `PUT /classifications/{id}/validation {action:"reset"}` | Vuelve a contar. |

En la galería, los repetidos se ven atenuados con la etiqueta "Repetido", y el filtro "Ocultar repetidos" está activo por defecto.

---

## H · Estadísticas y reportes

### H1 · Estadísticas de una cámara · FL-11
Panel de la cámara → **Estadísticas** → `GET /camera-stations/{id}/stats` (API §10).

| Bloque en pantalla | Datos |
|---|---|
| Tarjetas | `totals.files_processed`, `sightings`, `richness.species`, el % validado (`validated / sightings`), `files_error` y `discarded_repeat` ("6 descartados como repetidos") |
| **Por especie** (obligatorio TDR) | Barras horizontales y **tabla** (nombre común, científico, avistamientos, %, validados) |
| **Por género** y **por familia** (obligatorio TDR) | Un selector de nivel `Especie / Género / Familia` que cambia el gráfico y la tabla |
| Sin fauna | Personas, vehículos, vacíos |
| No identificados hasta especie | `unidentified_to_species` |
| Actividad | Barras por hora (`by_hour`) y por mes (`by_month`) |
| Esfuerzo | Días-cámara y avistamientos por cada 100 días-cámara |

**Filtros**, arriba y compartidos por la pantalla y las descargas: rango de fechas, "Solo validados" y origen. Cada cambio vuelve a llamar a `/stats` con la *query*.
**Vacío:** "Aún no hay clasificaciones en esta cámara", con el botón **Clasificar archivos**.

### H2 · Estadísticas de un proyecto · FL-11
Panel del proyecto → **Estadísticas** → `GET /projects/{id}/stats`. Muestra lo mismo que H1, más:
- **Por cámara:** una tabla (código, avistamientos, especies) y una **matriz cámara × especie** (mapa de calor con `by_camera[].species_counts`);
- en el mapa, el tamaño de cada marcador es proporcional a sus avistamientos.

**Visto por otro usuario** (proyecto público): aviso "Incluye solo las cámaras públicas del proyecto (3 de 5)".

### H3 · Exportar a Excel · FL-12
Botón **Excel** → `GET /reports/excel?camera_station_id=…&only_validated=…&from=&to=` con el `apiClient` (`responseType: blob`) → descarga con el nombre de `Content-Disposition`. Se muestra un spinner en el botón mientras se genera. Con `REPORT_EMPTY` → "No hay datos con estos filtros".

### H4 · Exportar a PDF · FL-12
Igual que H3 con `/reports/pdf`.

---

## I · App de escritorio y sincronización con la web

### I1 · Instalación y primer inicio · FL-20
| # | Usuario | App | Resultado |
|---|---|---|---|
| 1 | Ejecuta `WWM-Clasificador-Setup-1.0.0.exe` | Asistente de Inno Setup: carpeta, acceso directo | Se instala en `Program Files\WWM`; los datos van en `%LOCALAPPDATA%\WWM`. |
| 2 | Abre la app **con internet** | Detecta que faltan los modelos → pantalla "Preparando el clasificador (≈1,5 GB)", con progreso, velocidad y tiempo restante | Descarga, verifica el hash y escribe `models.ok`. |
| — | Se corta la red | "Se interrumpió la descarga" con el botón **Reintentar**, que reanuda | `NETWORK_UNAVAILABLE` / `DOWNLOAD_INTEGRITY_FAILED` |
| 3 | Siguientes inicios, **sin internet** | Verifica `models.ok` y los hashes → pantalla principal | Ninguna llamada de red. |

### I2 · Clasificar una carpeta · FL-21
| # | Usuario | App | Resultado |
|---|---|---|---|
| 1 | **Carpeta de origen** | Cuenta los archivos válidos (sin subcarpetas): "340 archivos (310 videos, 30 imágenes)". Avisa si hay subcarpetas: "Se ignorarán". | — |
| 2 | **Carpeta de destino** | Verifica permisos de escritura y espacio libre | `DESTINATION_NOT_WRITABLE`, `DISK_SPACE_LOW` |
| 3 | **Copiar** o **Mover** | Si elige mover: "Los archivos clasificados se moverán; los que no tengan especie quedarán en el origen" | — |
| 4 | **Datos de la cámara** (opcional, plegable) | Código (por ejemplo `CAM01`), nombre, latitud y longitud (en grados decimales, con un botón para pegar del GPS), fecha y hora de colocación y de retiro, y observaciones. Son los mismos campos de la web; se guardan en `_wwm/camara.json` y viajan en el paquete (PKG §2). | — |
| 5 | **Iniciar** | Por archivo: hash → fecha de captura → pipeline en modo precisión → acción. Una barra general y un log en vivo: "CAM01_…_042210.mp4 → Panthera onca (jaguar) 94 % · 00:07" | — |
| 6 | — | **Con especie:** copia o mueve el archivo a `destino\Panthera onca (jaguar)\`, crea `<NOMBRE>_fotograma.jpg` al lado y verifica la copia antes de borrar el original si eligió mover. **Sin especie, persona, vehículo o vacío:** el archivo se queda en el origen. | Cada línea se escribe en `destino\_wwm\clasificaciones.jsonl`. |
| 7 | — | Al terminar: "340 procesados · 87 clasificados en 14 carpetas · 245 sin especie (quedaron en el origen) · 8 con error". Botones **Abrir carpeta de destino**, **Exportar para la web** (I4) y **Ver errores**. | — |

### I3 · Detener y reanudar · FL-21
**Detener** → termina el archivo en curso, sin dejar un movimiento a medias, y deja el `jsonl` consistente. Al volver a **Iniciar** con las mismas carpetas: "Se encontraron 120 archivos ya procesados; se continuará con los 220 restantes" (los reconoce por el hash en el `jsonl`).

### I4 · Exportar el paquete para la web · FL-22
| # | Usuario | App | Resultado |
|---|---|---|---|
| 1 | **Exportar para la web** (al terminar, o con el menú **Archivo → Exportar carpeta procesada…**) | Pide confirmar o completar los **datos de la cámara** (I2, paso 4) | — |
| 2 | — | Genera `WWM_CAM01_20260320-1504.wwm.zip` según [PAQUETE_ESCRITORIO.md](../contratos/PAQUETE_ESCRITORIO.md) dentro de `destino\_wwm\` | "Paquete listo (9 MB). Súbelo en la web: cámara → Importar desde escritorio". Botón **Abrir carpeta**. |

### I5 · Importar el paquete en la web · FL-23
**Precondición:** usuario con sesión. Si es anónimo, la opción aparece y al pulsarla pide iniciar sesión.

| # | Usuario | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | Panel de la cámara → **Importar desde escritorio**, o FAB → **Importar desde escritorio**, que ofrece: **Usar una cámara existente** (sugiere la que coincide con el código del paquete) o **Crear la cámara con los datos del paquete** | `ImportDesktopModal`, paso 1: cámara (preseleccionada) + selector `.wwm.zip`; valida la extensión y el peso ≤ `import.max_package_mb` | — | — |
| 2 | **Analizar** | Progreso de subida | `POST /imports/desktop` (multipart) — API §12.1 | Vista previa. |
| 3 | — | Paso 2, **vista previa**:<br>• datos del paquete: app, fecha, modelo, código de cámara;<br>• si `camera_code_matches=false`: "El paquete dice CAM01 y vas a importar en CAM02. ¿Es correcto?";<br>• conteos: 320 nuevos, 12 duplicados (ya estaban), 8 inválidos, 3 fuera del periodo de la cámara;<br>• tabla de `issues` con la línea, el archivo, el motivo y la severidad;<br>• opción "Importar también las que tienen advertencia". | — | — |
| 3b | (Si eligió crear la cámara) | Muestra los datos de `camera_from_package` en un formulario editable con un mini-mapa. Si faltan las coordenadas, pide marcarlas con un clic. Pasa por la verificación de cámaras cercanas (D1, paso 4b). | `GET /camera-stations/nearby` | — |
| 4a | **Confirmar importación** | — | `POST /imports/{id}/confirm {include_warnings, camera?}` | "Se importaron 320 clasificaciones". Botones **Ver resultados** (pestaña Clasificaciones, filtro `source=desktop`) y **Validar ahora**. |
| 4b | **Cancelar** | — | `DELETE /imports/{id}` | — |
| — | `IMPORT_ALREADY_IMPORTED` | "Este paquete ya se importó el 21/03/2026 en esta cámara" | — | Enlace a esa importación. |
| — | `IMPORT_UNSUPPORTED_VERSION` / `IMPORT_CHECKSUM_MISMATCH` / `IMPORT_INVALID_PACKAGE` | Mensaje del catálogo | — | "Vuelve a exportarlo desde la app". |
| — | `IMPORT_PREVIEW_EXPIRED` (pasó más de 1 h) | "La vista previa expiró; vuelve a subir el paquete" | — | — |

**Resultado:** las clasificaciones importadas cuentan en las estadísticas de la cámara y de sus proyectos igual que las web (filtrables por `source`). Sus fotogramas se ven en la web. Los videos **nunca** viajaron.

---

## J · Administrador

**Precondición común:** login (C2) con la única cuenta `role=admin`. El menú muestra **Panel admin** → `/admin`. Si alguien sin rol entra a `/admin/*`, el front redirige a `/` y el back responde `ADMIN_REQUIRED`.

### J1 · Resumen de la plataforma · FL-40
`/admin` → `GET /admin/stats?from=&to=` (API §13.1).

| Bloque | Contenido |
|---|---|
| Usuarios | Total, activos, desactivados, nuevos por mes (línea), con clasificaciones |
| Sesiones anónimas | Total, activas, asociadas, vencidas, **conversión %**, clasificaciones por sesión |
| Contenido | Cámaras y proyectos por **pública / privada / anónima / borrada**, donde **lo privado solo aparece como número**; clasificaciones por origen; errores por código; uso del storage |
| Retención anónima | Estado actual (activada o desactivada), registros conservados y eliminados por la configuración |

Filtro de fechas arriba. Botón **Exportar Excel** → `GET /admin/reports/excel`.

### J2 · Fauna (datos anónimos y públicos) · FL-40
`/admin/fauna` → `GET /admin/stats?scope=all|anonymous|public&sections=…` → los mismos gráficos y tablas de H1 (especie, género, familia, por hora y por mes) + **mapa de calor** (`fauna_map`, redondeado a ~1 km).
Aviso fijo: "No incluye datos de cámaras privadas de los usuarios".

### J3 · Explorar registros · FL-41
`/admin/explorar` tiene dos pestañas:
- **Clasificaciones:** `GET /admin/classifications?scope=&taxon=&from=&to=&include_deleted=&page=`, con la misma galería de F2 (fotograma vía `/admin/classifications/{id}/evidence`), la columna **Origen** (`Anónimo #a91f` o el nombre del usuario, si es público) y el estado borrado.
- **Cámaras:** `GET /admin/camera-stations?scope=…`, en tabla y mapa.

### J4 · Sesiones anónimas · FL-41
`/admin/anonimos` → `GET /admin/anon-sessions?status=` → tabla (`Anónimo #a91f`, estado, creada, última actividad, conteos, conservada sí o no). Clic → J3 filtrado por `anon_session_id`.

### J5 · Borrado lógico y restauración · FL-42
| # | Admin | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | Selecciona uno o varios registros (clasificaciones, cámaras o una sesión anónima completa) | Botón **Borrar** | — | — |
| 2 | — | Modal con el **motivo obligatorio** y el impacto: "Se ocultarán 1 cámara y 8 clasificaciones" | `POST /admin/{entity}/{id}/delete` o `POST /admin/delete-batch` | Toast con los conteos. Desaparecen de todas las estadísticas. |
| 3 | Activa el filtro "Incluir borrados" | Los borrados se muestran atenuados con la etiqueta, el motivo y la fecha | `?include_deleted=true` | — |
| 4 | **Restaurar** | Confirmación | `POST /admin/{entity}/{id}/restore` | Vuelven a contar. |

El admin **no puede** seleccionar contenido privado, porque no le aparece.

### J6 · Usuarios · FL-43
`/admin/usuarios` → `GET /admin/users?q=&status=` → tabla: nombre, correo, institución, alta, último acceso, estado y **conteos** (cámaras públicas y privadas, proyectos, clasificaciones).
- **Desactivar** → motivo → `POST /admin/users/{id}/deactivate`. El usuario queda sin acceso y su contenido público se oculta.
- **Reactivar** → `POST /admin/users/{id}/reactivate`.
- **Generar enlace de recuperación** (cuando no hay correo) → motivo → `POST /admin/users/{id}/password-reset-link` → muestra el enlace con el botón **Copiar** y el aviso "Vence en 30 min; entrégalo solo al titular de la cuenta".
- El admin no ve el contenido privado del usuario, solo los números.

### J7 · Configuración de retención anónima · FL-44
| # | Admin | Front | Llamada | Resultado |
|---|---|---|---|---|
| 1 | `/admin/configuracion` | Muestra el interruptor **"Guardar los datos de usuarios sin sesión"** con su estado, quién lo cambió y cuándo | `GET /admin/settings` | — |
| 2 | Lo cambia | Modal: "Este cambio aplica **solo a los datos nuevos** desde este momento. Los datos anteriores no se modifican." + motivo obligatorio | `PUT /admin/settings {anon_data_retention, reason}` | Toast "Configuración actualizada". |
| 3 | — | Debajo, el historial de cambios | `GET /admin/audit-log?action=update_setting` | — |

**Efecto visible:** los visitantes nuevos ven el aviso correspondiente (B2, paso 3) en menos de 30 s.

### J9 · Monitor de la cola · FL-45
`/admin/cola` → `GET /admin/queue` (refresco cada 10 s): *workers*, en cola, en proceso, tiempo medio, antigüedad del más viejo (en rojo si pasa de 30 min), pendientes por dueño, la última hora y la cuota de correo ("3 de 80 hoy · 41 de 2500 este mes").

### J10 · Desempeño del modelo y sugerencias · FL-46
`/admin/modelo`:
- `model_feedback` de `GET /admin/stats`: barras con el % confirmado, corregido con alternativa, corregido desde el catálogo, no catalogado y rechazado, más la tabla de confusiones frecuentes;
- `GET /admin/unlisted-suggestions`: tabla de los nombres sugeridos con su conteo y su taxón superior. Clic → J3 filtrado por esas clasificaciones.

### J8 · Auditoría · FL-40…44
`/admin/auditoria` → `GET /admin/audit-log?action=&from=&to=` → tabla de las acciones con su motivo y su `request_id`.

---

## K · Mensajes de error en pantalla

El front muestra el `message` del back salvo que `utils/errorMessages.js` tenga un texto o una acción específica. Siempre agrega el código de referencia en los errores 5xx y en los de la IA.

| Código | Texto en pantalla | Acción del front |
|---|---|---|
| `AUTH_TOKEN_EXPIRED` | — | Refresh silencioso (C3) |
| `AUTH_TOKEN_INVALID` / `AUTH_REQUIRED` | "Inicia sesión para continuar" | Redirige a `/login?next=` |
| `ANON_SESSION_EXPIRED` | "Tu sesión sin cuenta expiró" | Borra el token |
| `ANON_LIMIT_REACHED` | "Llegaste al límite sin cuenta" | Modal con "Crear cuenta" |
| `FORBIDDEN` / `ADMIN_REQUIRED` | "No tienes permiso para esta acción" | — |
| `*_NOT_FOUND` | "No encontramos este recurso; puede haber sido eliminado o ser privado" | Cierra el panel |
| `VALIDATION_ERROR` | Errores por campo | Marca los campos |
| `MEDIA_*` / `DUPLICATE_*` | Mensaje específico del archivo | En la tarjeta |
| `QUEUE_USER_LIMIT` | "Tienes muchos archivos en espera; continuaremos cuando avancen" | Pausa y reanuda sola |
| `QUEUE_FULL` / `QUEUE_UNAVAILABLE` | "El servidor está ocupado; reintentaremos en unos minutos" | Reintento con *backoff* |
| `CONFLICT_STALE` | "Esto se modificó en otra ventana" | Botón Recargar |
| `EMAIL_TEMPORARILY_UNAVAILABLE` | "No podemos enviar correos ahora" | Sugiere contactar al admin |
| `AUTH_RESET_TOKEN_INVALID` | "El enlace venció o ya se usó" | Botón Pedir otro |
| `AI_*` / `STORAGE_WRITE_FAILED` | "No se pudo clasificar el archivo. Código de referencia: 7f3a…" | Reintentar |
| `RATE_LIMITED` | "Demasiadas solicitudes. Espera un momento." | Desactiva el botón |
| `INTERNAL_ERROR` / `DATABASE_ERROR` | "Ocurrió un error inesperado. Código de referencia: 7f3a…" | Reintentar |
| Sin respuesta (red) | "No hay conexión con el servidor" | Reintentar |
