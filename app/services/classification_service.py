"""Lecturas de clasificaciones individuales (HU-11: fotograma de evidencia, #27)."""

import uuid

from app.core.errors import NotFoundError
from app.db.uow import UnitOfWork
from app.integrations.storage.base import StorageBackend
from app.services.policies import Owner


def _not_found() -> NotFoundError:
    return NotFoundError("CLASSIFICATION_NOT_FOUND", "No encontramos esa clasificación.")


async def get_evidence(
    uow: UnitOfWork, storage: StorageBackend, viewer: Owner | None, classification_id: uuid.UUID
) -> bytes:
    """El fotograma solo sale si la clasificación es visible (S1: lo ajeno y privado da 404)."""
    row = await uow.classifications.get_visible(classification_id, viewer)
    if row is None or row.evidence_key is None:
        raise _not_found()
    try:
        return await storage.get(row.evidence_key)
    except FileNotFoundError as exc:  # el archivo se limpió: para el cliente es lo mismo
        raise _not_found() from exc
