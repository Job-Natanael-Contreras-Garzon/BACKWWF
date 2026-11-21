"""Repositorio base: consultas con nombre, **nunca** ``commit()`` (lo hace el servicio vía UoW)."""

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

M = TypeVar("M", bound=Base)

MAX_PAGE_SIZE = 200


class Repository(Generic[M]):
    model: type[M]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: uuid.UUID | str) -> M | None:
        return await self.session.get(self.model, entity_id)

    def add(self, entity: M) -> M:
        self.session.add(entity)
        return entity

    async def refresh(self, entity: M) -> None:
        """Recarga columnas que la BD calcula (p. ej. ``updated_at``) sin lazy-load en async."""
        await self.session.refresh(entity)

    async def flush(self) -> None:
        """Envía los cambios pendientes (p. ej. para obtener errores de unicidad) sin confirmar."""
        await self.session.flush()

    async def _first(self, stmt: Select[Any]) -> M | None:
        row: M | None = await self.session.scalar(stmt)
        return row

    async def _page(
        self, stmt: Select[Any], page: int, page_size: int, max_page_size: int = MAX_PAGE_SIZE
    ) -> tuple[list[M], int]:
        page_size = max(1, min(page_size, max_page_size))
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(
            stmt.limit(page_size).offset((max(page, 1) - 1) * page_size)
        )
        return list(rows), int(total or 0)
