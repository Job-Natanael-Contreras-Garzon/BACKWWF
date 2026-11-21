"""Estadísticas ecológicas (HU-13, FL-10/FL-11, §10.3). Las mismas reglas sirven a pantalla,
Excel y PDF (HU-14): por eso el cálculo vive en funciones puras sobre las filas.
"""

import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.core.enums import (
    CaptureSource,
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


def _bounds(filters: StatsFilters) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(filters.from_, time.min) if filters.from_ else None
    end = datetime.combine(filters.to + timedelta(days=1), time.min) if filters.to else None
    return start, end


def trap_days(cameras: Iterable[CameraStation], filters: StatsFilters, now: datetime) -> float:
    """CB-19: Σ (retiro, o fin del filtro, o ahora) − (instalación, o inicio del filtro)."""
    start_f, end_f = _bounds(filters)
    total = 0.0
    for camera in cameras:
        start = max(camera.deployed_at, start_f) if start_f else camera.deployed_at
        end = camera.retrieved_at or now
        if end_f:
            end = min(end, end_f)
        total += max((end - start).total_seconds(), 0) / 86400
    return round(total, 1)


def compute(
    rows: list[Classification],
    cameras: list[CameraStation],
    filters: StatsFilters,
    *,
    scope: str,
    scope_id: uuid.UUID,
    scope_name: str,
    sections: Iterable[StatsSection] = ALL_SECTIONS,
    now: datetime | None = None,
) -> Stats:
    wanted = set(sections)
    current = now or datetime.now(UTC)
    done = [r for r in rows if r.status == ClassificationStatus.DONE]
    animals = [r for r in done if r.category == Category.ANIMAL]
    sightings = [r for r in animals if r.validation_status not in NOT_SIGHTING]
    if filters.only_validated:
        sightings = [r for r in sightings if r.validation_status in VALIDATED]
    total = len(sightings)
    taxa = [(r, effective(r)) for r in sightings]
    stats = Stats(
        scope=scope,  # type: ignore[arg-type]
        scope_id=scope_id,
        scope_name=scope_name,
        filters=filters,
        generated_at=current,
    )

    if "totals" in wanted:
        stats.totals = Totals(
            files_processed=len(done) + sum(r.status == ClassificationStatus.ERROR for r in rows),
            files_with_fauna=len(animals),
            files_without_fauna=len(done) - len(animals),
            files_error=sum(r.status == ClassificationStatus.ERROR for r in rows),
            sightings=total,
            validated=sum(r.validation_status in VALIDATED for r in sightings),
            corrected=sum(r.validation_status in CORRECTED for r in sightings),
            rejected=sum(r.validation_status == ValidationStatus.REJECTED for r in animals),
            discarded_repeat=sum(
                r.validation_status == ValidationStatus.DISCARDED_REPEAT for r in animals
            ),
            pending_validation=sum(
                r.validation_status == ValidationStatus.UNVALIDATED for r in sightings
            ),
        )
    if "richness" in wanted:
        stats.richness = Richness(
            species=len({(t.genus, t.species) for _, t in taxa if t.rank == Rank.SPECIES}),
            genera=len({t.genus for _, t in taxa if t.genus}),
            families=len({t.family for _, t in taxa if t.family}),
        )
    if "non_animal" in wanted:
        cats = Counter(r.category for r in done)
        stats.non_animal = NonAnimal(
            person=cats[Category.PERSON], vehicle=cats[Category.VEHICLE], blank=cats[Category.BLANK]
        )
    if "taxa" in wanted:
        _taxa_sections(stats, taxa, total)
    if "by_camera" in wanted and scope == "project":
        stats.by_camera = _by_camera(taxa, cameras)
    if "by_month" in wanted or "by_hour" in wanted:
        dated = [
            r.captured_at
            for r in sightings
            if r.captured_at is not None and r.captured_at_source != CaptureSource.UPLOAD_TIME
        ]
        if "by_month" in wanted:
            months = Counter(d.strftime("%Y-%m") for d in dated)
            stats.by_month = [MonthRow(month=m, sightings=c) for m, c in sorted(months.items())]
        if "by_hour" in wanted:
            hours = Counter(d.hour for d in dated)
            stats.by_hour = [HourRow(hour=h, sightings=hours[h]) for h in range(24)]
    if "effort" in wanted:
        days = trap_days(cameras, filters, current.replace(tzinfo=None))
        stats.effort = Effort(
            trap_days=days,
            sightings_per_100_trap_days=round(total / days * 100, 1) if days else None,
            camera_stations_without_retrieval=sum(c.retrieved_at is None for c in cameras),
        )
    return stats


def _taxa_sections(
    stats: Stats, taxa: list[tuple[Classification, EffectiveTaxon]], total: int
) -> None:
    catalog = get_catalog()
    species: dict[tuple[str | None, str | None], list[tuple[Classification, EffectiveTaxon]]]
    species = defaultdict(list)
    genera: Counter[str] = Counter()
    families: Counter[str] = Counter()
    family_of_genus: dict[str, str | None] = {}
    unidentified: Counter[str] = Counter()
    for row, t in taxa:
        if t.rank == Rank.SPECIES:
            species[(t.genus, t.species)].append((row, t))
        elif t.rank is None:
            unidentified["unlisted"] += 1  # correct_unlisted sin taxón superior
        else:
            unidentified[t.rank.value] += 1
        if t.genus:
            genera[t.genus] += 1
            family_of_genus.setdefault(t.genus, t.family)
        if t.family:
            families[t.family] += 1

    rows: list[SpeciesRow] = []
    for group in species.values():
        sample = group[0][1]
        dates = [r.captured_at for r, _ in group if r.captured_at is not None]
        confidences = [float(r.confidence) for r, _ in group if r.confidence is not None]
        rows.append(
            SpeciesRow(
                label_id=sample.label_id,
                scientific_name=sample.scientific_name,
                common_name=sample.common_name,
                genus=sample.genus,
                family=sample.family,
                count=len(group),
                pct=_pct(len(group), total),
                validated=sum(r.validation_status in VALIDATED for r, _ in group),
                mean_confidence=(
                    round(sum(confidences) / len(confidences), 3) if confidences else None
                ),
                first_seen=min(dates) if dates else None,
                last_seen=max(dates) if dates else None,
                camera_stations=len({r.camera_station_id for r, _ in group}),
            )
        )
    stats.by_species = sorted(rows, key=lambda s: (-s.count, s.scientific_name or ""))

    def label(rank: Rank, name: str) -> str | None:
        taxon = catalog.group(rank, name)
        return taxon.label_id if taxon else None

    stats.by_genus = [
        GenusRow(
            label_id=label(Rank.GENUS, g),
            name=g,
            family=family_of_genus.get(g),
            count=c,
            pct=_pct(c, total),
        )
        for g, c in sorted(genera.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    stats.by_family = [
        FamilyRow(label_id=label(Rank.FAMILY, f), name=f, count=c, pct=_pct(c, total))
        for f, c in sorted(families.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    stats.unidentified_to_species = Unidentified(
        genus=unidentified["genus"],
        family=unidentified["family"],
        order=unidentified["order"],
        class_=unidentified["class"],
        unlisted=unidentified["unlisted"],
    )


def _by_camera(
    taxa: list[tuple[Classification, EffectiveTaxon]], cameras: list[CameraStation]
) -> list[CameraRow]:
    per_camera: dict[uuid.UUID, Counter[str | None]] = defaultdict(Counter)
    sightings: Counter[uuid.UUID] = Counter()
    for row, t in taxa:
        sightings[row.camera_station_id] += 1
        if t.rank == Rank.SPECIES:
            per_camera[row.camera_station_id][t.label_id] += 1
    result = [
        CameraRow(
            camera_station_id=c.id,
            code=c.code,
            sightings=sightings[c.id],
            species=len(per_camera[c.id]),
            species_counts=[
                SpeciesCount(label_id=label_id, count=n)
                for label_id, n in per_camera[c.id].most_common()
            ],
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
    rows: list[Classification]


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
    start, end = _bounds(filters)
    rows = await uow.classifications.for_stats(
        [c.id for c in cameras], start=start, end=end, source=filters.source
    )
    return Scope(kind, scope_id, name, cameras, rows)


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
        return compute(
            scope.rows,
            scope.cameras,
            filters,
            scope=scope.kind,
            scope_id=scope.id,
            scope_name=scope.name,
            sections=sections or ALL_SECTIONS,
        )
