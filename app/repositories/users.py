import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update

from app.models.user import PasswordResetToken, RefreshToken, User
from app.repositories.base import Repository


class UserRepository(Repository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        """Sin distinguir mayúsculas, igual que el índice único (CB-72)."""
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return await self._first(stmt)


class RefreshTokenRepository(Repository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        if for_update:
            stmt = stmt.with_for_update()
        return await self._first(stmt)

    async def revoke_if_active(self, token_id: uuid.UUID, now: datetime) -> bool:
        """Revoca atómicamente solo si sigue activo (evita carreras de rotación)."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(getattr(result, "rowcount", 0) or 0) > 0

    async def revoke_all_for_user(self, user_id: uuid.UUID, now: datetime) -> int:
        """Reuso de un token rotado o cambio de contraseña: se revocan todos (CB-78)."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_all_except(self, user_id: uuid.UUID, keep_token_id: uuid.UUID) -> int:
        """Elimina los demás tokens: evita que S2 dispare CB-78 contra S1 tras me/password."""
        result = await self.session.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.id != keep_token_id,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)


class PasswordResetTokenRepository(Repository[PasswordResetToken]):
    model = PasswordResetToken

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return await self._first(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )

    async def invalidate_pending_for_user(self, user_id: uuid.UUID, now: datetime) -> int:
        """Al emitir un token nuevo, los anteriores sin usar dejan de servir (CB-74)."""
        result = await self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        return int(getattr(result, "rowcount", 0) or 0)
