# app/models/base.py
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs

class Base(AsyncAttrs, DeclarativeBase):
    """Clase base para todos los modelos de SQLAlchemy 2.0"""
    pass
