# 📁 Endpoints de Proyectos (`/projects`)

Módulo para la creación y gestión de proyectos de investigación de fauna, control de propietarios y colaboradores.

---

## 1. Crear Proyecto
- **Ruta:** `POST /projects/`
- **Código Estado Éxito:** `201 Created`
- **Autenticación:** Requiere Header `x-user-id: <UUID>` (El usuario asignado en la cabecera será forzado como el propietario `user_id`).

### Cuerpo de Petición `ProjectCreate`
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

### Respuesta de Éxito (`201 Created`) `ProjectRead`
```json
{
  "id": "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22",
  "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "title": "Monitoreo Jaguar Chocó 2026",
  "description": "Estudio de densidad poblacional de Panthera onca.",
  "objectives": "Identificar individuos mediante patrones de rosetas.",
  "expected_results": "Catálogo completo de jaguares en la zona.",
  "status": "public",
  "colaborators": [],
  "created_at": "2026-08-18T00:00:00Z",
  "updated_at": "2026-08-18T00:00:00Z",
  "camera_stations": []
}
```

---

## 2. Listar Proyectos
- **Ruta:** `GET /projects/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*
- **Respuesta (`200 OK`):** Lista de objetos `ProjectRead`.

---

## 3. Obtener Proyecto por ID
- **Ruta:** `GET /projects/{project_id}`
- **Parámetros Path:** `project_id` *(UUID)*
- **Respuesta:**
  - `200 OK`: Detalle del proyecto incluyendo estaciones de cámara asociadas.
  - `404 Not Found`: Si el proyecto no existe.

---

## 4. Actualizar Proyecto
- **Ruta:** `PATCH /projects/{project_id}`
- **Autenticación:** Requiere Header `x-user-id` (Solo el dueño del proyecto puede modificarlo).
- **Cuerpo `ProjectUpdate`:**
```json
{
  "title": "Nuevo Título del Proyecto",
  "status": "archived"
}
```
- **Respuestas:**
  - `200 OK`: Proyecto actualizado.
  - `403 Forbidden`: Si el usuario del Header no es el propietario.
  - `404 Not Found`: Si el proyecto no existe.

---

## 5. Eliminar Proyecto
- **Ruta:** `DELETE /projects/{project_id}`
- **Autenticación:** Requiere Header `x-user-id` (Solo el dueño del proyecto puede eliminarlo).
- **Respuestas:**
  - `204 No Content`: Eliminación exitosa.
  - `403 Forbidden`: Si el usuario no es el dueño.
  - `404 Not Found`: Si el proyecto no existe.

---

## 6. Añadir Colaboradores a un Proyecto
- **Ruta:** `POST /projects/{project_id}/collaborators`
- **Autenticación:** Requiere Header `x-user-id` (Solo el dueño del proyecto).

### Cuerpo de Petición `ProjectAddCollaborators`
```json
{
  "colaborators": [
    "c2febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "d3febc99-9c0b-4ef8-bb6d-6bb9bd380a44"
  ]
}
```
- **Respuestas:**
  - `200 OK`: Proyecto actualizado con la lista de colaboradores.
  - `403 Forbidden`: Si no es el dueño.
  - `404 Not Found`: Si el proyecto o alguno de los colaboradores no existe.

---

## 7. Obtener Proyectos de un Usuario
- **Ruta:** `GET /projects/user/{user_id}`
- **Autenticación:** Requiere Header `x-user-id` (El `user_id` del Path debe coincidir con el Header `x-user-id`).
- **Respuesta (`200 OK`) `UserProjectsResponse`:**
```json
{
  "owned_projects": [
    "b1febc99-9c0b-4ef8-bb6d-6bb9bd380a22"
  ],
  "collaborator_projects": [
    "e4febc99-9c0b-4ef8-bb6d-6bb9bd380a55"
  ]
}
```
