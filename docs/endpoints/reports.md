# 📊 Endpoints de Reportes (`/reports`)

Módulo para la generación, almacenamiento y consulta de reportes consolidados y métricas derivadas de los proyectos.

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

## 1. Crear Reporte (`POST /reports/`)
- **Ruta:** `POST /reports/`
- **Código Estado:** `201 Created`

### Request Body `ReportCreate`
```json
{
  "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
  "title": "Informe de Riqueza de Especies Q3 2026",
  "report_data": {
    "total_detecciones": 142,
    "especies_identificadas": ["Panthera onca", "Puma concolor", "Tapirus bairdii"],
    "indice_shannon": 2.45
  },
  "applied_filters": {
    "fecha_inicio": "2026-06-01",
    "fecha_fin": "2026-08-15",
    "estaciones": ["CAM-01", "CAM-02"]
  }
}
```

### Response (`201 Created`)
```json
{
  "status": "success",
  "data": {
    "id": "f1febc99-9c0b-4ef8-bb6d-6bb9bd380a66",
    "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
    "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "title": "Informe de Riqueza de Especies Q3 2026",
    "report_data": {
      "total_detecciones": 142,
      "especies_identificadas": ["Panthera onca", "Puma concolor", "Tapirus bairdii"],
      "indice_shannon": 2.45
    },
    "applied_filters": {
      "fecha_inicio": "2026-06-01",
      "fecha_fin": "2026-08-15",
      "estaciones": ["CAM-01", "CAM-02"]
    },
    "created_at": "2026-08-18T00:00:00Z",
    "is_deleted": false
  },
  "message": "Reporte generado exitosamente"
}
```

---

## 2. Listar Reportes (`GET /reports/`)
- **Ruta:** `GET /reports/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": "f1febc99-9c0b-4ef8-bb6d-6bb9bd380a66",
      "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
      "title": "Informe de Riqueza de Especies Q3 2026",
      "created_at": "2026-08-18T00:00:00Z"
    }
  ],
  "message": "Reportes obtenidos exitosamente"
}
```

---

## 3. Obtener Reporte por ID (`GET /reports/{id}`)
- **Ruta:** `GET /reports/{report_id}`
- **Parámetros Path:** `report_id` *(UUID)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": "f1febc99-9c0b-4ef8-bb6d-6bb9bd380a66",
    "project_id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
    "title": "Informe de Riqueza de Especies Q3 2026",
    "report_data": {
      "total_detecciones": 142,
      "especies_identificadas": ["Panthera onca", "Puma concolor", "Tapirus bairdii"]
    },
    "created_at": "2026-08-18T00:00:00Z"
  },
  "message": "Reporte obtenido exitosamente"
}
```

---

## 4. Eliminar Reporte - Soft Delete (`DELETE /reports/{id}`)
- **Ruta:** `DELETE /reports/{report_id}`
- **Autenticación:** Requiere Header `Authorization: Bearer <access_token>`

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": null,
  "message": "Reporte eliminado exitosamente (Soft Delete)"
}
```
