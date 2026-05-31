from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://avnadmin:AVNS_zOJVLKeGTsRv-AwnrlP@pg-df37a89-contrerasjob123-fc4e.l.aivencloud.com:18981/wwfDataBase?ssl=require")

engine = create_async_engine(DATABASE_URL, echo=True)

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Generador de dependencias de la base de datos para FastAPI.
    Se agregó manejo explícito de transacciones para evitar ROLLBACKs implícitos.
    """
    session = async_session_maker()
    try:
        yield session
        # Si la petición termina sin errores, forzamos un commit de cualquier
        # transacción residual (como la generada por el `db.refresh()`)
        await session.commit()
    except Exception:
        # Si hubo cualquier error en la ruta, hacemos rollback
        await session.rollback()
        raise
    finally:
        # Nos aseguramos de cerrar la sesión y devolver la conexión al pool
        await session.close()
