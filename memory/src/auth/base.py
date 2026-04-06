"""
Abstract auth provider interface.

All auth backends must implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class UserInfo:
    """Authenticated user context."""
    user_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None


class AuthProvider(ABC):
    """
    Abstract authentication provider.

    Implementations:
      - LocalAuthProvider  : PostgreSQL-backed (self-hosted)
    """

    @abstractmethod
    async def verify_token(self, token: str) -> UserInfo:
        """Verify a bearer token and return user info. Raises on failure."""
        ...

    @abstractmethod
    async def create_user(self, email: str, password: str) -> UserInfo:
        """Register a new user. Raises on duplicate email."""
        ...

    @abstractmethod
    async def authenticate(self, email: str, password: str) -> tuple[UserInfo, str]:
        """
        Authenticate with email + password.
        Returns (user_info, token).
        """
        ...

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[UserInfo]:
        """Lookup user by ID. Returns None if not found."""
        ...
