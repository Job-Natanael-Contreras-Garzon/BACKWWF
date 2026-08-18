# 🎥 Endpoints de Videos (`/videos`)

Módulo clave para la carga de videos grabados por las cámaras trampa, extracción automática de metadatos (duración, resolución, fecha de captura) mediante **FFmpeg** y análisis automatizado mediante el servicio externo de **Inteligencia Artificial**.

---

## 1. Subir Archivo de Video y Procesar con IA
- **Ruta:** `POST /videos/`
- **Código Estado Éxito:** `201 Created`
- **Content-Type:** `multipart/form-data`

### Campos Formulario (Form Data)
- `station_id` *(UUID, requerido)*: ID de la estación de cámara trampa.
- `file` *(File, requerido)*: Archivo de video (formato `.mp4`, `.avi`, `.mov`, etc.).

### Proceso Interno Automatizado:
1. Valida la existencia de la cámara trampa (`station_id`).
2. Guarda el archivo físicamente en `uploads/videos/` con un nombre seguro de UUID.
3. Inicia un hilo asíncrono con FFmpeg (`ffprobe`) para extraer la duración y fecha de captura.
4. Crea el registro del video en la base de datos.
5. Invoca el servicio de IA configurado en `AI_SERVICE_URL`.
6. Si la IA detecta animales, inserta automáticamente los registros resultantes en la tabla de `species` con sus respectivos recortes (`url_img`), score de confianza y marca de tiempo exacta.

### Respuesta de Éxito (`201 Created`) `VideoRead`
```json
{
  "id": "d1febc99-9c0b-4ef8-bb6d-6bb9bd380a44",
  "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
  "file_url": "C:\\Proyectos\\hackaton\\wwf\\BACKWWF\\uploads\\videos\\a1b2c3d4_video01.mp4",
  "original_filename": "video01.mp4",
  "duration_seconds": 15,
  "file_size_mb": 12.45,
  "capture_date": "2026-08-10T14:30:00Z",
  "metadata_extra": {
    "width": 1920,
    "height": 1080,
    "codec_name": "h264",
    "duration_seconds": 15.04
  },
  "temperatura_promedio": null,
  "periodo": null,
  "upload_date": "2026-08-18T00:00:00Z"
}
```

---

## 2. Listar Videos
- **Ruta:** `GET /videos/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*
- **Respuesta (`200 OK`):** Lista de `VideoRead`.

---

## 3. Obtener Video por ID
- **Ruta:** `GET /videos/{video_id}`
- **Parámetros Path:** `video_id` *(UUID)*
- **Respuestas:**
  - `200 OK`: Objeto `VideoRead`.
  - `404 Not Found`: Si el video no existe.

---

## 4. Eliminar Video
- **Ruta:** `DELETE /videos/{video_id}`
- **Parámetros Path:** `video_id` *(UUID)*
- **Acción:** Elimina el registro de la base de datos y borra el archivo físico correspondiente en el almacenamiento en disco (`uploads/videos/`).
- **Respuestas:**
  - `204 No Content`: Eliminación completada.
  - `404 Not Found`: Si el video no existe en BD.
