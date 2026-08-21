# 📋 BACKLOG TÉCNICO & ESTADO DE IMPLEMENTACIÓN — INNOVAHACK

> **Última actualización:** 2026-08-21  
> **Contexto:** Registro consolidado tras la ejecución de las mejoras prioritarias y auditoría exhaustiva.

---

## ✅ Mejoras Implementadas en Esta Iteración

| # | Ítem | Componente | Descripción | Estado |
|---|---|---|---|---|
| **IMP-01** | **Migraciones de BD con Alembic** (C-03) | `BACKWWF` | Soporte asíncrono con `asyncpg`, `alembic.ini`, `migrations/env.py`, actualización de `Dockerfile` y remoción de `create_all` en runtime. Documentado en `docs/base_de_datos/README.md`. | ✅ **Implementado** |
| **IMP-02** | **Event Loop No Bloqueante en IA** (C-04) | `ia-clasificacion-fauna` | Operaciones pesadas de OpenCV e inferencias de MegaDetector/SpeciesNet delegadas a `ThreadPool` mediante `asyncio.to_thread`. Diagramas de concurrencia añadidos al `README.md`. | ✅ **Implementado** |
| **IMP-03** | **Muestreo Dinámico de Video (5 frames / 15s)** (F-09) | `ia-clasificacion-fauna` | Algoritmo proporcional basado en duración para capturar eventos de fauna sin perder precisión. | ✅ **Implementado** |
| **IMP-04** | **Validación de Tipos MIME y Extensiones** (F-02) | `BACKWWF` | Validación estricta antes de escribir en disco en `media_service.py` y `videos.py`. | ✅ **Implementado** |
| **IMP-05** | **Optimización Anti-N+1 en Inserción de Especies** | `BACKWWF` | Inserción masiva por lotes (`db.add_all`) en un único round-trip en `media_service.py`. | ✅ **Implementado** |
| **IMP-06** | **Verificación de Contratos Frontend (Post-Pull)** | `Front-WWF` | Verificación completa de Request Bodies, Query Params, Headers (`Bearer`, `X-Anon-Session-ID`) y respuestas `StandardResponse` en los 5 servicios CRUD y `api.js`. | ✅ **Completado** |
| **IMP-07** | **Sincronización de Documentación** | `BACKWWF/docs` | Actualizados `endpoints/videos.md` y `base_de_datos/README.md` alineados a la arquitectura real. | ✅ **Completado** |
| **IMP-08** | **Enums y Validadores de Aplicación** (BL-09) | `BACKWWF` | Creado `app/core/enums.py` con `CameraStationStatus`, `ProjectStatus`, `MediaType`, `ResponseStatus`, `UserGender`, `EnvironmentMode`. Integrado en schemas Pydantic y servicios sin alterar columnas de BD. | ✅ **Implementado** |

---

## 🔒 Seguridad (Backlog para Producción)

### BL-01 · Credenciales de BD en Texto Plano
- **Ubicación:** `BACKWWF/digitalocean.yaml`
- **Problema:** URL de conexión a PostgreSQL contiene usuario y contraseña en texto plano.
- **Acción futura:** Mover a variables de entorno secretas de la plataforma. Rotar credenciales antes de despliegue público.
- **Prioridad:** 🔴 Crítica (antes de hacer el repo público).

### BL-02 · Servicio IA Sin Autenticación
- **Ubicación:** `ia-clasificacion-fauna/app/main.py`
- **Problema:** Ningún endpoint protegido. Sin API Keys ni tokens JWT.
- **Riesgo:** Cualquier persona con la URL pública puede enviar archivos consumiendo recursos de inferencia.
- **Acción futura:** Implementar autenticación por API Key compartida entre BACKWWF y el servicio IA.
- **Prioridad:** 🟡 Media.

### BL-03 · Exposición de Errores Internos al Cliente
- **Ubicación:** `BACKWWF/app/main.py` (handler global de excepciones)
- **Estado actual:** Se mantiene activo intencionalmente para facilitar debugging en fase de desarrollo.
- **Acción futura:** Sanitizar mensajes antes de producción. Loguear detalle completo en servidor y responder con mensaje genérico.
- **Prioridad:** 🟡 Media.

### BL-04 · CORS Permisivo
- **Estado actual:** Abierto (`allow_origins=["*"]`) para facilitar desarrollo.
- **Acción futura:** Restringir `allow_origins` a dominios autorizados en producción.
- **Prioridad:** 🟢 Baja en desarrollo, 🔴 Crítica en producción.

---

## 💾 Almacenamiento Persistente en la Nube (Propuesta S3 / Spaces)

### BL-05 · Almacenamiento de Archivos Multimedia en Object Storage

**Problema:** Los archivos se guardan en disco local del contenedor (`uploads/videos/`). En plataformas de contenedores efímeros (Koyeb/DigitalOcean App Platform), los archivos se pierden en cada reinicio o deploy.

**Solución Planificada:** Integrar almacenamiento en Object Storage (DigitalOcean Spaces / AWS S3).

**Archivos a Modificar en el Futuro:**
| Archivo | Cambio |
|---|---|
| `requirements.txt` | Agregar `boto3` |
| `app/core/config.py` | Variables: `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` |
| `app/services/storage_service.py` | **[NUEVO]** Servicio de upload/download a S3/Spaces |
| `app/api/v1/videos.py` y `media_service.py` | Reemplazar guardado local por `storage_service.upload()` |

---

## 📖 Documentación

### BL-06 · Distinción entre Carpetas `implementacion/` e `implements/`
- `docs/implementacion/` = La orden e instrucción del requerimiento inicial.
- `docs/implements/` = El reporte y registro de lo que el agente ejecutó.
- **Acción:** Mantener ambas carpetas documentando su propósito diferenciado.

---

## 🧪 Testing

### BL-07 · Cobertura de Tests Unitarios
- **Existen:** Tests de estrés (`test_phase3_soft_delete_and_nm_stress.py`).
- **Faltan:** Tests unitarios por servicio (`auth`, `projects`, `media`, `species`), pruebas de schemas Pydantic y edge cases.
- **Prioridad:** 🟡 Media.

---

## 🧹 Mantenimiento de Código

### BL-08 · Código Comentado en Servicio IA
- `detector.py` contiene bloques comentados que pueden depurarse en futuras limpiezas.
- **Prioridad:** 🟢 Baja.
