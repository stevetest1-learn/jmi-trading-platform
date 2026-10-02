import datetime as dt

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(account_id: int, username: str) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(account_id),
        "username": username,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
