# 🏷️ Endpoints de Individuos (`/individuals`)

Módulo para el seguimiento individualizado de especímenes (por ejemplo, jaguares reconocidos individualmente por su patrón de rosetas).

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

## 1. Crear Individuo (`POST /individuals/`)
- **Ruta:** `POST /individuals/`
- **Código Estado:** `201 Created`

### Request Body `IndividualCreate`
```json
{
  "name": "Jaguar - Macho Alfa 'Balam'",
  "species_id": 101,
  "is_verified": true
}
```

### Response (`201 Created`)
```json
{
  "status": "success",
  "data": {
    "id": "e1febc99-9c0b-4ef8-bb6d-6bb9bd380a55",
    "name": "Jaguar - Macho Alfa 'Balam'",
    "species_id": 101,
    "is_verified": true,
    "created_at": "2026-08-18T00:00:00Z",
    "updated_at": "2026-08-18T00:00:00Z",
    "is_deleted": false
  },
  "message": "Individuo registrado exitosamente"
}
```

---

## 2. Listar Individuos (`GET /individuals/`)
- **Ruta:** `GET /individuals/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": "e1febc99-9c0b-4ef8-bb6d-6bb9bd380a55",
      "name": "Jaguar - Macho Alfa 'Balam'",
      "species_id": 101,
      "is_verified": true,
      "created_at": "2026-08-18T00:00:00Z",
      "is_deleted": false
    }
  ],
  "message": "Individuos obtenidos exitosamente"
}
```

---

## 3. Obtener Individuo por ID (`GET /individuals/{id}`)
- **Ruta:** `GET /individuals/{ind_id}`
- **Parámetros Path:** `ind_id` *(UUID)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": "e1febc99-9c0b-4ef8-bb6d-6bb9bd380a55",
    "name": "Jaguar - Macho Alfa 'Balam'",
    "species_id": 101,
    "is_verified": true,
    "created_at": "2026-08-18T00:00:00Z",
    "is_deleted": false
  },
  "message": "Individuo obtenido exitosamente"
}
```

---

## 4. Verificar Individuo (`POST /individuals/{id}/verify`)
- **Ruta:** `POST /individuals/{ind_id}/verify`
- **Parámetros Query:** `verified` *(bool, requerido)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": "e1febc99-9c0b-4ef8-bb6d-6bb9bd380a55",
    "name": "Jaguar - Macho Alfa 'Balam'",
    "is_verified": true,
    "updated_at": "2026-08-18T01:00:00Z"
  },
  "message": "Verificación del individuo actualizada exitosamente"
}
```

---

## 5. Eliminar Individuo - Soft Delete (`DELETE /individuals/{id}`)
- **Ruta:** `DELETE /individuals/{ind_id}`
- **Autenticación:** Requiere Header `Authorization: Bearer <access_token>`

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": null,
  "message": "Individuo eliminado exitosamente (Soft Delete)"
}
```
