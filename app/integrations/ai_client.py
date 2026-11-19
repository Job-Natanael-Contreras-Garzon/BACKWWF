import uuid
from pathlib import Path
import httpx

from app.core.config import settings
from app.integrations.ai_contract import DetectResponse


async def detect_media(
    file_path: Path,
    request_id: str | None = None,
    flow: str = "FL-08",
) -> DetectResponse:
    """Envía un archivo multimedia a {AI_SERVICE_URL}/api/v1/detect y valida DetectResponse."""
    base_url = settings.AI_SERVICE_URL.rstrip("/")
    if not base_url:
        raise RuntimeError("AI_SERVICE_URL no está configurada en Settings.")

    headers = {
        "X-Request-ID": request_id or uuid.uuid4().hex[:10],
        "X-Flow": flow,
    }
    ai_api_key = getattr(settings, "AI_API_KEY", "")
    if ai_api_key:
        headers["X-API-Key"] = ai_api_key

    async with httpx.AsyncClient(timeout=180.0) as client:
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f)}
            data = {"file_name": file_path.name}
            response = await client.post(
                f"{base_url}/api/v1/detect",
                headers=headers,
                files=files,
                data=data,
            )

    response.raise_for_status()
    body = response.json()
    payload = body.get("data", body)
    return DetectResponse.model_validate(payload)
