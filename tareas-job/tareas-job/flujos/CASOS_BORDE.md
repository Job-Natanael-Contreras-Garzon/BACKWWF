# Casos borde y su resolución

> Documento interno · CETERIS404 · v1 — 07/11/2026
> **Qué es:** las situaciones que no son el "camino feliz" y cómo debe responder el sistema en cada una. Cada caso tiene un ID (`CB-xx`) que se usa en los tests (BE-35, DEP-04).
> **Relación:** las reglas generales están en [FLUJOS_SISTEMA.md](../FLUJOS_SISTEMA.md); los recorridos, en [FLUJOS_DETALLADOS.md](FLUJOS_DETALLADOS.md); los endpoints y los códigos, en [contratos/API_BACK_FRONT.md](../contratos/API_BACK_FRONT.md) (**API §n**).
> **Tipos de respuesta:**
> - **Bloquea:** error, no se guarda.
> - **Advierte:** se guarda, y la respuesta trae `meta.warnings[]` o una advertencia en el ítem; el front pide confirmación o la muestra.
> - **Permite:** comportamiento normal.

---

## 1. Ubicación de cámaras trampa

**Principio:** una cámara trampa en el sistema representa **una instalación** (un equipo en un punto entre su colocación y su retiro), como pide el TDR. Varias cámaras en el mismo lugar son **legítimas** y frecuentes:
- *estaciones pareadas*: dos equipos enfrentados para fotografiar ambos flancos del animal;
- reinstalación en el mismo punto en otra temporada;
- investigadores distintos trabajando en la misma zona.

Por eso **nunca se bloquea por cercanía**: se informa y se ofrece la acción correcta.

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-01 | **El usuario coloca una cámara a menos de `NEARBY_RADIUS_M` (30 m) de otra suya que sigue instalada** | Antes de guardar, el front llama a `GET /camera-stations/nearby` (API §5.7) y muestra: "Tienes **CAM01** a 12 m (instalada desde el 01/03/2026). ¿Qué estás registrando?", con tres opciones:<br>• **Otra cámara en el mismo punto** (estación pareada): sigue el alta normal y exige otro código;<br>• **Reinstalé CAM01** (cambio de pilas, de temporada o de equipo) → CB-03;<br>• **Me equivoqué, abrir CAM01**: cancela el alta y abre esa cámara. | Advierte |
| CB-02 | Ídem, pero la cámara cercana está **retirada** | El mensaje cambia: "CAM01 estuvo aquí del 01/03 al 30/04. ¿Es una nueva instalación en el mismo punto?". La opción recomendada es **Nueva instalación de CAM01** (CB-03). | Advierte |
| CB-03 | **Reinstalación en el mismo punto** | `POST /camera-stations/{id}/redeploy` (API §5.8):<br>• crea una cámara **nueva** que copia la ubicación, el nombre, las observaciones, la visibilidad y los proyectos;<br>• le asigna un código nuevo sugerido (`CAM01-2`), editable, y `previous_camera_station_id` = la anterior;<br>• si la anterior seguía instalada, pide su fecha de retiro (por defecto, la de colocación de la nueva).<br>Así las clasificaciones de cada periodo quedan separadas, los días-cámara del esfuerzo se calculan bien y el proyecto suma ambas. | Permite |
| CB-04 | **Otro usuario tiene una cámara pública** en el mismo punto | `nearby` la incluye en `public_others` con una **banda de distancia** (`<10m`, `<50m`, `<200m`), nunca con la exacta: "Hay 1 cámara pública de otro investigador a menos de 10 m (WWF Bolivia)". Solo es informativo; se guarda normalmente. | Advierte |
| CB-05 | **Otro usuario tiene una cámara privada** en el mismo punto | **No se informa.** Ni siquiera se dice que existe, para no revelar la ubicación de cámaras privadas. Se guarda normalmente. | Permite |
| CB-05b | **Triangular** la ubicación exacta de una cámara pública ajena (consultando `nearby` desde varios puntos, o comparando el mapa con las estadísticas) | Imposible por diseño: a quien no es dueño siempre se le envían las coordenadas redondeadas a ~1 km, y la distancia en bandas (DD-17). | — |
| CB-06 | Coordenadas **idénticas** (< 1 m) a otra cámara propia con **periodos superpuestos** | Advertencia más fuerte: "Posible duplicado: CAM01 tiene la misma ubicación y fechas que se superponen". Las mismas opciones que CB-01. | Advierte |
| CB-07 | Coordenadas que parecen **invertidas** o en `0,0` | El uso es principalmente en Bolivia, pero **no se limita** a ella, así que una ubicación fuera de Bolivia **es válida y no genera aviso**. Solo se advierte en dos casos:<br>• las coordenadas son `0,0`;<br>• el punto cae fuera de Bolivia y, al **intercambiar** latitud y longitud, cae dentro (`REGION_BBOX`): "¿Latitud y longitud están invertidas?", con el botón **Intercambiar**.<br>Se guarda si el usuario confirma. Llega como `meta.warnings: [{code:"CAMERA_COORDS_SUSPECT"}]`. | Advierte |
| CB-08 | Latitud o longitud fuera de rango (`|lat| > 90`, `|lng| > 180`) | `VALIDATION_ERROR`. | Bloquea |
| CB-09 | **Mover la ubicación** de una cámara que ya tiene clasificaciones | Si el cambio es mayor a 50 m: "Esta cámara tiene 120 clasificaciones. Si la moviste físicamente, registra una **nueva instalación** (CB-03); si corriges un error de ubicación, continúa". | Advierte |
| CB-10 | Marcadores superpuestos en el mapa | El mapa agrupa (*MarkerClusterer*) y, si hay varios en el mismo punto, los despliega en abanico al hacer clic (*spiderfy*). En el panel aparece "2 cámaras en este punto". | — |

