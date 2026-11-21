"""Cámaras trampa (HU-06): alta, lectura con privacidad DD-17, edición con If-Match, borrado en
cascada, cercanía y reinstalación (FL-05, FL-06, FL-13, FL-15; CB-01..CB-21)."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import ceil

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.enums import Visibility
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.geo import distance_band, haversine_m, in_bbox
from app.core.logging import log_step
from app.core.responses import ApiWarning, Pagination
from app.db.uow import UnitOfWork
from app.models.camera_station import CameraStation
from app.repositories.camera_stations import CameraAggregates, Scope, Sort
from app.schemas.camera_station import (
    CameraCounts,
    CameraStationCreate,
    CameraStationMapItem,
    CameraStationRead,
    CameraStationUpdate,
    NearbyData,
    NearbyMine,
    NearbyPublic,
    OwnerView,
    RedeployData,
    RedeployRequest,
)
from app.services.policies import Owner, is_owner, serialize_location

_NOT_FOUND_MSG = "La cámara no existe o no tienes acceso a ella."
_FUTURE_TOLERANCE = timedelta(days=1)
_SUFFIX = re.compile(r"-\d+$")
_COORDS = Decimal("0.000001")


def _now_local() -> datetime:
    """'Ahora' sin zona, para comparar con fechas locales de la cámara (con 1 día de margen)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _coord(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_COORDS)


def _invalid_dates(message: str) -> BusinessRuleError:
    return BusinessRuleError("CAMERA_INVALID_DATES", message)


def _validate_dates(
    deployed_at: datetime, still_installed: bool, retrieved_at: datetime | None
) -> None:
    limit = _now_local() + _FUTURE_TOLERANCE
    if deployed_at > limit or (retrieved_at is not None and retrieved_at > limit):
        raise _invalid_dates("La fecha no puede ser futura.")  # CB-12
    if still_installed and retrieved_at is not None:
        raise _invalid_dates("Si la cámara sigue instalada, no lleva fecha de retiro.")
    if not still_installed and retrieved_at is None:
        raise _invalid_dates("Indica la fecha de retiro de la cámara.")
    if retrieved_at is not None and retrieved_at < deployed_at:
        raise _invalid_dates("El retiro no puede ser anterior a la colocación.")  # CB-11


def _coords_warnings(lat: float, lng: float) -> list[ApiWarning]:
    """CB-07: solo 0,0 o lat/lng aparentemente invertidas. Fuera de Bolivia es válido."""
    bbox = settings.region_bbox
    suspicious = (lat == 0 and lng == 0) or (
        not in_bbox(lat, lng, bbox) and in_bbox(lng, lat, bbox)
    )
    if not suspicious:
        return []
    return [
        ApiWarning(
            code="CAMERA_COORDS_SUSPECT",
            message="Revisa las coordenadas: ¿latitud y longitud están invertidas?",
            context={"latitude": lat, "longitude": lng},
        )
    ]


def _check_visibility(owner: Owner, visibility: Visibility) -> None:
    if owner.is_anonymous and visibility == Visibility.PUBLIC:
        raise BusinessRuleError(
            "ANON_PUBLIC_NOT_ALLOWED", "Regístrate para publicar cámaras en el mapa."
        )


def _code_taken() -> ConflictError:
    return ConflictError("CAMERA_CODE_TAKEN", "Ya tienes una cámara con ese código.")


async def _ensure_code_free(
    uow: UnitOfWork, owner: Owner, code: str, exclude_id: uuid.UUID | None = None
) -> None:
    existing = await uow.camera_stations.find_active_by_code(owner, code)
    if existing is not None and existing.id != exclude_id:
        raise _code_taken()


async def _flush_or_code_taken(uow: UnitOfWork) -> None:
    """CB-14: si dos pestañas crean el mismo código a la vez, decide el índice único."""
    try:
        await uow.camera_stations.flush()
    except IntegrityError as exc:
        raise _code_taken() from exc


async def _anon_retain(uow: UnitOfWork, owner: Owner) -> bool:
    if not owner.is_anonymous:
        return False
    return bool(await uow.settings.get_value("anon_data_retention", True))


