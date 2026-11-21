"""Estadísticas ecológicas (HU-13, FL-11, §10.3). Las mismas reglas sirven a pantalla, Excel y PDF
(HU-14). Las agregaciones corren en SQL (``repositories/stats.py``, D11); acá se arma la respuesta.
"""

import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import Row

from app.core.enums import (
    Category,
    ClassificationStatus,
    Rank,
    ValidationStatus,
)
from app.core.errors import NotFoundError
from app.core.logging import log_step
from app.db.uow import UnitOfWork
from app.models.camera_station import CameraStation
from app.models.classification import Classification
from app.repositories.stats import StatsRepository, StatsScope
from app.schemas.stats import (
    ALL_SECTIONS,
    CameraRow,
    Effort,
    FamilyRow,
    GenusRow,
    HourRow,
    MonthRow,
    NonAnimal,
    Richness,
    SpeciesCount,
    SpeciesRow,
    Stats,
    StatsFilters,
    StatsSection,
    Totals,
    Unidentified,
)
from app.services.catalog_service import get_catalog
from app.services.policies import Owner

VALIDATED = (
    ValidationStatus.CONFIRMED,
    ValidationStatus.CORRECTED,
    ValidationStatus.CORRECTED_UNLISTED,
)
CORRECTED = (ValidationStatus.CORRECTED, ValidationStatus.CORRECTED_UNLISTED)
NOT_SIGHTING = (ValidationStatus.REJECTED, ValidationStatus.DISCARDED_REPEAT)


@dataclass(frozen=True, slots=True)
class EffectiveTaxon:
    """Lo que cuenta: la corrección humana si la hay, si no la IA. Usa los nombres guardados en la
    fila, no el catálogo actual, para conservar la taxonomía histórica (CB-68)."""

    label_id: str | None
    rank: Rank | None
    class_: str | None
    order: str | None
    family: str | None
    genus: str | None
    species: str | None
    scientific_name: str | None
    common_name: str | None


def effective(row: Classification) -> EffectiveTaxon:
    if row.validation_status in CORRECTED:
        return EffectiveTaxon(
            row.corrected_label_id,
            row.corrected_rank,
            row.corrected_class,
            row.corrected_order,
            row.corrected_family,
            row.corrected_genus,
            row.corrected_species,
            row.corrected_scientific_name,
            row.corrected_common_name,
        )
    return EffectiveTaxon(
        row.label_id,
        row.rank,
        row.class_,
        row.order_,
        row.family,
        row.genus,
        row.species,
        row.scientific_name,
        row.common_name,
    )


def is_sighting(row: Classification) -> bool:
    """§10.3: done, animal, no rechazada ni descartada como repetida (y no borrada)."""
    return (
        not row.is_deleted
        and row.status == ClassificationStatus.DONE
        and row.category == Category.ANIMAL
        and row.validation_status not in NOT_SIGHTING
    )


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def date_bounds(filters: StatsFilters) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(filters.from_, time.min) if filters.from_ else None
    end = datetime.combine(filters.to + timedelta(days=1), time.min) if filters.to else None
    return start, end


def trap_days(cameras: Iterable[CameraStation], filters: StatsFilters, now: datetime) -> float:
    """CB-19: Σ (retiro, o fin del filtro, o ahora) − (instalación, o inicio del filtro)."""
    start_f, end_f = date_bounds(filters)
    total = 0.0
    for camera in cameras:
        start = max(camera.deployed_at, start_f) if start_f else camera.deployed_at
        end = camera.retrieved_at or now
        if end_f:
            end = min(end, end_f)
        total += max((end - start).total_seconds(), 0) / 86400
    return round(total, 1)


async def compute(
    uow: UnitOfWork,
    cameras: list[CameraStation],
    filters: StatsFilters,
    *,
    scope: str,
    scope_id: uuid.UUID | None,
    scope_name: str,
    sections: Iterable[StatsSection] = ALL_SECTIONS,
    now: datetime | None = None,
    dedup_sha256: bool = False,
) -> Stats:
    """§10.3 en SQL (D11): cada sección es una agregación en la BD."""
    wanted = set(sections)
    current = now or datetime.now(UTC)
    start, end = date_bounds(filters)
    q = StatsScope(
        camera_ids=[c.id for c in cameras],
        start=start,
        end=end,
        source=filters.source,
        only_validated=filters.only_validated,
        dedup_sha256=dedup_sha256,
    )
    repo = uow.stats
    totals = await repo.totals(q)
    total = totals["sightings"]
    stats = Stats(
        scope=scope,  # type: ignore[arg-type]
        scope_id=scope_id,
        scope_name=scope_name,
        filters=filters,
        generated_at=current,
    )
    if "totals" in wanted:
        stats.totals = Totals(**{k: totals[k] for k in Totals.model_fields})
    if "richness" in wanted:
        stats.richness = Richness(
            species=totals["species"], genera=totals["genera"], families=totals["families"]
        )
    if "non_animal" in wanted:
        stats.non_animal = NonAnimal(
            person=totals["person"], vehicle=totals["vehicle"], blank=totals["blank"]
        )
    if "taxa" in wanted:
        await _taxa_sections(repo, q, stats, total)
    if "by_camera" in wanted and scope == "project":
        stats.by_camera = _by_camera(await repo.by_camera(q), cameras)
    if "by_month" in wanted:
        stats.by_month = [
            MonthRow(month=m, sightings=int(n)) for m, n in sorted(await repo.by_month(q))
        ]
    if "by_hour" in wanted:
        hours = {int(h): int(n) for h, n in await repo.by_hour(q)}
        stats.by_hour = [HourRow(hour=h, sightings=hours.get(h, 0)) for h in range(24)]
    if "effort" in wanted:
        days = trap_days(cameras, filters, current.replace(tzinfo=None))
        stats.effort = Effort(
            trap_days=days,
            sightings_per_100_trap_days=round(total / days * 100, 1) if days else None,
            camera_stations_without_retrieval=sum(c.retrieved_at is None for c in cameras),
        )
    return stats


