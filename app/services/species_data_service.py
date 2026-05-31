import math
from datetime import datetime
from typing import Optional, Dict, Any
import httpx

# Configuration
TIEMPO_UMBRAL_MINUTOS = 30

# Maximum speeds by species (in km/h)
# Default speed: 5 km/h if species not found
VEL_MAX_ESPECIES = {
    'southern lesser long-tailed opossum': 4.0,
    'brown brocket deer': 6.0,
    'collared peccary': 5.0,
    'armadillo': 4.0,
    'brazilian rabbit': 5.0,
    'crab-eating fox': 7.0,
    'ocelot': 6.0,
    'giant anteater': 4.0,
    'pampas deer': 6.0,
    'tayra': 5.0,
    'capybara': 5.0,
    'black howler monkey': 5.0,
    'brazilian tapir': 6.0,
    'white-lipped peccary': 6.0,
    'giant armadillo': 4.0,
    'squirrel': 4.0,
    'tamandua': 4.0,
    'white-nosed coati': 4.0,
    'common opossum': 4.0,
    'gray four-eyed opossum': 4.0,
    'crab-eating raccoon': 5.0,
}


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
    Lógica biológica: calcula velocidad siempre que sea la misma especie y tiempo > 0.
    """
    # 1. Verificar si son la misma especie y si hay datos de tiempo
    if row['especie'] != prev_row['especie']:
        return None
    
    if row['min_desde_anterior'] is None or row['min_desde_anterior'] <= 0:
        return None
    
    tiempo_minutos = row['min_desde_anterior']
    distancia_km = row['dist_anterior_km']
    
    # 2. Calcular velocidad (Distancia / (Minutos / 60))
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


def interpretar_moonphase(moonphase: Optional[float]) -> Optional[str]:
    """
    Interpreta el valor de moonphase (0-1) y devuelve una descripción.
    0 = Luna nueva
    0.25 = Cuarto creciente
    0.5 = Luna llena
    0.75 = Cuarto menguante
    1 = Luna nueva (ciclo completo)
    """
    if moonphase is None:
        return None
    
    if moonphase < 0.03 or moonphase > 0.97:
        return "new_moon"
    elif 0.03 <= moonphase < 0.22:
        return "waxing_crescent"
    elif 0.22 <= moonphase < 0.28:
        return "first_quarter"
    elif 0.28 <= moonphase < 0.47:
        return "waxing_gibbous"
    elif 0.47 <= moonphase < 0.53:
        return "full_moon"
    elif 0.53 <= moonphase < 0.72:
        return "waning_gibbous"
    elif 0.72 <= moonphase < 0.78:
        return "last_quarter"
    else:
        return "waning_crescent"


def calcular_periodo_weckel(fecha_hora: Optional[datetime]) -> Optional[str]:
    """
    Clasifica la actividad en nocturno/diurno/crepuscular basándose en la hora decimal.
    - Nocturno: >= 18:31 (18.5167) o <= 05:00 (5.0)
    - Diurno: entre 06:31 (6.5167) y 17:00 (17.0)
    - Crepuscular: el resto (05:01-06:30 y 17:01-18:30)
    """
    if fecha_hora is None:
        return None
    
    # Calcular la hora decimal (Horas + Minutos/60 + Segundos/3600)
    hora_decimal = fecha_hora.hour + (fecha_hora.minute / 60) + (fecha_hora.second / 3600)
    
    # Condición Nocturno: >= 18:31 o <= 05:00
    if hora_decimal >= 18.5167 or hora_decimal <= 5.0:
        return "nocturno"
    
    # Condición Diurno: entre 06:31 y 17:00
    elif 6.5167 <= hora_decimal <= 17.0:
        return "diurno"
    
    # El resto es Crepuscular
    else:
        return "crepuscular"


def es_evento_independiente(row: Dict[str, Any], prev_row: Dict[str, Any]) -> int:
    """
    Determina si un evento es independiente basándose en:
    - Cambio de especie
    - Tiempo desde anterior (> 30 min)
    - Velocidad vs máxima biológica de la especie
    
    Returns 1 si es independiente, 0 si no.
    """
    # Si cambió la especie → evento independiente
    if row['especie'] != prev_row['especie']:
        return 1
    
    # Si es la misma especie, evaluamos la cámara
    if row['id_camara'] == prev_row['id_camara']:
        # Solo depende del tiempo
        return 1 if row['min_desde_anterior'] and row['min_desde_anterior'] > TIEMPO_UMBRAL_MINUTOS else 0
    else:
        # Diferente cámara: Verificamos velocidad vs Máxima biológica
        v_max_biologica = VEL_MAX_ESPECIES.get(row['especie'].lower(), 5.0)
        
        # Si la velocidad calculada > V. Max Biológica
        if row['velocidad_kmh'] and row['velocidad_kmh'] > v_max_biologica:
            return 1
        else:
            # Si la velocidad es normal, revisamos el tiempo
            return 1 if row['min_desde_anterior'] and row['min_desde_anterior'] > TIEMPO_UMBRAL_MINUTOS else 0
