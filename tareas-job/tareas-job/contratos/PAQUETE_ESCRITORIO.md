# Formato del paquete de sincronización · Escritorio → Web

> Documento interno · CETERIS404 · v2 — 19/11/2026 (alineado con `ia-clasificacion-fauna`) · **Formato `1.0`**
> Lo genera la app de escritorio (DS-17, Diego) y lo importa la web (BE-40, Job; FE-32, Miguel). Es la fuente única del formato.
> **Schema en código:** `ia-clasificacion-fauna/wwm_pipeline/package.py` (Pydantic, licencia MIT) y `package_validator.py`. El back tiene una copia idéntica y un test verifica que sean iguales.
> **Regla del TDR (§3.4):** el paquete lleva **registros**, no estadísticas. Tampoco incluye videos ni imágenes originales.

---

## 1. Archivo

- **Nombre:** `WWM_<codigo-camara o carpeta>_<AAAAMMDD-HHMM>.wwm.zip` (por ejemplo `WWM_CAM01_20260320-1504.wwm.zip`).
- **Compresión:** ZIP *deflate*. Los JPEG van sin comprimir de nuevo (*stored*).
- **Estructura**, exacta: cualquier otra ruta hace que el paquete se rechace.
```
manifest.json
classifications.jsonl
evidence/<sha256-del-archivo-original>.jpg
```
- **Tamaño de referencia:** unos 100 KB por archivo con fauna. Por ejemplo, 340 archivos con 92 fotogramas pesan unos 9 MB.

---

## 2. `manifest.json`

```json
{
  "format": "wwm-desktop-export",
  "format_version": "1.0",
  "app_version": "1.2.0",
  "created_at": "2026-03-20T15:04:05Z",
  "device_id": "3f9a1c0e",
  "camera_code": "CAM01",
  "camera": {
    "code": "CAM01",
    "name": "Quebrada norte",
    "latitude": -17.78345, "longitude": -63.18211,
    "deployed_at": "2026-03-01T08:30:00", "retrieved_at": "2026-03-19T17:00:00", "still_installed": false,
    "observations": "Sobre sendero de tapires"
  },
  "source_folder_name": "SD_CAM01_marzo",
  "run": { "job_id": "j-20260320-1450", "started_at": "2026-03-20T14:50:00Z", "finished_at": "2026-03-20T15:03:40Z", "action": "copy" },
  "model": { "detector": "MDv5a", "classifier": "speciesnet-4.0.2a", "sampling": "15fps@0-2s+6fps/max120", "pipeline_version": "1.0.0" },
  "counts": { "lines": 340, "animal": 87, "person": 4, "vehicle": 1, "blank": 240, "error": 8, "evidence_files": 92 },
  "checksums": { "classifications.jsonl": "sha256:…" }
}
```

| Campo | Regla |
|---|---|
| `format` | Debe ser exactamente `wwm-desktop-export`. |
| `format_version` | `MAJOR.MINOR`. La web acepta los MAJOR soportados (`/config/public → import.supported_format_versions`). Un MINOR nuevo solo **agrega** campos opcionales. |
| `device_id` | Hash corto del equipo, sin nombre de usuario ni rutas. |
| `camera_code` | Opcional, lo escribe el usuario. Si coincide con una cámara propia, la web la sugiere. |
| `camera` | **Opcional.** Los mismos datos de cámara que se registran en la web (API §1.5): `code`, `name`, `latitude`, `longitude`, `deployed_at`, `retrieved_at`, `still_installed` y `observations`. Los carga el usuario en la app de escritorio (todos opcionales, porque en campo puede no tener las coordenadas a mano). Con ellos, la web puede **crear la cámara al importar** (API §12.1, `create_camera=true`) o sugerir la existente con el mismo código. La visibilidad **no** viaja: la cámara se crea privada y el usuario decide en la web. |
| `source_folder_name` | Solo el **nombre** de la carpeta, nunca la ruta completa. |
| `counts` | Deben coincidir con el contenido. Si no coinciden → `IMPORT_INVALID_PACKAGE`. |
| `checksums` | SHA-256 de `classifications.jsonl`. Si no coincide → `IMPORT_CHECKSUM_MISMATCH`. |

---

## 3. `classifications.jsonl`
UTF-8, **una línea JSON por archivo procesado**, incluidos `blank` y `error`, para que la web pueda contar los archivos sin fauna.

Cada línea lleva **todos los datos que la web registra** de una clasificación: la taxonomía completa (clase, orden, **familia**, género, especie, nombre científico, nombre común, `rank`, `label_id`), la confianza, las alternativas, la fecha de captura y su fuente, la duración, el `sha256`, el fotograma (número de frame, **minuto y segundo**, recuadro) y el modelo. Así, lo importado queda idéntico a lo clasificado en la web. La carpeta local por especie sigue el formato actual de la app (DS-03), pero eso **no** limita lo que se exporta.

