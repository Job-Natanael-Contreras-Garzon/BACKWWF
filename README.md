# Backend - Sistema de Monitoreo de Fauna (Cámaras Trampa e IA)

Este repositorio contiene la API RESTful asíncrona para la gestión de proyectos de monitoreo de fauna silvestre, estaciones de cámaras trampa y procesamiento de video con IA.

## 🛠 Stack Tecnológico

*   **Framework Core:** [FastAPI](https://fastapi.tiangolo.com/) (Web framework de alto rendimiento).
*   **ORM:** [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/) (Estilo declarativo 2.0, tipado estricto, modo asíncrono puro).
*   **Base de Datos:** PostgreSQL a través del driver asíncrono `asyncpg`.
*   **Validación de Datos:** [Pydantic V2](https://docs.pydantic.dev/latest/) (Esquemas de validación y serialización).
*   **Documentación API:** Swagger UI / OpenAPI (Integración nativa).

## 🏗 Arquitectura de Base de Datos

El modelo relacional está compuesto por 7 entidades principales (usando `UUID` como PK primaria y mapeo estricto de tipos de PostgreSQL como `JSONB` y `TIMESTAMP(timezone=True)`):

1.  **Users:** Gestión de investigadores y organizaciones.
2.  **Projects:** Agrupación lógica de despliegues.
3.  **Reports:** Informes estructurados y pre-filtrados almacenados en formato `JSONB`.
4.  **Camera Stations:** Metadatos de hardware y geolocalización de las trampas de cámara.
5.  **Videos:** Multimedia capturada en las estaciones (con referencias a Storage externo S3/GCS).
6.  **Species:** Registro de detecciones derivadas del procesamiento de IA (`confidence_score`, metadata raw).
7.  **Individuals:** Identificación específica de ejemplares por especie.

## 🚀 Configuración y Ejecución Local

### 1. Entorno Virtual y Dependencias
Se requiere Python 3.10 o superior (recomendado 3.11+).

```bash
# Activar entorno virtual
.\app\venv\Scripts\Activate.ps1

# Instalar dependencias requeridas
pip install fastapi "uvicorn[standard]" sqlalchemy asyncpg pydantic
```

### 2. Variables de Entorno (Conexión)
La conexión a PostgreSQL está configurada en `app/db/session.py`. En producción, el DSN asíncrono debe seguir el formato:
`postgresql+asyncpg://user:password@host:port/dbname?ssl=require`

### 3. Iniciar el Servidor (Modo Desarrollo)
FastAPI incluye Uvicorn como servidor ASGI. Para iniciarlo con auto-recarga:

```bash
uvicorn app.main:app --reload
```

## 📖 Documentación Interactiva (Swagger / OpenAPI)

FastAPI genera y expone automáticamente la especificación OpenAPI de todos los endpoints y esquemas Pydantic. 
Una vez levantado el servidor, puedes acceder a:

*   **Swagger UI (Interactiva):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
*   **ReDoc (Alternativa de lectura):** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## 🧩 Decisiones Arquitectónicas (Dev Notes)

*   **`lazy="selectin"` en SQLAlchemy:** Debido a la naturaleza asíncrona de `asyncpg`, el "lazy loading" tradicional (carga diferida) emite excepciones (`MissingGreenletError`) ya que requiere I/O bloqueante. Se utilizó `selectin` en todas las relaciones bidireccionales para ejecutar un `SELECT ... IN (...)` en paralelo al query principal.
*   **Ciclo de vida (`lifespan`):** La inicialización de la DB (`create_all`) se inyecta en el contexto de arranque de FastAPI usando `@asynccontextmanager`, asegurando que el pool de conexiones (`Engine`) se cierre limpiamente en el apagado.
*   **Capa de Servicios (`services/`):** La lógica de procesamiento externo (IA) está abstraída en micro-servicios dentro de la capa `services` para evitar sobrecargar los Controladores (`routers`).

## 🐳 Despliegue en Koyeb

El proyecto está configurado para despliegue en [Koyeb](https://www.koyeb.com/) usando Docker.

### Archivos de Configuración Docker

- **`Dockerfile`**: Define la imagen Docker con Python 3.11-slim, ffmpeg y todas las dependencias.
- **`.dockerignore`**: Excluye archivos innecesarios de la imagen Docker.
- **`koyeb.yml`**: Configuración específica para despliegue en Koyeb.

### Pasos para Desplegar en Koyeb

1. **Subir el código a GitHub**
   - Asegúrate de que todos los archivos estén en tu repositorio de GitHub.

2. **Crear un nuevo servicio en Koyeb**
   - Ve al panel de Koyeb y crea un nuevo servicio.
   - Selecciona "GitHub" como fuente.
   - Selecciona tu repositorio `BACKWWF`.
   - Koyeb detectará automáticamente el `Dockerfile` y `koyeb.yml`.

3. **Configurar variables de entorno**
   - En el panel de Koyeb, agrega la variable de entorno:
     - `DATABASE_URL`: Tu cadena de conexión de PostgreSQL (ej: `postgresql+asyncpg://user:password@host:port/dbname?ssl=require`)

4. **Desplegar**
   - Koyeb construirá la imagen Docker y desplegará tu aplicación.
   - El servicio estará disponible en la URL proporcionada por Koyeb.

### Verificación

Una vez desplegado, puedes acceder a:
- **Swagger UI:** `https://tu-url-koyeb.koyeb.app/docs`
- **Health Check:** Koyeb verificará automáticamente el endpoint `/docs`

### Notas Importantes

- La aplicación usa `ffmpeg` para procesamiento de video, ya incluido en el Dockerfile.
- El puerto expuesto es `8000` (configurado en Dockerfile y koyeb.yml).
- Los archivos subidos se almacenan temporalmente en `/code/uploads` dentro del contenedor.
