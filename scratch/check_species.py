import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
from sqlalchemy import text
from app.db.session import engine

async def main():
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'species'
            ORDER BY ordinal_position;
        """))
        for row in res.fetchall():
            print(row)

asyncio.run(main())
