"""
API Authentication middleware.

Supports local backend auth: API key from .env OR JWT bearer token.

Usage:
    Set MEMORY_API_KEY in .env for simple API key auth.
    Or use Bearer token with JWT (local).
"""

import os
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from src.auth.base import UserInfo

API_KEY = os.getenv("MEMORY_API_KEY", "")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


async def require_api_key(
    api_key: Optional[str] = Security(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> str:
    """
    Validate authentication via API key or Bearer token.

    Priority:
      1. X-API-Key header (simple shared secret)
      2. Bearer token (JWT)
      3. If MEMORY_API_KEY is not set, auth is disabled (dev mode)
    """
    # 1. API key check (if configured)
    if API_KEY:
        if api_key and api_key == API_KEY:
            return api_key
    elif not bearer:
        # No API key configured and no bearer token → dev mode passthrough
        return "dev-mode"

    # 2. Bearer token check
    if bearer:
        try:
            from src.auth import get_auth_provider
            provider = get_auth_provider()
            user_info = await provider.verify_token(bearer.credentials)
            return user_info.user_id
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid bearer token")

    # 3. API key was configured but not provided / didn't match
    if API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return "dev-mode"


async def get_current_user(
    api_key: Optional[str] = Security(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> UserInfo:
    """
    Get the authenticated user info. For routes that need user context.

    Falls back to a default user in dev mode.
    """
    if bearer:
        try:
            from src.auth import get_auth_provider
            provider = get_auth_provider()
            return await provider.verify_token(bearer.credentials)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid bearer token")

    if API_KEY and api_key and api_key == API_KEY:
        return UserInfo(user_id="local-user", email=None)

    if not API_KEY:
        return UserInfo(user_id="local-user", email=None)

    raise HTTPException(status_code=401, detail="Authentication required")
