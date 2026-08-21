import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
from sqlalchemy import text
from app.db.session import engine


async def migrate():
    statements = [
        """
        CREATE TABLE IF NOT EXISTS media_files (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            station_id UUID NOT NULL REFERENCES camera_stations(id) ON DELETE CASCADE,
            file_type VARCHAR(20) NOT NULL,
            file_url VARCHAR(500) NOT NULL,
            original_filename VARCHAR(255),
            duration_seconds INTEGER,
            file_size_mb NUMERIC(10, 2),
            capture_date TIMESTAMP WITH TIME ZONE,
            metadata_extra JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            is_deleted BOOLEAN DEFAULT false,
            deleted_at TIMESTAMP WITH TIME ZONE
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_media_files_station_id ON media_files (station_id)",
        "CREATE INDEX IF NOT EXISTS ix_media_files_is_deleted ON media_files (is_deleted)",
        "ALTER TABLE species ADD COLUMN IF NOT EXISTS media_file_id UUID REFERENCES media_files(id) ON DELETE SET NULL",
        "ALTER TABLE species ADD COLUMN IF NOT EXISTS family VARCHAR(100)",
        "ALTER TABLE species ADD COLUMN IF NOT EXISTS genus VARCHAR(100)",
        "ALTER TABLE species ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()",
        "ALTER TABLE species ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT false",
        "ALTER TABLE species ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE",
        "CREATE INDEX IF NOT EXISTS ix_species_media_file_id ON species (media_file_id)",
        "CREATE INDEX IF NOT EXISTS ix_species_family ON species (family)",
        "CREATE INDEX IF NOT EXISTS ix_species_genus ON species (genus)",
        "CREATE INDEX IF NOT EXISTS ix_species_is_deleted ON species (is_deleted)"
    ]

    async with engine.begin() as conn:
        for stmt in statements:
            clean_stmt = stmt.strip()
            if clean_stmt:
                print(f"[MIGRATION] Ejecutando: {clean_stmt[:50]}...")
                await conn.execute(text(clean_stmt))
        print("[MIGRATION] Migración de Fase 4 ejecutada exitosamente.")


if __name__ == "__main__":
    asyncio.run(migrate())
