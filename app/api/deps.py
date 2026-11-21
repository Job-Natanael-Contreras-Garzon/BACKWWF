import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import settings
from app.core.enums import AnonSessionStatus
from app.core.errors import BusinessRuleError, ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token, hash_token
from app.db.uow import UnitOfWork
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import LocalStorage
from app.models.anon_session import AnonSession
from app.models.user import User
from app.services.policies import Owner


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    session_id: uuid.UUID | None


async def get_uow() -> AsyncIterator[UnitOfWork]:
    async with UnitOfWork() as uow:
        yield uow


UoWDep = Annotated[UnitOfWork, Depends(get_uow)]


async def get_current_auth(
    uow: UoWDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    if not authorization:
        raise UnauthorizedError("AUTH_REQUIRED", "Debes iniciar sesión para continuar.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("AUTH_REQUIRED", "Debes iniciar sesión para continuar.")

    payload = decode_access_token(token.strip())
    user_id = uuid.UUID(str(payload["sub"]))
    raw_sid = payload.get("sid")
    session_id: uuid.UUID | None = None
    if raw_sid is not None:
        try:
            session_id = uuid.UUID(str(raw_sid))
        except ValueError as exc:
            raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token no es válido.") from exc

    user = await uow.users.get(user_id)
    if user is None:
        raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token no es válido.")
    if not user.is_active:
        raise ForbiddenError(
            "ACCOUNT_DISABLED", "Tu cuenta está desactivada. Contacta al administrador."
        )
    return AuthContext(user=user, session_id=session_id)


AuthContextDep = Annotated[AuthContext, Depends(get_current_auth)]


async def get_current_user(auth: AuthContextDep) -> User:
    return auth.user


CurrentUserDep = Annotated[User, Depends(get_current_user)]

_ANON_EXPIRED_MSG = "Tu sesión sin cuenta expiró; sus datos ya no están disponibles."


async def get_anon_session(
    uow: UoWDep,
    x_anon_token: Annotated[str | None, Header(alias="X-Anon-Token")] = None,
) -> AnonSession:
    if not x_anon_token or not x_anon_token.strip():
        raise UnauthorizedError("ANON_SESSION_EXPIRED", _ANON_EXPIRED_MSG)

    session = await uow.anon_sessions.get_by_token_hash(hash_token(x_anon_token.strip()))
    now = datetime.now(UTC)
    if session is None or session.status != AnonSessionStatus.ACTIVE or session.expires_at <= now:
        raise UnauthorizedError("ANON_SESSION_EXPIRED", _ANON_EXPIRED_MSG)

    if (now - session.last_activity_at).total_seconds() >= 60:
        session.last_activity_at = now
        session.expires_at = now + timedelta(hours=settings.ANON_SESSION_TTL_HOURS)
        # Commit inmediato para que un rollback posterior del UoW no deshaga el touch deslizante.
        await uow.commit()

    return session


AnonSessionDep = Annotated[AnonSession, Depends(get_anon_session)]


async def get_owner(
    uow: UoWDep,
    authorization: Annotated[str | None, Header()] = None,
    x_anon_token: Annotated[str | None, Header(alias="X-Anon-Token")] = None,
) -> Owner:
    if authorization is not None:
        auth = await get_current_auth(uow, authorization)
        return Owner(user_id=auth.user.id)
    if x_anon_token is not None:
        anon = await get_anon_session(uow, x_anon_token)
        return Owner(anon_session_id=anon.id)
    raise UnauthorizedError("AUTH_REQUIRED", "Debes iniciar sesión para continuar.")


OwnerDep = Annotated[Owner, Depends(get_owner)]


async def get_optional_owner(
    uow: UoWDep,
    authorization: Annotated[str | None, Header()] = None,
    x_anon_token: Annotated[str | None, Header(alias="X-Anon-Token")] = None,
) -> Owner | None:
    """Lecturas públicas: sin credenciales = None; credenciales inválidas siguen dando 401."""
    if authorization is None and x_anon_token is None:
        return None
    return await get_owner(uow, authorization, x_anon_token)


OptionalOwnerDep = Annotated[Owner | None, Depends(get_optional_owner)]


def get_storage() -> StorageBackend:
    """Fotogramas (DD-3). Los tests lo reemplazan con un storage en un directorio temporal."""
    return LocalStorage(settings.STORAGE_LOCAL_PATH)


StorageDep = Annotated[StorageBackend, Depends(get_storage)]


def parse_if_match(raw: str) -> int:
    """Versión para el bloqueo optimista (CB-15). Acepta ``3``, ``"3"`` o ``W/"3"``."""
    cleaned = raw.strip().removeprefix("W/").strip('"')
    if not cleaned.isdigit():
        raise BusinessRuleError("VALIDATION_ERROR", "If-Match debe ser la versión del recurso.")
    return int(cleaned)
