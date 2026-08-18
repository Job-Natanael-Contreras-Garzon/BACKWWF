# 📋 Estandarización de Endpoints - Fauna Monitoring API

## 📐 Formato Estandarizado de Respuestas

Todas las respuestas de la API responden con una estructura JSON unificada que encapsula el estado (`status`), la carga útil de datos (`data`) y un mensaje informativo (`message`).

### 1. Respuesta Exitosa (2xx Success)
```json
{
  "status": "success",
  "data": { ... } | [ ... ] | null,
  "message": "Operación realizada exitosamente"
}
```

### 2. Respuesta de Error (4xx / 5xx Error)
```json
{
  "status": "error",
  "data": null,
  "message": "Detalle explicativo del error ocurrido"
}
```

---

## 🔑 Autenticación & Identificación de Sesión

Todo request enviado al backend puede operar bajo dos esquemas:

1. **Usuario Autenticado (Con Token JWT):**
   - Header HTTP: `Authorization: Bearer <access_token>`
   - Asocia el recurso directamente al `user_id` del usuario en sesión.

2. **Usuario Anónimo (Sin Token JWT):**
   - Header HTTP: `X-Anon-Session-ID: <UUID>`
   - Si no se envía ni Token ni el Header `X-Anon-Session-ID`, el servidor asume una sesión anónima, genera un nuevo UUID y lo retorna en las cabeceras de la respuesta (`X-Anon-Session-ID`).
   - Los proyectos y estaciones creados en modo anónimo quedan asociados a `anon_session_id`.

---

## 🚮 Reglas Globales de Eliminación (Soft Delete)

1. **Borrado Lógico:** Todos los endpoints `DELETE` marcan el registro con `is_deleted = True` y fijan la fecha en `deleted_at`.
2. **Requisito de Autenticación:** La eliminación **requiere obligatoriamente un Token JWT activo**. No existe borrado para datos en sesión anónima.
3. **Control de Propiedad:** Si un recurso es anónimo (aún no reclamado), devuelve `403 Forbidden` al intentar eliminarlo; el usuario debe **iniciar sesión/registrarse y reclamar el recurso** primero.

---

## 🗺️ Tabla Resumen de Endpoints Estandarizados (Nomenclatura en Inglés)

| Módulo | Método | Ruta | Descripción | Auth | Anon |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Authentication** | `POST` | `/auth/register` | Registro de nuevo usuario | ❌ | ❌ |
| | `POST` | `/auth/login` | Autenticación y generación de tokens JWT | ❌ | ❌ |
| | `POST` | `/auth/refresh` | Renovación de access_token con refresh_token | ❌ | ❌ |
| | `GET` | `/auth/me` | Obtener perfil del usuario autenticado | ✅ Token | ❌ |
| **Users & Session** | `POST` | `/users/me/claim` | Reclamar proyectos/estaciones anónimas (`anon_session_id`) | ✅ Token | ⚠️ Requiere `anon_session_id` |
| | `GET` | `/users/me/history` | Obtener proyectos y estaciones del usuario autenticado | ✅ Token | ❌ |
| **Camera Stations** | `POST` | `/camera-stations` | Crear estación de cámara trampa | ⚪ Opcional | ✅ `X-Anon-Session-ID` |
| | `GET` | `/camera-stations` | Listar estaciones activas (no eliminadas) | ⚪ Opcional | ⚪ Opcional |
| | `GET` | `/camera-stations/{id}` | Obtener estación por ID | ⚪ Opcional | ⚪ Opcional |
| | `PATCH` | `/camera-stations/{id}` | Actualizar datos de estación | ✅ Token | ❌ |
| | `DELETE` | `/camera-stations/{id}` | Soft delete de estación (Solo el dueño autenticado) | ✅ Token | ❌ (Error 403 si es anónima) |
| | `POST` | `/camera-stations/{id}/files` | Subir video o imagen a la estación para análisis de IA | ⚪ Opcional | ✅ `X-Anon-Session-ID` |
| | `GET` | `/camera-stations/{id}/summary` | Obtener métricas y resumen taxonómico de la estación | ⚪ Opcional | ⚪ Opcional |
| **Projects** | `POST` | `/projects` | Crear proyecto | ⚪ Opcional | ✅ `X-Anon-Session-ID` |
| | `GET` | `/projects` | Listar proyectos activos | ⚪ Opcional | ⚪ Opcional |
| | `GET` | `/projects/{id}` | Obtener proyecto por ID | ⚪ Opcional | ⚪ Opcional |
| | `PATCH` | `/projects/{id}` | Actualizar proyecto (Solo dueño) | ✅ Token | ❌ |
| | `DELETE` | `/projects/{id}` | Soft delete de proyecto (no borra estaciones vinculadas) | ✅ Token | ❌ (Error 403 si es anónimo) |
| | `POST` | `/projects/{id}/stations` | Asociar estación existente a proyecto (N:M) | ⚪ Opcional | ✅ `X-Anon-Session-ID` |
| | `DELETE` | `/projects/{id}/stations/{station_id}` | Desasociar estación de proyecto (Elimina relación N:M) | ⚪ Opcional | ✅ `X-Anon-Session-ID` |
| | `GET` | `/projects/{id}/summary` | Obtener resumen estadístico agregado de todas sus estaciones | ⚪ Opcional | ⚪ Opcional |
| **Species & AI** | `GET` | `/species/` | Listar detecciones de especies | ⚪ Opcional | ⚪ Opcional |
| | `GET` | `/species/data` | Dataset enriquecido (clima, fase lunar, velocidad) | ⚪ Opcional | ⚪ Opcional |
| | `POST` | `/species/{id}/verify` | Verificación por biólogo experto | ✅ Token | ❌ |

---

## 📁 Documentos Detallados por Módulo

- 🔐 [docs/endpoints/auth.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/auth.md)
- 👤 [docs/endpoints/users.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/users.md)
- 📷 [docs/endpoints/camera_stations.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/camera_stations.md)
- 📁 [docs/endpoints/projects.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/projects.md)
- 🐾 [docs/endpoints/species.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/species.md)
