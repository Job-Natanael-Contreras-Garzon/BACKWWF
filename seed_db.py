import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db.session import async_session_maker
from app.core.security import get_password_hash
from app.models import (
    User,
    Project,
    CameraStation,
    ProjectStation,
    MediaFile,
    Video,
    Species,
)

# (family, genus, scientific_name, common_name)
ESPECIES_MOCK = [
    ("Felidae", "Panthera", "Panthera onca", "Jaguar"),
    ("Felidae", "Puma", "Puma concolor", "Puma"),
    ("Felidae", "Leopardus", "Leopardus pardalis", "Ocelot"),
    ("Tapiridae", "Tapirus", "Tapirus terrestris", "Brazilian tapir"),
    ("Tayassuidae", "Dicotyles", "Dicotyles tajacu", "Collared peccary"),
    ("Myrmecophagidae", "Myrmecophaga", "Myrmecophaga tridactyla", "Giant anteater"),
    ("Caviidae", "Hydrochoerus", "Hydrochoerus hydrochaeris", "Capybara"),
    ("Atelidae", "Alouatta", "Alouatta caraya", "Black howler monkey"),
]


async def seed_data():
    print("Iniciando seeder...")
    async with async_session_maker() as session:
        # 1. Crear o recuperar usuario de prueba con contraseña real (bcrypt)
        result = await session.execute(select(User).where(User.email == "admin@wwf.org"))
        user = result.scalar_one_or_none()

        if not user:
            print("Creando usuario de prueba (admin@wwf.org / wwf123456)...")
            user = User(
                full_name="Dr. Jane Goodall",
                email="admin@wwf.org",
                hashed_password=get_password_hash("wwf123456"),
                institucion="WWF",
                sexo="F",
                is_active=True,
            )
            session.add(user)
            await session.flush()

        # 2. Crear un proyecto
        print("Creando proyecto de monitoreo...")
        project = Project(
            user_id=user.id,
            title="Monitoreo de Fauna - Amazonia 2026",
            description="Proyecto de prueba para validar indicadores ecológicos.",
            status="public",
        )
        session.add(project)
        await session.flush()

        # 3. Crear o reutilizar 3 Estaciones de Cámara y asociarlas en project_stations (N:M)
        print("Configurando cámaras trampa...")
        cam_data = [
            {"code": "CAM-01", "lat": -16.401, "lon": -61.405},
            {"code": "CAM-02", "lat": -16.415, "lon": -61.420},
            {"code": "CAM-03", "lat": -16.390, "lon": -61.380},
        ]

        stations = []
        for c in cam_data:
            existing_station = (
                await session.execute(
                    select(CameraStation).where(CameraStation.station_code == c["code"])
                )
            ).scalar_one_or_none()

            if existing_station:
                station = existing_station
            else:
                station = CameraStation(
                    project_id=project.id,
                    user_id=user.id,
                    station_code=c["code"],
                    location_name=f"Sector {c['code']}",
                    latitude=c["lat"],
                    longitude=c["lon"],
                    camera_brand="Browning",
                    status="active",
                )
                session.add(station)
                await session.flush()

            session.add(ProjectStation(project_id=project.id, station_id=station.id))
            stations.append(station)

        await session.flush()

        # 4. Generar MediaFiles, Videos y Detecciones (Species)
        print("Generando detecciones simuladas...")
        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        for i in range(60):
            station = random.choice(stations)
            family, genus, sci_name, common_name = random.choice(ESPECIES_MOCK)

            detection_time = start_date + timedelta(
                days=random.randint(0, 60),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            file_url = f"/uploads/videos/video_{uuid.uuid4().hex[:8]}.mp4"
            duration = random.randint(10, 60)
            size_mb = round(random.uniform(5.0, 50.0), 2)

            media = MediaFile(
                station_id=station.id,
                file_type="video",
                file_url=file_url,
                original_filename=f"clip_{i + 1:03d}.mp4",
                duration_seconds=duration,
                file_size_mb=size_mb,
                capture_date=detection_time,
            )
            video = Video(
                station_id=station.id,
                file_url=file_url,
                original_filename=media.original_filename,
                duration_seconds=duration,
                file_size_mb=size_mb,
                capture_date=detection_time,
            )
            session.add_all([media, video])
            await session.flush()

            session.add(
                Species(
                    station_id=station.id,
                    media_file_id=media.id,
                    video_id=video.id,
                    family=family,
                    genus=genus,
                    scientific_name=sci_name,
                    common_name=common_name,
                    confidence_score=round(random.uniform(0.70, 0.99), 4),
                    detection_timestamp=detection_time,
                    is_verified=random.choice([True, False, None]),
                )
            )

            # Simular eventos dependientes (ráfagas < 30 min)
            if random.random() < 0.3:
                for b in range(random.randint(1, 3)):
                    burst_time = detection_time + timedelta(minutes=random.randint(1, 15))
                    burst_url = f"/uploads/videos/video_burst_{uuid.uuid4().hex[:8]}.mp4"

                    media_burst = MediaFile(
                        station_id=station.id,
                        file_type="video",
                        file_url=burst_url,
                        original_filename=f"burst_{i + 1:03d}_{b + 1}.mp4",
                        duration_seconds=15,
                        file_size_mb=8.5,
                        capture_date=burst_time,
                    )
                    video_burst = Video(
                        station_id=station.id,
                        file_url=burst_url,
                        original_filename=media_burst.original_filename,
                        duration_seconds=15,
                        capture_date=burst_time,
                    )
                    session.add_all([media_burst, video_burst])
                    await session.flush()

                    session.add(
                        Species(
                            station_id=station.id,
                            media_file_id=media_burst.id,
                            video_id=video_burst.id,
                            family=family,
                            genus=genus,
                            scientific_name=sci_name,
                            common_name=common_name,
                            confidence_score=round(random.uniform(0.70, 0.99), 4),
                            detection_timestamp=burst_time,
                            is_verified=True,
                        )
                    )

        await session.commit()
        print("¡Seeding completado con éxito! Login: admin@wwf.org / wwf123456")


if __name__ == "__main__":
    asyncio.run(seed_data())