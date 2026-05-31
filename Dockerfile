# Imagen base oficial de Python (slim es más ligera)
FROM python:3.11-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /code

# Instalar dependencias del sistema necesarias (ffmpeg para ffmpeg-python)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copiar el archivo de dependencias primero (para aprovechar la caché de Docker)
COPY ./requirements.txt .

# Instalar las dependencias de Python
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copiar el resto del código de la aplicación
COPY ./app ./app

# Exponer el puerto que usa Uvicorn
EXPOSE 8000

# Comando para ejecutar la aplicación
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
