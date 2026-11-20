import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.uow import UnitOfWork
from app.models.user import User


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
