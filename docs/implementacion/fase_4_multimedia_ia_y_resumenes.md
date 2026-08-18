# 📘 Fase 4: Multimedia (Video/Imagen), IA y Resúmenes Estadísticos

## 🎯 Objetivo de la Fase
Expandir la capacidad de subida de archivos para aceptar tanto **Videos** como **Imágenes** (`POST /camera-stations/{id}/files`), procesar las detecciones con IA parseando automáticamente la taxonomía (`Familia`, `Género`, `Nombre Científico`, `Nombre Común`), y generar los endpoints de resumen estadístico por estación (`GET /camera-stations/{id}/summary`) y por proyecto (`GET /projects/{id}/summary`).

---

## 🛠️ Archivos a Crear / Modificar

| Acción | Archivo | Descripción |
| :--- | :--- | :--- |
| **[NEW]** | `app/models/media_file.py` | Modelo ORM `MediaFile` (videos e imágenes) |
| **[MODIFY]** | `app/models/species.py` | Campos `family` y `genus` en la tabla `species` |
| **[NEW]** | `app/api/v1/media_files.py` | Router para subida de medios `POST /camera-stations/{id}/files` |
| **[MODIFY]** | `app/api/v1/camera_stations.py` | Endpoint `GET /camera-stations/{id}/summary` |
| **[MODIFY]** | `app/api/v1/projects.py` | Endpoint `GET /projects/{id}/summary` |

---

## 📝 Instrucciones Paso a Paso

### 1. Modelo `MediaFile` (`app/models/media_file.py`)

```python
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import BaseEntity

class MediaFile(BaseEntity):
    __tablename__ = "media_files"

    station_id = Column(UUID(as_uuid=True), ForeignKey("camera_stations.id", ondelete="CASCADE"), nullable=False)
    file_type = Column(String, nullable=False)  # "video" | "image"
    file_url = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    file_size_mb = Column(Numeric(10, 2), nullable=True)
    capture_date = Column(DateTime(timezone=True), nullable=True)
    metadata_extra = Column(JSON, nullable=True)
```

---

### 2. Actualización de `Species` (`app/models/species.py`)

Añadir los campos `family` y `genus` a la tabla `species`:

```python
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import BaseEntity

class Species(BaseEntity):
    __tablename__ = "species"

    id = Column(Integer, primary_key=True, autoincremental=True)
    station_id = Column(UUID(as_uuid=True), ForeignKey("camera_stations.id"), nullable=False)
    media_file_id = Column(UUID(as_uuid=True), ForeignKey("media_files.id"), nullable=True)
    
    common_name = Column(String, index=True, nullable=False)
    scientific_name = Column(String, nullable=True)
    family = Column(String, nullable=True, index=True)
    genus = Column(String, nullable=True, index=True)
    
    confidence_score = Column(Numeric(5, 4), nullable=True)
    detection_timestamp = Column(DateTime(timezone=True), nullable=True)
    url_img = Column(String, nullable=True)
    is_verified = Column(Boolean, nullable=True)
```

---

### 3. Parsing Taxonómico Automático desde la IA (`app/services/ai_service.py` / `media_files.py`)

Cuando el servicio externo de IA responde con las detecciones, el formato puede ser del tipo `"Felidae;Panthera;Panthera onca;Jaguar"` o `"Panthera;onca;Jaguar"`.

Implementar la función de parsing:
```python
def parse_taxonomy(species_raw: str):
    """
    Parsea una cadena de especie delimitada por punto y coma ';'.
    Ejemplo 1: 'Felidae;Panthera;Panthera onca;Jaguar' -> family='Felidae', genus='Panthera', scientific_name='Panthera onca', common_name='Jaguar'
    Ejemplo 2: 'Panthera;onca;Jaguar' -> family=None, genus='Panthera', scientific_name='Panthera onca', common_name='Jaguar'
    """
    parts = [p.strip() for p in species_raw.split(";") if p.strip()]
    
    if len(parts) >= 4:
        return {
            "family": parts[0],
            "genus": parts[1],
            "scientific_name": parts[2],
            "common_name": parts[3]
        }
    elif len(parts) == 3:
        return {
            "family": None,
            "genus": parts[0],
            "scientific_name": f"{parts[0]} {parts[1]}",
            "common_name": parts[2]
        }
    elif len(parts) == 2:
        return {
            "family": None,
            "genus": parts[0],
            "scientific_name": f"{parts[0]} {parts[1]}",
            "common_name": parts[1]
        }
    else:
        return {
            "family": None,
            "genus": None,
            "scientific_name": None,
            "common_name": species_raw
        }
```

