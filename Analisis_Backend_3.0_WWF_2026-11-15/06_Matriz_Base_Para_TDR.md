---
title: "06 - Matriz Base para Cruce con TDR Oficiales WWF"
date: 2026-11-15
project: BACKWWF
version: "4.0.0 (MVP Hackathon)"
tags: [auditoria, tdr, matriz, madurez, wwf]
---

# 6. Matriz Base de Capacidades Técnicas para TDR

> [!NOTE]
> Documento anterior: [[05_Analisis_Mejoras_Criticas_y_Seguridad]] | Inicio: [[01_Arquitectura_y_Estructura]]

Esta matriz resume el estado real, los archivos involucrados y el nivel de madurez técnica de cada capacidad del backend `BACKWWF` para su contraste directo contra los **Términos de Referencia (TDR)** oficiales de WWF y la guía de desarrollo.

### Escala de Madurez (1 a 5)
* **1 — Crítico / Roto / No Implementado:** Código muerto, mockeado, inexistente o con fallas bloqueantes.
* **2 — Prototipo Hackathon:** Funciona en demo local bajo camino feliz, pero carece de seguridad, validación o escalabilidad.
* **3 — Funcional Parcial:** Lógica de negocio sólida, pero con brechas de autorización, rendimiento o estándares.
* **4 — Casi Producción:** Cumple estándares y seguridad básica; requiere ajustes menores de observabilidad o despliegue.
* **5 — Grado Empresarial:** Listo para producción, escalable, seguro, probado y monitoreado.

---

## 6.1 Matriz de Capacidades del Sistema

| Módulo / Dominio | Funcionalidad Actual | Archivos Involucrados | Madurez (1-5) | Observaciones y Brecha hacia Producción |
| :--- | :--- | :--- | :---: | :--- |
| **Core, Config y ASGI** | Configuración Pydantic, `lifespan`, exception handlers y CORS | `app/main.py`, `app/core/config.py`, `app/core/enums.py` | **2 / 5** | Secretos JWT con defaults inseguros, CORS inyecta `localhost` en prod, errores 500 exponen `str(exc)`, routers montados sin prefijo `/api/v1`. |
| **Autenticación JWT** | Registro, login, refresh token y perfil `/auth/me` con `bcrypt` y `PyJWT` | `app/api/v1/auth.py`, `app/services/auth_service.py`, `app/core/security.py`, `app/api/deps.py` | **3 / 5** | Flujo funcional, pero sin RBAC (roles admin/investigador/validador), sin revocación/blacklist de tokens ni rate limiting en login. |
| **Usuarios y Sesiones Anónimas** | Reclamo de datos anónimos (`claim`), historial y CRUD de usuarios | `app/api/v1/users.py`, `app/services/user_service.py`, `app/models/anon_session.py` | **2 / 5** | `claim` e `history` funcionan bien; `GET /users/*` está expuesto sin auth y `PATCH/DELETE /users/{id}` tienen vulnerabilidad crítica BOLA/IDOR. |
| **Proyectos e Investigación** | CRUD proyectos, soft delete, colaboradores y relación N:M con estaciones | `app/api/v1/projects.py`, `app/services/project_service.py`, `app/models/project.py`, `app/models/project_station.py` | **3 / 5** | CRUD y resúmenes bien estructurados; falta autorización en `associate/disassociate_station` y `ProjectStation` tiene PK compuesta anómala de 3 columnas. |
| **Estaciones de Cámara Trampa** | CRUD estaciones, geolocalización, telemetría y resumen taxonómico | `app/api/v1/camera_stations.py`, `app/services/station_service.py`, `app/models/camera_station.py` | **3 / 5** | Funcional con soft delete y validación de dueño en PATCH/DELETE. Mantiene FK legacy `project_id` paralela a `project_stations`. |
| **Ingesta Individual de Media** | Subida individual de imagen/video en disco local (`uploads/`) | `app/api/v1/media_files.py`, `app/services/media_service.py`, `app/api/v1/videos.py` | **2 / 5** | Duplicidad `media_files` vs `videos` (router sin prefix). I/O síncrono bloquea Event Loop; sin límite de tamaño ni Object Storage (S3/Spaces). |
| **Ingesta Masiva / Lotes (Carpetas)** | Carga y procesamiento de carpetas o meses de grabación | *(No implementado)* | **1 / 5** | **No implementado.** Sin subida multiparte/resumible, sin compresión/descompresión ni colas asíncronas (`Celery`/`Redis`). |
| **Extracción de Metadatos (FFmpeg)** | Lectura de duración, resolución y fecha de captura de videos | `app/services/video_service.py` | **1 / 5** | Ruta de FFmpeg en Windows hardcodeada; no es invocado por el flujo v4 (`media_service.py`), dejando duración y fecha real sin extraer. |
| **Integración con Servicio IA** | Envío multipart a `{AI_SERVICE_URL}/api/v1/detect` y parseo taxonómico | `app/services/ai_service.py`, `app/api/v1/ai_router.py` | **1 / 5** | Timeout inviable de `2.0s`, URLs por defecto inconsistentes, fallback mock que inventa jaguares en BD y `ai_router.py` roto. |
| **Especies, Individuos y Validación** | Listado, verificación humana (`is_verified`) y gestión de individuos | `app/api/v1/species.py`, `app/api/v1/individuals.py`, `app/models/species.py`, `app/models/individual.py` | **2 / 5** | Todos los endpoints están expuestos sin autenticación, hacen hard delete y no filtran `is_deleted == False`. |
| **Indicadores Ecológicos y Reportes** | 10 indicadores (RAI, Shannon, Simpson, Weckel, ocupación, mapa de calor, gremios) y CRUD reportes | `app/api/v1/reports.py`, `app/services/indicators_service.py`, `app/services/species_data_service.py` | **2 / 5** | Lógica estadística valiosa, pero expuesta sin auth, API key de VisualCrossing hardcodeada, datos climáticos aleatorios en fallback y filtros ligados a FK legacy. |
| **Base de Datos y Migraciones** | PostgreSQL Async (`asyncpg`), SQLAlchemy 2.0 y Alembic | `app/db/session.py`, `app/models/*`, `migrations/env.py` | **2 / 5** | `migrations/versions/` vacío (sin migraciones reales), credenciales Aiven expuestas en `digitalocean.yaml` y `check_db.py`, exceso de `lazy="selectin"`. |
| **Seguridad Perimetral y Despliegue** | Docker multi-stage, `docker-compose.yml`, `digitalocean.yaml`, `koyeb.yml` | `Dockerfile`, `docker-compose.yml`, `digitalocean.yaml`, `koyeb.yml` | **2 / 5** | Buen Dockerfile (usuario no-root `appuser`), pero sin reverse proxy/TLS local, sin Rate Limiting, sin `TrustedHostMiddleware` y secretos en YAML. |

---

## 6.2 Checklist de Siguientes Pasos (Pre-Cruce con TDR)
- [ ] Rotar de inmediato las credenciales de PostgreSQL en Aiven y la API Key de VisualCrossing expuestas en el repositorio.
- [ ] Definir en el TDR el volumen esperado por campaña (tamaño máximo por video y cantidad de archivos por lote) para dimensionar Object Storage + Cola de Tareas (`Celery`/`Redis`).
- [ ] Confirmar contrato oficial (request/response y tiempos de inferencia) del microservicio externo de IA para eliminar el fallback mock y el `timeout=2.0s`.
- [ ] Consolidar el modelo de datos eliminando la duplicidad entre `videos` y `media_files`, y generar la migración inicial limpia en Alembic.
