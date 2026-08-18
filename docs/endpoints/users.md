# 👤 Endpoints de Usuarios y Sesiones (`/users`)

Módulo para la administración de perfiles de usuario, historial y flujo de reclamo de datos creados en sesiones anónimas.

---

## 1. Reclamar Datos Anónimos (`POST /users/me/claim`)
- **Ruta:** `POST /users/me/claim`
- **Autenticación:** Requiere Header `Authorization: Bearer <access_token>`
- **Descripción:** Toma el `anon_session_id` generado durante la navegación sin sesión y reasigna automáticamente todas las estaciones y proyectos asociados a esa sesión anónima hacia el `user_id` autenticado. Invalida la sesión anónima tras el reclamo.

### Request Body `ClaimAnonSessionRequest`
```json
{
  "anon_session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
}
```

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "claimed_projects_count": 2,
    "claimed_stations_count": 5,
    "anon_session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "claimed_by_user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
  },
  "message": "Datos anónimos asociados exitosamente a su cuenta"
}
```

---

## 2. Obtener Mi Historial (`GET /users/me/history`)
- **Ruta:** `GET /users/me/history`
- **Autenticación:** Requiere Header `Authorization: Bearer <access_token>`
- **Descripción:** Devuelve de forma consolidada todos los proyectos y estaciones pertenecientes al usuario autenticado.

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "projects": [
      {
        "id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
        "title": "Monitoreo Jaguar Chocó 2026",
        "status": "public",
        "created_at": "2026-08-18T00:00:00Z"
      }
    ],
    "camera_stations": [
      {
        "id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
        "station_code": "CAM-01",
        "location_name": "Quebrada La Vieja",
        "status": "active",
        "created_at": "2026-08-18T00:00:00Z"
      }
    ]
  },
  "message": "Historial del usuario obtenido exitosamente"
}
```

---

## 3. Listar Usuarios (`GET /users/`)
- **Ruta:** `GET /users/`
- **Autenticación:** Requiere Header `Authorization: Bearer <access_token>`

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
      "full_name": "Juan Pérez",
      "email": "juan.perez@example.com",
      "institucion": "WWF Colombia",
      "is_active": true,
      "created_at": "2026-08-18T00:00:00Z"
    }
  ],
  "message": "Usuarios obtenidos exitosamente"
}
```