```json
{"file_name":"CAM01_20260315_042210.mp4","file_sha256":"9f2c…","file_size_bytes":18234567,"media_type":"video","duration_seconds":14.8,"captured_at":"2026-03-15T04:22:10","captured_at_source":"filename","status":"done","error_code":null,"category":"animal","taxonomy":{"label_id":"…","label_raw":"…","class":"mammalia","order":"carnivora","family":"felidae","genus":"panthera","species":"onca","scientific_name":"Panthera onca","common_name":"jaguar","rank":"species"},"confidence":0.94,"alternatives":[{"label_id":"…","scientific_name":"Puma concolor","common_name":"puma","rank":"species","score":0.03}],"frames_analyzed":89,"evidence":{"file":"evidence/9f2c….jpg","frame_index":212,"timestamp_seconds":7.07,"bbox":[0.31,0.12,0.78,0.66],"width":960,"height":540},"desktop_action":{"type":"copy","destination_folder":"Panthera onca (jaguar)"}}
```

**Campos de cada línea**, con la misma semántica que [API_IA_BACK §2.3](API_IA_BACK.md#23-reglas-del-contenido):

| Campo | Tipo | Obligatorio |
|---|---|---|
| `file_name`, `file_sha256`, `file_size_bytes`, `media_type` | — | sí |
| `duration_seconds` | number \| null | sí (null en imágenes) |
| `captured_at`, `captured_at_source` | datetime local \| null, enum | sí |
| `status` | `done` \| `error` | sí |
| `error_code` | string \| null | sí cuando `status=error` (códigos del pipeline, por ejemplo `IA_DECODE_FAILED`) |
| `category` | enum \| null | sí cuando `status=done` |
| `taxonomy` | objeto \| null | sí cuando `category=animal` |
| `confidence`, `alternatives`, `frames_analyzed` | — | sí cuando `status=done` |
| `evidence` | objeto \| null | **sí solo cuando `category == animal`** (`F2-D2`/`F2-D9`: por privacidad, en el paquete `person` y `vehicle` van con `evidence: null`; cuando existe, `evidence.file` debe existir dentro del zip) |
| `desktop_action` | `{type: copy\|move\|left_in_place, destination_folder}` | sí. Solo es informativo y la web no lo usa para calcular. |

---

## 4. `evidence/*.jpg`
- El nombre es `<file_sha256>.jpg` (64 caracteres hexadecimales).
- JPEG ≤ 960 px de lado mayor, calidad 80, sin EXIF, con el recuadro dibujado y la etiqueta (especie, confianza y `mm:ss`).
- Es el mismo fotograma que la app deja junto al archivo como `<NOMBRE>_fotograma.jpg`, pero **sin** metadatos.

---

## 5. Validación en la web (resumen de BE-40 y `wwm_pipeline/package_validator.py`)

| Control | Resultado si falla |
|---|---|
| Tamaño del zip ≤ `IMPORT_MAX_MB`; descomprimido ≤ 3 × el límite; ≤ 20 000 entradas | `IMPORT_TOO_LARGE` |
| Solo están las rutas de §1 (sin `../`, sin rutas absolutas ni *symlinks*) | `IMPORT_INVALID_PACKAGE` |
| `format` y `format_version` soportados | `IMPORT_UNSUPPORTED_VERSION` |
| El checksum del `jsonl` | `IMPORT_CHECKSUM_MISMATCH` |
| Cada línea cumple el schema | Línea inválida (*issue* `LINE_INVALID`) |
| `taxonomy.label_id` existe en el catálogo | Línea inválida (`CATALOG_TAXON_NOT_FOUND`) |
| `evidence.file` presente cuando `evidence` no es `null` y abre como JPEG válido con Pillow | Línea inválida (`EVIDENCE_MISSING` / `EVIDENCE_INVALID`) |
| `captured_at` dentro de colocación–retiro de la cámara | Advertencia (`CAPTURE_OUTSIDE_DEPLOYMENT`) |
| `(camera_station_id, file_sha256)` ya existe | Se cuenta como duplicado y se salta |
| El `package_sha256` ya se importó en esa cámara | `IMPORT_ALREADY_IMPORTED` |

---

## 6. Versionado
- `1.x`: compatible; la web ignora los campos desconocidos.
- `2.0`: incompatible. La web informa `IMPORT_UNSUPPORTED_VERSION` con el mensaje "actualiza la plataforma" o "actualiza la app", según cuál sea más vieja.
