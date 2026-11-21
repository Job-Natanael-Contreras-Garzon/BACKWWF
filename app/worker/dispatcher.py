"""Cola justa (DD-12, CB-30): ningún dueño acapara a los workers.

El orden efectivo reparte por turnos: primero el 1.º archivo en cola de cada dueño (por orden de
llegada del dueño), después el 2.º de cada uno, etc. Al despachar, además, se salta a los dueños
que ya tienen ``QUEUE_PER_OWNER_INFLIGHT`` archivos procesándose. La BD es la fuente de verdad:
Redis solo lleva el aviso de que hay trabajo.
"""

import uuid
from datetime import UTC, datetime
from math import ceil

from sqlalchemy import ColumnElement, Subquery, func, over, select, update

from app.core.config import settings
from app.core.enums import ClassificationStatus
from app.db.uow import UnitOfWork
from app.models.classification import Classification

_CANDIDATES = 20


def _owner_key() -> ColumnElement[uuid.UUID]:
    return func.coalesce(Classification.owner_user_id, Classification.anon_session_id)


def _fair_order() -> Subquery:
    """Subconsulta (id, owner_key, posición efectiva) de lo que está en cola.

    El turno de cada archivo cuenta también los que su dueño ya tiene procesando: si Ana ya
    tiene uno en curso, su siguiente archivo va detrás del primero de Luis.
    """
    owner_key = _owner_key()
    in_line = Classification.status.in_(
        (ClassificationStatus.QUEUED, ClassificationStatus.PROCESSING)
    )
    ranked = (
        select(
            Classification.id.label("id"),
            Classification.status.label("status"),
            owner_key.label("owner_key"),
            over(
                func.row_number(),
                partition_by=owner_key,
                # los que ya están procesando ocupan los primeros turnos de su dueño
                order_by=(
                    (Classification.status != ClassificationStatus.PROCESSING),
                    Classification.queued_at,
                    Classification.id,
                ),
            ).label("turn"),
            over(func.min(Classification.queued_at), partition_by=owner_key).label("owner_first"),
        )
        .where(Classification.is_deleted.is_(False), in_line)
        .subquery()
    )
    return (
        select(
            ranked.c.id,
            ranked.c.owner_key,
            over(
                func.row_number(),
                order_by=(ranked.c.turn, ranked.c.owner_first, ranked.c.owner_key, ranked.c.id),
            ).label("position"),
        )
        .where(ranked.c.status == ClassificationStatus.QUEUED)
        .subquery()
    )


async def queue_positions(uow: UnitOfWork, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    order = _fair_order()
    stmt = select(order.c.id, order.c.position).where(order.c.id.in_(ids))
    return {row[0]: int(row[1]) for row in (await uow.session.execute(stmt)).all()}


def estimated_wait_seconds(position: int) -> int:
    workers = max(settings.QUEUE_WORKERS, 1)
    return ceil(position * settings.QUEUE_AVG_PROCESSING_SECONDS / workers)


async def claim_next(uow: UnitOfWork) -> Classification | None:
    """Toma el siguiente archivo según la cola justa y lo marca ``processing``.

    ``FOR UPDATE SKIP LOCKED``: dos workers nunca toman el mismo archivo. Lo usa el worker de
    HU-11; el caller hace el commit.
    """
    owner_key = _owner_key()
    busy = (
        select(owner_key)
        .where(
            Classification.is_deleted.is_(False),
            Classification.status == ClassificationStatus.PROCESSING,
        )
        .group_by(owner_key)
        .having(func.count() >= settings.QUEUE_PER_OWNER_INFLIGHT)
    )
    order = _fair_order()
    candidates = (
        select(order.c.id)
        .where(order.c.owner_key.not_in(busy))
        .order_by(order.c.position)
        .limit(_CANDIDATES)
    )
    for candidate_id in list(await uow.session.scalars(candidates)):
        row = await uow.session.scalar(
            select(Classification)
            .where(
                Classification.id == candidate_id,
                Classification.status == ClassificationStatus.QUEUED,
            )
            .with_for_update(skip_locked=True)
        )
        if row is None:
            continue  # otro worker lo tomó
        now = datetime.now(UTC)
        await uow.session.execute(
            update(Classification)
            .where(Classification.id == row.id)
            .values(
                status=ClassificationStatus.PROCESSING,
                started_at=now,
                heartbeat_at=now,
                attempts=Classification.attempts + 1,
            )
        )
        await uow.session.refresh(row)
        return row
    return None
