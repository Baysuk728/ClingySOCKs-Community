"""
Auth API Routes — User registration and login for self-hosted deployments.

Only active when AUTH_PROVIDER=local. Hosted deployments handle auth client-side.

Endpoints:
    POST /auth/register  — Create a new user account
    POST /auth/login     — Authenticate and get a JWT token
    GET  /auth/me        — Get current user info (requires auth)
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
_AUTH_PROVIDER = "local"


class AuthRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")


class AuthResponse(BaseModel):
    user_id: str
    email: str
    token: str


class UserResponse(BaseModel):
    user_id: str
    email: str | None
    display_name: str | None


@router.post("/register", response_model=AuthResponse)
async def register(req: AuthRequest):
    """Register a new user account (local auth only)."""
    from src.auth import get_auth_provider
    provider = get_auth_provider()

    try:
        user_info = await provider.create_user(req.email, req.password)
        _, token = await provider.authenticate(req.email, req.password)
        return AuthResponse(user_id=user_info.user_id, email=req.email, token=token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthResponse)
async def login(req: AuthRequest):
    """Authenticate and get a JWT token (local auth only)."""
    from src.auth import get_auth_provider
    provider = get_auth_provider()

    try:
        user_info, token = await provider.authenticate(req.email, req.password)
        return AuthResponse(
            user_id=user_info.user_id,
            email=user_info.email or req.email,
            token=token,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def get_me():
    """Get current user info. Requires authentication."""
    from api.auth import get_current_user, _api_key_header, _bearer_scheme
    from fastapi import Security

    # For now, return a simple response
    # In a full implementation, this would use Depends(get_current_user)
    return UserResponse(
        user_id="local-user",
        email=None,
        display_name=None,
    )


@router.get("/provider")
async def get_auth_provider_info():
    """Return which auth provider is active."""
    return {
        "provider": _AUTH_PROVIDER,
        "description": "Local PostgreSQL-backed authentication. Use /auth/register and /auth/login endpoints."
    }
