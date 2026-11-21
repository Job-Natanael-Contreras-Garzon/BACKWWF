# Contrato de API · IA → Back

> Documento interno · CETERIS404 · v2 — 19/11/2026 (alineado con `ia-clasificacion-fauna`)
> **Fuente única de verdad** de lo que el servicio `ia-clasificacion-fauna` recibe y responde. Solo lo consume el **worker de clasificación** del back (cola Redis, DD-12), por la red interna de Docker (DD-8).
> **Dueños:** Diego implementa, Job consume.
> **Schema en código:** `ia-clasificacion-fauna/wwm_pipeline/contract.py` (Pydantic, licencia MIT) y `schemas/detect_result.schema.json`. El back tiene una copia idéntica en `app/integrations/ai_contract.py` y un test verifica que sean iguales (IA-21).

---

## 1. Convenciones

| Tema | Regla |
|---|---|
| Base URL | `AI_BASE_URL` = `http://ia:8001/api/v1` (o `AI_SERVICE_URL` = `http://ia:8001` sin `/api/v1` en red interna; en local `http://localhost:8001`). **No se publica** en el proxy. |
| Auth | `X-API-Key: <AI_API_KEY>`, obligatoria en todo salvo `/health`. En desarrollo la clave por defecto es `dev-key`; en producción es obligatoria sin fallback. Si falta o es incorrecta → `401 IA_UNAUTHORIZED`. |
| Correlación | El back envía `X-Request-ID` y `X-Flow` (por ejemplo `FL-08`); la IA los incluye en sus logs y devuelve `X-Request-ID`. |
| Envoltura | La misma del back: `{status, data, message, error, meta}`. Abajo se muestra solo `data`. |
| Concurrencia | Cada réplica de la IA procesa **un archivo a la vez**, con una cola interna corta (`INFERENCE_QUEUE_SIZE` = 2). La espera real de los usuarios está en la cola Redis del back, que manda a cada réplica tantos trabajos como su `WORKER_CONCURRENCY`. Si aun así la cola interna se llena → `503 IA_BUSY`, y el worker reintenta con *backoff* de 5 y 30 s. Para más capacidad se agregan réplicas de la IA y *workers* (DEP-03). |
| Timeout | La IA corta a los `PROCESS_TIMEOUT_SECONDS` (150 s) → `504 IA_PROCESSING_TIMEOUT`. El back espera `AI_TIMEOUT_SECONDS` (180 s), que siempre debe ser mayor. |
| Disco | La IA **no guarda nada**: el archivo de entrada va a un temporal por petición que se borra en un `finally`, y el fotograma se devuelve en base64. |

---

## 2. `POST /detect`

### 2.1 Petición
`multipart/form-data`:

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `file` | archivo | sí | Imagen o video tal como lo subió el usuario. Formatos aceptados hoy (`wwm_pipeline/formats.py`): imágenes `.jpg, .jpeg, .png, .bmp, .webp, .tiff`; videos `.mp4, .avi, .mov, .mkv, .wmv, .flv, .webm` (`.heic/.heif` y extensiones extra `DD-18` llegan en `IA-16`). |
| `file_name` | string | sí | El nombre original; la fecha de captura se busca en él. |
| `client_mtime` | datetime ISO | no | Respaldo para `capture` si no hay EXIF, contenedor ni fecha en el nombre. |

