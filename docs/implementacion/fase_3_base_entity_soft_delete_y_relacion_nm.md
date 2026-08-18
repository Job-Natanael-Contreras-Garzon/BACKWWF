# 📘 Fase 3: BaseEntity, Soft Delete y Relación N:M (Proyectos - Estaciones)

## 🎯 Objetivo de la Fase
Estandarizar todos los modelos ORM con la clase base **`BaseEntity`** (`id`, `created_at`, `updated_at`, `is_deleted`, `deleted_at`), implementar el borrado lógico (**Soft Delete**) reforzado con la regla estricta de autorización (error HTTP 403 para recursos anónimos), e implementar la relación **Muchos a Muchos (N:M)** entre Proyectos y Estaciones de Cámaras Trapa.

---

## 🛠️ Archivos a Crear / Modificar

| Acción | Archivo | Descripción |
| :--- | :--- | :--- |
| **[MODIFY]** | `app/models/base.py` | Definición de `BaseEntity` mixin con campos auditados y borrado lógico |
| **[NEW]** | `app/models/project_station.py` | Modelo de la tabla intermedia `project_stations` (N:M) |
| **[MODIFY]** | `app/models/project.py` | Refactor a `BaseEntity` y relación N:M |
| **[MODIFY]** | `app/models/camera_station.py` | Refactor a `BaseEntity` y relación N:M |
| **[MODIFY]** | `app/api/v1/camera_stations.py` | Reglas de Soft Delete (403 anónimo) y CRUD estandarizado |
| **[MODIFY]** | `app/api/v1/projects.py` | Reglas de Soft Delete, endpoints de asociación/desasociación N:M |

---

## 📝 Instrucciones Paso a Paso

### 1. Definición de `BaseEntity` (`app/models/base.py`)

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

DeclarativeBase = declarative_base()

class BaseEntity(DeclarativeBase):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
```

---

### 2. Tabla Intermedia N:M (`app/models/project_station.py`)

```python
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import BaseEntity

class ProjectStation(BaseEntity):
    __tablename__ = "project_stations"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    station_id = Column(UUID(as_uuid=True), ForeignKey("camera_stations.id", ondelete="CASCADE"), primary_key=True)
```

---

### 3. Reglas de Negocio para Soft Delete (Borrado Lógico)

#### Regla de Oro:
1. **Borrado Físico Prohibido:** Ningún endpoint `DELETE` ejecutará un `SQL DELETE`.
2. **Requisito de Usuario Autenticado:** Para eliminar un Proyecto o Estación se **requiere token de usuario autenticado**.
3. **Bloqueo a Recurso Anónimo (Error 403):** Si el recurso a eliminar tiene `user_id IS NULL` (fue creado anónimamente y aún no se reclama):
   ```python
   if resource.user_id is None:
       raise HTTPException(
           status_code=status.HTTP_403_FORBIDDEN,
           detail="No se pueden eliminar elementos anónimos. Inicie sesión y reclame el recurso para poder eliminarlo."
       )
   ```
4. **Validación de Propietario:** Si `resource.user_id != current_user.id`, responde con HTTP 403 Forbidden.

#### Ejemplo de implementación en `DELETE /camera-stations/{id}`:
```python
@router.delete("/{station_id}")
async def delete_camera_station(
    station_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(CameraStation).where(CameraStation.id == station_id, CameraStation.is_deleted == False))
    station = result.scalar_one_or_none()
    
    if not station:
        raise HTTPException(status_code=404, detail="Estación de cámara no encontrada.")
        
    # Validación 1: Si es anónima, se requiere reclamo previo
    if station.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden eliminar elementos anónimos. Inicie sesión y reclame el recurso primero."
        )
        
    # Validación 2: Verificar que sea el propietario
    if station.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para eliminar esta estación de cámara."
        )
        
    # Ejecutar Soft Delete
    station.is_deleted = True
    station.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    
    return StandardResponse(message="Estación eliminada exitosamente (Soft Delete)", data=None)
```

---

### 4. Endpoints N:M entre Proyectos y Estaciones (`app/api/v1/projects.py`)

#### 1. Asociar Estación Existente a Proyecto (`POST /projects/{id}/stations`)
```python
class AssociateStationSchema(BaseModel):
    station_id: UUID

@router.post("/{project_id}/stations")
async def associate_station_to_project(
    project_id: UUID,
    data: AssociateStationSchema,
    db: AsyncSession = Depends(get_db)
):
    # Validar existencia de proyecto y estación no eliminados
    p_res = await db.execute(select(Project).where(Project.id == project_id, Project.is_deleted == False))
    project = p_res.scalar_one_or_none()
    if not project: raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    s_res = await db.execute(select(CameraStation).where(CameraStation.id == data.station_id, CameraStation.is_deleted == False))
    station = s_res.scalar_one_or_none()
    if not station: raise HTTPException(status_code=404, detail="Estación de cámara no encontrada.")

    # Verificar si ya están asociados
    ps_res = await db.execute(select(ProjectStation).where(ProjectStation.project_id == project_id, ProjectStation.station_id == data.station_id))
    existing = ps_res.scalar_one_or_none()
    
    if existing:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
            await db.commit()
        return StandardResponse(message="Estación asociada al proyecto exitosamente")
        
    new_ps = ProjectStation(project_id=project_id, station_id=data.station_id)
    db.add(new_ps)
    await db.commit()
    
    return StandardResponse(message="Estación asociada al proyecto exitosamente", data={"project_id": str(project_id), "station_id": str(data.station_id)})
```

#### 2. Desasociar Estación de Proyecto (`DELETE /projects/{id}/stations/{station_id}`)
```python
@router.delete("/{project_id}/stations/{station_id}")
async def disassociate_station_from_project(
    project_id: UUID,
    station_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    ps_res = await db.execute(select(ProjectStation).where(ProjectStation.project_id == project_id, ProjectStation.station_id == station_id, ProjectStation.is_deleted == False))
    ps = ps_res.scalar_one_or_none()
    
    if not ps:
        raise HTTPException(status_code=404, detail="La relación entre el proyecto y la estación no existe.")
        
    ps.is_deleted = True
    ps.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    
    return StandardResponse(message="Estación desasociada del proyecto exitosamente")
```

---

## ✅ Criterios de Aceptación de la Fase 3
- Todos los listados y consultas incluyen automáticamente el filtro `is_deleted == False`.
- `DELETE /camera-stations/{id}` y `DELETE /projects/{id}` devuelven error HTTP 403 si el recurso pertenece a un `anon_session_id`.
- Se puede asociar la misma estación a múltiples proyectos a través de `POST /projects/{id}/stations`.
