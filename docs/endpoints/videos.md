# 🎥 Endpoints de Archivos Multimedia (`/camera-stations/{id}/files` / `/videos`)

Módulo para la carga de archivos multimedia (**Videos** e **Imágenes**), extracción automática de metadatos (duración, resolución, formato, fecha de captura) y análisis con la API externa de **Inteligencia Artificial**.

---

## 📐 Formato Estándar de Respuesta
Todas las respuestas siguen la estructura:
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
- `file` *(File, requerido)*: Archivo multimedia de video (`.mp4`, `.avi`, `.mov`) o imagen (`.jpg`, `.jpeg`, `.png`).

### Proceso Automatizado:
1. Valida la estación de destino.
2. Identifica si el archivo es video o imagen por su tipo MIME.
3. Guarda el archivo en `uploads/videos/` u `uploads/images/`.
4. Extrae metadatos técnicos (duración vía FFmpeg o resolución/EXIF para imágenes).
5. Invocación al servicio de IA externo.
6. Auto-parsing de taxonomía (`family`, `genus`, `scientific_name`, `common_name`) y creación de registros en `species`.

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
        "url_img": "http://localhost:8080/crops/crop_101.jpg"
      }
    ],
    "created_at": "2026-08-18T00:00:00Z"
  },
  "message": "Archivo multimedia procesado e identificado exitosamente"
}
```

---

## 2. Listar Archivos Multimedia (`GET /videos/` / `/media/`)
- **Ruta:** `GET /videos/`
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
  "message": "Archivos multimedia obtenidos exitosamente"
}
```

---

## 3. Eliminar Archivo Multimedia (`DELETE /videos/{id}`)
- **Ruta:** `DELETE /videos/{video_id}`
- **Autenticación:** Requiere `Authorization: Bearer <access_token>`

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": null,
  "message": "Archivo multimedia eliminado exitosamente (Soft Delete)"
}
```
