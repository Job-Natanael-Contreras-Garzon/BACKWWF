import asyncio
import base64
import io
import sys
from pathlib import Path

from app.integrations.ai_client import detect_media


async def main(paths: list[str]) -> None:
    if not paths:
        print("Uso: python scripts/verify_ai_spike.py <archivo1> [archivo2 ...]")
        sys.exit(1)

    for raw_path in paths:
        file_path = Path(raw_path)
        print(f"-> Enviando {file_path.name} a AI_SERVICE_URL...")
        res = await detect_media(file_path)
        print(
            f"   OK: category={res.result.category}, "
            f"confidence={res.result.confidence}, "
            f"taxonomy={res.result.taxonomy}"
        )
        if res.evidence and res.evidence.image_base64:
            raw_bytes = base64.b64decode(res.evidence.image_base64)
            try:
                from PIL import Image

                img = Image.open(io.BytesIO(raw_bytes))
                img.verify()
                print(f"   Evidence Pillow OK: format={img.format}, size={img.size}")
            except ImportError:
                print(f"   Evidence base64 OK: {len(raw_bytes)} bytes (Pillow no instalado en imagen actual)")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