La configuración de muestreo sale del preset `PipelineConfig.web()` y de las variables de entorno de la IA (`MAX_VIDEO_SECONDS=15`, `MAX_FILE_MB=300`, `MAX_IMAGE_PIXELS=100000000`). **No hay filtro geográfico (`geofence`):** se usa todo el catálogo de SpeciesNet. El back no envía parámetros de muestreo, así todas las clasificaciones web usan la misma configuración, que queda registrada en `model`.

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
    "frames_discarded": { "duplicate": 18, "blurry": 3, "cap": 0 },
    "votes": [ { "label_id": "…", "scientific_name": "Panthera onca", "frames": 17, "score": 0.94 } ],
    "truncated_at_seconds": null,
    "low_evidence": false,
    "processing_ms": 48210
  },
  "model": {
    "detector": "MDv5a",
    "classifier": "speciesnet-4.0.2a",
    "sampling": "10fps@0-2s+4fps/max60/hasta15s",
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
| `result.taxonomy` | Solo con `animal`; si no, `null`. Los niveles debajo de `rank` van en `null`. `scientific_name` corresponde al nivel de `rank` (`"Panthera"` si es `genus`). `common_name` viene en inglés tal cual desde SpeciesNet (`"jaguar"`, `"lowland tapir"`). |
| `result.confidence` | 0–1. Es la confianza agregada del taxón ganador (IA-13), no la de un solo frame. En `blank` es la confianza de que no hay nada. |
| `result.alternatives` | Las siguientes 2 o 3 opciones de la votación, con `score > 0.005`. Pueden ser `[]`. |
| `evidence` | En `animal`, `person` y `vehicle` es el fotograma completo de mayor confianza del resultado ganador, con el **recuadro dibujado**, JPEG ≤ 960 px de lado mayor, calidad 80, sin EXIF. En `blank` es `null`. |
| `evidence.timestamp_seconds` | `frame_index / fps`, con 2 decimales. Para imágenes es `0` y `frame_index` es `0`. |
| `evidence.bbox` | `[x1, y1, x2, y2]` normalizado entre 0 y 1, sobre el fotograma. |
| `analysis.truncated_at_seconds` | **`F1-D10`:** si el video supera `MAX_VIDEO_SECONDS` (15 s, con tolerancia de +0,5 s), **no se rechaza**; la IA analiza hasta los 15 s, informa `15.0` aquí y el back emite la advertencia `VIDEO_TRUNCATED`. Si no se recortó, es `null`. |
| `analysis.low_evidence` | `true` si el animal se vio con muy poca evidencia (p. ej. un solo frame con peso < 0,25) para que el back y la UI pidan revisión humana. |
| `analysis` (resto) | Diagnóstico (`frames_sampled` va a `frames_analyzed`, `frames_discarded` incluye `duplicate`, `blurry` y `cap`); el resto se registra en logs sin base64. |
| `model` | `ModelInfo` estricto (`extra="forbid"`, sin `geofence`): `detector`, `classifier`, `sampling`, `pipeline_version`. El back lo guarda tal cual en la clasificación. |

### 2.4 Otros ejemplos

**Imagen sin animal (`blank`)**
```json
{
  "media": { "file_name": "IMG_0042.JPG", "media_type": "image", "sha256": "…", "size_bytes": 2400000,
             "duration_seconds": null, "fps": null, "width": 4000, "height": 3000 },
  "capture": { "captured_at": "2026-03-15T11:02:00", "source": "exif" },
  "result": { "category": "blank", "taxonomy": null, "confidence": 0.97, "alternatives": [] },
  "evidence": null,
  "analysis": { "frames_sampled": 1, "frames_with_animal": 0, "frames_discarded": { "duplicate": 0, "blurry": 0, "cap": 0 }, "votes": [], "truncated_at_seconds": null, "low_evidence": false, "processing_ms": 2100 },
  "model": { "detector": "MDv5a", "classifier": "speciesnet-4.0.2a", "sampling": "image", "pipeline_version": "1.0.0" }
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
                            "genus": "dasyprocta", "species": null, "scientific_name": "Dasyprocta", "common_name": "agouti", "rank": "genus" },
              "confidence": 0.71, "alternatives": [] } }
```

### 2.5 Errores
| HTTP | `error.code` | Cuándo | `error.details` | El back lo traduce a |
|---|---|---|---|---|
| 400 | `IA_INVALID_FORMAT` | Falta `file` o `file_name` en la petición multipart | `{errors: [...]}` | `AI_BAD_RESPONSE` / `VALIDATION_ERROR` |
| 401 | `IA_UNAUTHORIZED` | Falta la API key o es incorrecta | — | `AI_UNAVAILABLE` + log `CRITICAL` |
| 413 | `IA_FILE_TOO_LARGE` | Supera `MAX_FILE_MB` (300 MB) | `{max_mb, size_mb}` | `MEDIA_TOO_LARGE` |
| 415 | `IA_INVALID_FORMAT` | La extensión o la firma no son soportadas (incluye `.heic/.heif` hasta `IA-16`) o archivo vacío | `{accepted: [...], reason}` | `MEDIA_UNSUPPORTED_FORMAT` |
| 422 | `IA_DECODE_FAILED` | OpenCV/PIL no pueden leerlo o supera `MAX_IMAGE_PIXELS` (`100_000_000`) | `{reason}` (`too_many_pixels` si excede MP) | `MEDIA_TOO_LARGE` si `reason == "too_many_pixels"`, si no `MEDIA_DECODE_FAILED` |
| 503 | `IA_MODEL_NOT_READY` | Los modelos aún se están cargando | — | `AI_NOT_READY` |
| 503 | `IA_BUSY` | La cola está llena | `{queue_size}` | Reintento (5 s, 30 s); si se agota, `AI_UNAVAILABLE` |
| 504 | `IA_PROCESSING_TIMEOUT` | Superó `PROCESS_TIMEOUT_SECONDS` (150 s) | `{elapsed_ms}` | `AI_TIMEOUT` |
| 500 | `IA_INTERNAL` | Excepción no controlada | — (el detalle solo va al log) | 1 reintento; si persiste, `AI_BAD_RESPONSE` |

*(Nota `F1-D10`: `422 IA_DURATION_EXCEEDED` fue retirado de la IA; los videos > 15 s dentro de `MAX_FILE_MB` se truncan a 15 s y devuelven `200` con `analysis.truncated_at_seconds = 15.0`.)*

Además, el back traduce sus propios fallos al llamar a la IA:
- conexión rechazada o DNS → `AI_UNAVAILABLE`;
- `httpx.TimeoutException` → `AI_TIMEOUT`;
- una respuesta que no cumple el schema → `AI_BAD_RESPONSE`, con un log `ERROR` que lista las claves recibidas.

---

## 3. `GET /health`
Sin API key y sin envoltura. Lo usan el *healthcheck* de Docker y `/health/ready` del back.
```json
{ "status": "ok", "models_loaded": true, "queue": { "size": 2, "pending": 0 },
  "config": { "sampling": "10fps@0-2s+4fps/max60/hasta15s", "max_video_seconds": 15.0, "max_file_mb": 300.0 },
  "version": { "pipeline": "1.0.0", "detector": "MDv5a", "classifier": "speciesnet-4.0.2a", "app": "dev" } }
```
`status` puede valer `ok` (200), `loading` (503), `models_missing` (503) o `error` (503).

---

## 4. `GET /catalog`
Con API key. Devuelve el catálogo completo de SpeciesNet (`3538` taxones, `IA-19`) para que el back lo sirva en `/catalog/species`. Soporta header `ETag` (SHA-256 del catálogo): si el back envía `If-None-Match` y no cambió, responde **304** sin cuerpo.
```json
{ "classifier": "speciesnet-4.0.2a", "count": 3538, "sha256": "d3a7cbde…", "taxa": [ { "…": "CatalogTaxon" } ] }
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
| `analysis.frames_sampled`, `analysis.low_evidence`, `analysis.truncated_at_seconds` | `frames_analyzed`, `low_evidence`, warning `VIDEO_TRUNCATED` en `warnings[]` (si no es `null`) |
| `model.*` | `model_detector`, `model_classifier`, `sampling`, `pipeline_version` (sin `geofence`) |

El back **nunca** inventa ni completa datos de la IA (DD-4).
