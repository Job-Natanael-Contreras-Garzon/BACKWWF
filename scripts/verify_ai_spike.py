"""SPIKE-01 · CA-5: llama a la IA real (o ia-fake) con archivos y muestra qué entendió el back.

Uso (desde la raíz del repo; lee AI_SERVICE_URL / AI_API_KEY / AI_TIMEOUT_SECONDS de Settings):
    python -m scripts.verify_ai_spike <archivo> [<archivo> ...]

Con ia-fake el escenario se elige por el nombre del archivo (_blank, _toolong, _busy, _crash, ...).
Para probar una clave incorrecta: AI_API_KEY=otra python -m scripts.verify_ai_spike <archivo>
"""

import asyncio
import base64
import io
import sys
import uuid
from pathlib import Path

from PIL import Image

from app.core.config import settings
from app.integrations.ai_client import AiClientError, detect_media


def _evidence_summary(image_base64: str) -> str:
    with Image.open(io.BytesIO(base64.b64decode(image_base64))) as image:
        image.load()
        return f"{image.format} {image.size[0]}x{image.size[1]}"


async def _verify(path: Path) -> None:
    request_id = f"spike-{uuid.uuid4().hex[:8]}"
    try:
        data = await detect_media(path, request_id=request_id)
    except AiClientError as exc:
        print(
            f"ERROR {path.name}: code={exc.code} ia_code={exc.ia_code} "
            f"http={exc.http_status} request_id={request_id}"
        )
        return

    taxon = data.result.taxonomy
    label = f"{taxon.scientific_name} ({taxon.rank.value}, {taxon.common_name})" if taxon else "-"
    evidence = _evidence_summary(data.evidence.image_base64) if data.evidence else "sin evidencia"
    print(
        f"OK    {path.name}: category={data.result.category.value} taxon={label} "
        f"confidence={data.result.confidence} low_evidence={data.analysis.low_evidence} "
        f"truncated_at_seconds={data.analysis.truncated_at_seconds} evidence={evidence} "
        f"request_id={request_id}"
    )


async def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__)
        return 2
    print(f"IA: {settings.AI_SERVICE_URL} · timeout {settings.AI_TIMEOUT_SECONDS} s")
    for raw in paths:
        await _verify(Path(raw))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
