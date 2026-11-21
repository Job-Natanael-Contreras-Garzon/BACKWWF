# Plan de implementación para cumplir el TDR

> Documento interno · CETERIS404 · **v2 — 07/11/2026**: decisiones DD-1..DD-11 confirmadas por Diego. Se agregan los flujos ([FLUJOS_SISTEMA.md](FLUJOS_SISTEMA.md)), los estándares ([ESTANDARES_BACKEND_IA.md](ESTANDARES_BACKEND_IA.md)), las tareas STD-*, la sesión anónima con asociación a cuenta, el storage local de fotogramas, el prefijo `/api/v1`, el PDF en el back y la sincronización escritorio → web.
> **Base:** [TDR](../TDR_CETERIS404_WWF.md) (fuente de verdad del alcance) y el código **tal como está en los repositorios** (back y front en `origin/main`, IA en la rama `escritorio`, al 07/11/2026). Lo que no está en el repo no se considera hecho.
> **Responsables:** Diego (líder · IA · escritorio) · Job (backend) · Miguel (frontend). Job **no** modifica el código de la IA.

---

## Índice

1. [Cómo leer este plan](#1-cómo-leer-este-plan)
2. [Decisiones de diseño que rigen todo el plan](#2-decisiones-de-diseño-que-rigen-todo-el-plan)
3. [Contrato entre componentes](#3-contrato-entre-componentes)
4. [IA — `ia-deteccion` (Diego)](#4-ia--ia-deteccion-diego)
5. [App de escritorio — Producto 1 (Diego)](#5-app-de-escritorio--producto-1-diego)
6. [Backend — `BACKWWF` (Job)](#6-backend--backwwf-job)
7. [Frontend — `Front-WWF` (Miguel)](#7-frontend--front-wwf-miguel)
8. [Seguridad y configuración nueva](#8-seguridad-y-configuración-nueva)
9. [Despliegue y entregables](#9-despliegue-y-entregables)
10. [Cronograma y dependencias](#10-cronograma-y-dependencias)
11. [Trazabilidad TDR → tareas](#11-trazabilidad-tdr--tareas)

---

## 1. Cómo leer este plan

Cada componente se divide en cuatro bloques:

- **A. Estado actual:** lo que hay hoy en el repo.
- **B. Cambios:** modificar o eliminar algo que ya existe.
- **C. Nuevas implementaciones:** lo que no existe.
- **D. Mejoras de seguridad y calidad.**

Cada tarea tiene un ID (`IA-`, `DS-`, `BE-`, `FE-`, `SEC-`, `DEP-`), su prioridad (**P0** bloquea un entregable · **P1** necesaria · **P2** deseable), la semana objetivo (S1–S6) y un criterio de aceptación.

---

## 2. Decisiones de diseño que rigen todo el plan

| #     | Decisión                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Por qué (TDR)                                                                                                                                                                                                                                                                                         |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DD-1  | **Una sola clasificación por archivo:** la especie ganadora y un fotograma de evidencia.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | §3.4: "no se contempla más de una especie en un mismo video/imagen"; los conteos son de avistamientos.                                                                                                                                                                                                |
| DD-2  | **Sin sesión se guarda en la BD bajo una credencial anónima temporal.** El back emite un token aleatorio (se guarda solo su hash); el front lo conserva en `sessionStorage`, así que sobrevive a F5 y se pierde al cerrar el navegador. Si el usuario se registra o inicia sesión **en esa misma sesión**, confirma y los datos se asocian a su cuenta en una transacción. Al cerrar el navegador la credencial no se puede recuperar, y tras 24 h de inactividad la sesión vence. Qué pasa luego con los datos lo decide la **configuración `anon_data_retention`**, que el admin activa o desactiva en caliente (FL-44):<br>• **activada (por defecto):** los datos **se conservan** como anónimos para las estadísticas de la plataforma, visibles solo para el admin, que puede borrarlos lógicamente;<br>• **desactivada:** al vencer la sesión se eliminan físicamente (el comportamiento literal del TDR).<br>El cambio **solo aplica a los datos creados desde ese momento**: cada fila guarda `anon_retain` al crearse y nunca se borran datos anteriores al cambio.<br>Antes de la primera clasificación se muestra un **aviso de uso de datos** acorde a la configuración. El contenido anónimo es siempre privado frente a otros usuarios y tiene límites de uso. Detalle: [FLUJOS_SISTEMA.md FL-03/04/30/44](FLUJOS_SISTEMA.md#4-flujos-de-acceso-y-sesión). | §3.1. Con la retención activa se aparta de "no se guarda", y conviene informarlo a WWF (D5). Si WWF pide cumplirlo al pie de la letra, se desactiva sin cambiar código.                                                                                                                               |
| DD-3  | **No se almacenan los videos ni las imágenes originales:** se procesan en un temporal y se borran. Solo se guardan el registro y el **fotograma de evidencia** comprimido (JPEG ≤ 960 px, ~100 KB, sin EXIF), en **disco local**, no en la BD. Va detrás de una interfaz `StorageBackend` (`local` hoy, `s3` a futuro, sin cambiar los servicios); la BD guarda solo la clave. Siempre se registran el **minuto y segundo** (`evidence_timestamp_seconds`) y el número de frame del fotograma. Los fotogramas se sirven por un endpoint con autorización, no como estáticos públicos.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | §3.4 + §3.1 (el usuario "puede volver a consultar" sus clasificaciones).                                                                                                                                                                                                                              |
| DD-4  | **Datos siempre reales.** Si la IA falla, el back responde 502/504 o marca el archivo con su `error_code`; el front muestra el error con un código de referencia. No hay *fallbacks* ni *mocks*. Las respuestas, los errores y los logs están estandarizados, con `request_id` de punta a punta y flujo y paso en cada log: [ESTANDARES_BACKEND_IA.md](ESTANDARES_BACKEND_IA.md).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Credibilidad ante WWF y diagnóstico de fallos.                                                                                                                                                                                                                                                        |
| DD-5  | **Estadísticas obligatorias:** avistamientos por especie, género y familia, por cámara y por proyecto. **Complementarias**, derivadas de los mismos datos: totales con y sin fauna, riqueza, clases no animales, estado de validación (% de correcciones), por cámara dentro del proyecto, distribución por mes y por hora, y esfuerzo en días-cámara (P2). Los indicadores que dependen del clima (VisualCrossing) y los 10 indicadores ecológicos actuales **se eliminan**. Detalle: [FL-11](FLUJOS_SISTEMA.md#fl-11--estadísticas).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | §3.1 + §3.4; las complementarias se confirman con WWF (D8).                                                                                                                                                                                                                                           |
| DD-6  | **Excel y PDF se generan en el back**, a partir del **mismo dataset** que `/stats`. Excel con `openpyxl`; PDF con `ReportLab` y gráficos con `matplotlib`. El jsPDF actual del front queda solo hasta que esté el PDF del back.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Una sola fuente de verdad (el PDF, el Excel y la pantalla dan los mismos números); la autorización y la visibilidad se validan en el servidor; trazabilidad (filtros, versión del modelo y `request_id` en el pie); funciona con proyectos grandes sin cargar todo en el navegador; se puede testear. |
| DD-7  | **Rutas con prefijo versionado `/api/v1`** en el back y en la IA. El proxy publica solo `/api/` del back.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Permite evolucionar la API (`/api/v2`) sin romper clientes.                                                                                                                                                                                                                                           |
| DD-8  | **La IA no es pública:** solo el back la consume, por red interna de Docker y con una API key.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Seguridad básica (§3.3).                                                                                                                                                                                                                                                                              |
| DD-9  | **Las clases no animales** (persona, vehículo, vacío) se devuelven como `category`, pero **no cuentan** en las estadísticas de fauna.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Catálogo SpeciesNet (§3.1) vs. avistamientos de especies.                                                                                                                                                                                                                                             |
| DD-11 | **Un único administrador** (`role=admin`, creado solo por comando en el servidor) con un panel de estadísticas globales (usuarios, sesiones anónimas, contenido y fauna) y la configuración de retención anónima (DD-2). **Matriz de privacidad**, aplicada en el back:<br>• datos **anónimos** y **públicos**: el admin ve los registros y las estadísticas;<br>• datos **privados**: **solo conteos** (cuántas cámaras y proyectos privados hay), nunca sus registros, especies ni ubicación, y no entran en las estadísticas globales.<br>**Borrado lógico en todo** (nunca físico desde la app, salvo los datos anónimos creados con la retención desactivada), con restauración y auditoría de cada acción del admin. Detalle: [FLUJOS_SISTEMA.md §11](FLUJOS_SISTEMA.md#11-flujos-del-administrador).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Extra que entrega CETERIS404 fuera del TDR, sin costo. Resuelve además un problema de seguridad actual (BE-51).                                                                                                                                                                                       |
| DD-12 | **Cola de procesamiento con Redis.** Subir un archivo solo lo valida y lo deja en un **temporal** y en la cola (respuesta 202 en segundos); los *workers* (`arq`) llaman a la IA, guardan el resultado y borran el temporal. La cola es **justa** por dueño (máximo 2 en proceso a la vez cada uno, por turnos), tiene límites por usuario y global, y la BD es la fuente de verdad del estado (un *reaper* recupera lo colgado). El usuario **sigue navegando** con la bandeja de subidas visible en toda la app. Redis también sostiene el *rate limit*, los contadores de correo y las tareas dprogramadas. Detalle: [API §7](contratos/API_BACK_FRONT.md#7-clasificación-lotes-cola-y-archivos), [FLUJOS FL-08/09/33](FLUJOS_SISTEMA.md).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Varios usuarios subiendo a la vez sin bloquearse; tolerancia a fallos de la IA.                                                                                                                                                                                                                       |
| DD-13 | **Recuperación de contraseña por correo con Resend** (plan gratuito: 100 al día y 3000 al mes), con topes propios más bajos (80 y 2500), límites por correo (3 por hora, 5 por día) y por IP, token de un solo uso de 30 min, respuesta genérica (no revela si el correo existe), envío por la cola y un respaldo del admin (enlace manual). Requiere el dominio verificado.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Evita perder cuentas; cuidando la cuota del plan gratuito.                                                                                                                                                                                                                                            |
| DD-14 | **La corrección parte de la propuesta de la IA:** el front muestra la especie de mayor confianza; con "No es esta especie" ofrece las 2 alternativas, buscar en el catálogo, "No está en el catálogo" (con un nombre sugerido en texto libre + el taxón superior opcional) o "No hay ningún animal". Todo queda registrado (`correction_source`, `suggested_name`, historial) para medir el acierto real del modelo y como insumo de futuras mejoras.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Validación rápida y datos para mejorar el modelo.                                                                                                                                                                                                                                                     |
| DD-16 | **Ráfagas (D10):** se cuenta **por archivo** (opción A). El sistema **sugiere** grupos de registros de la misma especie, en la misma cámara y a pocos minutos (5 min, ajustable), y el **investigador decide** si conserva todos o deja uno o los que elija. Los descartados quedan `discarded_repeat`: no cuentan como avistamiento, no se borran y no se consideran error de la IA. Detalle: [FLUJOS FL-16](FLUJOS_SISTEMA.md), [API §8.8](contratos/API_BACK_FRONT.md#88-ráfagas-registros-repetidos-del-mismo-animal-d10).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | TDR §3.1 ("cantidad de avistamientos"), con control del investigador.                                                                                                                                                                                                                                 |
| DD-17 | **Ubicación de cámaras públicas:** solo el dueño ve las coordenadas exactas; cualquier otra persona las ve **redondeadas a ~1 km**, y las distancias de `nearby` van en bandas (sin triangulación). Antes de hacer pública una cámara o un proyecto se muestra una **advertencia** (ubicación aproximada, especies, fotogramas; cuidado con las especies sensibles).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Protección de especies sensibles (D2).                                                                                                                                                                                                                                                                |
| DD-18 | **Para cualquier biólogo:** se aceptan hoy los formatos definidos en `wwm_pipeline/formats.py` (imagen: JPG, JPEG, PNG, BMP, WebP, TIFF; video: MP4, AVI, MOV, MKV, WMV, FLV, WebM; formatos adicionales como HEIC/HEIF, TIF, M4V, 3GP, MTS/M2TS quedan diferidos a `IA-16`), hasta 300 MB (y 100 MP). Si un video supera 15 s, **no se rechaza** (`F1-D10`): se analizan los primeros `15.0 s` y se devuelve warning `VIDEO_TRUNCATED`. | D4 / `F1-D10`. |
| DD-15 | **Varias cámaras en el mismo lugar son válidas** (estaciones pareadas, reinstalaciones, otros investigadores): no se bloquea por cercanía. Se **informa** de las propias y las públicas cercanas (nunca de las privadas ajenas) y se ofrece la **reinstalación** como una cámara nueva enlazada a la anterior. Todos los casos borde están en [flujos/CASOS_BORDE.md](flujos/CASOS_BORDE.md).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | El TDR pide una cámara por instalación con fechas de colocación y retiro.                                                                                                                                                                                                                             |
| DD-10 | **Sincronización escritorio → web:** la app exporta un paquete `.wwm.zip` con registros y fotogramas (sin videos ni estadísticas), y la web lo importa con vista previa, deduplicación por hash y validación de seguridad. Detalle: [FL-22/23](FLUJOS_SISTEMA.md#9-sincronización-escritorio--web).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Fuera del TDR: presentarlo como valor agregado (D6).                                                                                                                                                                                                                                                  |

**Documentos que acompañan este plan:** [FLUJOS_SISTEMA.md](FLUJOS_SISTEMA.md) (qué hace el sistema, flujo por flujo, y el modelo de datos) y [ESTANDARES_BACKEND_IA.md](ESTANDARES_BACKEND_IA.md) (arquitectura, respuestas, errores, logs y clean code).

---

## 3. Contrato entre componentes

> **El contrato completo está en [`contratos/`](contratos/)** y es la fuente única de verdad. Este apartado solo lo resume; si algo no coincide, manda el archivo del contrato.

| Contrato | Qué define | Implementa → consume |
|---|---|---|
| [contratos/API_BACK_FRONT.md](contratos/API_BACK_FRONT.md) | Los **42 grupos de endpoints** del back (`/api/v1`), los schemas (`CameraStation`, `Project`, `Classification`, `Batch`, `Stats`…), los body y las respuestas de ejemplo, los errores por endpoint, la matriz de permisos y la lista de lo que se elimina | Job → Miguel |
| [contratos/API_IA_BACK.md](contratos/API_IA_BACK.md) | `POST /detect` (`media`, `capture`, `result`, `evidence` en base64, `analysis`, `model`), `/health`, `/catalog`, los códigos `IA_*` y su traducción en el back, y el mapeo a columnas | Diego → Job |
| [contratos/PAQUETE_ESCRITORIO.md](contratos/PAQUETE_ESCRITORIO.md) | El formato `.wwm.zip` 1.0 (`manifest.json`, `classifications.jsonl`, `evidence/`), sus validaciones y su versionado | Diego → Job y Miguel |

**Decisiones del contrato que conviene conocer:**
- **Subida por archivo dentro de un lote y cola Redis** (DD-12): cada archivo responde **202 `queued`** con su posición y su espera estimada; los *workers* lo analizan en segundo plano y el front sigue el avance por *polling* desde una bandeja visible en toda la app.
- **La corrección de una especie se hace por `label_id` del catálogo**; el texto libre solo se guarda como sugerencia cuando la especie no está en el catálogo (DD-14).
- **Los fotogramas se piden con autenticación** (`GET /classifications/{id}/evidence`) y el front los muestra como *blob*.
- **La IA devuelve `alternatives`** (las siguientes 2 o 3 opciones), que el front ofrece como atajos al corregir.
- **La envoltura estándar** `{status, data, message, error, meta}` se usa en el back y en la IA ([ESTANDARES §4](ESTANDARES_BACKEND_IA.md#4-formato-de-respuesta-estándar)).

**Detalle de las tareas por componente** (v2: criterios de aceptación verificables, ⛔ lo que cada tarea necesita del otro, 🔁 con qué avanzar mientras tanto y ➡️ qué desbloquea), con lo que cada una debe producir o consumir del contrato: [tareas/TAREAS_BACKEND.md](tareas/TAREAS_BACKEND.md) · [tareas/TAREAS_FRONTEND.md](tareas/TAREAS_FRONTEND.md) · [tareas/TAREAS_IA.md](tareas/TAREAS_IA.md) · [tareas/TAREAS_ESCRITORIO.md](tareas/TAREAS_ESCRITORIO.md). Las tablas de §4–§7 de este plan son el **resumen**. **Dependencias entre personas, sustitutos (`ia-fake`, MSW, fixtures) e hitos semanales de integración (H1–H6):** [tareas/DEPENDENCIAS.md](tareas/DEPENDENCIAS.md).

**Recorridos paso a paso** (pantalla → acción → endpoint → resultado): [flujos/FLUJOS_DETALLADOS.md](flujos/FLUJOS_DETALLADOS.md). **Casos borde:** [flujos/CASOS_BORDE.md](flujos/CASOS_BORDE.md).

---

## 4. IA — `ia-deteccion` (Diego)

### 4.A Estado actual
- **Pipeline:** MegaDetector v5a (`torch.hub`, umbral 0.30) → recorte → SpeciesNet `v4.0.2a` **solo el clasificador**, sin *ensemble* ni geofence.
- **Video:** **3 frames fijos** (25/50/75 %). `VIDEO_FPS_SAMPLING = 2.0` y `SPECIESNET_CONFIDENCE_THRESHOLD = 0.15` están definidos pero **no se usan**.
- **Respuesta:** `results[].{timestamp_seconds, detections[].{species:"género;especie;común", confidence, crop_url}}`. Se pierden la familia, el orden y la clase, y llega una detección por frame.
- **Imágenes:** la API responde **500** cuando hay detecciones (`DetectionDetail(**d)` recibe `species` como lista).
- Guarda recortes para siempre en `detections/` y los sirve públicamente.
- Inferencia síncrona dentro de un endpoint `async`, así que bloquea el *event loop*.
- `detector.py` tiene ~130 líneas de código comentado; hay schemas duplicados y se usa `@app.on_event`, que está obsoleto.
- `main` está atrasado respecto de `escritorio`.

### 4.B Cambios (`ia-clasificacion-fauna` — ✅ completados)
| ID | Cambio | Prioridad · Semana | Criterio de aceptación / Estado |
|---|---|---|---|
| IA-01 | Hacer *merge* de `escritorio` en `main` y trabajar sobre `main`. | P1 · S1 | ✅ **Completado** en `ia-clasificacion-fauna`. |
| IA-02 | Extraer un **pipeline común** (`wwm_pipeline/pipeline.py`) usado por la API y por el escritorio. | P0 · S1 | ✅ **Completado** (`wwm_pipeline/`). |
| IA-03 | Corregir el **bug de imágenes**. | P0 · S1 | ✅ **Completado**. |
| IA-04 | Sacar la inferencia del *event loop* (`api/inference.py`, cola y timeout de un solo hilo). | P1 · S2 | ✅ **Completado**. |
| IA-05 | **No escribir en disco:** sin guardado de recortes en `detections/` y borrado de temporales en `finally`. | P0 · S2 | ✅ **Completado**. |
| IA-06 | Limpiar código y fijar dependencias con hash (`requirements-api.txt`, `requirements-desktop.txt`, `lifespan`). | P2 · S3 | ✅ **Completado**. |

### 4.C Nuevas implementaciones (`ia-clasificacion-fauna`)
| ID | Implementación | Prioridad · Semana | Criterio de aceptación / Estado |
|---|---|---|---|
| IA-10 | **Set de validación** con videos y fotos etiquetados a mano + `eval/` para línea base. | P0 · S1 | ⏳ **Pendiente** (infra `eval/` lista, falta etiquetado/corrida final). |
| IA-11 | **Estrategia de extracción de fotogramas** configurable (`wwm_pipeline/sampling.py`: web `10fps@0-2s+4fps/max60/hasta15s`, escritorio `15fps@0-2s+6fps/max120`, descartes `duplicate`/`blurry`/`cap`). | P0 · S1–S2 | ✅ **Completado**. |
| IA-12 | **Geofence** de SpeciesNet por país (`BOL`). | P0 · S2 | 🚫 **Omitido por diseño** (SpeciesNet corre sin geofence; `ModelInfo` tiene `extra="forbid"` sin `geofence`). |
| IA-13 | **Agregación por archivo:** votación ponderada entre frames con animal, subida al taxón padre y `low_evidence` si la evidencia es débil. | P0 · S2 | ✅ **Completado**. |
| IA-14 | **Taxonomía completa** (clase, orden, familia, género, especie, `common_name` en inglés por defecto, `rank`). | P0 · S2 | ✅ **Completado**. |
| IA-15 | **Fotograma de evidencia** completo con recuadro, en JPEG ≤ 960 px y base64. | P0 · S2 | ✅ **Completado**. |
| IA-16 | Formatos adicionales pendientes (`pillow-heif` para HEIC/HEIF y extensiones fuera de `formats.py` base: `.tif`, `.m4v`, `.3gp`, `.mts`, `.m2ts`). Videos > 15 s se **truncan a 15.0 s** (`F1-D10`, sin error de duración) y límite 100 MP (`too_many_pixels`). | P1 · S2 | 🚧 **Parcial**: formatos base de `formats.py` + `F1-D10` + 100 MP ✅ listos; HEIC/extra ⏳ pendiente (`IA-16`). |
| IA-17 | **Medición final:** correr `eval/` con la estrategia nueva y documentar mejora. | P0 · S3 | ⏳ **Pendiente** (depende de `IA-10`). |
| IA-18 | Endpoint `GET /api/v1/health` (modelos cargados, `status: ok\|loading\|models_missing\|error`, `max_file_mb: 300.0`, `version.app`, muestreo). | P2 · S3 | ✅ **Completado**. |
| IA-19 | **Catálogo de especies** (`catalog/speciesnet_catalog.json` con **3538 taxones**, `sample` 558) y `GET /api/v1/catalog` con `ETag`/`304`. | P1 · S3 | ✅ **Completado**. |
| IA-20 | **Metadatos del archivo** en el pipeline (`sha256`, duración y fecha de captura con fuente). | P0 · S2 | ✅ **Completado**. |
| IA-21 | **Schema del contrato** (`wwm_pipeline/contract.py` + `schemas/`), fuente de verdad Pydantic V2. | P0 · S1 | ✅ **Completado**. |
| IA-22 | **`ia-fake`**: contenedor simulado (`fake/`, puerto `8001`, con fixture `_toolong` truncado a 15.0 s y sin `error_duration.json`). | P0 · S1 | ✅ **Completado**. |

### 4.E Estándares (✅ completados en `ia-clasificacion-fauna`)
| ID | Tarea | Prioridad · Semana | Criterio de aceptación / Estado |
|---|---|---|---|
| IA-40 | Reestructuración en `wwm_pipeline/` (puro), `api/` y `desktop/`. | P0 · S1–S2 | ✅ **Completado**. |
| IA-41 | Envoltura `{status,data,message,error,meta}` y códigos `IA_*` (`400 IA_INVALID_FORMAT`, `422 IA_DECODE_FAILED`, `500 IA_INTERNAL`, `503/504`). | P0 · S2 | ✅ **Completado**. |
| IA-42 | Logs JSON con `request_id` y `flow` (`api/logs.py`). | P1 · S2 | ✅ **Completado**. |
| IA-43 | `ruff`, `mypy`, *pre-commit* y CI. | P1 · S2 | ✅ **Completado**. |

### 4.D Seguridad y calidad (✅ completados en `ia-clasificacion-fauna`)
| ID | Mejora | Prioridad · Semana |
|---|---|---|
| IA-30 | ✅ **API key** obligatoria (`X-API-Key`, `AI_API_KEY` obligatoria en `production`, `dev-key` en dev). | P0 · S3 |
| IA-31 | No exponer el puerto de la IA en producción (solo red interna Docker, puerto interno `8001`). | P0 · S6 |
| IA-32 | ✅ Límite de tamaño (`300 MB`, `100 MP`) y timeout de procesamiento por archivo (`api/inference.py`). | P1 · S3 |
| IA-33 | ✅ Tests (`tests/api/`, `pipeline/`, `contract/`, `fixtures/`). | P1 · S3 |

---

## 5. App de escritorio — Producto 1 (Diego)

### 5.A Estado actual
- `desktop_app.py` (Tkinter) → `dist/desktop_app.exe`: un `.exe` **portable** de PyInstaller de ~780 MB que se autoextrae al abrir (10–20 s).
- Elegir carpeta de entrada y de salida, y la opción copiar o mover; procesa en un hilo aparte con log en vivo. La carpeta **no es recursiva** ✅.
- Analiza hasta 3 frames y se **detiene al primer animal**; toma la mejor especie y la envía a `salida/<genero_especie_comun>/`. Si no hay especie, va a `animal_desconocido/`.
- **No guarda el fotograma junto al archivo**: solo deja un recorte en `detections/`, al lado del .exe.
- Primer inicio: descarga los pesos de MegaDetector a `models/`. **Pero** `torch.hub.load("ultralytics/yolov5")` baja el repo de YOLOv5 desde GitHub a `~/.cache/torch/hub` (y reintenta con `force_reload=True`, que necesita red), y SpeciesNet se baja con kagglehub a la caché del usuario.
- Manual: `README.txt` de usuario final.

### 5.B Cambios (`ia-clasificacion-fauna/desktop` — ✅ completados)
| ID | Cambio | Prioridad · Semana | Criterio de aceptación / Estado |
|---|---|---|---|
| DS-01 | Usar el **pipeline común** (`wwm_pipeline/`, modo precisión `15fps@0-2s+6fps/max120`). | P0 · S2 | ✅ **Completado**. |
| DS-02 | **Sin especie → el archivo se queda en la carpeta de origen** (sin `animal_desconocido/`). | P0 · S3 | ✅ **Completado**. |
| DS-03 | Nombre de carpeta seguro para Windows (`genero_especie_comun`, `panthera_sp`, `felidae_fam`). | P1 · S3 | ✅ **Completado**. |
| DS-04 | Dejar de escribir en `detections/` junto al `.exe`. | P0 · S3 | ✅ **Completado**. |

### 5.C Nuevas implementaciones
| ID | Implementación | Prioridad · Semana | Criterio de aceptación / Estado |
|---|---|---|---|
| DS-10 | **Fotograma de evidencia junto a cada archivo clasificado** (`_fotograma.jpg`). | P0 · S3 | ✅ **Completado**. |
| DS-11 | **Modo offline real** (`third_party/`, caché local de modelos, sin `force_reload`). | P0 · S3 | ✅ **Completado**. |
| DS-12 | **Instalador de Windows** (Inno Setup + PyInstaller, `build.ps1`, `installer/`, variantes estándar y completa). | P0 · S3 | ✅ **Completado** (base lista; validar `DS-16`). |
| DS-13 | Pantalla de primer inicio con descarga desde GitHub Releases + `sha256` (`desktop/model_store.py`). | P1 · S3 | ✅ **Completado**. |
| DS-14 | **Registro local de resultados:** `clasificaciones.jsonl` y reanudación por hash. | P1 · S3 | ✅ **Completado**. |
| DS-17 | **Exportar para la web** (`package.py` + `package_validator.py`): genera `.wwm.zip` con `manifest.json`, `classifications.jsonl` y `evidence/` (`F2-D2`/`F2-D9`: `evidence` solo cuando `category == animal`). | P1 · S3 (o S4) | ✅ **Completado** en IA/escritorio. |
| DS-18 | Fotograma con **minuto:segundo** (`mm:ss`) y `timestamp_seconds`. | P0 · S3 | ✅ **Completado**. |
| DS-19 | Logs JSON rotativos en `%LOCALAPPDATA%\WWM\logs` y diagnóstico. | P1 · S3 | ✅ **Completado**. |
| DS-20 | **Requisitos de hardware** y validación mínima en instalador/app (depende de `IA-17`). | P0 · S3 | ⏳ **Pendiente medición final** (`IA-17`). |
| DS-15 | **Manual de instalación y uso** (PDF). | P0 · S3 | ⏳ **Pendiente**. |
| DS-16 | **QA del Producto 1** en PC limpia con set de validación (`IA-10`). | P0 · S3 | ⏳ **Pendiente**. |

### 5.D Seguridad y calidad
| ID | Mejora | Prioridad · Semana | Estado |
|---|---|---|---|
| DS-30 | Antes de **mover**, verificar copia existente y tamaño. | P0 · S3 | ✅ **Completado**. |
| DS-31 | Botón *Detener* que termine el archivo en curso limpiamente. | P1 · S3 | ✅ **Completado**. |
| DS-32 | Firmar el instalador (opcional). | P2 | Opcional. |

---

## 6. Backend — `BACKWWF` (Job)

### 6.A Estado actual
- **Stack:** FastAPI 0.128 · SQLAlchemy 2 async + **asyncpg** · `pydantic-settings` · **PyJWT** + bcrypt · Alembic configurado · pytest (7 archivos).
- **Ya existe:**
  - auth JWT (`/auth/*`);
  - soft delete;
  - N:M `project_stations`;
  - `media_files` con video e imagen y validación de extensión y MIME;
  - `species` con `family`, `genus`, `scientific_name` y `common_name`;
  - `/summary` por cámara y proyecto;
  - `StandardResponse`;
  - enums centralizados.
- **En contra del TDR o con problemas:**
  - **sesión anónima** (`anon_sessions`, `X-Anon-Session-ID`, `/users/me/claim`, `/users/me/history`): la idea se mantiene (DD-2), pero el ID lo genera el cliente, se guarda en claro y no vence, así que se rehace (BE-01);
  - archivos guardados en `uploads/`;
  - **timeout de 2 s con *fallback* inventado** ("Jaguar 94,5 %");
  - `parse_taxonomy` espera 4 partes y la IA envía 3, así que `family` llega en `None`;
  - una fila por detección y por frame (sobreconteo);
  - `url_img` es un recorte interno de la IA;
  - `species`, `reports`, `videos`, `individuals` y `ai` **sin auth**;
  - visibilidad sin aplicar en los listados;
  - `colaborators`;
  - modelos `video` e `individual` duplicados o fuera de alcance;
  - `migrations/versions/` vacío;
  - sin validación de 15 s, sin `capture_date` real, sin Excel y sin catálogo.
- Su plan de 17 tickets ([plan Job](../plan_implementacion_TDR_CETERIS404-Job.md)) cubre gran parte; aquí quedan **alineadas** con el contrato §3. En particular, la §9 de su plan (`requirements.txt` con psycopg2 y python-jose) **no se aplica**: se mantienen asyncpg y PyJWT.

### 6.B Cambios
| ID | Cambio | Prioridad · Semana | Criterio de aceptación |
|---|---|---|---|
| BE-01 | **Rehacer la sesión anónima** según DD-2 y FL-03/04:<br>• el token lo genera el back (hoy lo inventa el front) y se guarda **hasheado**;<br>• header `X-Anon-Token`;<br>• `expires_at` por inactividad;<br>• dueño `owner_user_id` **XOR** `anon_session_id` con `CHECK`;<br>• `POST /anon-sessions/claim` atómico e idempotente, con resolución de choques de `code`;<br>• el contenido anónimo siempre es privado;<br>• límites `ANON_MAX_*`.<br>Reemplaza `/users/me/claim` y `/users/me/history`. | P0 · S1–S2 | Los tests de FL-03/04 en verde: crear → clasificar → registrarse → asociar → los datos aparecen en la cuenta; un token vencido da 401 `ANON_SESSION_EXPIRED`. |
| BE-02 | **Dependencia `get_owner`** (usuario **o** sesión anónima) en todas las mutaciones. Marcar algo como público, validar, exportar e importar requieren usuario. | P0 · S1 | Sin token ni sesión anónima → 401 `AUTH_REQUIRED`. |
| BE-03 | 🚧 **Cliente de IA real (v0 PR #4 — requiere realineación):** base `app/integrations/ai_client.py` y `ai_contract.py` fusionada en PR #4 (`SPIKE-01`); falta alinear `ai_contract.py` al `contract.py` final de Diego (quitar `geofence`, agregar `low_evidence`, `truncated_at_seconds`, puerto `:8001`, reintento en `500 IA_INTERNAL`) y conectar el pipeline real eliminando el fallback en routers. | P0 · S1 | Con la IA apagada: 502 y +0 filas en `species`. |
| BE-04 | **Adaptarse al contrato IA ([API_IA_BACK.md](contratos/API_IA_BACK.md)) y al modelo de datos** ([FLUJOS §3](FLUJOS_SISTEMA.md#3-modelo-de-datos-objetivo)):<br>• la tabla `species` (detecciones) pasa a `classifications` (**una fila por archivo**) más `classification_batches`;<br>• reemplazar `parse_taxonomy` por la lectura de `taxonomy`;<br>• guardar `category`, `rank`, `confidence`, **`low_evidence`**, `file_sha256`, `captured_at` y su fuente, `evidence_frame_index`, **`evidence_timestamp_seconds`**, `evidence_bbox` y `model` (`detector`, `classifier`, `sampling`, `pipeline_version`, **sin `geofence`**);<br>• emitir warning `VIDEO_TRUNCATED` si `truncated_at_seconds != null` (`F1-D10`);<br>• índice único `(camera_station_id, file_sha256)`.<br>Usar el contenedor `ia-fake` (`:8001`) y sus fixtures desde ya (`IA-22` lista). | P0 · S2–S3 | Un archivo = una clasificación; `family` poblado; un archivo repetido → `DUPLICATE_FILE`. |
| BE-05 | **Procesamiento efímero + storage de fotogramas:**<br>• `TemporaryDirectory` con borrado en `finally`;<br>• quitar `uploads/`, `file_url` y el volumen `./uploads`;<br>• crear `StorageBackend` con `LocalStorage` (`STORAGE_LOCAL_PATH`, volumen `evidence`), dejando `S3Storage` como *stub*;<br>• el fotograma se valida y re-codifica con Pillow y se guarda por clave;<br>• `GET /classifications/{id}/evidence` con autorización;<br>• sin estáticos públicos.<br>Ver [ESTANDARES §9](ESTANDARES_BACKEND_IA.md#9-almacenamiento-de-fotogramas). | P0 · S2 | Tras subir N archivos, solo quedan N JPEG en `evidence/` y ningún medio original; el fotograma de una cámara privada da 404 a otro usuario. |
| BE-06 | **Unificar el modelo multimedia:** eliminar `video` (modelo, schema, router, servicio) e `individual`; `species.video_id` fuera. | P1 · S2 | Solo existe `media_files`. |
| BE-07 | **Cámaras según el TDR:** `observations TEXT`, `visibility` (`public`/`private`, por defecto `private`), `still_installed` (o derivado de `retrieval_date IS NULL`), `deployment_date` y `retrieval_date` como `TIMESTAMP` con zona horaria, `name` + `station_code` único **por usuario**. Los campos fuera del TDR (marca, modelo, IR, etc.) pasan a opcionales y no se exigen. | P0 · S1–S2 | El alta y la edición aceptan exactamente los campos del TDR. |
| BE-08 | **Proyectos individuales:** eliminar `colaborators` y `/projects/{id}/collaborators`; renombrar `status` a `visibility`. | P1 · S2 | — |
| BE-09 | **`/stats`** (reemplaza a `/summary`) con la forma de [API §10](contratos/API_BACK_FRONT.md#10-estadísticas): obligatorias + complementarias de DD-5. Cuenta **archivos clasificados** con la taxonomía efectiva (la corregida, si existe) y excluye `rejected` y las clases no animales. Un único `StatsService`, que usan también Excel y PDF. | P0 · S3 (complementarias P1 · S4) | Mismos números en pantalla, Excel y PDF; el proyecto = la suma de sus cámaras. |
| BE-10 | **Validación ampliada:** `PUT /classifications/{id}/validation` (`confirm`/`correct`/`reject`), auditoría (`validated_by`, `validated_at`, `notes`) y los valores corregidos validados contra el catálogo. | P0 · S3 | Se puede confirmar, corregir o rechazar, y queda el registro de quién y cuándo. |
| BE-11 | **Prefijo `/api/v1` y nombres de rutas** según [API §15](contratos/API_BACK_FRONT.md#15-resumen-de-endpoints) (un `APIRouter(prefix="/api/v1")` que incluye todos). Se coordina con FE-09, porque el front cambia la base URL en el mismo PR o sprint. | P0 · S2 | No queda ninguna ruta fuera de `/api/v1` (salvo `/docs` en desarrollo). |
| BE-12 | **Eliminar los indicadores ecológicos y VisualCrossing** (`indicators_service.py`, `/reports/indicators/*`, `species_data_service` si solo los alimenta). | P1 · S3 | El back arranca sin claves de clima y sin código muerto. |
| BE-13 | **Lotes y subida por archivo** (FL-08): `POST /classification-batches` → `POST /classification-batches/{id}/files` (uno por archivo, que siempre responde un `BatchItem`) → `POST …/complete`. Reemplaza a `/camera-stations/{id}/files`, `/videos` y `/media-files`. La lógica va en `ClassificationService`, no en el router. Contrato: API §7. | P0 · S2 | Un lote de 3 (ok, > 15s con warning `VIDEO_TRUNCATED`, IA con timeout) → `completed_with_errors` con los 3 ítems correctos; el router tiene menos de 20 líneas. |
| BE-14 | **Autenticación según el contrato** (API §2): `register`, `login` (con `anon_session` en la respuesta), `refresh` con **rotación** y detección de reutilización, `logout`, `GET/PATCH /auth/me`, cambio de contraseña. | P0 · S1–S2 | Refresh reutilizado → toda la cadena revocada. |
| BE-15 | `GET /config/public` (API §4.1): límites, formatos y `anon_data_retention`. | P0 · S2 | — |
| BE-16 | `GET /classifications` con todos los filtros de API §8.1, más `GET`, `PATCH` (asignar cámara) y `DELETE` por ID. | P0 · S3 | — |
| BE-60 | **Infraestructura de la cola:** Redis (AOF, contraseña, red interna), `arq`, el temporal compartido `TMP_UPLOAD_PATH` y el servicio `worker` (misma imagen, otro comando). Las tareas programadas FL-30, FL-31 y FL-33 pasan a cron de `arq`, y `slowapi` usa Redis. | P0 · S2 | `docker compose up` levanta `redis` y `worker`; un archivo pasa de `queued` a `done`. |
| BE-61 | **Worker de clasificación + cola justa + reaper** (FL-08/09/33): despachador por dueño (`QUEUE_PER_OWNER_INFLIGHT`), posición y espera estimadas, latido, reintentos de los errores transitorios, idempotencia, *reaper*, límites `QUEUE_*`, endpoints de cancelar y reintentar. | P0 · S2–S3 | Los casos CB-30…CB-44 en verde. |
| BE-62 | **Recuperación de contraseña** (FL-14): endpoints `forgot`, `validate` y `reset`, `password_reset_tokens`, `EmailProvider` + Resend, envío por la cola, topes y contadores en Redis, `email_log`, enlace manual del admin. | P1 · S4 | Los casos CB-73…CB-78 en verde; nunca se superan 80 envíos por día. |
| BE-63 | **Cámaras cercanas, reinstalación y concurrencia:** `GET /camera-stations/nearby` (sin revelar las privadas ajenas), `POST /camera-stations/{id}/redeploy`, `version` + `If-Match` → `CONFLICT_STALE`, `meta.warnings` (`CAMERA_COORDS_SUSPECT`, `CAMERA_MOVED_WITH_DATA`), código único sin distinguir mayúsculas. P2: `time-offset`. | P1 · S3 | Los casos CB-01…CB-21 en verde. |
| BE-66 | **Ráfagas** (FL-16): `GET /classifications/burst-candidates` (agrupación encadenada por cámara, taxonomía efectiva y ventana; con *window functions* de SQL), `POST /classifications/repeat-batch` y `/dismiss`, la acción `discard_repeat`, `discarded_repeat` en `/stats` y en el Excel, y la exclusión de `model_feedback`. | P1 · S4 | El ejemplo de las 3 fotos de jaguar: el grupo se sugiere; dejar 1 → `/stats` cuenta 1; `reset` → vuelve a 3. |
| BE-64 | **Duplicados entre cámaras** (`DUPLICATE_FILE_OTHER_CAMERA`) y deduplicación por `sha256` en las estadísticas globales del admin. | P1 · S3 | CB-51, CB-52. |

### 6.C Nuevas implementaciones
| ID | Implementación | Prioridad · Semana | Criterio de aceptación |
|---|---|---|---|
| BE-20 | **Vencimiento de sesiones anónimas (FL-30)** y **limpieza (FL-31)** como cron de `arq` en el worker (BE-60), más el *reaper* FL-33 (BE-61). FL-30 pasa a `expired` las sesiones inactivas; conserva las filas con `anon_retain = true` y elimina físicamente, con sus fotogramas, las que tienen `anon_retain = false`, y registra los conteos en `anon_purge_runs`. FL-31 borra los temporales de más de 1 h y los fotogramas huérfanos por fallos de escritura, nunca los de registros borrados lógicamente. | P0 · S2 | Con la retención activa, una sesión vencida da 401 y conserva el 100 % de sus datos; con la retención inactiva, quedan 0 filas y 0 fotogramas; una sesión mixta (cambio a mitad de sesión) conserva solo lo creado con `true`. |
| BE-58 | **Configuración en caliente** (FL-44):<br>• tabla `system_settings` con `anon_data_retention = true` en la migración inicial;<br>• `SettingsService` con caché corta (por ejemplo, 30 s) e invalidación al guardar;<br>• columna `anon_retain` en las filas anónimas, que se fija **al crearlas** a partir de la configuración vigente;<br>• `data_retention` en la respuesta de `POST /anon-sessions` y `GET /anon-sessions/current`;<br>• `GET/PUT /admin/settings` con auditoría. | P1 · S3 | Cambiar el valor no modifica ninguna fila existente; las nuevas filas toman el valor nuevo antes de 30 s. |
| BE-21 | **Validador de medios:** firma binaria (`filetype`), extensiones alineadas a `formats.py`, tamaño máximo (`MAX_FILE_MB` = 300 MB / 100 MP) y lectura informativa de duración con `ffprobe` (si > 15 s no rechaza, registra para warning `VIDEO_TRUNCATED` per `F1-D10`). | P0 · S2 | Archivo inválido → `MEDIA_UNSUPPORTED_FORMAT` o `MEDIA_TOO_LARGE`; video > 15 s entra a cola y marca `VIDEO_TRUNCATED`. |
| BE-22 | **`captured_at`:** tomar `capture` de la respuesta de la IA (IA-20) y, si no viene, usar `lastModified` del front y, por último, la hora de subida. Guardar `captured_at_source`. | P0 · S3 | `captured_at_source` nunca está vacío. |
| BE-23 | **Autorización por dueño y visibilidad** en todos los routers: listados = propios + públicos; detalle privado ajeno → 403; mutaciones solo del dueño; asociar solo cámaras propias a proyectos propios. | P0 · S2 | Tests de IDOR en verde. |
| BE-24 | **`POST /classifications/validation-batch`** (`{ids[], action}`, solo `confirm`/`reject`). | P1 · S3 | — |
| BE-25 | **`GET /catalog/species?q=`**, sincronizado/servido desde `speciesnet_catalog.json` (3538 taxones listos vía `IA-19` / `GET /api/v1/catalog` con `ETag`/`304`; `common_name` en inglés por defecto). | P1 · S3 | El autocompletado responde en menos de 200 ms. |
| BE-26 | **`GET /reports/excel`** (openpyxl, en memoria, con `to_thread`): hojas *Resumen* (alcance, filtros, fecha, versión del modelo, `request_id`), *Por especie*, *Por género*, *Por familia* y *Clasificaciones* (archivo, cámara, coordenadas, fecha de captura y su fuente, **minuto:segundo** del fotograma, taxonomía de la IA y validada, confianza, estado, notas, origen web o escritorio). Columnas finales según D3. | P0 · S4 | El `.xlsx` abre en Excel y LibreOffice. |
| BE-26b | **`GET /reports/pdf`** (ReportLab + matplotlib): portada con el alcance y los filtros, totales, gráficos de barras por especie, género y familia, y tablas. Mismo dataset que BE-26 (DD-6). | P0 · S5 | Los números del PDF coinciden con los del Excel y la pantalla. |
| BE-27 | **Migración inicial de Alembic** con el esquema final + índices (`user_id, visibility`, `station_id, capture_date`, taxonomía). El arranque ejecuta `alembic upgrade head`; nada de `create_all`. | P0 · S3 | `upgrade` y `downgrade` funcionan sobre una BD vacía. |
| BE-28 | **(Opcional; con la subida por archivo de BE-13 ya no hace falta)** Procesamiento de lotes: si un lote con sesión supera el timeout HTTP, pasar a procesamiento en segundo plano con estado por archivo (`pending/processing/done/error`) y *polling* `GET /camera-stations/{id}/files?status=`. | P2 · — | Un lote de 20 videos no da timeout en el navegador. |
| BE-29 | `GET /health` (vivo) y `GET /health/ready` (BD + IA alcanzables). | P1 · S4 | Lo usa el *healthcheck* de Docker. |
| BE-40 | **Importación de paquetes de escritorio (FL-23):**<br>• `POST /imports/desktop` (vista previa);<br>• `POST /imports/{id}/confirm`;<br>• tabla `desktop_imports`;<br>• todas las validaciones de seguridad de FL-23 (tamaños, *zip slip*, `evidence` requerido solo en `category == animal` por `F2-D2`/`F2-D9`, re-codificar los JPG, checksum, schema por línea `LINE_INVALID`/`EVIDENCE_MISSING`, catálogo, duplicados);<br>• reutiliza el guardado de BE-04 y BE-05.<br>La generación de paquetes (`DS-17`) ya está lista en `ia-clasificacion-fauna`. | P1 · S5 | Importar el mismo paquete dos veces → la segunda vez marca todo como duplicado; un zip con `../` es rechazado. |

### 6.D Seguridad y calidad
| ID | Mejora | Prioridad · Semana |
|---|---|---|
| BE-30 | ✅ *(Parcial en PR #1/`BUG-01`)* Secretos solo por `.env`: `SECRET_KEY`, `REFRESH_SECRET_KEY` y `AI_API_KEY` obligatorios en producción (`fail-fast` validado en `config.py`). URLs eliminadas de código y scripts. | P0 · S1 |
| BE-31 | *Rate limiting* (`slowapi`): login y registro 10/min por IP; clasificación 30/min por IP o usuario. | P1 · S4 |
| BE-32 | Límite global del *body*, cabeceras de seguridad (`nosniff`, `X-Frame-Options`, `Referrer-Policy`) y CORS solo para el dominio de producción. | P1 · S4 |
| BE-33 | El manejador global de excepciones no expone *stack traces* cuando `ENVIRONMENT=production` (BL-03 del backlog). | P1 · S4 |
| BE-34 | Quitar `echo=True` del engine en producción y el logging del contenido de las respuestas de la IA. | P2 · S4 |
| BE-35 | **Tests por requisito del TDR:** auth, IDOR y visibilidad, sesión anónima + asociación + vencimiento sin pérdida de datos, matriz de privacidad del admin (un admin no puede leer ningún dato privado), borrado lógico y restauración, sin medios guardados, truncamiento `F1-D10` (warning `VIDEO_TRUNCATED`), `captured_at`, una clasificación por archivo, duplicados, IA caída → 502 sin datos inventados, stats, validación, Excel (*magic bytes* `PK`) y PDF (`%PDF`), importación de paquetes (`F2-D2`/`F2-D9`); cada error con su código del catálogo. La IA se simula con `ia-fake` / fixtures reales de `ia-clasificacion-fauna`. | P0 · S5 |
| BE-36 | Limpieza del repo: `scratch/`, `koyeb.yml`, `digitalocean.yaml` (si no se usan) y el `.mp4` aún versionado en `uploads/videos/`. | P2 · S4 |
| BE-51 | ✅ *(Cerrado en PR #2/`BUG-02`)* **Cierre de exposición de usuarios en `app/api/v1/users.py`:** `/users` requiere autenticación y verificación de dueño/IDOR. Pendiente migrar gestión administrativa a `/admin/users` (`BE-50`). | **P0 · S1** |
| BE-37 | Actualizar `BACKLOG_TECNICO.md`: IMP-02 e IMP-03 figuran como implementados en la IA, pero no existen en el repo de IA. Eliminarlos de ese backlog; la IA es responsabilidad de Diego (§4). | P2 · S1 |

### 6.E Administración (DD-11, [FLUJOS §11](FLUJOS_SISTEMA.md#11-flujos-del-administrador))
| ID | Tarea | Prioridad · Semana | Criterio de aceptación |
|---|---|---|---|
| BE-50 | **Rol y acceso:** `users.role` (`user`/`admin`), dependencia `require_role("admin")`, router `/api/v1/admin/*`, comandos `python -m app.cli create-admin` (falla si ya existe un admin: **un único administrador**), `reset-admin-password` y `--transfer-to`. El rol no se puede asignar por la API, y el admin tiene un *access token* de 15 min. | P1 · S3 | Un usuario normal recibe 403 `ADMIN_REQUIRED` en `/admin/*`; registrarse con `role=admin` en el body no tiene efecto; un segundo `create-admin` falla. |
| BE-52 | **`AdminScope`:** un único filtro de repositorio (`visibility = public OR anon_session_id IS NOT NULL`) que usan **todas** las consultas de contenido de `/admin/*`; los conteos de lo privado van por consultas separadas que solo devuelven `COUNT`. | P1 · S3 | El test "admin intenta leer una cámara, una clasificación o un fotograma privado" → 404 en todos los endpoints. |
| BE-53 | **`GET /admin/stats`** (FL-40): bloques de usuarios, sesiones anónimas (con la tasa de conversión), contenido (conteos por visibilidad, origen, errores, uso del storage) y fauna (reutiliza `StatsService` con `AdminScope`). Más `GET /admin/reports/excel`. | P1 · S4 | Las cifras de fauna excluyen lo privado; las de contenido sí cuentan lo privado. |
| BE-54 | **Exploración** `GET /admin/classifications` y `GET /admin/camera-stations` con `scope`, filtros, `include_deleted` y paginación; fotograma vía `/admin/classifications/{id}/evidence`. | P1 · S4 | — |
| BE-55 | **Borrado lógico unificado:** agregar `deleted_by` y `deleted_reason` a `BaseEntity`; un `SoftDeleteService` (con cascada y restauración de la misma operación); un filtro global `is_deleted = false` en todos los repositorios (salvo `include_deleted` del admin); endpoints `delete`, `restore` y `delete-batch`. | P1 · S4 | Lo borrado no aparece en listados, `/stats` ni exportaciones; la restauración lo devuelve todo. |
| BE-56 | **Gestión de usuarios** (FL-43): listado con conteos, desactivar (revoca los *refresh tokens* y oculta su contenido público) y reactivar; no se puede desactivar al último admin. | P1 · S4 | — |
| BE-57 | **`admin_audit_log`** (solo inserción) para cada acción del admin, más `GET /admin/audit-log`. | P1 · S4 | Cada borrado, restauración, desactivación o exportación tiene su fila con `reason` y `request_id`. |

### 6.F Estándares (ver [ESTANDARES_BACKEND_IA.md](ESTANDARES_BACKEND_IA.md))
| ID | Tarea | Prioridad · Semana | Criterio de aceptación |
|---|---|---|---|
| STD-01 | **Envoltura `ApiResponse` `{status,data,message,error,meta}`** y las funciones `ok()` / `paginated()` en `core/responses.py`; aplicarla a todos los routers. | P0 · S1 | Ningún endpoint JSON responde fuera de la envoltura. |
| STD-02 | **Paginación estándar** (`page`, `page_size` ≤ 200, `meta.pagination`) en todos los listados. | P1 · S2 | — |
| STD-03 | **`AppError` + catálogo de códigos** (`core/errors.py`, §5–§6) y handlers globales únicos; eliminar `HTTPException` con texto libre en servicios y routers; `AiClient` traduce los errores `IA_*`. | P0 · S1–S2 | `grep "HTTPException(" app/services` → 0; cada error tiene su test. |
| STD-04 | **Logs JSON** (`structlog`) + `RequestContextMiddleware` (`X-Request-ID`) + dependencia `flow()` + `log_step()` + *access log* propio; reenviar `X-Request-ID` y `X-Flow` a la IA. | P0 · S2 | Un error en FL-08 se rastrea por `request_id` en el back y en la IA. |
| STD-05 | Quitar los logs de datos sensibles (el JSON completo de la IA en `videos.py`, `echo=True`) y enmascarar correos (§7.5). | P0 · S2 | Revisión con `grep` en el PR. |
| STD-06 | **Reestructurar en capas** (§2.1): `crud/` → `repositories/` sin *commit*; servicios sin `fastapi`; `integrations/ai_client.py` y `integrations/storage/`; borrar `interfaces/` si queda vacío. | P1 · S2–S3 | `grep "from fastapi" app/services` → 0. |
| STD-07 | ✅ *(Cerrado en PR #1/`BUG-01`)* **`Settings` validado al arrancar** (`pydantic-settings` fail-fast en `app/core/config.py`) con `.env.example` alineado a perfiles `development` / `production`. | P0 · S1 | Sin `.env` correcto el back no arranca y registra error de configuración. |
| STD-08 | `ruff`, `mypy` (`core/`, `services/`), *pre-commit* (con `gitleaks`), CI de GitHub Actions (lint + tipos + tests + build de Docker) y plantilla de PR. | P1 · S2 | CI en verde en cada PR. |

---

## 7. Frontend — `Front-WWF` (Miguel)

### 7.A Estado actual
- **Ya existe:**
  - servicios por recurso (`auth`, `cameraStation`, `project`, `species`, `user`);
  - `api.js` con el *interceptor* Bearer, *refresh* en 401 y desempaquetado de `StandardResponse`;
  - login y registro conectados;
  - `enums.js`;
  - mapa de Google con selección por área;
  - creación de proyectos público o privado;
  - gráficos por especie, familia y género en cámara y proyecto, calculados en el cliente;
  - PDF y **CSV**;
  - `UploadWidget` codificado.
- **En contra del TDR o con problemas:**
  - `session.js` + `X-Anon-Session-ID` + `claimAnonSession`: el ID se genera en el cliente y queda en `localStorage`, que sobrevive a cerrar el navegador, en contra de DD-2 (FE-01);
  - "Modo Explorador" que permite publicar sin login;
  - `CreateStationModal` en `console.log`;
  - `UploadWidget` **sin montar**;
  - sin validación de 15 s;
  - validación sin conectar y sin corrección;
  - **11 archivos con *mocks*** y *fallback* del mapa a `mockDatabase.js`;
  - asociar y desasociar cámaras solo cambia el estado local;
  - Excel inexistente (hay CSV);
  - URL por defecto con la IP fija `206.81.8.110:8001`.
- **No hay `.env` local:** el repo dejó de versionarlo y el *pull* lo eliminó. Hay que crearlo con la configuración nueva (SEC-01, SEC-02).
- Su comparativa ([comparativa Miguel](../comparativa_estado_vs_plan-miguel.md)) es correcta en el detalle de componentes; aquí se ajusta al contrato §3.

### 7.B Cambios
| ID | Cambio | Prioridad · Semana | Criterio de aceptación |
|---|---|---|---|
| FE-01 | **Rehacer `session.js`** según DD-2 y FL-03:<br>• el token lo pide al back (`POST /anon-sessions`) en la primera acción que guarda algo; ya no se genera en el cliente;<br>• se guarda en **`sessionStorage`**, no en `localStorage`;<br>• header `X-Anon-Token`;<br>• ante `ANON_SESSION_EXPIRED` borra el token y avisa. | P0 · S2 | F5 conserva los datos; cerrar el navegador y volver → no hay datos; no queda nada en `localStorage`. |
| FE-02 | **"Modo Explorador" con límites:** se puede clasificar, crear cámaras y proyectos privados; el selector de público está deshabilitado con un *tooltip* ("Regístrate para publicar"). Validar, exportar e importar piden login. Aviso fijo de "datos temporales". | P0 · S2 | Sin sesión no se puede publicar nada; el aviso está siempre visible. |
| FE-11 | **Diálogo de asociación (FL-04):** tras el login o el registro, `GET /anon-sessions/current`; si hay datos, "¿Asociar N clasificaciones y M cámaras a tu cuenta?" → `claim` o `close` (no asociar); informar las cámaras renombradas por choque de código. | P0 · S3 | El flujo completo funciona contra el back real. |
| FE-03 | **Eliminar los *mocks*:** `src/data/*.json`, `mockDatabase.js` y los *fallbacks* del mapa y de los stores; ante un error de la API, mostrar un estado de error o vacío. | P0 · S4 | `grep mockDatabase\|data/datos src` → 0 resultados. |
| FE-04 | **Ocultar los 10 indicadores ecológicos** y sus gráficos (DD-5): dejar solo los reportes por especie, género y familia. | P1 · S4 | El menú de reportes solo muestra lo del TDR. |
| FE-05 | **Consumir `/stats`** en `CameraDataModal` y `ProjectGiantModal`, en lugar de calcular en el cliente por detección. | P0 · S4 | Los números coinciden con el Excel del back. |
| FE-06 | Mostrar el **fotograma de evidencia** desde `GET /classifications/{id}/evidence`, en lugar de `url_img`, con el **minuto:segundo** (`mm:ss`). La imagen se pide con el cliente autenticado y se muestra como `blob:` URL, porque lleva token. | P0 · S4 | Se ve el fotograma completo con su `mm:ss` en los resultados y en la tabla de la cámara. |
| FE-07 | Cambiar el CSV y el jsPDF por los **botones Excel y PDF del back** (`/reports/excel`, `/reports/pdf`), con los filtros activos, en cámara y en proyecto (DD-6). Se mantiene jsPDF solo hasta que esté BE-26b. | P0 · S5 | Descarga Excel y PDF en cámara y en proyecto, con los mismos números que la pantalla. |
| FE-08 | Conectar asociar y desasociar cámaras a `projectService`. El selector muestra **solo las cámaras propias**. | P0 · S3 | Al recargar, la asociación se mantiene. |
| FE-09 | `VITE_API_URL` obligatorio, apuntando a `…/api/v1` (sin la IP fija por defecto); rutas de [API §15](contratos/API_BACK_FRONT.md#15-resumen-de-endpoints) (coordinado con BE-11); texto "Máx 10 seg" → "Máx 15 seg". | P0 · S2 | — |
| FE-10 | Unificar el cliente HTTP en `apiClient` (axios) en todos los servicios. | P2 · S4 | — |
| FE-13 | **Arranque con `GET /config/public`** (límites, formatos, retención) antes de montar las rutas. | P0 · S2 | Sin configuración → pantalla de error con Reintentar. |
| FE-14 | **Mapa con datos reales:** `GET /camera-stations?view=map&bbox=` con *debounce*, filtros, `mapId` y la key desde `.env`. | P0 · S2 | — |
| FE-15 | **`UploadManager` global + `UploadTray`:** la subida sigue al navegar; estados *subiendo*, *en cola (posición, espera)*, *analizando*, *listo* y *error*; cancelar y reintentar; pausa automática con `QUEUE_USER_LIMIT`; *backoff* con `QUEUE_FULL`; notificación al terminar; aviso de `beforeunload` solo mientras hay bytes subiendo. | P0 · S3 | Subir 20 archivos y navegar por 3 pantallas sin interrumpir nada (CB-31). |
| FE-16 | **Recuperar la contraseña:** `/recuperar` y `/restablecer` (FD C6). | P1 · S4 | — |
| FE-18 | **Revisión de ráfagas** (FD G4): sub-pestaña Ráfagas con el selector de ventana, la comparación lado a lado, conservar todos, dejar uno o elegir, la etiqueta "Repetido" en la galería con el filtro "Ocultar repetidos" y el botón "Volver a contar". | P1 · S4 | — |
| FE-17 | **Cámaras cercanas y reinstalación:** `NearbyCamerasDialog`, flujo de reinstalación, agrupación de marcadores (*clustering* y *spiderfy*), manejo de `meta.warnings` y `CONFLICT_STALE`. | P1 · S3 | FD D1 (paso 4b) y D5. |

### 7.C Nuevas implementaciones
| ID | Implementación | Prioridad · Semana | Criterio de aceptación |
|---|---|---|---|
| FE-20 | **Registrar una cámara con clic en el mapa:** modo "colocar cámara" → clic → lat/lng precargados (editables) → formulario con **nombre o código, fecha y hora de colocación, "sigue instalada" o fecha y hora de retiro, observaciones y pública/privada** → `POST /camera-stations/` → aparece el marcador. | P0 · S2–S3 | El flujo funciona de punta a punta contra el back real. |
| FE-21 | Editar y eliminar cámaras propias (con modal de confirmación), visibles solo para el dueño (`isOwner`). | P1 · S3 | — |
| FE-22 | **Subida con sesión:** montar `UploadWidget` (desde el FAB y desde la cámara); selección múltiple; validación en el cliente (formato, `video.duration ≤ 15` y peso); progreso por archivo; manejo de errores 422/502/504; envío de `lastModified` para `capture_date`. | P0 · S3 | Se suben 10 archivos con su estado individual. |
| FE-23 | **Subida anónima:** el mismo widget con `X-Anon-Token`; la cámara registrada es **obligatoria**, igual que con sesión (D7); los resultados se guardan en el back bajo la sesión anónima; aviso "Regístrate o inicia sesión para conservarlos; se pierden al cerrar el navegador". | P0 · S3 | Funciona sin login, sobrevive a F5 y se puede asociar con FE-11. |
| FE-24 | **Vista de resultados:** galería con una tarjeta por archivo (fotograma, especie común y científica, género, familia, confianza, `rank`, `category`). Las clases no animales se muestran aparte y no suman a "especies". | P0 · S3 | — |
| FE-25 | **Validación:** confirmar, rechazar o **corregir la especie** con un autocompletado de `GET /catalog/species`, y validar en lote. Estado visual de validado o corregido. | P0 · S4 | Las correcciones se reflejan en el resumen y en el Excel. |
| FE-26 | **Reportes por especie, género y familia:** selector de nivel y de alcance (cámara o proyecto), gráfico de barras y **tabla**, filtro de fechas y "solo validados". | P0 · S4 | Disponible en cámara y en proyecto. |
| FE-27 | Proyecto: botón **"+ Registrar nueva cámara"** con el proyecto preseleccionado; lista de cámaras con "quitar del proyecto". | P1 · S3 | — |
| FE-28 | Sesión completa: `getMe` al recargar, nombre del usuario y **Cerrar sesión**, input `institucion` en el registro, rutas y acciones protegidas. | P0 · S2 | Al pulsar F5 la sesión se mantiene; el logout limpia todo. |
| FE-29 | **Vista pública:** sin sesión, el mapa muestra solo las cámaras y proyectos **públicos** (según D2: ubicación exacta o aproximada). | P1 · S4 | — |
| FE-30 | **Dockerfile** (build de Vite + Nginx con *fallback* de SPA) y `.env.example`. | P0 · S5 | `docker build` → sirve la app en el puerto 80. |
| FE-31 | **Manual de usuario web** (con capturas de todos los flujos) y material para la capacitación. | P0 · S6 | — |
| FE-32 | **Importar desde escritorio (FL-23):** elegir el `.wwm.zip` y la cámara (sugerida por `camera_code`) → vista previa (nuevos, duplicados, inválidos, advertencias) → confirmar → ver los resultados. | P1 · S5 | Funciona con un paquete real de DS-17. |
| FE-33 | **Estadísticas complementarias** (DD-5): tarjetas de totales y riqueza, estado de validación, matriz cámara × especie en el proyecto y gráficos por mes y por hora. | P1 · S4–S5 | Coinciden con `/stats`. |

| FE-34 | **Aviso de uso de datos** para el anónimo (FL-03, paso 6), según `data_retention`. Con la retención activa debe aceptarse una vez por sesión antes de la primera clasificación; con la retención inactiva solo informa que los resultados se eliminarán al cerrar. | P0 · S3 | Sin aceptar el aviso (con retención) no se puede clasificar; el texto cambia al cambiar la configuración. |
| FE-60 | **Panel de administración** (ruta `/admin`, solo visible con `role=admin`), con cinco partes:<br>• **Resumen:** tarjetas de usuarios, sesiones anónimas y conversión, y contenido por visibilidad;<br>• **Fauna:** gráficos por especie, género y familia, por mes y por hora, y un mapa de calor, con el selector de alcance anónimo, público o ambos;<br>• **Explorar:** tabla y mapa de clasificaciones y cámaras anónimas o públicas, con fotograma;<br>• **Usuarios:** listado con conteos, desactivar y reactivar;<br>• **Configuración:** interruptor "Guardar los datos de usuarios sin sesión", con confirmación, motivo, una aclaración de que solo aplica a los datos nuevos, y el historial de cambios con lo conservado y lo eliminado;<br>• **Auditoría.**<br>El borrado y la restauración piden un motivo, y el filtro "incluir borrados" está disponible. | P1 · S5 | Ninguna pantalla muestra datos privados; las cámaras privadas solo aparecen como número. |

### 7.E Estándares (ver [ESTANDARES_BACKEND_IA.md §2.3](ESTANDARES_BACKEND_IA.md#23-front-front-wwfsrc))
| ID | Tarea | Prioridad · Semana | Criterio de aceptación |
|---|---|---|---|
| FE-50 | **`apiClient` único:** agrega `X-Request-ID`, `Authorization` o `X-Anon-Token`; desempaqueta `data` y `meta`; convierte todo error en `ApiError {code, message, requestId, details, httpStatus}`. | P0 · S2 | Ningún componente lee `error.response.data`. |
| FE-51 | **`errorMessages.js`** (espejo del catálogo §6.1) + un componente único de error que muestra "Código de referencia: `<request_id>`"; acciones por código (`AUTH_TOKEN_EXPIRED` → login). | P0 · S3 | Cada código del catálogo tiene su mensaje. |
| FE-52 | **Errores por archivo** en la subida (§4.4): cada tarjeta muestra el error de su ítem sin bloquear el resto. | P0 · S3 | — |
| FE-53 | ESLint `no-console`, Prettier, *pre-commit* y CI (lint + build). | P1 · S2 | — |

### 7.D Seguridad y calidad
| ID | Mejora | Prioridad · Semana |
|---|---|---|
| FE-40 | Guardar los tokens de forma acotada: *access* en memoria y *refresh* en `localStorage` (o *cookie* `httpOnly` si Job lo soporta); limpiar todo al cerrar sesión o en un 401 definitivo. | P1 · S2 |
| FE-41 | La API key de Google Maps nueva, restringida por dominio (ver SEC-01); nunca versionada. | P0 · S2 |
| FE-42 | `npm audit` sin vulnerabilidades altas; `npm run lint` y `npm run build` en verde antes de cada entrega. | P1 · S5 |

---

## 8. Seguridad y configuración nueva

> Configuración que hay que **crear desde cero** para los entornos de desarrollo y producción. Toda va en `.env` (nunca en el repo) y se documenta en un `.env.example` sin valores reales.

| ID | Recurso | Qué hacer | Dónde se usa | Responsable · Semana |
|---|---|---|---|---|
| SEC-01 | **Nueva API key de Google Maps** | En Google Cloud: crear un proyecto (idealmente a nombre de WWF o con WWF como propietario), activar **Maps JavaScript API**, crear la key con **restricción de referentes HTTP** (`http://localhost:5173/*` en desarrollo y `https://<dominio>/*` en producción) y **restricción de API** (solo Maps JavaScript API), y definir una cuota o alerta de facturación. Conviene usar una key para desarrollo y otra para producción. | `Front-WWF/.env` → `VITE_GOOGLE_MAPS_API_KEY` | Diego/Miguel · S1 |
| SEC-02 | **Map ID de Google Maps** | El front usa `mapId="DEMO_MAP_ID"`, que solo sirve para desarrollo. Crear un **Map ID** en Google Cloud (Map Management, tipo JavaScript, vector) para que `AdvancedMarker` funcione en producción, y sacarlo a `VITE_GOOGLE_MAPS_MAP_ID`. | `FullScreenMap.jsx` | Miguel · S2 |
| SEC-03 | **Base de datos nueva** | Opción A (recomendada para producción): PostgreSQL 16 en el `docker-compose` del servidor, con volumen y backups. Opción B: un servicio gestionado (Aiven u otro) a nombre de WWF. Crear un usuario de aplicación con permisos solo sobre su base. | `BACKWWF/.env` → `DATABASE_URL` | Job · S1 (desarrollo), S6 (producción) |
| SEC-04 | **Secretos JWT** | Generar `SECRET_KEY` y `REFRESH_SECRET_KEY` distintos, aleatorios y de ≥ 32 bytes (`python -c "import secrets;print(secrets.token_urlsafe(48))"`), uno por entorno. | `BACKWWF/.env` | Job · S1 |
| SEC-05 | ✅ *(Parcial: soporte listo en IA)* **API key Back ↔ IA** | Generar `AI_API_KEY` aleatoria en producción (en dev la IA acepta `dev-key`), compartida entre `BACKWWF/.env` y `ia-clasificacion-fauna/.env`. | IA-30, BE-03 | Diego · S3 |
| SEC-06 | **VisualCrossing** | **No se necesita** si se aplica DD-5 / BE-12. Solo si WWF pide mantener los indicadores de clima habría que crear una key nueva. | — | — |
| SEC-07 | **Dominio + HTTPS** | **WWF ya tiene servidor y dominio.** Registros DNS A/AAAA hacia el servidor; certificado de Let's Encrypt (Caddy o Certbot); redirección de HTTP a HTTPS y HSTS. Igual se entrega todo **dockerizado** (DEP-01/02). | Proxy inverso | Diego · S6 |
| SEC-08 | **Servidor** | Usuario no root con acceso SSH solo por clave (sin contraseña ni root), `ufw` (solo 22, 80 y 443), `fail2ban`, actualizaciones automáticas de seguridad y Docker con *log rotation*. | VPS de WWF | Diego · S6 |
| SEC-09 | **Gestión de secretos y cuentas** | **Todas las cuentas van a nombre de WWF** (Google Cloud, Resend, servidor, dominio, GitHub Releases si corresponde), con el equipo como administrador durante el proyecto. Los secretos de producción se guardan en un gestor compartido (Bitwarden o 1Password) y se entregan a WWF al cierre. | — | Diego · S6 |
| SEC-12 | **Resend** | Crear la cuenta (a nombre de WWF o del equipo), **verificar el dominio** (registros DNS SPF y DKIM que entrega Resend) cuando exista (SEC-07), generar la API key con permiso solo de envío y configurar `EMAIL_FROM`. Hasta verificar el dominio, la recuperación funciona solo con el respaldo del admin. | `BACKWWF/.env` → `RESEND_API_KEY` | Diego · S6 (cuenta en S4) |
| SEC-13 | **Redis** | Contraseña (`requirepass`), sin puerto publicado, `appendonly yes`, `maxmemory` acotado. | `docker-compose.prod.yml` | Job · S5 |
| SEC-11 | **Cuenta de administrador** | La **única** cuenta admin es de **una persona de WWF**. En el despliegue se crea con `create-admin` (su correo y una contraseña temporal de 12 caracteres o más) y `must_change_password=true`, así que en el primer login debe cambiarla. Las credenciales se entregan por un canal seguro y se registran en el gestor de SEC-09. Opcional: restringir `/api/v1/admin/*` por IP. | Back, proxy | Diego · S6 |
| SEC-10 | **Revisión de exposición** | Antes de la entrega: `git grep` de patrones de claves en los tres repos; ningún `.env` versionado; `.gitignore` con `.env*`, `uploads/`, `detections/`, `temp/`, `models/` y `*.mp4`. | 3 repos | Todos · S6 |

---

## 9. Despliegue y entregables

| ID | Tarea | Prioridad · Semana | Responsable | Criterio de aceptación |
|---|---|---|---|---|
| DEP-01 | `docker-compose.prod.yml` único con: `proxy` (Caddy o Nginx, 80/443), `frontend` (Nginx estático), `backend` (uvicorn, 2 *workers*), **`worker`** (arq, misma imagen que el back), **`redis`** (AOF, red interna), `ia` (red interna, volumen `models`, límite de 6–8 GB de RAM), `db` (Postgres 16, volumen) y `backup` (`pg_dump` diario). | P0 · S5–S6 | Diego (coordina), Job (back + db), Miguel (front) | `docker compose up -d` levanta todo en un VPS limpio. |
| DEP-02 | **Guía de despliegue** paso a paso (requisitos del servidor, DNS, `.env`, primer arranque, migraciones, actualización y restauración de backups). Aplica al §3.3 del TDR: entregar el proyecto dockerizado si WWF aún no tiene servidor o dominio. | P0 · S6 | Diego | Otra persona puede desplegar siguiendo solo la guía. |
| DEP-03 | Recalcular `REQUISITOS_INFRAESTRUCTURA_WWF.md` con el muestreo final (IA-11) y los tiempos medidos (IA-17). | P1 · S3 | Diego | Los números de RAM, CPU y tiempo salen de mediciones reales. |
| DEP-04 | **Pruebas e2e** (guion manual o Playwright), un caso por flujo de [FLUJOS_SISTEMA.md](FLUJOS_SISTEMA.md):<br>• anónimo → clasificar → F5 (se conserva) → registrarse → asociar;<br>• anónimo → cerrar el navegador (se pierde);<br>• cámara por clic → subida → resultados con `mm:ss` → validar o corregir → stats → Excel y PDF;<br>• IA apagada → error con código de referencia;<br>• importar un paquete de escritorio;<br>• proyecto público o privado visto por otro usuario. | P0 · S6 | Miguel + Job | Guion ejecutado y sin bloqueantes. |
| DEP-05 | **Entrega del Producto 1**: los dos instaladores (estándar y completo) + manual con requisitos + reporte de precisión antes y después. | P0 · fin de S3 | Diego | Aprobación de WWF (50 %). |
| DEP-06 | **Entrega del Producto 2**: plataforma desplegada (o el paquete dockerizado) + manual de usuario + sesión de capacitación. | P0 · fin de S6 | Todos | Aprobación de WWF (50 %). |

---

## 10. Cronograma y dependencias

| Semana | Diego (IA · escritorio) | Job (back) | Miguel (front) |
|---|---|---|---|
| **S1** | Informar a WWF las decisiones (FLUJOS §13) · etiquetar los videos de prueba · **contrato §3 + IA-21 (schema)** · revisar los estándares con el equipo · IA-01, 02, 03, **21, 22 (`ia-fake`)**, **40** · **IA-10 (línea base)** · IA-11 | **STD-01 · STD-03 · STD-07** · **BE-51** · BE-30 · BE-01 (diseño + migración) · BE-02 · BE-03 · BE-07 · **BE-14** · BE-37 · SEC-03/04 (desarrollo) | SEC-01/02 · FE-09 · FE-50 · inicio de FE-20 (UI de la cámara con clic en el mapa) |
| **S2** | IA-04, 05, 12, 13, 14, 15, 16, **20**, 41, 42, 43 · DS-01 | BE-01 · **BE-04 (modelo)** · BE-05 · BE-06 · BE-08 · **BE-11** · **BE-13** · **BE-60** · **BE-61** · BE-15 · BE-20 · BE-21 · **BE-23** · STD-02, 04, 05, 06, 08 | FE-01 · FE-02 · FE-13 · FE-14 · FE-20 · FE-28 · FE-40/41 · FE-53 |
| **S3** | IA-17, 18, 19, 30, 32, 33 · DS-02, 03, 04, 10–16, 18, 19, 30, 31 · DS-17 si da el tiempo · **Entrega del Producto 1** · DEP-03 | BE-04 (con la IA nueva) · BE-09 · BE-10 · BE-16 · BE-22 · BE-24 · BE-25 · **BE-27** · BE-61 (cierre) · BE-63 · BE-64 · BE-50 · BE-52 · BE-58 | FE-08 · **FE-11** · **FE-15** · FE-17 · FE-21 · **FE-22** · **FE-23** · FE-24 · FE-27 · FE-51 · FE-52 |
| **S4** | DS-17 (si no entró en S3) · soporte de integración IA ↔ back · revisión de PRs | **BE-26 (Excel)** · BE-09 (complementarias) · **BE-62** · BE-66 · BE-29 · BE-31–34 · BE-36 · **BE-53…57 (admin)** | FE-03 · FE-04 · FE-05 · FE-06 · FE-16 · **FE-25** · FE-18 · **FE-26** · FE-29 · FE-10 · FE-33 |
| **S5** | DEP-01 (IA + proxy) | **BE-26b (PDF)** · **BE-40 (importación)** · BE-35 (tests) · DEP-01 (back + db) | FE-07 · **FE-32** · **FE-60 (panel admin)** · FE-30 · FE-42 · DEP-01 (front) |
| **S6** | SEC-07/08/09 · DEP-02 · despliegue | Soporte al despliegue · migración en producción | FE-31 · DEP-04 (e2e) |
| — | SEC-10 y DEP-06: **todos** | | |

**Dependencias críticas:**
- **Contrato §3 + estándares (S1)** → todo lo demás. STD-01/03 y FE-50 van primero porque el resto de los endpoints se escribe ya con la envoltura y los códigos.
- **BE-11 ↔ FE-09** (prefijo `/api/v1` y rutas nuevas): se integran en la misma semana.
- **Contrato §3 (S1)** → BE-04, BE-13, FE-22/23/24.
- **DS-17 → BE-40 → FE-32** (sincronización escritorio → web).
- **IA-13/14/15 (S2)** → BE-04 (S3). Mientras tanto, Job usa el JSON de ejemplo en sus tests.
- **BE-01/02/23 (S2)** → FE-01/02/28.
- **BE-09/10/25/26** → FE-05/25/26/07.
- **IA-19 (catálogo)** → BE-25 → FE-25.

---

## 11. Trazabilidad TDR → tareas

| Requisito del TDR | Tareas |
|---|---|
| §3.1 Uso con o sin sesión (DD-2: temporal + asociación a cuenta, D5) | BE-01, BE-02, BE-20, BE-23 · FE-01, FE-02, FE-11, FE-23, FE-28 |
| §3.1 Cámara: clic en el mapa, nombre o código, colocación y retiro, observaciones, pública o privada | BE-07, BE-23 · FE-20, FE-21, FE-29 · SEC-01/02 |
| §3.1 Subir videos ≤ 15 s e imágenes de una cámara registrada | BE-05, BE-21, BE-22, BE-28 · FE-22 · IA-16 |
| §3.1 Clasificación + fotograma + estadísticas por especie, género y familia | IA-11…IA-15 · BE-04, BE-09 · FE-05, FE-06, FE-24, FE-26 |
| §3.1 Validar y descargar los datos clasificados y validados | IA-19 · BE-10, BE-24, BE-25, BE-26 · FE-07, FE-25 |
| §3.1 Catálogo SpeciesNet sin reentrenamiento | IA-12, IA-14, IA-19 · BE-25 |
| §3.1 Proyecto individual, público o privado, con cámaras propias o nuevas, estadísticas agregadas | BE-08, BE-09, BE-23 · FE-08, FE-27, FE-26 |
| §3.1 Reportes en gráficos y tablas · Excel y PDF | BE-09, BE-26 · FE-07, FE-26 |
| §3.2 Instalable en Windows; descarga del modelo y luego offline | DS-11, DS-12, DS-13 |
| §3.2 Carpeta sin subcarpetas → copiar o mover por especie | DS-01, DS-02, DS-03, DS-30, DS-31 |
| §3.2 Fotograma junto a cada video clasificado | DS-10 · IA-15 |
| §3.2 Precisión antes que velocidad | IA-10, IA-11, IA-12, IA-13, IA-17 · DS-01 |
| §3.3 Despliegue (o paquete dockerizado), seguridad básica, dominio | DEP-01, DEP-02 · SEC-03…SEC-10 · IA-30/31 · BE-30…BE-34 |
| §3.4 No almacenar medios | BE-05 · IA-05 · DS-04 |
| §3.4 Sin especie → el archivo queda en el origen | DS-02 |
| §3.4 Una especie por archivo | IA-13 · BE-04 |
| §3.4 Solo las estadísticas de §3.1 | BE-12 · FE-04 |
| §4 Manuales y capacitación | DS-15 · FE-31 · DEP-02 · DEP-06 |
| Calidad, mantenibilidad y diagnóstico (no lo pide el TDR de forma explícita, pero sostiene todo lo anterior) | STD-01…08 · IA-40…43 · FE-50…53 · DS-19 |
| Extra fuera del TDR: sincronización escritorio → web (D6) | DS-14, DS-17 · BE-40 · FE-32 |
| Extra fuera del TDR (sin costo): administración, estadísticas globales, retención anónima configurable y borrado lógico | BE-50…58 · FE-34, FE-60 · SEC-11 |
| Seguridad actual (usuarios expuestos) | **BE-51** |
| Concurrencia de subidas sin bloquear al usuario (DD-12) | BE-60, BE-61 · FE-15 · SEC-13 |
| Recuperación de contraseña (DD-13) | BE-62 · FE-16 · SEC-12 |
| Casos borde (CB-xx) | BE-35 · BE-63, BE-64 · FE-17 · DEP-04 |