async def _check_anon_limit(uow: UnitOfWork, owner: Owner) -> None:
    if owner.is_anonymous and (
        await uow.camera_stations.count_active_for_owner(owner) >= settings.ANON_MAX_CAMERAS
    ):
        raise BusinessRuleError(
            "ANON_LIMIT_REACHED",
            f"Sin cuenta puedes registrar hasta {settings.ANON_MAX_CAMERAS} cámaras.",
            context={"limit": settings.ANON_MAX_CAMERAS},
        )


async def _owned_or_error(
    uow: UnitOfWork, owner: Owner, camera_id: uuid.UUID, *, for_update: bool = False
) -> CameraStation:
    """Propia → la devuelve; pública ajena → 403; privada ajena o inexistente → 404 (S1)."""
    camera = await uow.camera_stations.get_owned(camera_id, owner, for_update=for_update)
    if camera is not None:
        return camera
    if await uow.camera_stations.get_visible(camera_id, owner) is not None:
        raise ForbiddenError("FORBIDDEN", "Esta cámara no es tuya.")
    raise NotFoundError("CAMERA_NOT_FOUND", _NOT_FOUND_MSG)


async def _owner_views(
    uow: UnitOfWork, cameras: list[CameraStation], viewer: Owner | None
) -> dict[uuid.UUID, OwnerView]:
    user_ids = {c.owner_user_id for c in cameras if c.owner_user_id is not None}
    profiles = await uow.camera_stations.user_profiles(user_ids)
    views: dict[uuid.UUID, OwnerView] = {}
    for camera in cameras:
        mine = is_owner(camera, viewer)
        if camera.owner_user_id is None:
            views[camera.id] = OwnerView(type="anonymous", is_mine=mine)
            continue
        # §1.3: nombre e institución solo si el contenido es público o es tuyo.
        show = mine or camera.visibility == Visibility.PUBLIC
        name, institution = profiles.get(camera.owner_user_id, (None, None))
        views[camera.id] = OwnerView(
            type="user",
            is_mine=mine,
            display_name=name if show else None,
            institution=institution if show else None,
        )
    return views


async def _to_reads(
    uow: UnitOfWork, cameras: list[CameraStation], viewer: Owner | None
) -> list[CameraStationRead]:
    ids = [c.id for c in cameras]
    aggregates = await uow.camera_stations.aggregates(ids)
    project_ids = await uow.camera_stations.visible_project_ids(ids, viewer)
    owners = await _owner_views(uow, cameras, viewer)
    reads: list[CameraStationRead] = []
    for camera in cameras:
        lat, lng, precision = serialize_location(camera, viewer)
        agg = aggregates.get(camera.id, CameraAggregates())
        reads.append(
            CameraStationRead(
                id=camera.id,
                code=camera.code,
                name=camera.name,
                latitude=lat,
                longitude=lng,
                deployed_at=camera.deployed_at,
                retrieved_at=camera.retrieved_at,
                still_installed=camera.still_installed,
                observations=camera.observations,
                visibility=camera.visibility,
                owner=owners[camera.id],
                project_ids=project_ids.get(camera.id, []),
                counts=CameraCounts(
                    classifications=agg.classifications,
                    sightings=agg.sightings,
                    species=agg.species,
                    pending_validation=agg.pending_validation,
                ),
                last_capture_at=agg.last_capture_at,
                location_precision=precision,  # type: ignore[arg-type]
                previous_camera_station_id=camera.previous_camera_station_id,
                version=camera.version,
                created_at=camera.created_at,
                updated_at=camera.updated_at,
            )
        )
    return reads


async def _read_one(
    uow: UnitOfWork, camera: CameraStation, viewer: Owner | None
) -> CameraStationRead:
    return (await _to_reads(uow, [camera], viewer))[0]


