---
title: "02 - Endpoints y Estado Funcional Real"
date: 2026-11-15
project: BACKWWF
version: "4.0.0 (MVP Hackathon)"
tags: [auditoria, endpoints, api, wwf, backwwf]
---

# 2. Inventario de Endpoints y Estado Funcional Real

> [!NOTE]
> Documento anterior: [[01_Arquitectura_y_Estructura]] | Siguiente: [[03_Flujo_Datos_IA_y_BaseDeDatos]]

> [!IMPORTANT]
> **Hallazgo de Enrutamiento:** Aunque los docstrings mencionan el prefijo `/api/v1/...` y `settings.API_V1_STR` está definido en `app/core/config.py`, `app/main.py` incluye todos los routers **sin prefijo global**. Las rutas reales expuestas están en la raíz (`/`).

---

## 2.1 Inventario Completo de Rutas Expuestas y Auditoría de Estado

### A. Sistema (`app/main.py`)
| Método | Ruta Real | Archivo | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | `app/main.py` | Pública | **100% Funcional** | Retorna metadatos de la app en `StandardResponse`. Sombrea a `GET /` de `videos.py`. |
| `GET` | `/health` | `app/main.py` | Pública | **100% Funcional** | Ejecuta `SELECT 1` en PostgreSQL y reporta estado `healthy`/`unhealthy`. |

### B. Autenticación (`app/api/v1/auth.py` — prefix `/auth`)
| Método | Ruta Real | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/auth/register` | Pública | **100% Funcional** | Valida email único (`is_deleted == False`), hashea con `bcrypt`, retorna usuario y par JWT. |
| `POST` | `/auth/login` | Pública | **100% Funcional** | Verifica hash `bcrypt` y `is_active`, retorna usuario y par JWT. |
| `POST` | `/auth/refresh` | Refresh Token | **100% Funcional** | Valida `REFRESH_SECRET_KEY` y `type == "refresh"`, emite nuevo par de tokens (sin blacklist/revocación). |
| `GET` | `/auth/me` | JWT (`get_current_user`) | **100% Funcional** | Retorna perfil del usuario autenticado. |

### C. Usuarios y Sesiones Anónimas (`app/api/v1/users.py` — prefix `/users`)
| Método | Ruta Real | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/users/me/claim` | JWT (`get_current_user`) | **100% Funcional** | Reasigna proyectos y estaciones con `anon_session_id` al usuario autenticado y marca `AnonSession.is_claimed=True`. |
| `GET` | `/users/me/history` | JWT (`get_current_user`) | **100% Funcional** | Lista proyectos y estaciones propias no eliminadas. |
| `GET` | `/users/` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Lista usuarios paginados, pero **no filtra `is_deleted == False`** (usa `CRUDBase.get_multi`) ni exige autenticación. |
| `GET` | `/users/{user_id}` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Filtra `is_deleted`, pero está abierto al público sin autenticación. |
| `PATCH` | `/users/{user_id}` | JWT (`get_current_user`) | **Incompleto / Parcial** | **Fallo grave de autorización (BOLA):** exige JWT pero **no valida** que `user_id == current_user.id`. Permite editar `is_active` de terceros. |
| `DELETE` | `/users/{user_id}` | JWT (`get_current_user`) | **Incompleto / Parcial** | **Fallo grave de autorización (BOLA):** no valida propiedad ni rol. Hace `user.is_deleted = True` sin asignar `deleted_at`. |

