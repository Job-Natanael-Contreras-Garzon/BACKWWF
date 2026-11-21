import uuid

from fastapi import APIRouter, Depends, Response

from app.api.deps import OptionalOwnerDep, StorageDep, UoWDep
from app.core.logging import flow
from app.services import classification_service as service

router = APIRouter(
    prefix="/classifications", tags=["Classifications"], dependencies=[Depends(flow("FL-09"))]
)


@router.get(
    "/{classification_id}/evidence",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_evidence(
    classification_id: uuid.UUID, uow: UoWDep, storage: StorageDep, viewer: OptionalOwnerDep
) -> Response:
    """#27: no se monta el volumen como estático; cada fotograma pasa por la visibilidad."""
    data = await service.get_evidence(uow, storage, viewer, classification_id)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
