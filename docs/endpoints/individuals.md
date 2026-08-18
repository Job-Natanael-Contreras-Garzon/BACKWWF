# 🏷️ Endpoints de Individuos (`/individuals`)

Módulo para el seguimiento individualizado de especímenes (por ejemplo, jaguares reconocidos individualmente por el patrón de rosetas).

---

## 1. Crear Individuo
- **Ruta:** `POST /individuals/`
- **Código Estado Éxito:** `201 Created`

### Cuerpo de Petición `IndividualCreate`
```json
{
  "name": "Jaguar - Macho Alfa 'Balam'",
  "species_id": 101,
  "is_verified": true
}
```

### Respuesta (`201 Created`) `IndividualRead`
```json
{
  "id": "e1febc99-9c0b-4ef8-bb6d-6bb9bd380a55",
  "name": "Jaguar - Macho Alfa 'Balam'",
  "species_id": 101,
  "is_verified": true,
  "created_at": "2026-08-18T00:00:00Z"
}
```

---

## 2. Listar Individuos
- **Ruta:** `GET /individuals/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*
- **Respuesta (`200 OK`):** Lista de `IndividualRead`.

---

## 3. Obtener Individuo por ID
- **Ruta:** `GET /individuals/{ind_id}`
- **Parámetros Path:** `ind_id` *(UUID)*
- **Respuestas:**
  - `200 OK`: Objeto `IndividualRead`.
  - `404 Not Found`: Si no existe el individuo.

---

## 4. Verificar Individuo
- **Ruta:** `POST /individuals/{ind_id}/verify`
- **Parámetros Query:** `verified` *(bool, requerido)*
- **Respuesta (`200 OK`):** Objeto `IndividualRead` actualizado.

---

## 5. Eliminar Individuo
- **Ruta:** `DELETE /individuals/{ind_id}`
- **Parámetros Path:** `ind_id` *(UUID)*
- **Respuestas:**
  - `204 No Content`: Eliminación completada.
  - `404 Not Found`: Si no existe.
