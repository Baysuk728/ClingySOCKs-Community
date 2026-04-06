"""
Auth provider factory — selects the correct implementation based on AUTH_PROVIDER env var.
"""

from __future__ import annotations

import os
from functools import lru_cache

from src.auth.base import AuthProvider

AUTH_PROVIDER_TYPE = "local"


@lru_cache(maxsize=1)
def get_auth_provider() -> AuthProvider:
    """
    Get the singleton auth provider instance.
    """
    from src.auth.local_auth import LocalAuthProvider
    return LocalAuthProvider()
