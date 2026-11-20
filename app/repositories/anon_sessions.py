from datetime import datetime

from sqlalchemy import select

from app.core.enums import AnonSessionStatus
from app.models.anon_session import AnonSession
from app.repositories.base import Repository


class AnonSessionRepository(Repository[AnonSession]):
    model = AnonSession

    async def get_by_token_hash(self, token_hash: str) -> AnonSession | None:
        return await self._first(select(AnonSession).where(AnonSession.token_hash == token_hash))

    async def list_expirable(self, now: datetime, limit: int = 500) -> list[AnonSession]:
        """Sesiones activas vencidas, para el cron FL-30."""
        stmt = (
            select(AnonSession)
            .where(AnonSession.status == AnonSessionStatus.ACTIVE, AnonSession.expires_at < now)
            .order_by(AnonSession.expires_at)
            .limit(limit)
        )
        return list(await self.session.scalars(stmt))