async def list_cameras(
    uow: UnitOfWork,
    viewer: Owner | None,
    *,
    scope: Scope,
    view: str,
    page: int,
    page_size: int,
    sort: Sort,
    project_id: uuid.UUID | None,
    bbox: tuple[float, float, float, float] | None,
    q: str | None,
    still_installed: bool | None,
) -> tuple[list[CameraStationRead] | list[CameraStationMapItem], Pagination]:
    with log_step("camera.list"):
        if scope == "mine" and viewer is None:
            raise UnauthorizedError("AUTH_REQUIRED", "Debes iniciar sesión para ver tus cámaras.")
        if project_id is not None and await uow.projects.get_visible(project_id, viewer) is None:
            raise NotFoundError("PROJECT_NOT_FOUND", "El proyecto no existe o no tienes acceso.")
        is_map = view == "map"
        cameras, total = await uow.camera_stations.search(
            viewer,
            scope=scope,
            page=page,
            page_size=page_size,
            max_page_size=settings.MAP_PAGE_SIZE_MAX if is_map else 200,
            sort=sort,
            project_id=project_id,
            bbox=bbox,
            q=q,
            still_installed=still_installed,
        )
        effective_size = max(1, min(page_size, settings.MAP_PAGE_SIZE_MAX if is_map else 200))
        pagination = Pagination(
            page=max(page, 1),
            page_size=effective_size,
            total=total,
            total_pages=ceil(total / effective_size) if total else 0,
        )
        if not is_map:
            return await _to_reads(uow, cameras, viewer), pagination
        aggregates = await uow.camera_stations.aggregates([c.id for c in cameras])
        items: list[CameraStationMapItem] = []
        for camera in cameras:
            lat, lng, precision = serialize_location(camera, viewer)
            agg = aggregates.get(camera.id, CameraAggregates())
            items.append(
                CameraStationMapItem(
                    id=camera.id,
                    code=camera.code,
                    name=camera.name,
                    latitude=lat,
                    longitude=lng,
                    location_precision=precision,  # type: ignore[arg-type]
                    visibility=camera.visibility,
                    is_mine=is_owner(camera, viewer),
                    still_installed=camera.still_installed,
                    sightings=agg.sightings,
                    species=agg.species,
                )
            )
        return items, pagination


async def create_camera(
    uow: UnitOfWork, owner: Owner, data: CameraStationCreate
) -> tuple[CameraStationRead, list[ApiWarning]]:
    with log_step("camera.create"):
        _check_visibility(owner, data.visibility)
        _validate_dates(data.deployed_at, data.still_installed, data.retrieved_at)
        await _check_anon_limit(uow, owner)
        if data.project_id is not None:
            project = await uow.projects.get_owned(data.project_id, owner)
            if project is None:
                if await uow.projects.get_visible(data.project_id, owner) is not None:
                    raise ForbiddenError("FORBIDDEN", "Ese proyecto no es tuyo.")
                raise NotFoundError("PROJECT_NOT_FOUND", "El proyecto no existe.")
        await _ensure_code_free(uow, owner, data.code)

        camera = CameraStation(
            code=data.code,
            name=data.name,
            latitude=_coord(data.latitude),
            longitude=_coord(data.longitude),
            deployed_at=data.deployed_at,
            retrieved_at=data.retrieved_at,
            still_installed=data.still_installed,
            observations=data.observations,
            visibility=data.visibility,
            version=1,
        )
        owner.assign_to(camera, anon_retain=await _anon_retain(uow, owner))
        uow.camera_stations.add(camera)
        await _flush_or_code_taken(uow)
        if data.project_id is not None:
            uow.projects.add_camera(data.project_id, camera.id)
        await uow.commit()
        await uow.camera_stations.refresh(camera)
        warnings = _coords_warnings(data.latitude, data.longitude)
        return await _read_one(uow, camera, owner), warnings


async def get_camera(
    uow: UnitOfWork, viewer: Owner | None, camera_id: uuid.UUID
) -> CameraStationRead:
    with log_step("camera.get"):
        camera = await uow.camera_stations.get_visible(camera_id, viewer)
        if camera is None:  # también si es privada y ajena (S1, CB-05)
            raise NotFoundError("CAMERA_NOT_FOUND", _NOT_FOUND_MSG)
        return await _read_one(uow, camera, viewer)


