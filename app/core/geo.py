"""Distancias y redondeo de coordenadas para cámaras (DD-17, CB-01..CB-07)."""

import math
from decimal import ROUND_HALF_UP, Decimal

_EARTH_RADIUS_M = 6_371_008.8
METERS_PER_DEGREE_LAT = 111_320.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def round_1km(value: Decimal | float) -> float:
    """2 decimales (~1 km), con el mismo redondeo que ``round(numeric, 2)`` de PostgreSQL."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def distance_band(meters: float) -> str:
    """Para cámaras ajenas nunca se da la distancia exacta: evita triangular (CB-04, CB-05b)."""
    if meters < 10:
        return "<10m"
    if meters < 50:
        return "<50m"
    return "<200m"


def in_bbox(lat: float, lng: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lng, min_lat, max_lng, max_lat = bbox
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
