import os
import logging
from datetime import datetime, timezone

# Configurar la ruta de FFmpeg antes de importar la librería
FFMPEG_PATH = r"C:\Users\contr\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-essentials_build\bin"
os.environ["PATH"] = FFMPEG_PATH + os.pathsep + os.environ.get("PATH", "")

import ffmpeg

# Configurar logger para este módulo
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def extract_video_metadata(file_path: str):
    """
    Extrae duración, resolución y fecha de creación del video usando ffmpeg-python.
    """
    try:
        # 1. Convertir siempre a ruta absoluta
        abs_path = os.path.abspath(file_path)
        logger.info(f"[Metadata Extractor] Ruta original recibida: {file_path}")
        logger.info(f"[Metadata Extractor] Ruta absoluta calculada: {abs_path}")

        # 2. Verificar existencia en el disco antes de pasar a FFmpeg
        if not os.path.exists(abs_path):
            logger.error(f"[Metadata Extractor] ERROR: No se encontró el archivo físico en {abs_path}")
            return {"error": f"File not found at {abs_path}"}

        logger.info("[Metadata Extractor] Archivo encontrado. Ejecutando ffmpeg.probe...")
        
        # probe ejecuta ffprobe de manera síncrona usando la ruta absoluta
        probe = ffmpeg.probe(abs_path)
        logger.info("[Metadata Extractor] ffmpeg.probe ejecutado con éxito.")
        
        format_info = probe.get('format', {})
        duration = float(format_info.get('duration', 0))
        
        file_stats = os.stat(abs_path)
        capture_date = datetime.fromtimestamp(file_stats.st_mtime, tz=timezone.utc)

        video_stream = next((stream for stream in probe.get('streams', []) if stream['codec_type'] == 'video'), None)
        
        metadata = {
            "duration_seconds": duration,
            "capture_date": capture_date.isoformat() if capture_date else None,
            "width": int(video_stream.get('width', 0)) if video_stream else 0,
            "height": int(video_stream.get('height', 0)) if video_stream else 0,
            "codec": video_stream.get('codec_name', 'unknown') if video_stream else 'unknown'
        }
        
        logger.info(f"[Metadata Extractor] Extracción finalizada: {metadata}")
        return metadata

    except ffmpeg.Error as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"[Metadata Extractor] Error de FFmpeg: {error_msg}")
        return {"error": f"FFmpeg error: {error_msg}"}
    except Exception as e:
        logger.error(f"[Metadata Extractor] Excepción no controlada: {str(e)}")
        return {"error": str(e)}
