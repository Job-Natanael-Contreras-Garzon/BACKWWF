# Contrato de API · IA → Back

> Documento interno · CETERIS404 · v1 — 07/11/2026
> **Fuente única de verdad** de lo que el servicio `ia-deteccion` recibe y responde. Solo lo consume el **worker de clasificación** del back (cola Redis, DD-12), por la red interna de Docker (DD-8).
> **Dueños:** Diego implementa, Job consume.
> **Schema en código:** `ia-deteccion/wwm_pipeline/contract.py` (Pydantic). El back tiene una copia idéntica en `app/integrations/ai_contract.py` y un test verifica que sean iguales (IA-21).

---

## 1. Convenciones

| Tema | Regla |
|---|---|
| Base URL | `AI_BASE_URL` = `http://ia:8001/api/v1` (red interna). **No se publica** en el proxy. |
| Auth | `X-API-Key: <AI_API_KEY>`, obligatoria en todo salvo `/health`. Si falta o es incorrecta → `401 IA_UNAUTHORIZED`. |
| Correlación | El back envía `X-Request-ID` y `X-Flow` (por ejemplo `FL-08`); la IA los incluye en sus logs y devuelve `X-Request-ID`. |
| Envoltura | La misma del back: `{status, data, message, error, meta}`. Abajo se muestra solo `data`. |
| Concurrencia | Cada réplica de la IA procesa **un archivo a la vez**, con una cola interna corta (`INFERENCE_QUEUE_SIZE` = 2). La espera real de los usuarios está en la cola Redis del back, que manda a cada réplica tantos trabajos como su `WORKER_CONCURRENCY`. Si aun así la cola interna se llena → `503 IA_BUSY`, y el worker reintenta con *backoff* de 5 y 30 s. Para más capacidad se agregan réplicas de la IA y *workers* (DEP-03). |
| Timeout | La IA corta a los `PROCESS_TIMEOUT_SECONDS` (150 s) → `504 IA_PROCESSING_TIMEOUT`. El back espera `AI_TIMEOUT_SECONDS` (180 s), que siempre debe ser mayor. |
| Disco | La IA **no guarda nada**: el archivo de entrada va a un temporal que se borra en un `finally`, y el fotograma se devuelve en base64. |

---

## 2. `POST /detect`

### 2.1 Petición
`multipart/form-data`:

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `file` | archivo | sí | Imagen o video tal como lo subió el usuario. |
| `file_name` | string | sí | El nombre original; la fecha de captura se busca en él. |
| `client_mtime` | datetime ISO | no | Respaldo para `capture` si no hay EXIF, contenedor ni fecha en el nombre. |

La configuración de muestreo y la de geofence salen del `.env` de la IA. El back no las envía, así todas las clasificaciones web usan la misma configuración, que queda registrada en `model`.

### 2.2 Respuesta 200 · animal en un video
```json
{
  "media": {
    "file_name": "CAM01_20260315_042210.mp4",
    "media_type": "video",
    "sha256": "9f2c…",
    "size_bytes": 18234567,
    "duration_seconds": 14.8,
    "fps": 30.0,
    "width": 1920, "height": 1080
  },
  "capture": { "captured_at": "2026-03-15T04:22:10", "source": "filename" },
  "result": {
    "category": "animal",
    "taxonomy": {
      "label_id": "5c7ce479-…",
      "label_raw": "5c7ce479-…;mammalia;carnivora;felidae;panthera;onca;jaguar",
      "class": "mammalia", "order": "carnivora", "family": "felidae",
      "genus": "panthera", "species": "onca",
      "scientific_name": "Panthera onca", "common_name": "jaguar",
      "rank": "species"
    },
    "confidence": 0.94,
    "alternatives": [
      { "label_id": "…", "scientific_name": "Puma concolor", "common_name": "puma", "rank": "species", "score": 0.03 },
      { "label_id": "…", "scientific_name": "Leopardus pardalis", "common_name": "ocelote", "rank": "species", "score": 0.01 }
    ]
  },
  "evidence": {
    "frame_index": 212,
    "timestamp_seconds": 7.07,
    "bbox": [0.31, 0.12, 0.78, 0.66],
    "detection_confidence": 0.91,
    "image_base64": "/9j/4AAQSkZJRgABAQ…",
    "image_mime": "image/jpeg",
    "width": 960, "height": 540
  },
  "analysis": {
    "frames_sampled": 59,
    "frames_with_animal": 21,
    "frames_discarded": { "duplicate": 18, "blurry": 3 },
    "votes": [ { "label_id": "…", "scientific_name": "Panthera onca", "frames": 17, "score": 0.94 } ],
    "processing_ms": 48210
  },
  "model": {
    "detector": "MDv5a",
    "classifier": "speciesnet-4.0.2a",
    "geofence": "BOL",
    "sampling": "4fps+first10",
    "pipeline_version": "1.0.0"
  }
}
```

