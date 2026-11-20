"""Importaciones de escritorio, auditoría del admin, configuración, purgas y correos."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.core.enums import EmailStatus, EmailType, ImportStatus
from app.models.admin import AdminAuditLog, AnonPurgeRun, EmailLog, SystemSetting
from app.models.desktop_import import DesktopImport
from app.repositories.base import Repository


class DesktopImportRepository(Repository[DesktopImport]):
    model = DesktopImport

    async def get_owned(self, import_id: uuid.UUID, user_id: uuid.UUID) -> DesktopImport | None:
        stmt = select(DesktopImport).where(
            DesktopImport.id == import_id,
            DesktopImport.owner_user_id == user_id,
            DesktopImport.is_deleted.is_(False),
        )
        return await self._first(stmt)

    async def find_completed(
        self, camera_station_id: uuid.UUID, package_sha256: str
    ) -> DesktopImport | None:
        """CB-82: el mismo paquete ya se importó en esa cámara."""
        stmt = select(DesktopImport).where(
            DesktopImport.camera_station_id == camera_station_id,
            DesktopImport.package_sha256 == package_sha256,
            DesktopImport.status == ImportStatus.COMPLETED,
            DesktopImport.is_deleted.is_(False),
        )
        return await self._first(stmt)


class AdminAuditLogRepository(Repository[AdminAuditLog]):
    """Solo inserción (``add``) y lectura paginada: la auditoría no se edita ni se borra."""

    model = AdminAuditLog

    async def list_recent(
        self, page: int = 1, page_size: int = 50
    ) -> tuple[list[AdminAuditLog], int]:
        stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id)
        return await self._page(stmt, page, page_size)


class SystemSettingRepository(Repository[SystemSetting]):
    model = SystemSetting

    async def get_value(self, key: str, default: Any = None) -> Any:
        setting = await self.session.get(SystemSetting, key)
        return default if setting is None else setting.value


class AnonPurgeRunRepository(Repository[AnonPurgeRun]):
    model = AnonPurgeRun


class EmailLogRepository(Repository[EmailLog]):
    model = EmailLog

    async def count_since(self, email_type: EmailType, since: datetime) -> int:
        """Correos que cuentan para la cuota diaria o mensual (CB-76)."""
        stmt = select(func.count()).where(
            EmailLog.type == email_type,
            EmailLog.created_at >= since,
            EmailLog.status.in_((EmailStatus.QUEUED, EmailStatus.SENT)),
        )
        return int(await self.session.scalar(stmt) or 0)
