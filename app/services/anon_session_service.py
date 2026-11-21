import secrets
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.enums import AnonSessionStatus
from app.core.errors import ConflictError, RateLimitError, UnauthorizedError
from app.core.logging import log_step
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import hash_token
from app.db.uow import UnitOfWork
from app.models.anon_session import AnonSession
from app.models.user import User
from app.schemas.anon_session import (
    AnonResourceCounts,
    AnonSessionAuthHint,
    AnonSessionCreateData,
    AnonSessionCurrentData,
    AnonSessionLimits,
    ClaimAnonSessionData,
    CloseAnonSessionData,
    RenamedCameraStation,
)

anon_session_rate_limiter = SlidingWindowRateLimiter(window_seconds=3600.0)
_ANON_RATE_LIMIT_MSG = "Has creado demasiadas sesiones temporales. Intenta más tarde."
_ANON_EXPIRED_MSG = "Tu sesión sin cuenta expiró; sus datos ya no están disponibles."


def _rename_with_suffix(code: str, n: int) -> str:
    suffix = f"-{n}"
    return f"{code[: 50 - len(suffix)]}{suffix}"


async def create_session(
    uow: UnitOfWork,
    *,
    client_ip: str,
    limiter: SlidingWindowRateLimiter = anon_session_rate_limiter,
) -> AnonSessionCreateData:
    with log_step("anon_session.create"):
        if not limiter.check_and_record(
            f"ip:{client_ip}", settings.ANON_SESSION_RATE_LIMIT_PER_HOUR
        ):
            raise RateLimitError("RATE_LIMITED", _ANON_RATE_LIMIT_MSG)

        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=settings.ANON_SESSION_TTL_HOURS)
        data_retention = bool(await uow.settings.get_value("anon_data_retention", True))

        uow.anon_sessions.add(
            AnonSession(
                token_hash=hash_token(raw_token),
                created_at=now,
                last_activity_at=now,
                expires_at=expires_at,
                status=AnonSessionStatus.ACTIVE,
            )
        )
        await uow.commit()
        return AnonSessionCreateData(
            anon_token=raw_token,
            expires_at=expires_at,
            data_retention=data_retention,
        )


async def get_current(uow: UnitOfWork, session: AnonSession) -> AnonSessionCurrentData:
    with log_step("anon_session.current", anon_session_id=str(session.id)):
        cls_count, cam_count, proj_count = await uow.anon_sessions.count_active_resources(
            session.id
        )
        data_retention = bool(await uow.settings.get_value("anon_data_retention", True))
        return AnonSessionCurrentData(
            status=session.status,
            expires_at=session.expires_at,
            data_retention=data_retention,
            counts=AnonResourceCounts(
                classifications=cls_count,
                camera_stations=cam_count,
                projects=proj_count,
            ),
            limits=AnonSessionLimits(
                max_files=settings.ANON_MAX_FILES,
                max_camera_stations=settings.ANON_MAX_CAMERAS,
                used_files=cls_count,
                used_camera_stations=cam_count,
            ),
        )


async def get_auth_hint(uow: UnitOfWork, anon_token: str | None) -> AnonSessionAuthHint | None:
    """Devuelve resumen de sesión anónima activa para register/login, o None sin fallar."""
    if not anon_token or not anon_token.strip():
        return None
    session = await uow.anon_sessions.get_by_token_hash(hash_token(anon_token.strip()))
    now = datetime.now(UTC)
    if session is None or session.status != AnonSessionStatus.ACTIVE or session.expires_at <= now:
        return None
    cls_count, cam_count, proj_count = await uow.anon_sessions.count_active_resources(session.id)
    return AnonSessionAuthHint(
        has_data=(cls_count + cam_count + proj_count) > 0,
        counts=AnonResourceCounts(
            classifications=cls_count,
            camera_stations=cam_count,
            projects=proj_count,
        ),
    )


async def _plan_camera_renames(
    uow: UnitOfWork,
    anon_session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[list[RenamedCameraStation], dict[uuid.UUID, str]]:
    existing_lower = {
        c.lower() for c in await uow.camera_stations.list_active_codes_for_user(user_id)
    }
    anon_cameras = await uow.camera_stations.list_active_for_anon(anon_session_id)
    used_lower = existing_lower | {code.lower() for _, code in anon_cameras}

    renames: list[RenamedCameraStation] = []
    rename_map: dict[uuid.UUID, str] = {}
    for cam_id, code in anon_cameras:
        if code.lower() not in existing_lower:
            continue
        suffix_num = 2
        while True:
            candidate = _rename_with_suffix(code, suffix_num)
            if candidate.lower() not in used_lower:
                break
            suffix_num += 1
        used_lower.add(candidate.lower())
        existing_lower.add(candidate.lower())
        renames.append(RenamedCameraStation(id=cam_id, old_code=code, new_code=candidate))
        rename_map[cam_id] = candidate
    return renames, rename_map


async def claim_session(
    uow: UnitOfWork,
    *,
    user: User,
    anon_token: str | None,
) -> ClaimAnonSessionData:
    with log_step("anon_session.claim", user_id=str(user.id)):
        if not anon_token or not anon_token.strip():
            raise UnauthorizedError("ANON_SESSION_EXPIRED", _ANON_EXPIRED_MSG)

        # CB-70/71: solo reclama la sesión exacta del token recibido, bloqueada con FOR UPDATE.
        session = await uow.anon_sessions.get_by_token_hash(
            hash_token(anon_token.strip()), for_update=True
        )
        if session is None:
            raise UnauthorizedError("ANON_SESSION_EXPIRED", _ANON_EXPIRED_MSG)

        if session.status == AnonSessionStatus.CLAIMED:
            if session.claimed_by_user_id == user.id:
                return ClaimAnonSessionData(
                    claimed=AnonResourceCounts(classifications=0, camera_stations=0, projects=0),
                    renamed_camera_stations=[],
                )
            raise ConflictError(
                "ANON_SESSION_ALREADY_CLAIMED",
                "Estos datos ya se asociaron a otra cuenta.",
            )

        now = datetime.now(UTC)
        if session.status != AnonSessionStatus.ACTIVE or session.expires_at <= now:
            raise UnauthorizedError("ANON_SESSION_EXPIRED", _ANON_EXPIRED_MSG)

        # Orden consistente (AnonSession -> User) para serializar claims concurrentes sin deadlocks.
        await uow.users.lock_for_update(user.id)

        cls_count, cam_count, proj_count = await uow.anon_sessions.count_active_resources(
            session.id
        )
        renames, rename_map = await _plan_camera_renames(uow, session.id, user.id)
        await uow.anon_sessions.transfer_to_user(session.id, user.id, rename_map)
        session.status = AnonSessionStatus.CLAIMED
        session.claimed_by_user_id = user.id
        session.claimed_at = now
        await uow.commit()

        return ClaimAnonSessionData(
            claimed=AnonResourceCounts(
                classifications=cls_count,
                camera_stations=cam_count,
                projects=proj_count,
            ),
            renamed_camera_stations=renames,
        )


async def close_session(uow: UnitOfWork, session: AnonSession) -> CloseAnonSessionData:
    with log_step("anon_session.close", anon_session_id=str(session.id)):
        has_any, has_non_retained = await uow.anon_sessions.summarize_retention(session.id)
        if not has_any:
            data_retained = bool(await uow.settings.get_value("anon_data_retention", True))
        else:
            data_retained = not has_non_retained

        session.status = AnonSessionStatus.EXPIRED
        await uow.commit()
        return CloseAnonSessionData(status="expired", data_retained=data_retained)
