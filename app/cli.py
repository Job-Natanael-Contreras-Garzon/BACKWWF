import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from app.core.logging import configure_logging
from app.db.session import engine
from app.worker.cron_anon import purge_anon_sessions


async def _run_purge_anon() -> dict[str, int]:
    try:
        summary = await purge_anon_sessions()
        return asdict(summary)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("purge-anon", help="Ejecuta la purga FL-30 de sesiones anónimas.")

    args = parser.parse_args(argv)
    if args.command == "purge-anon":
        result = asyncio.run(_run_purge_anon())
        sys.stdout.write(json.dumps(result) + "\n")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