async def _taxa_sections(repo: StatsRepository, q: StatsScope, stats: Stats, total: int) -> None:
    catalog = get_catalog()

    def label(rank: Rank, name: str) -> str | None:
        taxon = catalog.group(rank, name)
        return taxon.label_id if taxon else None

    species = [
        SpeciesRow(
            label_id=r.label_id,
            scientific_name=r.scientific_name,
            common_name=r.common_name,
            genus=r.genus,
            family=r.family,
            count=int(r.count),
            pct=_pct(int(r.count), total),
            validated=int(r.validated),
            mean_confidence=(
                round(float(r.mean_confidence), 3) if r.mean_confidence is not None else None
            ),
            first_seen=r.first_seen,
            last_seen=r.last_seen,
            camera_stations=int(r.camera_stations),
        )
        for r in await repo.by_species(q)
    ]
    stats.by_species = sorted(species, key=lambda s: (-s.count, s.scientific_name or ""))
    genera = sorted(await repo.by_genus(q), key=lambda r: (-int(r.count), r.name))
    stats.by_genus = [
        GenusRow(
            label_id=label(Rank.GENUS, r.name),
            name=r.name,
            family=r.family,
            count=int(r.count),
            pct=_pct(int(r.count), total),
        )
        for r in genera
    ]
    families = sorted(await repo.by_family(q), key=lambda r: (-int(r.count), r.name))
    stats.by_family = [
        FamilyRow(
            label_id=label(Rank.FAMILY, r.name),
            name=r.name,
            count=int(r.count),
            pct=_pct(int(r.count), total),
        )
        for r in families
    ]
    ranks = await repo.by_rank(q)
    stats.unidentified_to_species = Unidentified(
        genus=ranks.get("genus", 0),
        family=ranks.get("family", 0),
        order=ranks.get("order", 0),
        class_=ranks.get("class", 0),
        unlisted=ranks.get(None, 0),  # correct_unlisted sin taxón superior (CB-65)
    )


def _by_camera(rows: list[Row[Any]], cameras: list[CameraStation]) -> list[CameraRow]:
    sightings: Counter[uuid.UUID] = Counter()
    per_camera: dict[uuid.UUID, list[SpeciesCount]] = defaultdict(list)
    for camera_id, label_id, count in rows:
        sightings[camera_id] += int(count)
        if label_id is not None:
            per_camera[camera_id].append(SpeciesCount(label_id=label_id, count=int(count)))
    result = [
        CameraRow(
            camera_station_id=c.id,
            code=c.code,
            sightings=sightings[c.id],
            species=len(per_camera[c.id]),
            species_counts=sorted(per_camera[c.id], key=lambda s: -s.count),
        )
        for c in cameras
    ]
    return sorted(result, key=lambda r: (-r.sightings, r.code))


@dataclass(frozen=True, slots=True)
class Scope:
    """Lo que ve este viewer: la base común de /stats y de los reportes (HU-14)."""

    kind: str
    id: uuid.UUID
    name: str
    cameras: list[CameraStation]


async def load_scope(
    uow: UnitOfWork,
    viewer: Owner | None,
    filters: StatsFilters,
    *,
    camera_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> Scope:
    """CA-1: en un proyecto visto por otro solo entran sus cámaras públicas (o propias)."""
    if camera_id is not None:
        camera = await uow.camera_stations.get_visible(camera_id, viewer)
        if camera is None:
            raise NotFoundError("CAMERA_NOT_FOUND", "No encontramos esa cámara.")
        kind, scope_id, name, cameras = "camera_station", camera.id, camera.code, [camera]
    else:
        project = await uow.projects.get_visible(project_id, viewer) if project_id else None
        if project is None:
            raise NotFoundError("PROJECT_NOT_FOUND", "No encontramos ese proyecto.")
        ids = await uow.projects.camera_ids(project.id)
        cameras = await uow.camera_stations.list_visible_by_ids(ids, viewer)
        kind, scope_id, name = "project", project.id, project.name
    return Scope(kind, scope_id, name, cameras)


async def get_stats(
    uow: UnitOfWork,
    viewer: Owner | None,
    filters: StatsFilters,
    sections: list[StatsSection] | None,
    *,
    camera_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> Stats:
    with log_step("stats.get"):
        scope = await load_scope(uow, viewer, filters, camera_id=camera_id, project_id=project_id)
        return await compute(
            uow,
            scope.cameras,
            filters,
            scope=scope.kind,
            scope_id=scope.id,
            scope_name=scope.name,
            sections=sections or ALL_SECTIONS,
        )
