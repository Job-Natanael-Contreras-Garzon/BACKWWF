# 📷 Endpoints de Estaciones de Cámara (`/camera-stations`)

Módulo para la administración de estaciones de muestreo y dispositivos de cámara trampa en campo.

---

## 1. Crear Estación de Cámara
- **Ruta:** `POST /camera-stations/`
- **Código Estado Éxito:** `201 Created`
- **Autenticación:** Requiere Header `x-user-id: <UUID>` (Solo el dueño del proyecto al que pertenece la cámara puede agregarla).

### Cuerpo de Petición `CameraStationCreate`
```json
{
  "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
  "station_code": "CAM-01",
  "location_name": "Quebrada La Vieja",
  "latitude": 4.654321,
  "longitude": -74.054321,
  "altitude_meters": 2600.5,
  "camera_brand": "Browning",
  "camera_model": "Strike Force HD",
  "serial_number": "SN-987654",
  "trigger_speed_ms": 200,
  "ir_range_meters": 25,
  "deployment_date": "2026-01-15",
  "retrieval_date": "2026-03-15",
  "status": "active",
  "meta_data": {
    "habitat": "Bosque altoandino",
    "banca_baterias": "Litio 100%"
  }
}
```

### Respuesta de Éxito (`201 Created`) `CameraStationRead`
```json
{
  "id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
  "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
  "station_code": "CAM-01",
  "location_name": "Quebrada La Vieja",
  "latitude": 4.654321,
  "longitude": -74.054321,
  "altitude_meters": 2600.5,
  "camera_brand": "Browning",
  "camera_model": "Strike Force HD",
  "serial_number": "SN-987654",
  "trigger_speed_ms": 200,
  "ir_range_meters": 25,
  "deployment_date": "2026-01-15",
  "retrieval_date": "2026-03-15",
  "status": "active",
  "meta_data": {
    "habitat": "Bosque altoandino",
    "banca_baterias": "Litio 100%"
  },
  "created_at": "2026-08-18T00:00:00Z"
}
```

---

## 2. Listar Estaciones de Cámara
- **Ruta:** `GET /camera-stations/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*
- **Respuesta (`200 OK`):** Lista de `CameraStationRead`.

---

## 3. Obtener Estación por ID
- **Ruta:** `GET /camera-stations/{station_id}`
- **Parámetros Path:** `station_id` *(UUID)*
- **Respuestas:**
  - `200 OK`: Objeto `CameraStationRead`.
  - `404 Not Found`: Si la estación no existe.

---

## 4. Actualizar Estación
- **Ruta:** `PATCH /camera-stations/{station_id}`
- **Autenticación:** Header `x-user-id` (Solo dueño del proyecto).
- **Cuerpo `CameraStationUpdate`:**
```json
{
  "station_code": "CAM-01-REVISED",
  "status": "maintenance"
}
```
- **Respuestas:**
  - `200 OK`: Estación actualizada.
  - `403 Forbidden`: Si el usuario no es el dueño del proyecto.
  - `404 Not Found`: Si no existe la estación.

---

## 5. Eliminar Estación
- **Ruta:** `DELETE /camera-stations/{station_id}`
- **Autenticación:** Header `x-user-id` (Solo dueño del proyecto).
- **Respuestas:**
  - `204 No Content`: Estación eliminada.
  - `403 Forbidden`: Si no es dueño del proyecto.
  - `404 Not Found`: Si no existe la estación.
