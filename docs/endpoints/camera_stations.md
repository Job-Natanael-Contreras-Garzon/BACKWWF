# 📷 Endpoints de Estaciones de Cámara (`/camera-stations`)

Módulo para la administración de estaciones de muestreo, dispositivos de cámaras trampa en campo, subida de contenido multimedia (videos e imágenes) y resúmenes estadísticos.

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

## 1. Crear Estación de Cámara (`POST /camera-stations/`)
- **Ruta:** `POST /camera-stations/`
- **Código Estado:** `201 Created`
- **Autenticación:**
  - **Autenticado:** Header `Authorization: Bearer <access_token>` (Asigna `user_id`).
  - **Anónimo:** Header `X-Anon-Session-ID: <UUID>` (Generado automáticamente si no se envía).

### Request Body `CameraStationCreate`
```json
{
  "station_code": "CAM-01",
  "location_name": "Quebrada La Vieja",
  "latitude": 4.654321,
  "longitude": -74.054321,
  "altitude_meters": 2600.5,
  "camera_brand": "Browning",
  "camera_model": "Strike Force HD",
  "serial_number": "SN-987654",
  "days_active": 30,
  "deployment_date": "2026-01-15",
  "retrieval_date": null,
  "status": "active"
}
```

### Response (`201 Created`)
```json
{
  "status": "success",
  "data": {
    "id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "anon_session_id": null,
    "station_code": "CAM-01",
    "location_name": "Quebrada La Vieja",
    "latitude": 4.654321,
    "longitude": -74.054321,
    "altitude_meters": 2600.5,
    "days_active": 30,
    "deployment_date": "2026-01-15",
    "retrieval_date": null,
    "status": "active",
    "created_at": "2026-08-18T00:00:00Z",
    "updated_at": "2026-08-18T00:00:00Z",
    "is_deleted": false,
    "deleted_at": null
  },
  "message": "Estación de cámara creada exitosamente"
}
```

---

## 2. Listar Estaciones (`GET /camera-stations/`)
- **Ruta:** `GET /camera-stations/`
- **Descripción:** Obtiene todas las estaciones de cámara activas (`is_deleted = False`).
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
      "station_code": "CAM-01",
      "location_name": "Quebrada La Vieja",
      "status": "active",
      "created_at": "2026-08-18T00:00:00Z",
      "is_deleted": false
    }
  ],
  "message": "Estaciones de cámara obtenidas exitosamente"
}
```

---

## 3. Obtener Estación por ID (`GET /camera-stations/{id}`)
- **Ruta:** `GET /camera-stations/{station_id}`
- **Parámetros Path:** `station_id` *(UUID)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "station_code": "CAM-01",
    "location_name": "Quebrada La Vieja",
    "latitude": 4.654321,
    "longitude": -74.054321,
    "status": "active",
    "created_at": "2026-08-18T00:00:00Z",
    "is_deleted": false
  },
  "message": "Estación de cámara obtenida exitosamente"
}
```

---

## 4. Subir Archivo Multimedia (Video o Imagen) (`POST /camera-stations/{id}/files`)
- **Ruta:** `POST /camera-stations/{station_id}/files`
- **Content-Type:** `multipart/form-data`
- **Descripción:** Permite subir un archivo de **video** (`.mp4`, `.avi`, `.mov`) o **imagen** (`.jpg`, `.png`). Extrae metadatos, consulta al modelo de IA y genera automáticamente los registros de detecciones parseando `family`, `genus`, `scientific_name` y `common_name`.

### Campos Form Data
- `file` *(File, requerido)*: Archivo multimedia.

### Response (`201 Created`)
```json
{
  "status": "success",
  "data": {
    "media_file_id": "m1febc99-9c0b-4ef8-bb6d-6bb9bd380a77",
    "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "file_type": "image",
    "file_url": "uploads/images/a1b2c3d4_foto01.jpg",
    "detections_count": 2,
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
    ]
  },
  "message": "Archivo multimedia procesado e identificado exitosamente por la IA"
}
```

---

## 5. Resumen Estadístico de la Estación (`GET /camera-stations/{id}/summary`)
- **Ruta:** `GET /camera-stations/{station_id}/summary`
- **Descripción:** Métricas consolidadas de detecciones para la cámara trampa con desglose taxonómico.

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "distinct_species_count": 3,
    "total_detections_count": 15,
    "frequency_by_species": [
      {"species": "Jaguar", "count": 8},
      {"species": "Puma", "count": 5},
      {"species": "Ocelote", "count": 2}
    ],
    "frequency_by_family": [
      {"family": "Felidae", "count": 15}
    ],
    "frequency_by_genus": [
      {"genus": "Panthera", "count": 8},
      {"genus": "Puma", "count": 5},
      {"genus": "Leopardus", "count": 2}
    ]
  },
  "message": "Resumen estadístico de la estación obtenido exitosamente"
}
```

---

## 6. Eliminar Estación - Soft Delete (`DELETE /camera-stations/{id}`)
- **Ruta:** `DELETE /camera-stations/{station_id}`
- **Autenticación:** **Requiere obligatoriamente Token JWT** (`Authorization: Bearer <access_token>`).
- **Regla de Negocio:**
  - Si la estación fue creada en modo anónimo (`user_id is Null`), responde con `403 Forbidden` exigiendo al usuario registrarse y reclamarla previamente.
  - Si el usuario no es el dueño, responde `403 Forbidden`.
  - Marca `is_deleted = True` y `deleted_at = timestamp`.

### Response Exitoso (`200 OK`)
```json
{
  "status": "success",
  "data": null,
  "message": "Estación eliminada exitosamente (Soft Delete)"
}
```