## 2. Datos y fechas de la cámara

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-11 | `retrieved_at < deployed_at` | `CAMERA_INVALID_DATES`. | Bloquea |
| CB-12 | `deployed_at` o `retrieved_at` en el **futuro** (más de 1 día) | `CAMERA_INVALID_DATES` ("La fecha no puede ser futura"). | Bloquea |
| CB-13 | Código repetido para el mismo dueño, **sin distinguir mayúsculas** (`cam01` vs `CAM01`) | `CAMERA_CODE_TAKEN`. El índice único es `(dueño, lower(code)) WHERE NOT is_deleted`, así que el código de una cámara borrada **se puede reutilizar**. | Bloquea |
| CB-14 | Dos pestañas crean el mismo código a la vez | Decide el índice único de la BD: la segunda recibe `CAMERA_CODE_TAKEN`. | Bloquea |
| CB-15 | **Dos pestañas o dispositivos editan la misma cámara** | Bloqueo optimista: cada cámara y proyecto tiene `version`; el `PATCH` envía `If-Match: <version>` y, si no coincide → `409 CONFLICT_STALE` "La cámara se modificó en otra ventana" con el botón **Recargar**. | Bloquea |
| CB-16 | **Subir archivos a una cámara retirada** | **Se permite**: es lo normal, porque los archivos se descargan de la tarjeta SD después de retirar el equipo. | Permite |
| CB-17 | El `captured_at` de un archivo está **fuera del periodo** colocación–retiro | Se guarda con una advertencia en el ítem (`CAPTURE_OUTSIDE_DEPLOYMENT`), visible en la galería y filtrable. Suele indicar el reloj mal configurado (CB-18) o una cámara equivocada. | Advierte |
| CB-18 | **Reloj de la cámara mal configurado** (por ejemplo, todas las fechas en 2000-01-01 o desfasadas una hora) | Acción **Corregir la hora de la cámara** (P2): `POST /camera-stations/{id}/time-offset {offset_seconds, from?, to?}` aplica el desfase a las clasificaciones con fecha de `exif`, `container` o `filename` en ese rango, conserva el valor original (`captured_at_original`) y lo registra en la auditoría. | Permite |
| CB-19 | Cambiar fechas de colocación o retiro cuando ya hay clasificaciones | Se permite. Las advertencias de CB-17 y el esfuerzo (días-cámara) se recalculan en la siguiente consulta. | Permite |
| CB-20 | Pasar a **privada** una cámara que está en un proyecto **público** | Se permite. Sale de las estadísticas que ven los demás y el aviso del proyecto pasa a "3 de 5 cámaras públicas". | Permite |
| CB-20b | **Hacer pública** una cámara o un proyecto | Siempre pasa antes por la advertencia de DD-17 (ubicación aproximada, especies, fotogramas; recomendación sobre especies sensibles). | Advierte |
| CB-21 | **Eliminar una cámara** que está en proyectos | Borrado lógico. Sale de los proyectos y sus clasificaciones dejan de contar. Si tiene ítems **en cola** → se cancelan (`CAMERA_DELETED`). | Permite |

