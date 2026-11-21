from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.integrations.ia_contract.enums import Rank
from app.services.catalog_service import get_catalog

router = APIRouter(prefix="/catalog", tags=["Catalog"], dependencies=[Depends(flow("FL-10"))])


@router.get("/species", response_model=ApiResponse[list[dict[str, Any]]])
async def search_species(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    rank: Rank | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ApiResponse[list[dict[str, Any]]]:
    """#30: sin auth; sin distinguir tildes; las especies primero (§9.1)."""
    return ok([t.as_dict() for t in get_catalog().search(q, rank, limit)])


@router.get("/species/{label_id}", response_model=ApiResponse[dict[str, Any]])
async def get_species(label_id: str) -> ApiResponse[dict[str, Any]]:
    return ok(get_catalog().get(label_id).as_dict())
