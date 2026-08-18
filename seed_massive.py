import asyncio
import uuid
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models import User, Project, CameraStation, Video, Species

ESPECIES_MOCK = [
    "Jaguar", "Puma", "Ocelot", "Brazilian tapir", "Collared peccary", 
    "Giant anteater", "Capybara", "Black howler monkey", "Tayra", 
    "White-nosed coati", "Pampas deer", "Giant armadillo"
]

async def seed_data():
    print("Iniciando seeder masivo...")
    async with async_session_maker() as session:
        # 1. Recuperar proyecto existente o crear uno
        result = await session.execute(select(Project).limit(1))
        project = result.scalars().first()
        
        if not project:
            print("No se encontró proyecto, creando...")
            result = await session.execute(select(User).limit(1))
            user = result.scalars().first()
            if not user:
                user = User(full_name="Dr. Masivo", email="masivo@wwf.org", institucion="WWF")
                session.add(user)
                await session.flush()
            project = Project(user_id=user.id, title="Monitoreo Masivo 2025", status="public")
            session.add(project)
            await session.flush()
            
        # 2. Crear más estaciones (20 en total)
        print("Instalando 20 cámaras trampa adicionales...")
        stations = []
        for i in range(1, 21):
            station = CameraStation(
                project_id=project.id,
                station_code=f"CAM-M{i:02d}",
                location_name=f"Sector Masivo {i:02d}",
                latitude=round(-16.4 + random.uniform(-0.1, 0.1), 5),
                longitude=round(-61.4 + random.uniform(-0.1, 0.1), 5),
                camera_brand="Reconyx",
                status="active"
            )
            session.add(station)
            stations.append(station)
        await session.flush()
        
        # 3. Generar Detecciones Masivas
        print("Generando miles de detecciones simuladas...")
        start_date = datetime(2025, 1, 1)
        
        total_creados = 0
        
        # Vamos a generar 2500 eventos principales. Con ráfagas, llegarán a ~4500.
        for i in range(2500):
            station = random.choice(stations)
            especie = random.choice(ESPECIES_MOCK)
            
            # Fecha a lo largo de todo el año
            days_offset = random.randint(0, 360)
            hours_offset = random.randint(0, 23)
            mins_offset = random.randint(0, 59)
            
            detection_time = start_date + timedelta(days=days_offset, hours=hours_offset, minutes=mins_offset)
            
            video = Video(
                station_id=station.id,
                file_url=f"s3://fake-bucket/m_video_{uuid.uuid4().hex[:8]}.mp4",
                duration_seconds=random.randint(10, 60),
                file_size_mb=round(random.uniform(5.0, 50.0), 2),
                capture_date=detection_time
            )
            session.add(video)
            await session.flush()  # flush needed to get video.id
            
            species_det = Species(
                station_id=station.id,
                video_id=video.id,
                common_name=especie,
                confidence_score=round(random.uniform(0.70, 0.99), 4),
                detection_timestamp=detection_time,
                is_verified=random.choice([True, False, None])
            )
            session.add(species_det)
            total_creados += 1
            
            # SIMULAR EVENTOS DEPENDIENTES (30% prob)
            if random.random() < 0.30:
                for burst in range(random.randint(1, 4)):
                    burst_time = detection_time + timedelta(minutes=random.randint(1, 15))
                    video_burst = Video(
                        station_id=station.id,
                        file_url=f"s3://fake-bucket/m_burst_{uuid.uuid4().hex[:8]}.mp4",
                        duration_seconds=15,
                        capture_date=burst_time
                    )
                    session.add(video_burst)
                    await session.flush()
                    
                    sp_burst = Species(
                        station_id=station.id,
                        video_id=video_burst.id,
                        common_name=especie,
                        confidence_score=round(random.uniform(0.70, 0.99), 4),
                        detection_timestamp=burst_time,
                        is_verified=True
                    )
                    session.add(sp_burst)
                    total_creados += 1
            
            # Hacer commit cada 250 eventos principales para no saturar memoria
            if i % 250 == 0 and i > 0:
                await session.commit()
                print(f"Progreso: ~{total_creados} registros creados...")

        await session.commit()
        print(f"¡Seeding masivo completado! Total de registros creados: {total_creados}")

if __name__ == "__main__":
    asyncio.run(seed_data())