## 3. Proyectos

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-22 | Proyecto público **sin cámaras públicas** | Lo ven los demás con "Este proyecto aún no tiene cámaras públicas", sin estadísticas. | Permite |
| CB-23 | Asociar una cámara **ajena** (aunque sea pública) | `CAMERA_NOT_OWNED` (el proyecto es individual, TDR §3.1). | Bloquea |
| CB-24 | Asociar una cámara ya asociada | `ALREADY_ASSOCIATED`. | Bloquea |
| CB-25 | Dos proyectos con el mismo nombre | Se permite; los nombres no son únicos. | Permite |
| CB-26 | Una cámara en **varios** proyectos | Se permite (relación N:M). Cada proyecto la cuenta en sus propias estadísticas. | Permite |
| CB-27 | Eliminar un proyecto | Las cámaras y las clasificaciones **no** se tocan. | Permite |

## 4. Subida y cola de procesamiento

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-30 | **Muchos usuarios suben a la vez** | Los archivos entran a la **cola** (Redis) y responden de inmediato `queued` con su posición y el tiempo estimado. El análisis lo hacen los *workers* (DD-12). La cola es **justa**: cada dueño tiene como máximo `QUEUE_PER_OWNER_INFLIGHT` (2) archivos despachados a la vez, de modo que un lote de 500 no bloquea al que sube 3. | Permite |
| CB-31 | El usuario **navega a otras vistas** mientras sube | La subida sigue: el `UploadManager` vive a nivel de la app y la bandeja de subidas (`UploadTray`) se ve en todas las pantallas. | Permite |
| CB-32 | **Cierra la pestaña mientras los bytes se están subiendo** | Lo no enviado se pierde (el navegador no lo conserva). Mientras haya archivos *subiendo*, el front muestra el aviso de `beforeunload`. Lo que ya llegó al servidor sigue en la cola. | Advierte |
| CB-33 | **Cierra la pestaña con archivos ya en cola** | Se procesan igual. Con sesión, los ve al volver (bandeja + notificación). Si es anónimo y cerró el navegador, ya no puede verlos y quedan según `anon_retain`. Antes de cerrar se le avisa: "El análisis continúa en el servidor, pero sin cuenta no podrás ver los resultados si cierras el navegador". | Advierte |
| CB-34 | El usuario **excede su tope de pendientes** (`QUEUE_MAX_PENDING_PER_USER` = 500; anónimo: `ANON_MAX_FILES`) | `429 QUEUE_USER_LIMIT` "Tienes 500 archivos en espera; espera a que avancen". El front pausa la subida y la reanuda sola cuando baja la cantidad. | Bloquea |
| CB-35 | **Cola global llena** o disco temporal sobre el 85 % | `503 QUEUE_FULL` "El servidor está muy ocupado; reintentaremos en 1 min". El front reintenta con *backoff*. | Bloquea |
| CB-36 | **Redis caído** | La subida responde `503 QUEUE_UNAVAILABLE`; el resto del sistema (mapa, estadísticas, validación) **sigue funcionando**. Al volver Redis, el *reaper* re-encola desde la BD (CB-38). | Bloquea |
| CB-37 | **La IA está caída o lenta** | El *worker* reintenta 2 veces (5 s y 30 s) los errores transitorios (`AI_UNAVAILABLE`, `AI_TIMEOUT`, `IA_BUSY`). Si siguen fallando → el ítem queda en `error` y el usuario puede **Reintentar** desde la bandeja (se re-encola, porque el temporal sigue disponible hasta `TMP_UPLOAD_TTL_HOURS`). | Permite |
| CB-38 | **Se reinicia un worker o el servidor** a mitad de un archivo | La BD es la fuente de verdad del estado. El *reaper* (cada 5 min) vuelve a `queued` los ítems `processing` sin latido por más de 10 min y re-encola los `queued` que no estén en Redis. El trabajo es **idempotente**: si el ítem ya está `done`, se salta. | Permite |
| CB-39 | Un archivo queda en cola **más de `TMP_UPLOAD_TTL_HOURS`** (24 h) | Se marca `error` `PROCESSING_EXPIRED` y se borra su temporal. | Permite |
| CB-40 | **Cancelar** archivos en cola | `DELETE /classification-batches/{id}/items/{client_index}` o `POST …/cancel` (todo el lote). Solo afecta a los `queued`; el que ya está `processing` termina. | Permite |
| CB-41 | El dueño **asocia su sesión anónima a una cuenta** con ítems en cola | El *worker* toma el dueño **del lote en el momento de escribir**; como el *claim* actualiza el lote, los resultados terminan en la cuenta. | Permite |
| CB-42 | La sesión anónima **vence** con ítems en cola | Se procesan igual. `anon_retain` se fijó **al subir** el archivo, no al terminarlo. | Permite |
| CB-43 | El admin **cambia la retención** con ítems anónimos en cola | Igual que CB-42: manda el valor que había al subirlos. | Permite |
| CB-44 | **Desactivan la cuenta** de un usuario con ítems en cola | Sus ítems `queued` se cancelan (`ACCOUNT_DISABLED`). | Permite |