---

### 4. Endpoint de Subida Multimedia (`POST /camera-stations/{id}/files`)

```python
@router.post("/{station_id}/files")
async def upload_station_file(
    station_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    # Detectar si es video o imagen por content_type
    content_type = file.content_type or ""
    file_type = "video" if "video" in content_type else "image"
    
    # Guardar archivo localmente
    upload_dir = os.path.abspath(f"uploads/{file_type}s")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{uuid.uuid4().hex[:8]}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
    
    # Crear registro MediaFile
    media_in = MediaFile(
        station_id=station_id,
        file_type=file_type,
        file_url=file_path,
        original_filename=file.filename,
        file_size_mb=file_size_mb
    )
    db.add(media_in)
    await db.commit()
    await db.refresh(media_in)
    
    # Enviar a IA y guardar detecciones parseando taxonomía
    ai_response = await analyze_video_with_external_ai(file_path)
    for result in ai_response.get("results", []):
        for detection in result.get("detections", []):
            tax = parse_taxonomy(detection["species"])
            sp = Species(
                station_id=station_id,
                media_file_id=media_in.id,
                common_name=tax["common_name"],
                scientific_name=tax["scientific_name"],
                family=tax["family"],
                genus=tax["genus"],
                confidence_score=detection.get("confidence"),
                url_img=detection.get("crop_url")
            )
            db.add(sp)
    await db.commit()
    
    return StandardResponse(
        message=f"Archivo {file_type} subido y procesado exitosamente",
        data={"media_file_id": str(media_in.id), "file_type": file_type, "file_url": file_path}
    )
```

---

### 5. Resúmenes Estadísticos Agregados

#### A. Resumen por Estación (`GET /camera-stations/{id}/summary`)
Devuelve:
- Total de archivos procesados (`videos` e `imágenes`).
- Cantidad de especies distintas.
- Desglose de frecuencia por **Especie**, **Familia** y **Género**.

```python
@router.get("/{station_id}/summary")
async def get_station_summary(station_id: UUID, db: AsyncSession = Depends(get_db)):
    # Conteo de especies, familias y géneros
    species_stmt = (
        select(Species.common_name, func.count(Species.id))
        .where(Species.station_id == station_id, Species.is_deleted == False)
        .group_by(Species.common_name)
    )
    family_stmt = (
        select(Species.family, func.count(Species.id))
        .where(Species.station_id == station_id, Species.family != None, Species.is_deleted == False)
        .group_by(Species.family)
    )
    genus_stmt = (
        select(Species.genus, func.count(Species.id))
        .where(Species.station_id == station_id, Species.genus != None, Species.is_deleted == False)
        .group_by(Species.genus)
    )
    
    sp_res = (await db.execute(species_stmt)).all()
    fam_res = (await db.execute(family_stmt)).all()
    gen_res = (await db.execute(genus_stmt)).all()
    
    return StandardResponse(
        message="Resumen estadístico de la estación obtenido exitosamente",
        data={
            "station_id": str(station_id),
            "distinct_species_count": len(sp_res),
            "frequency_by_species": [{"species": row[0], "count": row[1]} for row in sp_res],
            "frequency_by_family": [{"family": row[0], "count": row[1]} for row in fam_res],
            "frequency_by_genus": [{"genus": row[0], "count": row[1]} for row in gen_res]
        }
    )
```

#### B. Resumen por Proyecto (`GET /projects/{id}/summary`)
Suma y agrega las detecciones de **todas las estaciones vinculadas** al proyecto (vía la tabla N:M `project_stations`).

---

## ✅ Criterios de Aceptación de la Fase 4
- `POST /camera-stations/{id}/files` procesa correctamente archivos `.mp4`, `.jpg`, `.png`.
- Las detecciones de IA completan automáticamente los campos `family` y `genus`.
- `GET /camera-stations/{id}/summary` y `GET /projects/{id}/summary` retornan el conteo y desglose taxonómico.
