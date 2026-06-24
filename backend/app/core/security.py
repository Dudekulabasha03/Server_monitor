"""JWT and password security utilities."""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from jose import JWTError, jwt
import bcrypt

from app.config import settings

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    # bcrypt has 72-byte limit; SHA-256 pre-hash removes the limit safely.
    digest = hashlib.sha256(plain.encode()).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    digest = hashlib.sha256(plain.encode()).digest()
    return bcrypt.checkpw(digest, hashed.encode())


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def create_refresh_token() -> tuple[str, str]:
    """Return (raw_token, hashed_token). Store hashed in DB, send raw to client."""
    raw = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