## 5. Archivos y duplicados

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-50 | El **mismo archivo** (mismo `sha256`) en la **misma cámara** | El ítem `DUPLICATE_FILE` con un enlace a la existente. Se detecta **al subir**, antes de encolar (no consume la IA). | Bloquea |
| CB-51 | El mismo archivo en **otra cámara del mismo dueño** | El ítem `DUPLICATE_FILE_OTHER_CAMERA` "Ya está clasificado en CAM02", con las acciones **Mover a esta cámara** (`PATCH /classifications/{id}`) o **Ignorar**. Así se evita el doble conteo en un proyecto que tenga ambas cámaras. | Bloquea |
| CB-52 | El mismo archivo subido por **dos usuarios distintos** | Se permite: son cuentas independientes. En las estadísticas **globales del admin** se cuenta una vez por `sha256` (deduplicado). | Permite |
| CB-53 | **El mismo nombre con distinto contenido** | Se permite; el sistema identifica por `sha256`, no por nombre. | Permite |
| CB-54 | **Contenido igual con distinto nombre** (archivo renombrado) | Se trata como duplicado (CB-50 o CB-51). | Bloquea |
| CB-55 | El mismo archivo por la **web y por un paquete de escritorio** en la misma cámara | Se trata como duplicado (CB-50); la importación lo cuenta en `duplicates`. | Bloquea |
| CB-56 | Video de 15,3 s | Se acepta (tolerancia de +0,5 s). Uno de 15,6 s → `MEDIA_DURATION_EXCEEDED`. | Permite |
| CB-57 | Extensión correcta y contenido de otro tipo (por ejemplo, un `.mp4` que es un PDF) | `MEDIA_UNSUPPORTED_FORMAT` (se valida la firma binaria). | Bloquea |
| CB-57b | Un formato que el navegador **no puede previsualizar** (AVI, WMV, MKV, MTS, HEIC) | Se acepta igual: el front no valida su duración (no puede leerla) y lo hace el back con `ffprobe`. En la tarjeta se ve un ícono genérico hasta que llega el fotograma. | Permite |
| CB-57c | Una extensión fuera de la lista (por ejemplo `.raw`, `.cr2`, `.mpg` exótico) | `MEDIA_UNSUPPORTED_FORMAT`, con la lista de formatos aceptados. | Bloquea |
| CB-58 | Archivo corrupto o truncado | `MEDIA_DECODE_FAILED`. Se detecta al subir si `ffprobe` falla; si no, en la IA. | Bloquea |
| CB-59 | Imagen enorme (por ejemplo 50 MP) o *decompression bomb* | Se rechaza por encima de `MAX_IMAGE_PIXELS` (Pillow, 100 MP) con `MEDIA_TOO_LARGE`; por debajo, la IA redimensiona. | Bloquea |
| CB-60 | **Ráfagas**: la cámara toma 3 fotos por disparo y las 3 tienen al mismo animal | **Por defecto cuentan 3** (opción A, D10). El sistema **sugiere** el grupo ("Posible ráfaga: 3 de Jaguar en 52 s") y el investigador decide: conservar todos, dejar uno (por defecto el de mayor confianza) o elegir cuáles. Los descartados quedan `discarded_repeat`: no cuentan, no se borran y no son error de la IA (FL-16). | Permite |
| CB-60b | Una "ráfaga" con **especies distintas** (por ejemplo, Jaguar y Puma a 1 min) | No es un grupo: la agrupación exige la misma taxonomía efectiva. Si el usuario corrige una de ellas, el grupo se recalcula en la siguiente consulta. | Permite |
| CB-60c | Archivos sin fecha real (`upload_time`) | No se sugieren como ráfaga, porque no hay forma de saber si son del mismo disparo. El usuario puede marcarlos a mano (`discard_repeat`). | Permite |
| CB-60d | Intentar conservar **ninguno** del grupo | `REPEAT_KEEP_REQUIRED`: siempre queda al menos uno. Para descartarlo de verdad, se usa `reject`. | Bloquea |

