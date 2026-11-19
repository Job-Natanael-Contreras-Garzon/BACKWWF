import asyncio
import asyncpg

from app.core.config import settings


async def check_schema() -> None:
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(dsn)

    rows = await conn.fetch("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'users';
    """)

    print("Columnas en la tabla 'users':")
    for row in rows:
        print(f"- {row['column_name']}: {row['data_type']}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(check_schema())