### D. Proyectos (`app/api/v1/projects.py` — prefix `/projects`)
| Método | Ruta Real | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/projects/` | Opcional + `X-Anon-Session-ID` | **100% Funcional** | Soporta creación autenticada o anónima creando registro en `anon_sessions`. |
| `GET` | `/projects/` | Pública | **100% Funcional** | Lista proyectos con `is_deleted == False`. |
| `GET` | `/projects/{project_id}` | Pública | **100% Funcional** | Retorna detalle y estaciones activas asociadas vía `project_stations`. |
| `PATCH` | `/projects/{project_id}` | JWT (`get_current_user`) | **100% Funcional** | Valida propiedad (`project.user_id == current_user.id`). |
| `DELETE` | `/projects/{project_id}` | JWT (`get_current_user`) | **100% Funcional** | Soft delete con validación de propiedad y bloqueo de proyectos anónimos (403). |
| `POST` | `/projects/{project_id}/stations` | Opcional (`get_current_user_optional`) | **Incompleto / Parcial** | Asociación N:M idempotente, pero **no verifica permisos/propiedad** sobre el proyecto o la estación. |
| `DELETE` | `/projects/{project_id}/stations/{station_id}` | Opcional (`get_current_user_optional`) | **Incompleto / Parcial** | Soft delete de relación N:M, pero **no verifica permisos/propiedad**. |
| `GET` | `/projects/{project_id}/summary` | Pública | **100% Funcional** | Agrega detecciones activas de `Species` por especie, familia y género en las estaciones del proyecto. |
| `POST` | `/projects/{project_id}/collaborators` | JWT (`get_current_user`) | **Incompleto / Parcial** | Verifica propiedad, pero no valida que los UUIDs de `colaborators` existan en la tabla `users`. |

### E. Estaciones de Cámara (`app/api/v1/camera_stations.py` — prefix `/camera-stations`)
| Método | Ruta Real | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/camera-stations/` | Opcional + `X-Anon-Session-ID` | **100% Funcional** | Crea estación y, si incluye `project_id`, crea vínculo N:M en `project_stations`. |
| `GET` | `/camera-stations/` | Pública | **100% Funcional** | Lista estaciones con `is_deleted == False`. |
| `GET` | `/camera-stations/{station_id}` | Pública | **100% Funcional** | Detalle de estación activa. |
| `PATCH` | `/camera-stations/{station_id}` | JWT (`get_current_user`) | **100% Funcional** | Valida propiedad (`station.user_id == current_user.id`). |
| `DELETE` | `/camera-stations/{station_id}` | JWT (`get_current_user`) | **100% Funcional** | Soft delete con validación de propiedad. |
| `GET` | `/camera-stations/{station_id}/summary` | Pública | **100% Funcional** | Resumen taxonómico agregado de `Species` para la estación. |

### F. Archivos Multimedia v4 (`app/api/v1/media_files.py` — prefix `/camera-stations`)
| Método | Ruta Real | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/camera-stations/{station_id}/files` | Opcional + `X-Anon-Session-ID` | **Incompleto / Parcial (con Mock en IA)** | Guarda archivo en disco local, crea `MediaFile`, llama a `analyze_media_with_ai` (que hace fallback mock si la IA falla o supera 2s), inserta `Species` en lote e incrementa `n_clips`. **No extrae duración/fecha con FFmpeg** ni valida tamaño máximo. |
| `GET` | `/camera-stations/{station_id}/files` | Pública | **100% Funcional** | Lista `MediaFile` activos de la estación. |
| `GET` | `/camera-stations/files/{media_file_id}` | Pública | **100% Funcional** | Detalle de `MediaFile` activo. |

### G. Videos Legacy (`app/api/v1/videos.py` — ⚠️ Sin prefix)
| Método | Ruta Real | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Router legacy sobre tabla `videos`. Extrae metadatos con FFmpeg (ruta Windows hardcodeada en `video_service.py`), actualiza stats y llama a IA. |
| `GET` | `/` | **Expuesto (Sin Auth)** | **Código Muerto (Sombreado)** | Nunca es alcanzado porque `@app.get("/")` en `app/main.py` se registra antes. |
| `GET` | `/{video_id}` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Lee de tabla legacy `videos`, sin auth ni soft delete. |
| `DELETE` | `/{video_id}` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Hard delete en tabla `videos` y borrado físico en disco (`os.remove`), sin auth. |

### H. Especies, Individuos, Reportes e IA Legacy (`species.py`, `individuals.py`, `reports.py`, `ai_router.py`)
| Método | Ruta Real | Archivo | Autenticación | Estado Real | Observaciones |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/species/` | `species.py` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Usa `CRUDBase.get_multi` (no filtra `is_deleted == False`). |
| `GET` | `/species/data` | `species.py` | **Expuesto (Sin Auth)** | **Incompleto / Parcial (Mock fallback)** | Enriquece detecciones con Open-Meteo y VisualCrossing; si fallan, inventa temperatura y fase lunar aleatorias. |
| `GET` | `/species/{species_id}` | `species.py` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | No filtra `is_deleted == False`. |
| `POST` | `/species/{species_id}/verify` | `species.py` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Permite a cualquier usuario anónimo verificar/alterar `is_verified`. |
| `DELETE` | `/species/{species_id}` | `species.py` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | Ejecuta **hard delete** vía `CRUDBase.remove` pese a que `Species` tiene `is_deleted`. |
| `POST/GET/DELETE` | `/individuals/*` | `individuals.py` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | CRUD básico sin auth ni soft delete. |
| `GET` | `/reports/indicators/*` (10 rutas) | `reports.py` | **Expuesto (Sin Auth)** | **Incompleto / Parcial** | `frequency`, `diversity`, `rai`, `rai-monthly`, `activity-weckel`, `ocupacion`, `temperatura`, `eventos-independientes`, `mapa-calor`, `gremios`. Filtra por `CameraStation.project_id` (legacy 1:N) en vez de `project_stations` (N:M) y no filtra `is_deleted == False`. |
| `POST/GET/DELETE` | `/reports/*` | `reports.py` | **Expuesto (Sin Auth)** | **100% Funcional (básico)** | CRUD simple sobre tabla `reports` sin auth ni validación de propiedad. |
| `POST` | `/ai/process-video/{video_id}` | `ai_router.py` | **Expuesto (Sin Auth)** | **Código Muerto / Roto** | Espera clave `detections` en la respuesta de `analyze_video_with_external_ai` (que retorna `results`) e intenta pasar `ai_raw_response` a `SpeciesCreate` (campo inexistente en el schema). |

