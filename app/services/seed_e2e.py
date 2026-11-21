"""HU-16 · Semilla determinista para las pruebas E2E del front (``DEP-04``, Playwright).

Crea siempre lo mismo: un admin, dos investigadores, cámaras pública y privada, un proyecto,
clasificaciones de fauna (con fotograma), vacías, con error y una ya validada. Nunca corre en
producción y es idempotente: si la semilla ya está, no hace nada.
"""

import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from PIL import Image

from app.core.config import settings
from app.core.enums import (
    BatchSource,
    BatchStatus,
    CaptureSource,
    Category,
    ClassificationStatus,
    EnvironmentMode,
    MediaType,
    UserRole,
    ValidationStatus,
    Visibility,
)
from app.core.errors import ForbiddenError
from app.core.security import get_password_hash, hash_token
from app.db.uow import UnitOfWork
from app.integrations.storage.base import StorageBackend
from app.models.camera_station import CameraStation
from app.models.classification import Classification, ClassificationBatch
from app.models.project import Project, ProjectCameraStation
from app.models.user import User
from app.services.catalog_service import get_catalog
from app.services.evidence import evidence_key

ADMIN_EMAIL = "admin@e2e.example.com"
USERS = (("ana@e2e.example.com", "Ana Rojas"), ("beto@e2e.example.com", "Beto Paz"))
# Lat/lng de la Chiquitania; fijas para que las capturas de pantalla no cambien.
CAMERAS = (
    ("E2E-PUB-01", "Quebrada pública", Visibility.PUBLIC, "-16.381234", "-60.962345"),
    ("E2E-PRI-01", "Salitral privado", Visibility.PRIVATE, "-16.402211", "-60.981133"),
)
FAUNA = (("Panthera onca", 6), ("Puma concolor", 4), ("Tapirus terrestris", 3))
BASE_TIME = datetime(2026, 3, 1, 21, 0)
PER_CAMERA = sum(n for _, n in FAUNA) + 2  # + una vacía y una con error


@dataclass(frozen=True, slots=True)
class SeedResult:
    status: str
    users: int = 0
    camera_stations: int = 0
    classifications: int = 0


def _jpeg(seed: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (40 + seed * 17 % 200, 90, 60)).save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _taxon(name: str) -> dict[str, Any]:
    t = get_catalog().search(name, limit=1)[0]
    return {
        "label_id": t.label_id,
        "rank": t.rank,
        "class_": t.class_,
        "order_": t.order,
        "family": t.family,
        "genus": t.genus,
        "species": t.species,
        "scientific_name": t.scientific_name,
        "common_name": t.common_name,
    }


async def seed(uow: UnitOfWork, storage: StorageBackend, password: str) -> SeedResult:
    if settings.ENVIRONMENT == EnvironmentMode.PRODUCTION:
        raise ForbiddenError("FORBIDDEN", "seed-e2e no corre en producción.")
    if await uow.users.get_by_email(ADMIN_EMAIL) is not None:
        return SeedResult(status="already_seeded")

    password_hash = get_password_hash(password)
    uow.users.add(
        User(
            email=ADMIN_EMAIL,
            password_hash=password_hash,
            full_name="Admin E2E",
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    people = [
        uow.users.add(
            User(
                email=email,
                password_hash=password_hash,
                full_name=name,
                role=UserRole.USER,
                is_active=True,
            )
        )
        for email, name in USERS
    ]
    await uow.session.flush()
    ana = people[0]

    cameras = []
    for code, name, visibility, lat, lng in CAMERAS:
        camera = CameraStation(
            code=code,
            name=name,
            visibility=visibility,
            latitude=Decimal(lat),
            longitude=Decimal(lng),
            deployed_at=BASE_TIME - timedelta(days=10),
            still_installed=True,
            owner_user_id=ana.id,
        )
        uow.session.add(camera)
        cameras.append(camera)
    project = Project(
        name="Monitoreo Chiquitania E2E", visibility=Visibility.PUBLIC, owner_user_id=ana.id
    )
    uow.session.add(project)
    await uow.session.flush()
    uow.session.add(ProjectCameraStation(project_id=project.id, camera_station_id=cameras[0].id))

    files: list[tuple[str, bytes]] = []
    count = 0
    for camera in cameras:
        batch = ClassificationBatch(
            camera_station_id=camera.id,
            source=BatchSource.WEB,
            status=BatchStatus.COMPLETED,
            expected_files=PER_CAMERA,
            total=PER_CAMERA,
            done=PER_CAMERA - 1,
            failed=1,
            closed_at=datetime.now(UTC),
            owner_user_id=ana.id,
        )
        uow.session.add(batch)
        await uow.session.flush()
        rows: list[Classification] = []
        for name, n in FAUNA:
            for i in range(n):
                rows.append(
                    Classification(
                        id=uuid.uuid4(),
                        category=Category.ANIMAL,
                        confidence=Decimal("0.91"),
                        **_taxon(name),
                        file_name=f"{name.split()[0].lower()}_{i:02d}.jpg",
                    )
                )
        rows.append(
            Classification(
                id=uuid.uuid4(),
                category=Category.BLANK,
                confidence=Decimal("0.97"),
                file_name="vacia_00.jpg",
            )
        )
        rows.append(
            Classification(
                id=uuid.uuid4(),
                status=ClassificationStatus.ERROR,
                error_code="MEDIA_DECODE_FAILED",
                file_name="danada_00.jpg",
            )
        )
        for i, row in enumerate(rows):
            when = BASE_TIME + timedelta(hours=i * 7)
            row.camera_station_id, row.batch_id, row.owner_user_id = camera.id, batch.id, ana.id
            row.file_sha256 = hash_token(f"e2e-{camera.code}-{row.file_name}")
            row.file_size_bytes, row.media_type = 2048, MediaType.IMAGE
            row.captured_at, row.captured_at_source = when, CaptureSource.EXIF
            if row.status is None:
                row.status = ClassificationStatus.DONE
            if row.category == Category.ANIMAL:
                row.evidence_key = evidence_key(row.id, datetime(2026, 3, 1, tzinfo=UTC))
                row.evidence_frame_index, row.evidence_timestamp_seconds = 0, 0.0
                files.append((row.evidence_key, _jpeg(i)))
        rows[0].validation_status = ValidationStatus.CONFIRMED
        uow.session.add_all(rows)
        count += len(rows)

    for key, data in files:  # primero los archivos, luego las filas (§ almacenamiento)
        await storage.put(key, data, "image/jpeg")
    await uow.commit()
    return SeedResult(
        status="seeded", users=len(people) + 1, camera_stations=len(cameras), classifications=count
    )
