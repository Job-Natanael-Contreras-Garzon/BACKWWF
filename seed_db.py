import asyncio
import uuid
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models import User, Project, CameraStation, Video, Species

# Especies de prueba con diferentes nombres para enriquecer diversidad
ESPECIES_MOCK = [
    "Jaguar", "Puma", "Ocelot", "Brazilian tapir", "Collared peccary", 
    "Giant anteater", "Capybara", "Black howler monkey"
]

async def seed_data():
    print("Iniciando seeder...")
    async with async_session_maker() as session:
        # 1. Crear o recuperar un usuario
        result = await session.execute(select(User).limit(1))
        user = result.scalars().first()
        
        if not user:
            print("Creando usuario de prueba...")
            user = User(
                full_name="Dr. Jane Goodall",
                email=f"jane.goodall.{random.randint(100,999)}@wwf.org",
                institucion="WWF",
                sexo="F"
            )
            session.add(user)
            await session.flush()
        
        # 2. Crear un proyecto
        print("Creando proyecto de monitoreo...")
        project = Project(
            user_id=user.id,
            title="Monitoreo de Fauna - Amazonia 2025",
            description="Proyecto de prueba para validar indicadores ecológicos.",
            status="public"
        )
        session.add(project)
        await session.flush()
        
        # 3. Crear 3 Estaciones de Cámara con coordenadas realistas
        print("Instalando cámaras trampa...")
        cam_data = [
            {"code": "CAM-01", "lat": -16.401, "lon": -61.405},
            {"code": "CAM-02", "lat": -16.415, "lon": -61.420},
            {"code": "CAM-03", "lat": -16.390, "lon": -61.380},
        ]
        
        stations = []
        for c in cam_data:
            station = CameraStation(
                project_id=project.id,
                station_code=c["code"],
                location_name=f"Sector {c['code']}",
                latitude=c["lat"],
                longitude=c["lon"],
                camera_brand="Browning",
                status="active"
            )
            session.add(station)
            stations.append(station)
            
        await session.flush()
        
        # 4. Generar Detecciones (Species) + Videos
        print("Generando detecciones simuladas...")
        start_date = datetime(2025, 1, 1)
        
        for _ in range(80):
            # Seleccionar cámara aleatoria y especie aleatoria
            station = random.choice(stations)
            especie = random.choice(ESPECIES_MOCK)
            
            # Fecha aleatoria dentro de los primeros 60 días del año
            days_offset = random.randint(0, 60)
            hours_offset = random.randint(0, 23)
            mins_offset = random.randint(0, 59)
            
            detection_time = start_date + timedelta(days=days_offset, hours=hours_offset, minutes=mins_offset)
            
            # Crear Video
            video = Video(
                station_id=station.id,
                file_url=f"s3://fake-bucket/video_{uuid.uuid4().hex[:8]}.mp4",
                duration_seconds=random.randint(10, 60),
                file_size_mb=random.uniform(5.0, 50.0),
                capture_date=detection_time
            )
            session.add(video)
            await session.flush()
            
            # Crear Especie (Detección IA)
            species_det = Species(
                station_id=station.id,
                video_id=video.id,
                common_name=especie,
                confidence_score=round(random.uniform(0.70, 0.99), 2),
                detection_timestamp=detection_time,
                is_verified=random.choice([True, False, None])
            )
            session.add(species_det)
            
            # SIMULAR EVENTOS DEPENDIENTES (Ráfagas de la misma especie en la misma cámara)
            # Hay un 30% de probabilidad de que el animal se quede frente a la cámara
            if random.random() < 0.3:
                for burst in range(random.randint(1, 3)):
                    burst_time = detection_time + timedelta(minutes=random.randint(1, 15)) # Menos de 30 min para ser dependiente
                    video_burst = Video(
                        station_id=station.id,
                        file_url=f"s3://fake-bucket/video_burst_{uuid.uuid4().hex[:8]}.mp4",
                        duration_seconds=15,
                        capture_date=burst_time
                    )
                    session.add(video_burst)
                    await session.flush()
                    
                    sp_burst = Species(
                        station_id=station.id,
                        video_id=video_burst.id,
                        common_name=especie, # Misma especie
                        confidence_score=round(random.uniform(0.70, 0.99), 2),
                        detection_timestamp=burst_time,
                        is_verified=True
                    )
                    session.add(sp_burst)

        await session.commit()
        print("¡Seeding completado con éxito! Se han insertado datos de prueba.")

if __name__ == "__main__":
    asyncio.run(seed_data())