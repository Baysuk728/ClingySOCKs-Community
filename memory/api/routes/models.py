"""
/models routes — Serve the centralised model registry.

The frontend fetches GET /models/available on startup to populate
model dropdowns, replacing the old hardcoded AVAILABLE_MODELS
constant and the legacy cloud service.

Set  MODEL_DISCOVERY=live  in .env to fetch real-time model lists
from each provider's API (Gemini, OpenAI, Anthropic, xAI, OpenRouter).
Results are cached for 1 hour (configurable via MODEL_CACHE_TTL).
"""

from fastapi import APIRouter
from src.model_registry import (
    get_available_models_async,
    get_provider_names,
    get_default_model,
    is_valid_model,
    get_configured_providers,
    invalidate_cache,
)

router = APIRouter()


@router.get("/available")
async def available_models():
    """
    Return all available models grouped by provider.

    Response shape:
    {
      "models": { "gemini": ["gemini/...", ...], "openai": [...], ... },
      "providers": { "gemini": "Gemini (Google)", ... },
      "defaults": { "gemini": "gemini/gemini-2.5-flash", ... },
      "configured": ["gemini", "openai", "claude", "openrouter"]
    }
    """
    models = await get_available_models_async()
    providers = get_provider_names()
    defaults = {provider: get_default_model(provider) for provider in models}
    configured = get_configured_providers()

    return {
        "models": models,
        "providers": providers,
        "defaults": defaults,
        "configured": configured,
    }


@router.post("/refresh")
async def refresh_models():
    """Force-refresh the model cache (clear TTL cache, re-fetch)."""
    invalidate_cache()
    models = await get_available_models_async(live=True)
    return {"refreshed": True, "providers": list(models.keys()), "total": sum(len(v) for v in models.values())}


@router.get("/validate/{model_id:path}")
async def validate_model(model_id: str):
    """Check if a model ID is in the curated registry."""
    return {"model_id": model_id, "valid": is_valid_model(model_id)}
