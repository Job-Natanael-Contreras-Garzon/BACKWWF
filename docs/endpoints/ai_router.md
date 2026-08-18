# 🤖 Endpoints de Procesamiento de IA (`/ai`)

Módulo dedicado al procesamiento manual o diferido de archivos de video a través de la integración con la API externa de Inteligencia Artificial.

---

## 1. Procesar Video con IA
- **Ruta:** `POST /ai/process-video/{video_id}`
- **Descripción:** Toma un video guardado en la base de datos por su `video_id`, envía la ruta del archivo local al servicio de IA configurado y crea los nuevos registros de detección en la tabla `species`.

### Parámetros Path
- `video_id` *(UUID, requerido)*: ID del video a procesar.

### Respuesta de Éxito (`200 OK`) Lista de `SpeciesRead`
```json
[
  {
    "id": 102,
    "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "video_id": "d1febc99-9c0b-4ef8-bb6d-6bb9bd380a44",
    "common_name": "Puma",
    "scientific_name": "Puma concolor",
    "confidence_score": 0.88,
    "detection_timestamp": "2026-08-10T14:30:10Z",
    "url_img": null,
    "is_verified": null,
    "created_at": "2026-08-18T00:00:00Z"
  }
]
```

### Respuestas de Error
- `404 Not Found`: Si el `video_id` no existe en la base de datos.
- `500 Internal Server Error`: Si ocurre un error al comunicarse con el servicio de IA externo.
