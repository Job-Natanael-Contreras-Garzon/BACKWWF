# app/services/ai_service.py
import asyncio
from typing import Dict, Any

async def analyze_video_with_external_ai(video_url: str) -> Dict[str, Any]:
    """
    Simula una llamada HTTP a una API de IA externa (ej. un microservicio con YOLO, ResNet, etc.)
    """
    await asyncio.sleep(1) # Simulando tiempo de red/procesamiento
    
    # JSON Simulado que retorna el modelo de IA
    return {
        "detections": [
            {
                "common_name": "Jaguar",
                "scientific_name": "Panthera onca",
                "confidence_score": 0.9542,
                "detection_timestamp": "2024-05-30T10:15:30Z"
            },
            {
                "common_name": "Tapir",
                "scientific_name": "Tapirus bairdii",
                "confidence_score": 0.8870,
                "detection_timestamp": "2024-05-30T10:16:05Z"
            }
        ],
        "model_version": "v2.1.0-jungle",
        "processing_time_ms": 1250
    }
