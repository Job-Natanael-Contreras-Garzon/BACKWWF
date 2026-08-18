# 🛠️ Guía de Implementación por Fases - Backend Fauna Monitoring API (WWF)

## 📌 Propósito de la Documentación
Esta carpeta contiene las instrucciones técnicas detalladas paso a paso para la implementación del refactor y mejoras del backend. Está estructurada para que cualquier desarrollador pueda tomar cada fase y ejecutar las modificaciones necesarias de forma ordenada, consistente y sin ambigüedades.

---

## 🗺️ Mapa de Fases de Desarrollo

| Fase | Archivo | Descripción Principal | Objetivos Clave |
| :---: | :--- | :--- | :--- |
| **Fase 1** | [fase_1_infraestructura_y_seguridad.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/implementacion/fase_1_infraestructura_y_seguridad.md) | Infraestructura Base, JWT & Middleware | Variables `.env`, Hashing contraseñas, Tokens JWT Access/Refresh, Formato `{status, data, message}` |
| **Fase 2** | [fase_2_autenticacion_y_sesiones_anonimas.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/implementacion/fase_2_autenticacion_y_sesiones_anonimas.md) | Auth, Sesión Anónima & Reclamo | Módulo `/auth`, Header `X-Anon-Session-ID`, Endpoint `/users/me/claim` y `/users/me/history` |
| **Fase 3** | [fase_3_base_entity_soft_delete_y_relacion_nm.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/implementacion/fase_3_base_entity_soft_delete_y_relacion_nm.md) | BaseEntity, Soft Delete & Relación N:M | BaseEntity común, Filtro `is_deleted = False`, Validación propiedad (Error 403 anónimo), N:M Proyectos-Estaciones |
| **Fase 4** | [fase_4_multimedia_ia_y_resumenes.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/implementacion/fase_4_multimedia_ia_y_resumenes.md) | Multimedia (Video/Imagen), IA & Resúmenes | Modelo `MediaFile`, Subida de imágenes y videos, Parsing taxonómico (`Familia;Género;Especie`), Endpoints `/summary` |
| **Fase 5** | [fase_5_verificacion_y_despliegue.md](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/implementacion/fase_5_verificacion_y_despliegue.md) | Verificación, Pruebas & Despliegue | Script de pruebas integrales, validación Swagger UI y guía de producción Docker/Koyeb |

---

## 🎯 Reglas Técnicas Generales para Desarrolladores

1. **Respuestas Estandarizadas Obligatorias:**
   - **Éxito:** `{ "status": "success", "data": <payload>, "message": "<texto>" }`
   - **Error:** `{ "status": "error", "data": null, "message": "<texto_del_error>" }`
2. **Nomenclatura de Rutas:**
   - Todas las rutas de API deben escribirse estrictamente en **inglés** (`/auth`, `/users`, `/projects`, `/camera-stations`, `/species`).
3. **Manejo de Sesión Anónima:**
   - Si un request no lleva ni Token JWT `Authorization: Bearer <token>` ni Header `X-Anon-Session-ID: <uuid>`, el sistema genera automáticamente un nuevo `X-Anon-Session-ID` y lo inyecta en los Headers de respuesta.
4. **Soft Delete:**
   - Ninguna entidad debe ser borrada con `SQL DELETE`. Se debe actualizar `is_deleted = True` y `deleted_at = datetime.now(timezone.utc)`. Los recursos anónimos **no pueden borrarse** (responden HTTP 403).
