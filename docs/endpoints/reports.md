# 📊 Endpoints de Reportes (`/reports`)

Módulo para la generación, almacenamiento y consulta de reportes consolidados y métricas derivadas de los proyectos.

---

## 1. Crear Reporte
- **Ruta:** `POST /reports/`
- **Código Estado Éxito:** `201 Created`

### Cuerpo de Petición `ReportCreate`
```json
{
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
  }
}
```

### Respuesta (`201 Created`) `ReportRead`
```json
{
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
  "generated_at": "2026-08-18T00:00:00Z"
}
```

---

## 2. Listar Reportes
- **Ruta:** `GET /reports/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*
- **Respuesta (`200 OK`):** Lista de `ReportRead`.

---

## 3. Obtener Reporte por ID
- **Ruta:** `GET /reports/{report_id}`
- **Parámetros Path:** `report_id` *(UUID)*
- **Respuestas:**
  - `200 OK`: Objeto `ReportRead`.
  - `404 Not Found`: Si no existe el reporte.

---

## 4. Eliminar Reporte
- **Ruta:** `DELETE /reports/{report_id}`
- **Parámetros Path:** `report_id` *(UUID)*
- **Respuestas:**
  - `204 No Content`: Reporte eliminado.
  - `404 Not Found`: Si no existe.
