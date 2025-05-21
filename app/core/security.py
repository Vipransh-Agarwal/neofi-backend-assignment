from datetime import datetime, timedelta
import os
import uuid

import bcrypt
from jose import JWTError, jwt

# ─── Configurable settings ──────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret_key")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

_revoked_jti: set[str] = set()


# ─── Password hashing (bcrypt) ───────────────────────────────────────────────

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ─── Internal: JWT creation helpers ───────────────────────────────────────────

def _create_token(
    data: dict,
    expires_delta: timedelta,
    token_type: str,
) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + expires_delta

    jti = str(uuid.uuid4())
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "jti": jti,
            "type": token_type,
        }
    )
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token


def create_access_token(data: dict) -> str:
    return _create_token(
        data=data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )


def create_refresh_token(data: dict) -> str:
    return _create_token(
        data=data,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


# ─── Token decoding & revocation ─────────────────────────────────────────────

def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise

    token_type = payload.get("type")
    if token_type != expected_type:
        raise JWTError(f"Token is not a valid {expected_type} token")

    jti = payload.get("jti")
    if not jti or jti in _revoked_jti:
        raise JWTError("Token has been revoked or is invalid")

    return payload


def revoke_token(token: str) -> None:
    try:
        decoded = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
        jti = decoded.get("jti")
        if jti:
            _revoked_jti.add(jti)
    except Exception:
        pass


# ─── Convenience wrapper ─────────────────────────────────────────────────────

def decode_access_token(token: str) -> dict:
    """
    Shorthand for decode_token(token, expected_type="access").
    """
    return decode_token(token, expected_type="access")
