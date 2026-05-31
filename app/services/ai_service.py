# app/services/ai_service.py
import asyncio
import httpx
from typing import Dict, Any
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

load_dotenv()

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")

async def analyze_video_with_external_ai(video_path: str) -> Dict[str, Any]:
    """
    Llama a la API de IA externa para analizar un video.
    Envía el video como un archivo multipart/form-data al endpoint {AI_SERVICE_URL}/api/v1/detect
    
    Args:
        video_path: Ruta local del archivo de video a analizar
        
    Returns:
        JSON response con las detecciones de especies
    """
    endpoint = f"{AI_SERVICE_URL}/api/v1/detect"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(video_path, "rb") as video_file:
                files = {"file": (video_path.split("\\")[-1], video_file, "video/mp4")}
                
                logger.info(f"[AI Service] Enviando video a {endpoint}")
                response = await client.post(endpoint, files=files)
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"[AI Service] Respuesta recibida: {len(result.get('results', []))} detecciones")
                return result
                
    except httpx.HTTPError as e:
        logger.error(f"[AI Service] Error en la llamada HTTP: {e}")
        raise
    except FileNotFoundError:
        logger.error(f"[AI Service] Archivo no encontrado: {video_path}")
        raise
    except Exception as e:
        logger.error(f"[AI Service] Error inesperado: {e}")
        raise