### 2.3 Reglas del contenido
| Campo | Regla |
|---|---|
| `media.sha256` | Se calcula sobre el archivo completo. El back lo usa para detectar duplicados. |
| `capture.source` | `exif` · `container` · `filename` · `none`. Si es `none`, `captured_at` va en `null`, y el back usa `client_mtime` y luego la hora de subida. |
| `result.category` | `animal` · `person` · `vehicle` · `blank`. |
| `result.taxonomy` | Solo con `animal`; si no, `null`. Los niveles debajo de `rank` van en `null`. `scientific_name` corresponde al nivel de `rank` (`"Panthera"` si es `genus`). |
| `result.confidence` | 0–1. Es la confianza agregada del taxón ganador (IA-13), no la de un solo frame. En `blank` es la confianza de que no hay nada. |
| `result.alternatives` | Las siguientes 2 o 3 opciones de la votación, con `score > 0.005`. Pueden ser `[]`. |
| `evidence` | En `animal`, `person` y `vehicle` es el fotograma completo de mayor confianza del resultado ganador, con el **recuadro dibujado**, JPEG ≤ 960 px de lado mayor, calidad 80, sin EXIF. En `blank` es `null`. |
| `evidence.timestamp_seconds` | `frame_index / fps`, con 2 decimales. Para imágenes es `0` y `frame_index` es `0`. |
| `evidence.bbox` | `[x1, y1, x2, y2]` normalizado entre 0 y 1, sobre el fotograma. |
| `analysis` | Solo es diagnóstico: el back lo guarda en el log (sin el base64), no en la BD, salvo `frames_sampled`, que va a `frames_analyzed`. |
| `model` | El back lo guarda tal cual en la clasificación. |

### 2.4 Otros ejemplos

**Imagen sin animal (`blank`)**
```json
{
  "media": { "file_name": "IMG_0042.JPG", "media_type": "image", "sha256": "…", "size_bytes": 2400000,
             "duration_seconds": null, "fps": null, "width": 4000, "height": 3000 },
  "capture": { "captured_at": "2026-03-15T11:02:00", "source": "exif" },
  "result": { "category": "blank", "taxonomy": null, "confidence": 0.97, "alternatives": [] },
  "evidence": null,
  "analysis": { "frames_sampled": 1, "frames_with_animal": 0, "frames_discarded": { "duplicate": 0, "blurry": 0 }, "votes": [], "processing_ms": 2100 },
  "model": { "detector": "MDv5a", "classifier": "speciesnet-4.0.2a", "geofence": "BOL", "sampling": "image", "pipeline_version": "1.0.0" }
}
```

**Persona**
```json
{ "…": "…", "result": { "category": "person", "taxonomy": null, "confidence": 0.88, "alternatives": [] },
  "evidence": { "frame_index": 30, "timestamp_seconds": 1.0, "bbox": [0.4, 0.1, 0.6, 0.9], "detection_confidence": 0.88,
                "image_base64": "…", "image_mime": "image/jpeg", "width": 960, "height": 540 } }
```

**Animal identificado solo hasta el género**
```json
{ "result": { "category": "animal",
              "taxonomy": { "label_id": "…", "label_raw": "…", "class": "mammalia", "order": "rodentia", "family": "dasyproctidae",
                            "genus": "dasyprocta", "species": null, "scientific_name": "Dasyprocta", "common_name": "agutí", "rank": "genus" },
              "confidence": 0.71, "alternatives": [] } }
```

