"""
Local Vault API Routes — BYOK key management for self-hosted deployments.

Drop-in replacement for vault.py routes when AUTH_PROVIDER=local.
Keys are stored in the database (api_keys table) instead of the cloud vault.

Endpoints:
    GET  /vault/mode              — Get vault mode info
    POST /vault/keys              — Save/update an API key
    GET  /vault/keys              — List keys (masked)
    DELETE /vault/keys/{provider}  — Delete a key
    POST /vault/keys/test         — Test an API key
    GET  /vault/database/status   — Get database connection status
    POST /vault/cache/clear       — Clear vault cache
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


class SaveKeyRequest(BaseModel):
    provider: str = Field(..., description="Provider name: openrouter, gemini, openai, anthropic, xai, elevenlabs, google_tts, search")
    api_key: str = Field(..., description="The raw API key to encrypt and store")
    user_id: str = Field("local-user", description="User ID (defaults to local-user for self-hosted)")
    search_provider: Optional[str] = Field(None, description="For search keys: exa, tavily, brave, serpapi")


class DeleteKeyRequest(BaseModel):
    user_id: str = Field("local-user", description="User ID")


class TestKeyRequest(BaseModel):
    provider: str = Field(..., description="Provider to test")
    api_key: str = Field(..., description="Raw API key to test")


# ─── Mode Info ────────────────────────────────────

@router.get("/mode")
async def get_vault_mode():
    return {
        "mode": "local",
        "env_fallback": True,
        "description": (
            "Self-hosted mode — keys stored in PostgreSQL. "
            "Environment variables are used as fallback."
        ),
    }


# ─── Key Management ──────────────────────────────

@router.post("/keys")
async def save_key(req: SaveKeyRequest):
    from src.integrations.local_vault import local_vault

    valid_providers = {"openrouter", "gemini", "openai", "anthropic", "xai", "elevenlabs", "google_tts", "search"}
    if req.provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider. Must be one of: {', '.join(sorted(valid_providers))}"
        )

    masked = await local_vault.save_key(
        user_id=req.user_id,
        provider=req.provider,
        api_key=req.api_key,
        search_provider=req.search_provider,
    )

    return {"success": True, "provider": req.provider, "maskedKey": masked}


@router.get("/keys")
async def list_keys(user_id: str = "local-user"):
    from src.integrations.local_vault import local_vault
    keys = await local_vault.list_keys_masked(user_id)
    return {"keys": keys}


@router.delete("/keys/{provider}")
async def delete_key(provider: str, req: DeleteKeyRequest):
    from src.integrations.local_vault import local_vault
    await local_vault.delete_key(req.user_id, provider)
    return {"success": True, "provider": provider}


@router.post("/keys/test")
async def test_key(req: TestKeyRequest):
    """Test an API key by making a minimal API call."""
    try:
        if req.provider in ("openrouter", "openai"):
            import httpx
            base = "https://openrouter.ai/api/v1" if req.provider == "openrouter" else "https://api.openai.com/v1"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
            if resp.status_code == 200:
                return {"success": True, "message": f"{req.provider} key is valid"}
            return {"success": False, "error": f"API returned {resp.status_code}: {resp.text[:200]}"}

        elif req.provider == "gemini":
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={req.api_key}"
                )
            if resp.status_code == 200:
                return {"success": True, "message": "Gemini key is valid"}
            return {"success": False, "error": f"API returned {resp.status_code}"}

        elif req.provider == "anthropic":
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": req.api_key, "anthropic-version": "2023-06-01"},
                )
            if resp.status_code == 200:
                return {"success": True, "message": "Anthropic key is valid"}
            return {"success": False, "error": f"API returned {resp.status_code}"}

        elif req.provider == "xai":
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {req.api_key}"},
                )
            if resp.status_code == 200:
                return {"success": True, "message": "xAI key is valid"}
            return {"success": False, "error": f"API returned {resp.status_code}"}

        elif req.provider == "elevenlabs":
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers={"xi-api-key": req.api_key},
                )
            if resp.status_code == 200:
                return {"success": True, "message": "ElevenLabs key is valid"}
            return {"success": False, "error": f"API returned {resp.status_code}"}

        else:
            return {"success": False, "error": f"Testing not supported for provider: {req.provider}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Database Status ─────────────────────────────

@router.get("/database/status")
async def get_database_status():
    from src.db.session import get_db_source, get_db_host, check_connection
    return {
        "source": get_db_source(),
        "host": get_db_host(),
        "mode": "local",
        "connected": check_connection(),
    }


# ─── Cache Management ────────────────────────────

@router.post("/cache/clear")
async def clear_cache(user_id: str = "local-user"):
    from src.integrations.local_vault import local_vault
    await local_vault.invalidate_cache(user_id)
    return {"success": True}
