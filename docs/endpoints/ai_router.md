# 🤖 Endpoints de Procesamiento de IA (`/ai`)

Módulo dedicado al procesamiento manual o diferido de archivos de video/imagen mediante la integración con el servicio externo de Inteligencia Artificial.

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

## 1. Procesar Video/Imagen con IA (`POST /ai/process-video/{id}`)
- **Ruta:** `POST /ai/process-video/{video_id}`
- **Parámetros Path:** `video_id` *(UUID, requerido)*: ID del archivo a procesar.

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": 102,
      "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
      "media_file_id": "d1febc99-9c0b-4ef8-bb6d-6bb9bd380a44",
      "common_name": "Puma",
      "scientific_name": "Puma concolor",
      "family": "Felidae",
      "genus": "Puma",
      "confidence_score": 0.88,
      "detection_timestamp": "2026-08-10T14:30:10Z",
      "url_img": "http://localhost:8080/crops/crop_102.jpg",
      "is_verified": null,
      "created_at": "2026-08-18T00:00:00Z"
    }
  ],
  "message": "Análisis de IA procesado exitosamente"
}
```

### Respuestas de Error
```json
{
  "status": "error",
  "data": null,
  "message": "El archivo especificado no existe en la base de datos."
}
```
