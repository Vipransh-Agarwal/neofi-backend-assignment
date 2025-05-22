from datetime import datetime, timedelta
import os
import uuid

import bcrypt
import redis
from jose import JWTError, jwt

# ─── Configurable settings ──────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret_key")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# ─── Redis setup for revoked JTIs ───────────────────────────────────────────

# Connect to Redis on localhost:6379, database 0, return strings by default
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

# We will store each revoked JTI as its own key with an expiry.
# Key format: "revoked_jti:<jti>" → value: "" (empty), TTL = seconds until token expiry


# ─── Password hashing (bcrypt) ───────────────────────────────────────────────

def get_password_hash(password: str) -> str:
    """
    Hash the plaintext password with bcrypt and return a utf-8 string.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify that plain_password, when hashed, matches hashed_password.
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ─── Internal: JWT creation helpers ───────────────────────────────────────────

def _create_token(
    data: dict,
    expires_delta: timedelta,
    token_type: str,
) -> str:
    """
    Create a JWT that includes:
      - "exp" (expiry) = now (UTC) + expires_delta
      - "iat" (issued at) = now (UTC)
      - "jti" = a new UUID
      - "type" = either "access" or "refresh"
    """
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
    """
    Create a short‐lived access token (type="access").
    """
    return _create_token(
        data=data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )


def create_refresh_token(data: dict) -> str:
    """
    Create a long‐lived refresh token (type="refresh").
    """
    return _create_token(
        data=data,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


# ─── Token decoding & revocation (using Redis) ───────────────────────────────

def is_jti_revoked(jti: str) -> bool:
    """
    Return True if the given jti exists in Redis (i.e. it's been revoked).
    """
    try:
        return redis_client.exists(f"revoked_jti:{jti}") == 1
    except redis.exceptions.RedisError:
        # If Redis is down, we “fail open” (treat token as not revoked)
        return False


def revoke_token(token: str) -> None:
    """
    Decode the token (skipping expiry), extract its "jti", then
    store a Redis key "revoked_jti:<jti>" with TTL = time until token expiry.
    """
    try:
        decoded = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False},  # ignore expiration
        )
        jti = decoded.get("jti")
        exp_timestamp = decoded.get("exp")
        if jti and exp_timestamp:
            now_ts = int(datetime.utcnow().timestamp())
            ttl = exp_timestamp - now_ts
            if ttl > 0:
                redis_client.set(f"revoked_jti:{jti}", "", ex=ttl)
    except Exception:
        # If the token is invalid or missing claims, do nothing
        pass


def decode_token(token: str, expected_type: str) -> dict:
    """
    Decode and verify a JWT:
      1. Verify signature & expiration (jwt.decode).
      2. Check payload["type"] == expected_type.
      3. Check Redis: key "revoked_jti:<jti>" does not exist.
      4. Return the payload if all checks pass.
    Raises JWTError on any failure.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        # Signature invalid or expired
        raise

    token_type = payload.get("type")
    if token_type != expected_type:
        raise JWTError(f"Token is not a valid {expected_type} token")

    jti = payload.get("jti")
    if not jti or is_jti_revoked(jti):
        raise JWTError("Token has been revoked or is invalid")

    return payload


def decode_access_token(token: str) -> dict:
    """
    Convenience wrapper: decode_token(token, expected_type="access").
    """
    return decode_token(token, expected_type="access")
