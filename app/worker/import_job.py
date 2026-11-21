"""Job del worker para confirmar importaciones de escritorio (HU-10, D10, CB-85)."""

import uuid
from typing import Any

from app.core.logging import flow_var
from app.services import import_service


async def import_package(ctx: dict[str, Any], import_id: str) -> str:
    token = flow_var.set("FL-23")
    try:
        status = await import_service.run_import(uuid.UUID(import_id), ctx["storage"])
        return str(status) if status else "skipped"
    finally:
        flow_var.reset(token)