## 6. Clasificación y validación

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-61 | La IA no llega a especie (solo género o familia) | `rank=genus` o `family`. Cuenta en `by_genus` y `by_family` y en `unidentified_to_species`, no en `by_species`. | Permite |
| CB-62 | La IA dice `blank` pero había un animal | Sin fotograma. El usuario puede **Marcar como animal** eligiendo un taxón del catálogo (`correct`). | Permite |
| CB-63 | La IA dice animal y **no hay ninguno** | El usuario elige **No hay ningún animal** → `reject`, que deja de contar. | Permite |
| CB-64 | La especie correcta **no es la propuesta ni ninguna alternativa** | **Buscar en el catálogo** → `correct` con `correction_source=catalog`. | Permite |
| CB-65 | La especie correcta **no está en el catálogo de SpeciesNet** | **No está en el catálogo** → `correct_unlisted` con `suggested_name` (texto libre, obligatorio) y, opcionalmente, el taxón superior que sí conoce (por ejemplo, el género) desde el catálogo. Cuenta como avistamiento en el nivel del taxón superior si lo indicó; si no, en `unidentified_to_species.unlisted`. Queda registrado para futuras mejoras (FL-46). | Permite |
| CB-66 | El usuario cambia de opinión | `reset` o una nueva acción; se guarda el último estado, y el historial queda en `validation_history`. | Permite |
| CB-67 | Validar en lote con IDs ajenos o borrados | Se omiten en `skipped`; el resto se aplica. | Permite |
| CB-68 | La versión del catálogo o del modelo cambia en el futuro | `label_id` es estable en SpeciesNet. Las clasificaciones guardan `model.classifier`; los `label_id` que ya no existan siguen mostrándose con su taxonomía guardada. | Permite |

## 7. Sesión anónima y cuenta

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-70 | Abrir **dos pestañas** sin cuenta | Cada pestaña tiene su propio `sessionStorage` y, por lo tanto, **su propia sesión anónima**. Se informa en el `AnonBanner`: "Esta pestaña tiene su propia sesión". | Permite |
| CB-71 | Iniciar sesión en la pestaña B cuando los datos anónimos están en la pestaña A | Solo se asocian los datos de la pestaña donde se inicia sesión. Si la pestaña A sigue abierta, al recargarla ofrece asociar (ya con sesión iniciada, `claim` con su propio token). | Permite |
| CB-72 | Registrarse con un correo **ya registrado** | `AUTH_EMAIL_TAKEN`, con el enlace a "¿Olvidaste tu contraseña?". | Bloquea |
| CB-73 | **Recuperar la contraseña** de un correo que no existe | La misma respuesta genérica que si existiera (no revela qué correos hay). No se envía nada. | Permite |
| CB-74 | Pedir varios enlaces de recuperación seguidos | Solo vale el **último** (los anteriores se invalidan). Hay límites por correo e IP (FL-14). | Permite |
| CB-75 | Usar un enlace de recuperación vencido (más de 30 min) o ya usado | `AUTH_RESET_TOKEN_INVALID`, con el botón "Pedir otro enlace". | Bloquea |
| CB-76 | **Se agotó la cuota diaria de correos** | `503 EMAIL_TEMPORARILY_UNAVAILABLE` "No podemos enviar correos en este momento; intenta mañana o contacta al administrador". Aplica a todos por igual, así que no revela si el correo existe. El admin puede generar un enlace manual (FL-14). | Bloquea |
| CB-77 | La cuenta está desactivada y pide recuperar la contraseña | La respuesta genérica; no se envía el correo. | Permite |
| CB-78 | La contraseña cambia mientras hay sesiones abiertas en otros equipos | Se revocan todos los *refresh tokens*; los otros equipos quedan fuera al vencer su *access token* (≤ 30 min). | Permite |

