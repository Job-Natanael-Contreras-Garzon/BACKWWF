import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, Boolean, func, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.models.base import Base

class Individual(Base):
    __tablename__ = "individuals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    species_id: Mapped[Optional[int]] = mapped_column(ForeignKey("species.id", ondelete="SET NULL"))
    
    # NUEVO CAMPO
    is_verified: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)
    
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    species: Mapped[Optional["Species"]] = relationship(back_populates="individuals", lazy="selectin")
