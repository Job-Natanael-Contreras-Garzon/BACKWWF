import math
import random
from datetime import datetime
from typing import Optional, Dict, Any
import asyncio
import httpx

# Caches in-memory to prevent rate-limiting and speed up responses drastically
_CACHE_TEMP = {}
_CACHE_MOON = {}

# Shared HTTP client — one per process lifetime, avoids per-call socket exhaustion
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None

# Cap concurrent outbound HTTP requests to avoid hitting Windows select() FD limit (512)
MAX_CONCURRENT_HTTP = 20
_HTTP_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=3.0)
    return _HTTP_CLIENT


def _get_semaphore() -> asyncio.Semaphore:
    global _HTTP_SEMAPHORE
    if _HTTP_SEMAPHORE is None:
        _HTTP_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_HTTP)
    return _HTTP_SEMAPHORE


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
    Calcula el periodo del dia basado en la hora.
    5:00-11:59: manana
    12:00-18:59: tarde
    19:00-4:59: noche
    """
    if 5 <= hora < 12:
        return "mañana"
    elif 12 <= hora < 19:
        return "tarde"
    else:
        return "noche"


async def obtener_temperatura_media(latitud: float, longitud: float, fecha: datetime) -> float:
    """
    Obtiene la temperatura media del dia desde la API de Open-Meteo.
    Implementa un mecanismo de cache y un fallback aleatorio (mock) si el API 
    lanza 400 Bad Request (fechas pasadas invalidas) o algun otro error/rate limit.
    Uses a shared AsyncClient and semaphore to avoid file-descriptor exhaustion.
    """
    fecha_str = fecha.strftime("%Y-%m-%d")
    cache_key = f"{latitud}_{longitud}_{fecha_str}"
    
    if cache_key in _CACHE_TEMP:
        return _CACHE_TEMP[cache_key]

    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={latitud}&longitude={longitud}&start_date={fecha_str}&end_date={fecha_str}&daily=temperature_2m_mean&timezone=auto"
    
    async with _get_semaphore():
        try:
            client = _get_http_client()
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                if "daily" in data and "temperature_2m_mean" in data["daily"] and data["daily"]["temperature_2m_mean"][0] is not None:
                    temp = float(data["daily"]["temperature_2m_mean"][0])
                    _CACHE_TEMP[cache_key] = temp
                    return temp
            else:
                # Intento secundario con forecast por si las fechas son muy recientes y no estan en archive
                url_f = f"https://api.open-meteo.com/v1/forecast?latitude={latitud}&longitude={longitud}&start_date={fecha_str}&end_date={fecha_str}&daily=temperature_2m_mean&timezone=auto"
                response_f = await client.get(url_f)
                if response_f.status_code == 200:
                    data_f = response_f.json()
                    if "daily" in data_f and "temperature_2m_mean" in data_f["daily"] and data_f["daily"]["temperature_2m_mean"][0] is not None:
                        temp = float(data_f["daily"]["temperature_2m_mean"][0])
                        _CACHE_TEMP[cache_key] = temp
                        return temp
        except Exception as e:
            print(f"Error obteniendo temperatura: {e}")
    
    # Fallback aleatorio realista si falla, e.g. temperatura calida/selvatica (15°C a 35°C)
    fallback_temp = round(random.uniform(15.0, 35.0), 1)
    _CACHE_TEMP[cache_key] = fallback_temp
    return fallback_temp


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


async def obtener_moonphase(latitud: float, longitud: float, fecha: datetime) -> float:
    """
    Obtiene la fase lunar (moonphase) desde la API de VisualCrossing.
    Implementa un mecanismo de cache y un fallback aleatorio (mock) ante errores/rate limits.
    Uses a shared AsyncClient and semaphore to avoid file-descriptor exhaustion.
    """
    fecha_str = fecha.strftime("%Y-%m-%d")
    cache_key = f"{latitud}_{longitud}_{fecha_str}"
    
    if cache_key in _CACHE_MOON:
        return _CACHE_MOON[cache_key]

    api_key = "4CVBMAAYQ2HW86J7AARDANRDA"
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{latitud},{longitud}/{fecha_str}?key={api_key}&include=days&elements=moonphase"
    
    async with _get_semaphore():
        try:
            client = _get_http_client()
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                if "days" in data and len(data["days"]) > 0:
                    moonphase = data["days"][0].get("moonphase")
                    if moonphase is not None:
                        val = float(moonphase)
                        _CACHE_MOON[cache_key] = val
                        return val
        except Exception as e:
            print(f"Error obteniendo moonphase: {e}")
    
    # Fallback aleatorio entre 0.0 y 1.0 (las fases van de 0 a 1)
    fallback_moon = round(random.uniform(0.0, 1.0), 2)
    _CACHE_MOON[cache_key] = fallback_moon
    return fallback_moon


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


async def enrich_species_data(species_list: list) -> list:
    import asyncio
    from app.schemas import SpeciesDataResponse
    
    # PRE-WARM CACHES CONCURRENTLY
    unique_temp_reqs = {}
    unique_moon_reqs = {}
    
    for sp in species_list:
        latitud = float(sp.station.latitude) if sp.station and sp.station.latitude else None
        longitud = float(sp.station.longitude) if sp.station and sp.station.longitude else None
        fecha_hora = sp.detection_timestamp
        
        if latitud and longitud and fecha_hora:
            fecha_str = fecha_hora.strftime("%Y-%m-%d")
            cache_key = f"{latitud}_{longitud}_{fecha_str}"
            
            if cache_key not in _CACHE_TEMP:
                unique_temp_reqs[cache_key] = (latitud, longitud, fecha_hora)
            if cache_key not in _CACHE_MOON:
                unique_moon_reqs[cache_key] = (latitud, longitud, fecha_hora)

    tasks = []
    for lat, lon, fh in unique_temp_reqs.values():
        tasks.append(obtener_temperatura_media(lat, lon, fh))
    for lat, lon, fh in unique_moon_reqs.values():
        tasks.append(obtener_moonphase(lat, lon, fh))
        
    if tasks:
        await asyncio.gather(*tasks)

    results = []
    
    # DICCIONARIO para agrupar el "prev_row" por ESPECIE (Equivale a groupby("especie").shift())
    prev_rows_by_species = {}
    
    for sp in species_list:
        id_deteccion = sp.id
        id_camara = str(sp.station_id)
        url_img = sp.url_img
        fecha_hora = sp.detection_timestamp
        especie = sp.common_name
        
        # Recuperamos el registro anterior de ESTA MISMA ESPECIE
        prev_row = prev_rows_by_species.get(especie)
        
        latitud = float(sp.station.latitude) if sp.station and sp.station.latitude else None
        longitud = float(sp.station.longitude) if sp.station and sp.station.longitude else None
        
        duracion_clip_seg = sp.video.duration_seconds if sp.video and sp.video.duration_seconds else None
        
        fecha = fecha_hora.strftime('%Y-%m-%d') if fecha_hora else None
        hora = fecha_hora.strftime('%H:%M:%S') if fecha_hora else None
        hora_int = fecha_hora.hour if fecha_hora else None
        periodo_dia = calcular_periodo_dia(hora_int) if hora_int is not None else None
        
        temp_media = None
        if latitud and longitud and fecha_hora:
            temp_media = await obtener_temperatura_media(latitud, longitud, fecha_hora)
        
        min_desde_anterior = None
        dist_anterior_km = None
        
        if prev_row and fecha_hora and prev_row['fecha_hora']:
            diff = fecha_hora - prev_row['fecha_hora']
            min_desde_anterior = diff.total_seconds() / 60
            
            if latitud and longitud and prev_row.get('latitud') and prev_row.get('longitud'):
                dist_anterior_km = calcular_distancia_haversine(
                    latitud, longitud,
                    prev_row['latitud'], prev_row['longitud']
                )
        
        row = {
            'especie': especie,
            'id_camara': id_camara,
            'min_desde_anterior': min_desde_anterior,
            'dist_anterior_km': dist_anterior_km
        }
        
        velocidad_kmh = None
        if prev_row:
            velocidad_kmh = calcular_velocidad(row, prev_row)
        
        row['velocidad_kmh'] = velocidad_kmh
        
        evento_independiente = 1
        if prev_row:
            evento_independiente = es_evento_independiente(row, prev_row)
        
        periodo_weckel = None
        if latitud and longitud and fecha_hora:
            periodo_weckel = await obtener_moonphase(latitud, longitud, fecha_hora)
        
        periodoweckel = calcular_periodo_weckel(fecha_hora)
        
        result = SpeciesDataResponse(
            id_deteccion=id_deteccion,
            id_camara=id_camara,
            url_img=url_img,
            fecha_hora=fecha_hora,
            fecha=fecha,
            hora=hora,
            periodo_dia=periodo_dia,
            especie=especie,
            duracion_clip_seg=duracion_clip_seg,
            latitud=latitud,
            longitud=longitud,
            temp_media=temp_media,
            min_desde_anterior=min_desde_anterior,
            dist_anterior_km=dist_anterior_km,
            velocidad_kmh=velocidad_kmh,
            periodo_weckel=periodo_weckel,
            evento_independiente=evento_independiente,
            periodoweckel=periodoweckel
        )
        
        results.append(result)
        
        # Guardamos la fila actual como la anterior para ESTA especie
        prev_rows_by_species[especie] = {
            'especie': especie,
            'id_camara': id_camara,
            'fecha_hora': fecha_hora,
            'latitud': latitud,
            'longitud': longitud,
            'min_desde_anterior': min_desde_anterior,
            'dist_anterior_km': dist_anterior_km,
            'velocidad_kmh': velocidad_kmh
        }
    
    return results

