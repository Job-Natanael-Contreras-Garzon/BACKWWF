# ─────────────────────────────────────────────
#  Stage 1: build dependencies (con caché óptima)
# ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Dependencias del sistema necesarias para compilar wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias en un directorio aislado para copiarlas al stage final
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─────────────────────────────────────────────
#  Stage 2: imagen final (slim, sin gcc ni libpq-dev)
# ─────────────────────────────────────────────
FROM python:3.11-slim AS final

# Metadatos
LABEL org.opencontainers.image.title="Fauna Monitoring API"
LABEL org.opencontainers.image.description="WWF Wildlife Camera Trap Backend"
LABEL org.opencontainers.image.version="4.0.0"

WORKDIR /code

# Runtime: solo ffmpeg (para extracción de metadatos de video)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias instaladas desde el stage builder
COPY --from=builder /install /usr/local

# Copiar el código de la aplicación
COPY ./app ./app

# Usuario no-root para producción (buena práctica de seguridad)
RUN useradd --no-create-home --shell /bin/false appuser \
    && mkdir -p /code/uploads/videos \
    && chown -R appuser:appuser /code
USER appuser

# Puerto que expone la app
EXPOSE 8000

# Health check — DigitalOcean lo usa para determinar si el contenedor está sano
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# Comando de inicio — 2 workers en producción
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--no-access-log"]
