"""Unidad de trabajo: una transacción por caso de uso, y el ``commit`` solo lo pide el servicio.

    async with UnitOfWork() as uow:
        camera = await uow.camera_stations.get_owned(camera_id, owner)
        ...
        await uow.commit()

Si el bloque termina sin ``commit()`` o con una excepción, todo se revierte.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import async_session_maker
from app.repositories.anon_sessions import AnonSessionRepository
from app.repositories.camera_stations import CameraStationRepository
from app.repositories.classifications import ClassificationBatchRepository, ClassificationRepository
from app.repositories.operations import (
    AdminAuditLogRepository,
    AnonPurgeRunRepository,
    DesktopImportRepository,
    EmailLogRepository,
    SystemSettingRepository,
)
from app.repositories.projects import ProjectRepository
from app.repositories.users import (
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)


class UnitOfWork:
    session: AsyncSession

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = async_session_maker
    ) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.users = UserRepository(self.session)
        self.refresh_tokens = RefreshTokenRepository(self.session)
        self.password_reset_tokens = PasswordResetTokenRepository(self.session)
        self.anon_sessions = AnonSessionRepository(self.session)
        self.camera_stations = CameraStationRepository(self.session)
        self.projects = ProjectRepository(self.session)
        self.batches = ClassificationBatchRepository(self.session)
        self.classifications = ClassificationRepository(self.session)
        self.desktop_imports = DesktopImportRepository(self.session)
        self.audit_log = AdminAuditLogRepository(self.session)
        self.settings = SystemSettingRepository(self.session)
        self.purge_runs = AnonPurgeRunRepository(self.session)
        self.email_log = EmailLogRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            await self.session.rollback()  # no-op si ya hubo commit; revierte todo lo demás
        finally:
            await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
