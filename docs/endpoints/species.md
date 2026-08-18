# 🐾 Endpoints de Especies (`/species`)

Módulo encargado de gestionar las detecciones de fauna silvestre generadas por el modelo de IA o ingresadas manualmente, la validación por biólogos expertos y el dataset enriquecido para análisis de biodiversidad.

---

## 📐 Formato Estándar de Respuesta
Todas las respuestas siguen la estructura:
```json
{
  "status": "success",
  "data": { ... } | [ ... ] | null,
  "message": "Descripción de la operación"
}
```

---

## 1. Listar Detecciones de Especies (`GET /species/`)
- **Ruta:** `GET /species/`
- **Parámetros Query:** `skip` *(default 0)*, `limit` *(default 100)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
    {
      "id": 101,
      "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
      "media_file_id": "m1febc99-9c0b-4ef8-bb6d-6bb9bd380a77",
      "common_name": "Jaguar",
      "scientific_name": "Panthera onca",
      "family": "Felidae",
      "genus": "Panthera",
      "confidence_score": 0.94,
      "detection_timestamp": "2026-08-10T14:30:05Z",
      "url_img": "http://localhost:8080/crops/detection_101.jpg",
      "is_verified": true,
      "created_at": "2026-08-18T00:00:00Z",
      "is_deleted": false
    }
  ],
  "message": "Detecciones de especies obtenidas exitosamente"
}
```

---

## 2. Dataset Enriquecido de Especies (`GET /species/data`)
- **Ruta:** `GET /species/data`
- **Descripción:** Endpoint avanzado que calcula e integra variables ambientales, meteorológicas y astronómicas para cada registro de detección:
  - **Periodo del día:** Matutino, Vespertino, Nocturno, Crepuscular.
  - **Temperatura media:** Consulta histórica en tiempo real utilizando la API de **Open-Meteo**.
  - **Cálculos espacio-temporales:** Minutos desde la última detección, distancia Haversine (km) entre estaciones consecutivas y velocidad estimada (km/h).
  - **Fase lunar y Periodo Weckel:** Datos astronómicos calculados para estudios de actividad.

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": [
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
  ],
  "message": "Dataset enriquecido obtenido exitosamente"
}
```

---

## 3. Obtener Detección por ID (`GET /species/{id}`)
- **Ruta:** `GET /species/{species_id}`
- **Parámetros Path:** `species_id` *(int)*

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": 101,
    "station_id": "c1febc99-9c0b-4ef8-bb6d-6bb9bd380a33",
    "common_name": "Jaguar",
    "scientific_name": "Panthera onca",
    "family": "Felidae",
    "genus": "Panthera",
    "confidence_score": 0.94,
    "is_verified": true
  },
  "message": "Detección de especie obtenida exitosamente"
}
```

---

## 4. Verificación Humana Experta (`POST /species/{id}/verify`)
- **Ruta:** `POST /species/{species_id}/verify`
- **Autenticación:** Requiere `Authorization: Bearer <access_token>`

### Request Body `VerifyRequest`
```json
{
  "verified": true
}
```

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": 101,
    "common_name": "Jaguar",
    "is_verified": true,
    "updated_at": "2026-08-18T01:00:00Z"
  },
  "message": "Estado de verificación actualizado exitosamente"
}
```
