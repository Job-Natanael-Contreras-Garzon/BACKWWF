# 📁 Endpoints de Proyectos (`/projects`)

Módulo para la creación y gestión de proyectos de investigación, asociación N:M con estaciones de cámara, resúmenes estadísticos agregados y borrado suave (Soft Delete).

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

## 1. Crear Proyecto (`POST /projects/`)
- **Ruta:** `POST /projects/`
- **Código Estado:** `201 Created`
- **Autenticación:**
  - **Autenticado:** Header `Authorization: Bearer <access_token>` (Asigna el `user_id`).
  - **Anónimo:** Header `X-Anon-Session-ID: <UUID>` (Si no se envía, el servidor lo genera y lo retorna en las cabeceras de respuesta).

### Request Body `ProjectCreate`
```json
{
  "title": "Monitoreo Jaguar Chocó 2026",
  "description": "Estudio de densidad poblacional de Panthera onca.",
  "objectives": "Identificar individuos mediante patrones de rosetas.",
  "expected_results": "Catálogo completo de jaguares en la zona.",
  "status": "public",
  "colaborators": []
}
```

### Response (`201 Created`)
```json
{
  "status": "success",
  "data": {
    "id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
    "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "anon_session_id": null,
    "title": "Monitoreo Jaguar Chocó 2026",
    "description": "Estudio de densidad poblacional de Panthera onca.",
    "objectives": "Identificar individuos mediante patrones de rosetas.",
    "expected_results": "Catálogo completo de jaguares en la zona.",
    "status": "public",
    "colaborators": [],
    "created_at": "2026-08-18T00:00:00Z",
    "updated_at": "2026-08-18T00:00:00Z",
    "is_deleted": false,
    "deleted_at": null
  },
  "message": "Proyecto creado exitosamente"
}
```

---

## 2. Listar Proyectos (`GET /projects/`)
- **Ruta:** `GET /projects/`
- **Descripción:** Obtiene todos los proyectos activos (`is_deleted = False`).
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
      "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
      "anon_session_id": null,
      "title": "Monitoreo Jaguar Chocó 2026",
      "status": "public",
      "created_at": "2026-08-18T00:00:00Z",
      "updated_at": "2026-08-18T00:00:00Z",
      "is_deleted": false,
      "deleted_at": null
    }
  ],
  "message": "Proyectos obtenidos exitosamente"
}
```

---

## 3. Obtener Proyecto por ID (`GET /projects/{id}`)
- **Ruta:** `GET /projects/{project_id}`
- **Parámetros Path:** `project_id` *(UUID)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
    "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "title": "Monitoreo Jaguar Chocó 2026",
    "description": "Estudio de densidad poblacional de Panthera onca.",
    "status": "public",
    "camera_stations": [
      {
        "id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
        "station_code": "CAM-01",
        "location_name": "Quebrada La Vieja",
        "status": "active"
      }
    ],
    "created_at": "2026-08-18T00:00:00Z",
    "updated_at": "2026-08-18T00:00:00Z",
    "is_deleted": false,
    "deleted_at": null
  },
  "message": "Proyecto obtenido exitosamente"
}
```

---

## 4. Actualizar Proyecto (`PATCH /projects/{id}`)
- **Ruta:** `PATCH /projects/{project_id}`
- **Autenticación:** Requiere `Authorization: Bearer <access_token>` (Solo el propietario).

### Request Body `ProjectUpdate`
```json
{
  "title": "Nuevo Título del Proyecto",
  "status": "archived"
}
```

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
    "title": "Nuevo Título del Proyecto",
    "status": "archived",
    "updated_at": "2026-08-18T01:00:00Z",
    "is_deleted": false
  },
  "message": "Proyecto actualizado exitosamente"
}
```

---

## 5. Eliminar Proyecto - Soft Delete (`DELETE /projects/{id}`)
- **Ruta:** `DELETE /projects/{project_id}`
- **Autenticación:** **Requiere obligatoriamente Token JWT** (`Authorization: Bearer <access_token>`).
- **Regla de Negocio:**
  - Si el proyecto es anónimo (`user_id is Null`), responde con `403 Forbidden` solicitando al usuario que se registre/inicie sesión y reclame el recurso antes de eliminarlo.
  - Si el usuario no es el dueño (`user_id != token.user_id`), responde `403 Forbidden`.
  - Marca `is_deleted = True` y `deleted_at = timestamp`. **No borra físicamente el registro ni las estaciones que contenía**.

### Response Exitoso (`200 OK`)
```json
{
  "status": "success",
  "data": null,
  "message": "Proyecto eliminado exitosamente (Soft Delete)"
}
```

### Response Error Anónimo (`403 Forbidden`)
```json
{
  "status": "error",
  "data": null,
  "message": "No se pueden eliminar proyectos anónimos. Inicie sesión y reclame el recurso primero."
}
```

---

## 6. Asociar Estación a Proyecto - N:M (`POST /projects/{id}/stations`)
- **Ruta:** `POST /projects/{project_id}/stations`
- **Descripción:** Asocia una estación existente a este proyecto.

### Request Body
```json
{
  "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33"
}
```

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
    "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33"
  },
  "message": "Estación asociada al proyecto exitosamente"
}
```

---

## 7. Desasociar Estación de Proyecto (`DELETE /projects/{id}/stations/{station_id}`)
- **Ruta:** `DELETE /projects/{project_id}/stations/{station_id}`
- **Descripción:** Elimina la relación entre la estación y el proyecto (la estación sigue existiendo en el sistema).

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": null,
  "message": "Estación desasociada del proyecto exitosamente"
}
```

---

## 8. Resumen Estadístico Agregado del Proyecto (`GET /projects/{id}/summary`)
- **Ruta:** `GET /projects/{project_id}/summary`
- **Descripción:** Agrega todas las detecciones de **todas las estaciones vinculadas al proyecto** y proporciona el desglose taxonómico.

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
    "total_associated_stations": 4,
    "distinct_species_count": 8,
    "total_detections_count": 340,
    "frequency_by_species": [
      {"species": "Jaguar", "count": 45},
      {"species": "Puma", "count": 30},
      {"species": "Tapir", "count": 25}
    ],
    "frequency_by_family": [
      {"family": "Felidae", "count": 75},
      {"family": "Tapiridae", "count": 25}
    ],
    "frequency_by_genus": [
      {"genus": "Panthera", "count": 45},
      {"genus": "Puma", "count": 30},
      {"genus": "Tapirus", "count": 25}
    ]
  },
  "message": "Resumen del proyecto obtenido exitosamente"
}
```
