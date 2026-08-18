# 🐾 Endpoints de Especies e IA (`/species`)

Módulo encargado de gestionar las detecciones de fauna silvestre generadas por el modelo de IA o ingresadas manualmente, la validación por biólogos expertos y el dataset enriquecido para análisis de biodiversidad.

---

## 1. Listar Detecciones de Especies
- **Ruta:** `GET /species/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*
- **Respuesta (`200 OK`):** Lista de `SpeciesRead`.

### Ejemplo de Respuesta `SpeciesRead`
```json
[
  {
    "id": 101,
    "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "video_id": "d1febc99-9c0b-4ef8-bb6d-6bb9bd380a44",
    "common_name": "Jaguar",
    "scientific_name": "Panthera onca",
    "confidence_score": 0.94,
    "detection_timestamp": "2026-08-10T14:30:05Z",
    "url_img": "http://localhost:8080/crops/detection_101.jpg",
    "is_verified": true,
    "created_at": "2026-08-18T00:00:00Z"
  }
]
```

---

## 2. Dataset Enriquecido de Especies (`/species/data`)
- **Ruta:** `GET /species/data`
- **Descripción:** Endpoint avanzado que calcula e integra variables ambientales, meteorológicas y astronómicas para cada registro de detección:
  - **Periodo del día:** Matutino, Vespertino, Nocturno, Crepuscular.
  - **Temperatura media:** Consulta histórica en tiempo real utilizando la API de **Open-Meteo** basada en la latitud, longitud y fecha/hora de la estación.
  - **Cálculos espacio-temporales:** Minutos desde la última detección, distancia Haversine (km) entre estaciones consecutivas y velocidad estimada (km/h).
  - **Fase lunar y Periodo Weckel:** Datos astronómicos calculados para estudios de actividad nictemeral.
  - **Evento independiente:** Indicador binario (`1` o `0`) de eventos independientes según intervalos ecológicos.

### Respuesta (`200 OK`) Lista de `SpeciesDataResponse`
```json
[
  {
    "id_deteccion": 101,
    "id_camara": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "url_img": "http://localhost:8080/crops/detection_101.jpg",
    "fecha_hora": "2026-08-10T14:30:05Z",
    "fecha": "2026-08-10",
    "hora": "14:30:05",
    "periodo_dia": "Vespertino",
    "especie": "Jaguar",
    "duracion_clip_seg": 15,
    "latitud": 4.654321,
    "longitud": -74.054321,
    "temp_media": 18.4,
    "min_desde_anterior": 45.2,
    "dist_anterior_km": 1.15,
    "velocidad_kmh": 1.52,
    "periodo_weckel": 0.75,
    "evento_independiente": 1,
    "periodoweckel": "Diurno"
  }
]
```

---

## 3. Obtener Detección por ID
- **Ruta:** `GET /species/{species_id}`
- **Parámetros Path:** `species_id` *(int)*
- **Respuestas:**
  - `200 OK`: Objeto `SpeciesRead`.
  - `404 Not Found`: Si el registro no existe.

---

## 4. Verificación Humana (Experto / Biólogo)
- **Ruta:** `POST /species/{species_id}/verify`
- **Descripción:** Permite a un usuario biólogo o experto verificar la exactitud de la detección de IA (marcando verdadero positivo o falso positivo).

### Cuerpo de Petición (`VerifyRequest`)
```json
{
  "verified": true
}
```

### Respuesta (`200 OK`) `SpeciesRead`
Devuelve la detección de especie con el campo `is_verified` actualizado a `true` o `false`.

---

## 5. Eliminar Registro de Especie
- **Ruta:** `DELETE /species/{species_id}`
- **Parámetros Path:** `species_id` *(int)*
- **Respuestas:**
  - `204 No Content`: Eliminado correctamente.
  - `404 Not Found`: Si no existe el registro.