### 2.5 Errores
| HTTP | `error.code` | Cuándo | `error.details` | El back lo traduce a |
|---|---|---|---|---|
| 401 | `IA_UNAUTHORIZED` | Falta la API key o es incorrecta | — | `AI_UNAVAILABLE` + log `CRITICAL` |
| 413 | `IA_FILE_TOO_LARGE` | Supera `MAX_FILE_MB` | `{max_mb, size_mb}` | `MEDIA_TOO_LARGE` |
| 415 | `IA_INVALID_FORMAT` | La extensión o la firma no son soportadas | `{accepted: [...]}` | `MEDIA_UNSUPPORTED_FORMAT` |
| 422 | `IA_DECODE_FAILED` | OpenCV o PIL no pueden leerlo | `{reason}` | `MEDIA_DECODE_FAILED` |
| 422 | `IA_DURATION_EXCEEDED` | Video > `MAX_VIDEO_SECONDS` + 0,5 | `{duration_seconds, max_seconds}` | `MEDIA_DURATION_EXCEEDED` |
| 503 | `IA_MODEL_NOT_READY` | Los modelos aún se están cargando | — | `AI_NOT_READY` |
| 503 | `IA_BUSY` | La cola está llena | `{queue_size}` | Reintento; si se agota, `AI_UNAVAILABLE` |
| 504 | `IA_PROCESSING_TIMEOUT` | Superó `PROCESS_TIMEOUT_SECONDS` | `{elapsed_ms}` | `AI_TIMEOUT` |
| 500 | `IA_INTERNAL` | Excepción no controlada | — (el detalle solo va al log) | `AI_BAD_RESPONSE` |

Además, el back traduce sus propios fallos al llamar a la IA:
- conexión rechazada o DNS → `AI_UNAVAILABLE`;
- `httpx.TimeoutException` → `AI_TIMEOUT`;
- una respuesta que no cumple el schema → `AI_BAD_RESPONSE`, con un log `ERROR` que lista las claves recibidas.

---

## 3. `GET /health`
Sin API key. Lo usan el *healthcheck* de Docker y `/health/ready` del back.
```json
{ "status": "ok", "models_loaded": true, "queue": { "size": 4, "pending": 1 },
  "config": { "sampling": "4fps+first10", "geofence": "BOL", "max_video_seconds": 15, "max_file_mb": 200 },
  "version": { "pipeline": "1.0.0", "detector": "MDv5a", "classifier": "speciesnet-4.0.2a" } }
```
Mientras carga los modelos responde 503 con `models_loaded: false`.

---

## 4. `GET /catalog`
Con API key. Devuelve el catálogo de SpeciesNet (IA-19) para que el back lo sirva en `/catalog/species`. El back **también** lo tiene versionado como archivo; este endpoint sirve para comprobar que la versión coincide.
```json
{ "classifier": "speciesnet-4.0.2a", "count": 2498, "sha256": "…", "taxa": [ { "…": "CatalogTaxon" } ] }
```

---

## 5. Lo que hace el back con la respuesta

| Dato de la IA | Columna en `classifications` |
|---|---|
| `media.file_name`, `media_type`, `sha256`, `size_bytes`, `duration_seconds` | `file_name`, `media_type`, `file_sha256`, `file_size_bytes`, `duration_seconds` |
| `capture.captured_at`, `capture.source` (o el respaldo del back) | `captured_at`, `captured_at_source` |
| `result.category`, `taxonomy.*`, `confidence`, `alternatives` | `category`, columnas de taxonomía, `confidence`, `alternatives` (JSONB) |
| `evidence.image_base64` | Se decodifica, se valida y re-codifica con Pillow, y se guarda en el storage → `evidence_key` |
| `evidence.frame_index`, `timestamp_seconds`, `bbox`, `width`, `height` | `evidence_frame_index`, `evidence_timestamp_seconds`, `evidence_bbox`, `evidence_width`, `evidence_height` |
| `analysis.frames_sampled` | `frames_analyzed` |
| `model.*` | `model_detector`, `model_classifier`, `geofence`, `sampling`, `pipeline_version` |

El back **nunca** inventa ni completa datos de la IA (DD-4).
