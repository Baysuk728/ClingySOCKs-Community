"""
Auth provider abstraction for ClingySOCKs.

Uses local PostgreSQL-backed auth.
"""

from src.auth.base import AuthProvider, UserInfo
from src.auth.factory import get_auth_provider

__all__ = ["AuthProvider", "UserInfo", "get_auth_provider"]
