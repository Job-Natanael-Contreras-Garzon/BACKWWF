"""Estadísticas ecológicas en SQL (D11, §10.3): cada sección es una agregación en la BD, para
que el costo no crezca con la cantidad de archivos que habría que traer a memoria.

Todas las consultas parten de la misma subconsulta ``_scoped``: las filas que cuentan, con la
taxonomía **efectiva** ya resuelta (la corrección humana si existe, si no la IA) y una columna
``sighting`` que aplica la regla de avistamiento. Agrupar por columnas de la subconsulta evita que
PostgreSQL vea dos ``CASE`` "distintos" en el SELECT y en el GROUP BY.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Subquery, and_, case, distinct, extract, func, or_, select

from app.core.enums import (
    CaptureSource,
    Category,
    ClassificationSource,
    ClassificationStatus,
    Rank,
    ValidationStatus,
)
from app.models.classification import Classification as C
from app.repositories.base import Repository
from app.repositories.classifications import effective_column

VALIDATED = (
    ValidationStatus.CONFIRMED,
    ValidationStatus.CORRECTED,
    ValidationStatus.CORRECTED_UNLISTED,
)
CORRECTED = (ValidationStatus.CORRECTED, ValidationStatus.CORRECTED_UNLISTED)
NOT_SIGHTING = (ValidationStatus.REJECTED, ValidationStatus.DISCARDED_REPEAT)


@dataclass(frozen=True, slots=True)
class StatsScope:
    camera_ids: list[uuid.UUID]
    start: datetime | None = None
    end: datetime | None = None
    source: ClassificationSource | None = None
    only_validated: bool = False
    dedup_sha256: bool = False  # CB-52: el panel admin cuenta cada archivo una sola vez


def _count(condition: ColumnElement[bool]) -> Any:
    return func.count(case((condition, 1)))


class StatsRepository(Repository[C]):
    model = C

    @staticmethod
    def _scoped(scope: StatsScope) -> Subquery:
        """Solo cuentan las filas ``done`` y ``error`` no borradas de esas cámaras (§10.3)."""
        sighting = and_(
            C.status == ClassificationStatus.DONE,
            C.category == Category.ANIMAL,
            C.validation_status.not_in(NOT_SIGHTING),
        )
        if scope.only_validated:
            sighting = and_(sighting, C.validation_status.in_(VALIDATED))
        stmt = select(
            C.camera_station_id.label("camera_id"),
            C.status.label("status"),
            C.category.label("category"),
            C.validation_status.label("vs"),
            C.confidence.label("confidence"),
            C.captured_at.label("captured_at"),
            C.captured_at_source.label("captured_source"),
            case((sighting, True), else_=False).label("sighting"),
            effective_column(C.corrected_label_id, C.label_id).label("label_id"),
            effective_column(C.corrected_rank, C.rank).label("rank"),
            effective_column(C.corrected_family, C.family).label("family"),
            effective_column(C.corrected_genus, C.genus).label("genus"),
            effective_column(C.corrected_species, C.species).label("species"),
            effective_column(C.corrected_scientific_name, C.scientific_name).label("scientific"),
            effective_column(C.corrected_common_name, C.common_name).label("common"),
        ).where(
            C.camera_station_id.in_(scope.camera_ids),
            C.is_deleted.is_(False),
            C.status.in_((ClassificationStatus.DONE, ClassificationStatus.ERROR)),
        )
        filters: list[ColumnElement[bool]] = []
        if scope.start is not None:
            filters.append(C.captured_at >= scope.start)
        if scope.end is not None:
            filters.append(C.captured_at < scope.end)
        if scope.source is not None:
            filters.append(C.source == scope.source)
        stmt = stmt.where(*filters)
        if scope.dedup_sha256:
            first = (
                select(C.id)
                .distinct(C.file_sha256)
                .where(
                    C.camera_station_id.in_(scope.camera_ids),
                    C.is_deleted.is_(False),
                    C.status.in_((ClassificationStatus.DONE, ClassificationStatus.ERROR)),
                    *filters,
                )
                .order_by(C.file_sha256, C.created_at, C.id)
            )
            stmt = stmt.where(C.id.in_(first))
        return stmt.subquery("scoped")

    async def _rows(self, stmt: Any) -> list[Any]:
        return list((await self.session.execute(stmt)).all())

    async def totals(self, scope: StatsScope) -> dict[str, int]:
        if not scope.camera_ids:
            return dict.fromkeys(_TOTAL_KEYS, 0)
        q = self._scoped(scope)
        done = q.c.status == ClassificationStatus.DONE
        animal = and_(done, q.c.category == Category.ANIMAL)
        s = q.c.sighting.is_(True)
        columns = {
            "files_processed": func.count(),
            "files_with_fauna": _count(animal),
            "files_without_fauna": _count(and_(done, q.c.category != Category.ANIMAL)),
            "files_error": _count(q.c.status == ClassificationStatus.ERROR),
            "sightings": _count(s),
            "validated": _count(and_(s, q.c.vs.in_(VALIDATED))),
            "corrected": _count(and_(s, q.c.vs.in_(CORRECTED))),
            "rejected": _count(and_(animal, q.c.vs == ValidationStatus.REJECTED)),
            "discarded_repeat": _count(and_(animal, q.c.vs == ValidationStatus.DISCARDED_REPEAT)),
            "pending_validation": _count(and_(s, q.c.vs == ValidationStatus.UNVALIDATED)),
            "person": _count(and_(done, q.c.category == Category.PERSON)),
            "vehicle": _count(and_(done, q.c.category == Category.VEHICLE)),
            "blank": _count(and_(done, q.c.category == Category.BLANK)),
            "species": func.count(
                distinct(case((and_(s, q.c.rank == Rank.SPECIES), q.c.genus + " " + q.c.species)))
            ),
            "genera": func.count(distinct(case((s, q.c.genus)))),
            "families": func.count(distinct(case((s, q.c.family)))),
        }
        (row,) = await self._rows(select(*columns.values()))
        return {name: int(v or 0) for name, v in zip(columns, row, strict=True)}

    async def by_species(self, scope: StatsScope) -> list[Any]:
        if not scope.camera_ids:
            return []
        q = self._scoped(scope)
        stmt = (
            select(
                func.max(q.c.label_id).label("label_id"),
                func.max(q.c.scientific).label("scientific_name"),
                func.max(q.c.common).label("common_name"),
                q.c.genus.label("genus"),
                func.max(q.c.family).label("family"),
                func.count().label("count"),
                _count(q.c.vs.in_(VALIDATED)).label("validated"),
                func.avg(q.c.confidence).label("mean_confidence"),
                func.min(q.c.captured_at).label("first_seen"),
                func.max(q.c.captured_at).label("last_seen"),
                func.count(distinct(q.c.camera_id)).label("camera_stations"),
            )
            .where(q.c.sighting.is_(True), q.c.rank == Rank.SPECIES)
            .group_by(q.c.genus, q.c.species)
        )
        return await self._rows(stmt)

    async def by_genus(self, scope: StatsScope) -> list[Any]:
        if not scope.camera_ids:
            return []
        q = self._scoped(scope)
        stmt = (
            select(
                q.c.genus.label("name"),
                func.max(q.c.family).label("family"),
                func.count().label("count"),
            )
            .where(q.c.sighting.is_(True), q.c.genus.is_not(None))
            .group_by(q.c.genus)
        )
        return await self._rows(stmt)

    async def by_family(self, scope: StatsScope) -> list[Any]:
        if not scope.camera_ids:
            return []
        q = self._scoped(scope)
        stmt = (
            select(q.c.family.label("name"), func.count().label("count"))
            .where(q.c.sighting.is_(True), q.c.family.is_not(None))
            .group_by(q.c.family)
        )
        return await self._rows(stmt)

    async def by_rank(self, scope: StatsScope) -> dict[str | None, int]:
        if not scope.camera_ids:
            return {}
        q = self._scoped(scope)
        stmt = select(q.c.rank, func.count()).where(q.c.sighting.is_(True)).group_by(q.c.rank)
        return {(str(r) if r is not None else None): int(n) for r, n in await self._rows(stmt)}

    async def by_camera(self, scope: StatsScope) -> list[Any]:
        """(cámara, label_id de especie o None, cantidad) por cada combinación."""
        if not scope.camera_ids:
            return []
        q = self._scoped(scope)
        species_label = case((q.c.rank == Rank.SPECIES, q.c.label_id)).label("species_label")
        inner = select(q.c.camera_id, species_label).where(q.c.sighting.is_(True)).subquery()
        stmt = select(inner.c.camera_id, inner.c.species_label, func.count()).group_by(
            inner.c.camera_id, inner.c.species_label
        )
        return await self._rows(stmt)

    def _dated(self, q: Subquery) -> ColumnElement[bool]:
        """§10.3: las fechas de subida (``upload_time``) no sirven para patrones temporales."""
        return and_(
            q.c.sighting.is_(True),
            q.c.captured_at.is_not(None),
            or_(
                q.c.captured_source.is_(None),
                q.c.captured_source != CaptureSource.UPLOAD_TIME,
            ),
        )

    async def by_month(self, scope: StatsScope) -> list[Any]:
        if not scope.camera_ids:
            return []
        q = self._scoped(scope)
        inner = (
            select(func.to_char(q.c.captured_at, "YYYY-MM").label("month"))
            .where(self._dated(q))
            .subquery()
        )
        return await self._rows(select(inner.c.month, func.count()).group_by(inner.c.month))

    async def by_hour(self, scope: StatsScope) -> list[Any]:
        if not scope.camera_ids:
            return []
        q = self._scoped(scope)
        inner = (
            select(extract("hour", q.c.captured_at).label("hour")).where(self._dated(q)).subquery()
        )
        return await self._rows(select(inner.c.hour, func.count()).group_by(inner.c.hour))


_TOTAL_KEYS = (
    "files_processed",
    "files_with_fauna",
    "files_without_fauna",
    "files_error",
    "sightings",
    "validated",
    "corrected",
    "rejected",
    "discarded_repeat",
    "pending_validation",
    "person",
    "vehicle",
    "blank",
    "species",
    "genera",
    "families",
)