---

## 2.2 Manejo de Carga de Videos: Individual vs. Carpeta / Lote (Meses de Grabación)

### Carga de Video Individual (Estado Actual)
Existen **dos flujos paralelos y duplicados** en el código:
1. **Flujo v4 (`POST /camera-stations/{station_id}/files` en `app/api/v1/media_files.py` -> `MediaService.process_media_upload`):**
   - Acepta un único `file: UploadFile = File(...)` vía `multipart/form-data`.
   - Valida extensión (`ALLOWED_EXTENSIONS`) y `Content-Type` (`ALLOWED_MIME_TYPES`, permitiendo `application/octet-stream`).
   - Guarda el archivo completo en disco local (`uploads/videos/{uuid12}_{filename}`) usando `shutil.copyfileobj(file.file, buffer)` de forma **síncrona** dentro de la corrutina `async def`.
   - Crea registro en `media_files` con `capture_date = datetime.now(timezone.utc)` (no lee la fecha real del video ni su duración).
   - Llama de forma síncrona-bloqueante para la petición HTTP (`await analyze_media_with_ai(...)`) al microservicio externo con `timeout=2.0` segundos.
   - Inserta las detecciones en `species` e incrementa `station.n_clips` en 1.
2. **Flujo Legacy (`POST /` en `app/api/v1/videos.py`):**
   - Acepta un único `file: UploadFile` y `station_id: UUID = Form(...)`.
   - Guarda en `uploads/videos/{uuid8}_{filename}` de forma síncrona.
   - Ejecuta `extract_video_metadata` en un hilo (`asyncio.to_thread`) usando `ffmpeg.probe`, actualiza `videos` y recalcula estadísticas en `camera_stations`.
   - Llama a `analyze_video_with_external_ai` y crea registros en `species` uno por uno.

### Carga de Carpeta o Lote de Videos (Meses de Grabación)
* **Estado:** **No implementado.**
* No existe ningún endpoint que acepte `List[UploadFile]`, archivos comprimidos (`.zip`/`.tar`), carga multiparte resumible (TUS/S3 Multipart), ni procesamiento en segundo plano (ni siquiera `BackgroundTasks` de FastAPI, Celery, RQ o Redis).
* **Impacto operativo:** Subir una tarjeta SD de cámara trampa con cientos o miles de clips (meses de grabación) obligaría al cliente a disparar peticiones HTTP individuales que bloquearían el Event Loop de Uvicorn, agotarían el disco efímero del contenedor y harían timeout en la llamada síncrona de 2 segundos al servicio de IA.
