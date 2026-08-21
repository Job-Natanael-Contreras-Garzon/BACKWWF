# 🎥 Endpoints de Archivos Multimedia (`/camera-stations/{id}/files` & `/videos`)

Módulo para la carga de archivos multimedia (**Videos** e **Imágenes**), validación de tipos MIME y extensiones, extracción automática de metadatos (duración, resolución, formato, fecha de captura) y análisis con la API externa de **Inteligencia Artificial**.

---

## 📐 Formato Estándar de Respuesta
Todas las respuestas siguen la estructura unificada `StandardResponse`:
```json
{
  "status": "success",
  "data": { ... } | [ ... ] | null,
  "message": "Descripción de la operación"
}
```

---

## 1. Subir Archivo Multimedia (Video o Imagen) (`POST /camera-stations/{id}/files`)
- **Ruta:** `POST /camera-stations/{station_id}/files`
- **Código Estado:** `201 Created`
- **Content-Type:** `multipart/form-data`
- **Autenticación:** Opcional (Soporta `Authorization: Bearer <token>` o `X-Anon-Session-ID: <UUID>`).

### Campos Form Data
- `file` *(File, requerido)*: Archivo multimedia de video (`.mp4`, `.avi`, `.mov`, `.mkv`, `.wmv`, `.flv`, `.webm`) o imagen (`.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`, `.tiff`).

### Validaciones y Seguridad:
1. **Validación de Extensión y MIME Type:** Rechaza extensiones no permitidas con `HTTP 400 Bad Request`.
2. **Validación de Estación:** Verifica que la estación exista y no esté eliminada (`is_deleted == False`).
3. **Persistencia y Batch Insert:** Guarda en disco local (`uploads/videos` o `uploads/images`) e inserta todas las detecciones de IA en la tabla `species` en un único batch insert transaccional.

### Response (`201 Created`)
```json
{
  "status": "success",
  "data": {
    "media_file_id": "m1febc99-9c0b-4ef8-bb6d-6bb9bd380a77",
    "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "file_type": "image",
    "file_url": "uploads/images/a1b2c3d4_foto01.jpg",
    "original_filename": "foto01.jpg",
    "file_size_mb": 4.5,
    "detections_count": 1,
    "detections": [
      {
        "id": 101,
        "common_name": "Jaguar",
        "scientific_name": "Panthera onca",
        "family": "Felidae",
        "genus": "Panthera",
        "confidence_score": 0.94,
        "url_img": "http://localhost:8081/detections/video01/animal/crop_101.jpg"
      }
    ]
  },
  "message": "Archivo image subido y procesado exitosamente por la IA"
}
```

---

## 2. Listar Archivos Multimedia de una Estación (`GET /camera-stations/{id}/files`)
- **Ruta:** `GET /camera-stations/{station_id}/files`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": "m1febc99-9c0b-4ef8-bb6d-6bb9bd380a77",
      "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
      "file_type": "video",
      "file_url": "uploads/videos/video01.mp4",
      "duration_seconds": 15,
      "created_at": "2026-08-18T00:00:00Z"
    }
  ],
  "message": "Archivos multimedia de la estación obtenidos exitosamente"
}
```

---

## 3. Obtener Detalle de Archivo Multimedia (`GET /camera-stations/files/{media_file_id}`)
- **Ruta:** `GET /camera-stations/files/{media_file_id}`
- **Parámetros Path:** `media_file_id` *(UUID)*

---

## 4. Endpoints Directos de Video (`/videos`)
- `POST /videos/`: Sube video asociando `station_id` vía Form Data con validación MIME.
- `GET /videos/`: Lista todos los videos registrados.
- `GET /videos/{id}`: Detalle de un video.
- `DELETE /videos/{id}`: Elimina registro lógico y físico del video.