async def update_camera(
    uow: UnitOfWork,
    owner: Owner,
    camera_id: uuid.UUID,
    if_match: int,
    data: CameraStationUpdate,
) -> tuple[CameraStationRead, list[ApiWarning]]:
    with log_step("camera.update"):
        camera = await _owned_or_error(uow, owner, camera_id, for_update=True)
        if camera.version != if_match:  # CB-15
            raise ConflictError(
                "CONFLICT_STALE",
                "La cámara se modificó en otra ventana. Recarga para ver los cambios.",
                context={"expected": if_match, "current": camera.version},
            )
        changes = data.model_dump(exclude_unset=True)
        for required in ("code", "latitude", "longitude", "deployed_at", "still_installed"):
            if required in changes and changes[required] is None:
                raise BusinessRuleError("VALIDATION_ERROR", f"El campo {required} es obligatorio.")

        visibility = changes.get("visibility") or camera.visibility
        _check_visibility(owner, visibility)
        still_installed = changes.get("still_installed", camera.still_installed)
        retrieved_at = changes.get("retrieved_at", camera.retrieved_at)
        if still_installed and "still_installed" in changes and "retrieved_at" not in changes:
            retrieved_at = None  # volver a "instalada" limpia el retiro
        deployed_at = changes.get("deployed_at", camera.deployed_at)
        _validate_dates(deployed_at, still_installed, retrieved_at)
        if "code" in changes and changes["code"].lower() != camera.code.lower():
            await _ensure_code_free(uow, owner, changes["code"], exclude_id=camera.id)

        old_lat, old_lng = float(camera.latitude), float(camera.longitude)
        new_lat = changes.get("latitude", old_lat)
        new_lng = changes.get("longitude", old_lng)
        warnings: list[ApiWarning] = []
        if "latitude" in changes or "longitude" in changes:
            warnings += _coords_warnings(new_lat, new_lng)
            moved = haversine_m(old_lat, old_lng, new_lat, new_lng)
            if moved > settings.CAMERA_MOVE_WARNING_M:
                total = (
                    (await uow.camera_stations.aggregates([camera.id]))
                    .get(camera.id, CameraAggregates())
                    .classifications
                )
                if total > 0:  # CB-09
                    warnings.append(
                        ApiWarning(
                            code="CAMERA_MOVED_WITH_DATA",
                            message=(
                                f"Esta cámara tiene {total} clasificaciones. Si la moviste "
                                "físicamente, registra una nueva instalación."
                            ),
                            context={"classifications": total, "distance_m": round(moved, 1)},
                        )
                    )
            camera.latitude, camera.longitude = _coord(new_lat), _coord(new_lng)

        for field in ("code", "name", "observations", "deployed_at"):
            if field in changes:
                setattr(camera, field, changes[field])
        camera.still_installed = still_installed
        camera.retrieved_at = retrieved_at
        camera.visibility = visibility
        camera.version += 1
        await _flush_or_code_taken(uow)
        await uow.commit()
        await uow.camera_stations.refresh(camera)
        return await _read_one(uow, camera, owner), warnings


async def delete_camera(uow: UnitOfWork, owner: Owner, camera_id: uuid.UUID) -> None:
    with log_step("camera.delete"):
        deleted = await uow.camera_stations.get_owned(camera_id, owner, include_deleted=True)
        if deleted is not None and deleted.is_deleted:
            raise ConflictError("ENTITY_ALREADY_DELETED", "La cámara ya estaba eliminada.")
        camera = await _owned_or_error(uow, owner, camera_id, for_update=True)
        now = datetime.now(UTC)
        actor = owner.user_id or owner.anon_session_id
        await uow.camera_stations.cascade_soft_delete(camera.id, now, actor)
        camera.is_deleted, camera.deleted_at, camera.deleted_by = True, now, actor
        await uow.commit()


def _overlaps(camera: CameraStation, start: datetime, end: datetime | None) -> bool:
    cam_end = camera.retrieved_at
    starts_before_query_ends = end is None or camera.deployed_at <= end
    ends_after_query_starts = cam_end is None or cam_end >= start
    return starts_before_query_ends and ends_after_query_starts


