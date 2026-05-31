import math
from datetime import datetime
from typing import Optional, Dict, Any
import httpx


def calcular_periodo_dia(hora: int) -> str:
    """
    Calcula el periodo del día basado en la hora.
    5:00-11:59: mañana
    12:00-18:59: tarde
    19:00-4:59: noche
    """
    if 5 <= hora < 12:
        return "mañana"
    elif 12 <= hora < 19:
        return "tarde"
    else:
        return "noche"


async def obtener_temperatura_media(latitud: float, longitud: float, fecha: datetime) -> Optional[float]:
    """
    Obtiene la temperatura media del día desde la API de Open-Meteo.
    """
    fecha_str = fecha.strftime("%Y-%m-%d")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitud}&longitude={longitud}&start_date={fecha_str}&end_date={fecha_str}&daily=temperature_2m_mean&timezone=auto"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                if "daily" in data and "temperature_2m_mean" in data["daily"]:
                    return data["daily"]["temperature_2m_mean"][0]
    except Exception as e:
        print(f"Error obteniendo temperatura: {e}")
    
    return None


def calcular_distancia_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia en km entre dos puntos usando la fórmula Haversine.
    """
    # Convertir a radianes
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    lon1_rad = math.radians(lon1)
    lon2_rad = math.radians(lon2)
    
    # Diferencias
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Fórmula Haversine
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    # Radio de la Tierra en km
    r = 6371
    
    return r * c


def calcular_velocidad(row: Dict[str, Any], prev_row: Dict[str, Any]) -> Optional[float]:
    """
    Calcula la velocidad en km/h basándose en la distancia y el tiempo.
    """
    # 1. Verificar si son la misma especie y si hay datos de tiempo
    if row['especie'] != prev_row['especie'] or row['min_desde_anterior'] is None:
        return None
    
    tiempo_minutos = row['min_desde_anterior']
    distancia_km = row['dist_anterior_km']
    
    # 2. Manejar tiempos extremadamente cortos o cero para evitar errores
    if tiempo_minutos <= 0.99999:
        return 99999.0
    
    # 3. Calcular velocidad (Distancia / (Minutos / 60))
    velocidad_kmh = distancia_km / (tiempo_minutos / 60)
    
    return velocidad_kmh


async def obtener_moonphase(latitud: float, longitud: float, fecha: datetime) -> Optional[float]:
    """
    Obtiene la fase lunar (moonphase) desde la API de VisualCrossing.
    """
    fecha_str = fecha.strftime("%Y-%m-%d")
    api_key = "4CVBMAAYQ2HW86J7AARDANRDA"
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{latitud},{longitud}/{fecha_str}?key={api_key}&include=days&elements=moonphase"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                if "days" in data and len(data["days"]) > 0:
                    return data["days"][0].get("moonphase")
    except Exception as e:
        print(f"Error obteniendo moonphase: {e}")
    
    return None