## 8. Importación desde escritorio

| ID | Caso | Regla | Respuesta |
|---|---|---|---|
| CB-80 | El paquete dice `CAM01` y se importa en `CAM02` | Advertencia en la vista previa (`camera_code_matches=false`). | Advierte |
| CB-81 | El paquete mezcla archivos de varias cámaras | No se puede detectar de forma confiable; la regla es **una carpeta = una cámara** (manual DS-15). Ayuda la advertencia CB-17 de fechas fuera del periodo. | Advierte |
| CB-82 | Importar el **mismo paquete dos veces** | `IMPORT_ALREADY_IMPORTED`. | Bloquea |
| CB-83 | Paquetes distintos con archivos repetidos | Los repetidos cuentan como `duplicates`. | Permite |
| CB-84 | El paquete es de una versión de la app más nueva que la soportada | `IMPORT_UNSUPPORTED_VERSION` "Actualiza la plataforma". | Bloquea |
| CB-85 | Paquete grande (miles de líneas) | La importación confirmada **también va a la cola** (un trabajo de importación) para no bloquear la petición; el progreso se ve en la bandeja. | Permite |
| CB-86 | El paquete trae los datos de la cámara **incompletos** (sin coordenadas) y el usuario elige crearla | La vista previa marca `camera_from_package.complete=false`; antes de confirmar, el front pide completar lo que falta (por ejemplo, un clic en el mapa). | Advierte |
| CB-87 | El paquete trae un código que **ya existe** en otra cámara propia | `matching_camera_station_id` → el front sugiere "Importar en CAM01 (existente)"; si igual quiere crear otra, pide otro código. | Advierte |

## 9. App de escritorio

| ID | Caso | Regla |
|---|---|---|
| CB-90 | La carpeta de destino es la misma que la de origen, o está dentro de ella | Bloquea: "Elige una carpeta de destino distinta y fuera del origen". |
| CB-91 | Ya existe un archivo con ese nombre en la carpeta de destino | Agrega el sufijo ` (2)`; nunca sobrescribe. |
| CB-92 | Disco de destino lleno a mitad del proceso | Se detiene limpio (`DISK_SPACE_LOW`); el registro permite reanudar. |
| CB-93 | Se va la luz o se cuelga el equipo durante un "mover" | El original solo se borra después de verificar la copia (DS-30). Al reanudar, se detecta la copia parcial (el tamaño no coincide) y se rehace. |
| CB-94 | Archivo abierto o bloqueado por otro programa | Se salta con `FILE_LOCKED` y se informa en el resumen. |
| CB-95 | Rutas largas (más de 260 caracteres) o con tildes | Se usan rutas `\\?\` y UTF-8; se prueba en QA (DS-16). |

## 10. Administración

| ID | Caso | Regla |
|---|---|---|
| CB-96 | El admin intenta acceder a contenido privado por la URL o el ID | 404, en todos los endpoints `/admin/*` (BE-52). |
| CB-97 | El admin borra una sesión anónima con ítems en cola | Se cancelan los `queued`; los `processing` terminan y quedan borrados. |
| CB-98 | El admin intenta desactivarse a sí mismo | `CANNOT_DEACTIVATE_SELF`. |
| CB-99 | Se pierde el acceso a la única cuenta admin | `python -m app.cli reset-admin-password` en el servidor. |

---

## Puntos para WWF que salen de estos casos
- ~~D10~~ **Resuelto:** se cuenta por archivo (opción A) y el investigador puede descartar los repetidos de una ráfaga (FL-16, CB-60).
- ~~D11~~ **Resuelto:** WWF trabaja principalmente en Bolivia, pero sin restringirse a ella. No se limita ninguna ubicación; el mapa **arranca centrado en Santa Cruz** (`MAP_DEFAULT_CENTER`) y solo se avisa en el caso de coordenadas sospechosas (CB-07).
