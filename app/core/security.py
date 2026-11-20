import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import UnauthorizedError

# Hash cost-12 precalculado para verificación en tiempo constante si el correo no existe.
DUMMY_BCRYPT_HASH: str = bcrypt.hashpw(
    b"wwf-constant-time-dummy", bcrypt.gensalt(rounds=12)
).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica contraseña en texto plano contra bcrypt sin fallar si supera 72 bytes."""
    if not plain_password or not hashed_password:
        return False
    password_bytes = plain_password.encode("utf-8")
    too_long = len(password_bytes) > 72
    probe = b"x" * 72 if too_long else password_bytes
    try:
        matched = bcrypt.checkpw(probe, hashed_password.encode("utf-8"))
    except ValueError:
        return False
    return False if too_long else matched


def get_password_hash(password: str) -> str:
    """Genera hash bcrypt cost 12; rechaza contraseñas mayores a 72 bytes UTF-8."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("La contraseña supera el máximo de 72 bytes.")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def hash_token(token: str) -> str:
    """Digest SHA-256 hexadecimal para almacenar refresh tokens sin texto plano."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    subject: str | uuid.UUID,
    session_id: uuid.UUID | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    if session_id is not None:
        payload["sid"] = str(session_id)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: str | uuid.UUID,
    token_id: uuid.UUID | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "jti": str(token_id or uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_jwt(token: str, *, secret: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("AUTH_TOKEN_EXPIRED", "Tu sesión ha expirado.") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token no es válido.") from exc

    if payload.get("type") != expected_type or not payload.get("sub"):
        raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token no es válido.")
    try:
        uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token no es válido.") from exc
    return dict(payload)


def decode_access_token(token: str) -> dict[str, Any]:
    return _decode_jwt(token, secret=settings.SECRET_KEY, expected_type="access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    return _decode_jwt(token, secret=settings.REFRESH_SECRET_KEY, expected_type="refresh")