async def nearby(
    uow: UnitOfWork,
    owner: Owner,
    *,
    lat: float,
    lng: float,
    radius_m: int,
    exclude_id: uuid.UUID | None,
    deployed_at: datetime | None,
    retrieved_at: datetime | None,
) -> NearbyData:
    with log_step("camera.nearby"):
        radius = min(max(radius_m, 1), settings.NEARBY_MAX_RADIUS_M)
        candidates = await uow.camera_stations.near_candidates(lat, lng, radius, owner, exclude_id)
        within = [
            (c, haversine_m(lat, lng, float(c.latitude), float(c.longitude))) for c in candidates
        ]
        within = sorted(((c, d) for c, d in within if d <= radius), key=lambda pair: pair[1])
        mine = [c for c, _ in within if is_owner(c, owner)]
        aggregates = await uow.camera_stations.aggregates([c.id for c in mine])
        owners = await _owner_views(uow, [c for c, _ in within if not is_owner(c, owner)], owner)
        start = deployed_at or _now_local()

        mine_out: list[NearbyMine] = []
        public_out: list[NearbyPublic] = []
        for camera, distance in within:
            if is_owner(camera, owner):
                mine_out.append(
                    NearbyMine(
                        id=camera.id,
                        code=camera.code,
                        name=camera.name,
                        distance_m=round(distance, 1),
                        still_installed=camera.still_installed,
                        deployed_at=camera.deployed_at,
                        retrieved_at=camera.retrieved_at,
                        classifications=aggregates.get(
                            camera.id, CameraAggregates()
                        ).classifications,
                        same_location=distance < 1,
                        overlapping_period=_overlaps(camera, start, retrieved_at),
                    )
                )
            else:  # solo públicas ajenas (CB-04); las privadas ajenas nunca llegan (CB-05)
                public_out.append(
                    NearbyPublic(
                        id=camera.id,
                        code=camera.code,
                        distance_band=distance_band(distance),
                        owner=owners[camera.id],
                    )
                )
        return NearbyData(mine=mine_out, public_others=public_out)


async def _suggest_code(uow: UnitOfWork, owner: Owner, previous_code: str) -> str:
    base = _SUFFIX.sub("", previous_code) or previous_code
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = f"{base[: 50 - len(suffix)]}{suffix}"
        if await uow.camera_stations.find_active_by_code(owner, candidate) is None:
            return candidate
        n += 1


async def redeploy(
    uow: UnitOfWork, owner: Owner, camera_id: uuid.UUID, data: RedeployRequest
) -> RedeployData:
    """CB-03: nueva instalación en el mismo punto, enlazada a la anterior."""
    with log_step("camera.redeploy"):
        previous = await _owned_or_error(uow, owner, camera_id, for_update=True)
        if data.deployed_at < previous.deployed_at:
            raise _invalid_dates(
                "La nueva colocación no puede ser anterior a la de la cámara previa."
            )
        _validate_dates(data.deployed_at, True, None)
        await _check_anon_limit(uow, owner)
        code = data.code or await _suggest_code(uow, owner, previous.code)
        await _ensure_code_free(uow, owner, code)

        if data.close_previous and previous.still_installed:
            retrieved = data.previous_retrieved_at or data.deployed_at
            _validate_dates(previous.deployed_at, False, retrieved)
            previous.still_installed, previous.retrieved_at = False, retrieved
            previous.version += 1

        camera = CameraStation(
            code=code,
            name=previous.name,
            latitude=previous.latitude,
            longitude=previous.longitude,
            deployed_at=data.deployed_at,
            still_installed=True,
            observations=data.observations
            if data.observations is not None
            else previous.observations,
            visibility=previous.visibility,
            previous_camera_station_id=previous.id,
            version=1,
        )
        owner.assign_to(camera, anon_retain=await _anon_retain(uow, owner))
        uow.camera_stations.add(camera)
        await _flush_or_code_taken(uow)
        await uow.camera_stations.copy_projects(previous.id, camera.id)
        await uow.commit()
        await uow.camera_stations.refresh(camera)
        await uow.camera_stations.refresh(previous)
        new_read, previous_read = await _to_reads(uow, [camera, previous], owner)
        return RedeployData(camera_station=new_read, previous=previous_read)
