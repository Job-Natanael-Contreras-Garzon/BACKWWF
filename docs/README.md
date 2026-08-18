# Documentación General del Backend - Fauna Monitoring API (WWF)

## 📌 Descripción del Proyecto
Este backend es una API RESTful desarrollada con **FastAPI** para el monitoreo de fauna silvestre mediante cámaras trampa. Permite la gestión de usuarios, proyectos de investigación, estaciones de monitoreo (cámaras trampa), carga de archivos multimedia (videos), integración con servicios de Inteligencia Artificial para la detección e identificación de especies, análisis ecológicos enriquecidos y generación de reportes.

---

## 🛠️ Tecnologías Utilizadas

- **Framework principal:** FastAPI (Python 3.10+)
- **Base de Datos & ORM:** PostgreSQL / SQLite (con SQLAlchemy Async, Asyncpg / Aiosqlite)
- **Migraciones:** Alembic
- **Procesamiento de Video:** FFmpeg (`ffprobe` para extracción de metadatos)
- **Integraciones Externas:**
  - Servicio de IA para detección de fauna (Roboflow / YOLO / Custom API)
  - API de Open-Meteo para datos meteorológicos históricos (temperatura media)
  - Algoritmo de Fase Lunar / Periodo Weckel para patrones de actividad
- **Despliegue & Contenedores:** Docker, Koyeb

---

## 📁 Estructura del Proyecto

```
BACKWWF/
├── app/
│   ├── api/
│   │   ├── deps.py             # Dependencias de autenticación y sesión
│   │   └── v1/                 # Endpoints API v1
│   │       ├── ai_router.py
│   │       ├── camera_stations.py
│   │       ├── individuals.py
│   │       ├── projects.py
│   │       ├── reports.py
│   │       ├── species.py
│   │       ├── users.py
│   │       └── videos.py
│   ├── crud/                   # Capa de operaciones CRUD
│   ├── db/                     # Configuración de base de datos y sesiones async
│   ├── models/                 # Modelos SQLAlchemy (ORM)
│   ├── schemas/                # Esquemas Pydantic (Validación y Serialización)
│   └── services/               # Servicios de lógica de negocio (IA, metadatos, clima)
├── docs/                       # Documentación del proyecto
│   ├── README.md               # Índice general y arquitectura
│   ├── base_de_datos/          # Documentación del modelo ER y esquemas
│   └── endpoints/              # Documentación técnica detallada de cada Endpoint
├── uploads/                    # Directorio local de almacenamiento de videos
├── Dockerfile                  # Configuración de contenedor Docker
├── requirements.txt            # Dependencias Python
└── main.py                     # Punto de entrada de la aplicación FastAPI
```

---

## 🔒 Autenticación y Autorización

Actualmente, la API utiliza un encabezado HTTP de autorización simulado:
- `x-user-id` *(UUID)*: ID del usuario autenticado actual.

Este encabezado es obligatorio en endpoints protegidos (creación de proyectos, modificación de proyectos/estaciones por el propietario, etc.).

---

## 📚 Índice de Documentación de Endpoints

La documentación técnica detallada de los endpoints de la API se encuentra en la carpeta [`docs/endpoints/`](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints):

1. 👥 [**Usuarios (`/users`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/users.md): Registro, consulta, modificación y eliminación de usuarios.
2. 📁 [**Proyectos (`/projects`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/projects.md): Gestión de proyectos de investigación y asignación de colaboradores.
3. 📷 [**Estaciones de Cámara (`/camera-stations`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/camera_stations.md): Gestión de cámaras trampa asociadas a proyectos.
4. 🎥 [**Videos (`/videos`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/videos.md): Subida de videos, extracción de metadatos con FFmpeg y procesamiento automático con IA.
5. 🐾 [**Especies e IA (`/species`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/species.md): Detecciones de fauna, verificación por experto y dataset enriquecido (`/species/data`).
6. 🏷️ [**Individuos (`/individuals`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/individuals.md): Registro e identificación individualizada de animales.
7. 📊 [**Reportes (`/reports`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/reports.md): Almacenamiento y consulta de reportes y métricas generadas.
8. 🤖 [**Procesamiento de IA (`/ai`)**](file:///c:/Proyectos/hackaton/wwf/BACKWWF/docs/endpoints/ai_router.md): Endpoint para re-procesar videos almacenados con servicios de IA externos.

---

## 🚀 Inicio Rápido

1. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configurar variables de entorno (`.env`):**
   ```env
   DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/wwf_db
   AI_SERVICE_URL=http://localhost:8080
   ```
3. **Ejecutar servidor de desarrollo:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
4. **Documentación interactiva Swagger UI:**
   - URL: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`
