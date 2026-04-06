"""
Local auth provider — PostgreSQL-backed authentication for self-hosted deployments.

Uses bcrypt for password hashing and JWT for session tokens.
All data lives in the same PostgreSQL database as the rest of ClingySOCKs.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from src.auth.base import AuthProvider, UserInfo

# JWT config
_JWT_SECRET = os.getenv("JWT_SECRET", "")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "720"))  # 30 days default


def _get_jwt_secret() -> str:
    """Get or generate JWT secret. In production, set JWT_SECRET in .env."""
    if _JWT_SECRET:
        return _JWT_SECRET
    # Deterministic fallback for dev — NOT secure for production
    return "clingysocks-dev-jwt-secret-change-in-production"


class LocalAuthProvider(AuthProvider):
    """PostgreSQL-backed auth using the app_users table."""

    async def create_user(self, email: str, password: str) -> UserInfo:
        from src.db.session import get_session
        from src.db.auth_models import AppUser

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        user_id = str(uuid.uuid4())

        with get_session() as session:
            # Check for duplicate
            existing = session.query(AppUser).filter_by(email=email.lower()).first()
            if existing:
                raise ValueError(f"User with email '{email}' already exists")

            user = AppUser(
                id=user_id,
                email=email.lower(),
                password_hash=password_hash,
            )
            session.add(user)

        return UserInfo(user_id=user_id, email=email.lower())

    async def authenticate(self, email: str, password: str) -> tuple[UserInfo, str]:
        from src.db.session import get_session
        from src.db.auth_models import AppUser

        with get_session() as session:
            user = session.query(AppUser).filter_by(email=email.lower()).first()
            if not user:
                raise ValueError("Invalid email or password")

            if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
                raise ValueError("Invalid email or password")

            info = UserInfo(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
            )

        token = self._create_token(info)
        return info, token

    async def verify_token(self, token: str) -> UserInfo:
        try:
            payload = jwt.decode(token, _get_jwt_secret(), algorithms=[_JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")

        return UserInfo(
            user_id=payload["sub"],
            email=payload.get("email"),
            display_name=payload.get("name"),
        )

    async def get_user(self, user_id: str) -> Optional[UserInfo]:
        from src.db.session import get_session
        from src.db.auth_models import AppUser

        with get_session() as session:
            user = session.query(AppUser).filter_by(id=user_id).first()
            if not user:
                return None
            return UserInfo(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
            )

    @staticmethod
    def _create_token(user: UserInfo) -> str:
        payload = {
            "sub": user.user_id,
            "email": user.email,
            "name": user.display_name,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRY_HOURS),
        }
        return jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)
