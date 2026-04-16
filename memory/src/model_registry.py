"""
Model Registry — Single Source of Truth for Available LLM Models

Every model dropdown, validation check, and default selection should
reference this module.  No other file should hardcode model lists.

Updating models?  Edit ONLY the `_CURATED_MODELS` dict below.
The backend `/models/available` endpoint and the frontend both
read from this single registry.

Live discovery:
  The registry can also fetch real-time model lists from provider APIs
  (Gemini, OpenAI, Anthropic, xAI, OpenRouter).  Discovered models are
  merged with the curated list.  Set  MODEL_DISCOVERY=live  in .env to
  enable (cached for 1 hour).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import httpx

# ── Curated Model List ────────────────────────────────
# Provider key → list of LiteLLM model IDs (with provider prefix).
# Keep this list SHORT: only models you actually want in dropdowns.
# Ordered by recommendation (first = default for that provider).
# When live discovery is enabled, these are shown first (pinned),
# and newly discovered models are appended after them.

_CURATED_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
        "gemini/gemini-3-flash-preview",
        "gemini/gemini-3.1-pro-preview",
        "gemini/gemini-3.1-flash-live-preview",
    ],
    "openai": [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/gpt-5",
        "openai/o3",
        "openai/o4-mini",
        "openai/gpt-4.1",
    ],
    "claude": [
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-opus-4-6",
        "anthropic/claude-sonnet-4-5-20250514",
        "anthropic/claude-haiku-4-5-20250414",
    ],
    "grok": [
        "xai/grok-2-1212",
        "xai/grok-2-vision-1212",
        "xai/grok-beta",
    ],
    "openrouter": [
        # Popular picks — these appear first (pinned) in dropdown
        "openrouter/mistralai/mistral-large-2512",
        "openrouter/mistralai/mistral-medium-3.1",
        "openrouter/meta-llama/llama-4-maverick",
        "openrouter/deepseek/deepseek-r1",
        "openrouter/deepseek/deepseek-chat",
        "openrouter/qwen/qwen-2.5-72b-instruct",
    ],
    "local": [
        # Placeholder — populated dynamically via Ollama / OpenAI-compatible discovery.
        # If no local server is running, this provider is hidden from the frontend.
    ],
    "elevenlabs": [
        "eleven_turbo_v2_5",
        "eleven_multilingual_v2",
    ],
}

# ── Provider display names (used by both BE and FE) ──

PROVIDER_NAMES: dict[str, str] = {
    "gemini": "Gemini (Google)",
    "openai": "OpenAI",
    "claude": "Claude (Anthropic)",
    "grok": "Grok (xAI)",
    "openrouter": "OpenRouter",
    "local": "Local (Ollama / LM Studio)",
    "elevenlabs": "ElevenLabs (TTS)",
}

# ── Provider API endpoints & config ──────────────────

# ── Gemini filter ─────────────────────────────────────
# Substrings that mark a Gemini model as NOT a general chat model
_GEMINI_EXCLUDE = (
    "gemma",          # Gemma open-weight models (not API-hosted chat)
    "-tts",           # TTS-only models
    "-image",         # image-generation-only variants
    "robotics",       # Gemini Robotics ER
    "nano-banana",    # experimental/joke model
    "computer-use",   # computer-use automation variant
    "deep-research",  # deep-research pipeline
    "customtools",    # custom-tools preview
    "-latest",        # alias duplicates (gemini-flash-latest etc.)
)


def _gemini_chat_filter(m: dict) -> bool:
    """Keep only general-purpose Gemini chat/reasoning models."""
    methods = m.get("supportedGenerationMethods", [])
    if "generateContent" not in methods:
        return False
    name = m.get("name", "")
    if name.startswith("models/"):
        name = name[len("models/"):]
    if any(ex in name for ex in _GEMINI_EXCLUDE):
        return False
    return True


# ── OpenAI filter ─────────────────────────────────────
# Substrings that mark an OpenAI model as NOT a chat model
_OPENAI_EXCLUDE = (
    "ft:", "dall-e", "whisper", "tts", "text-embedding", "babbage", "davinci",
    "omni-moderation", "sora", "gpt-image", "chatgpt-image",
    "audio", "realtime", "transcribe", "search-",
    "codex", "instruct",
    "gpt-3.5",       # legacy
    "-chat-latest",  # alias duplicates (gpt-5-chat-latest etc.)
)
# Date-snapshot pattern: modelname-YYYY-MM-DD  or modelname-YYMM-preview
import re
_OPENAI_SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{4}-preview$")


def _openai_chat_filter(m: dict) -> bool:
    """Keep only primary chat/reasoning models — no snapshots, no non-text."""
    mid = m.get("id", "")
    if any(ex in mid for ex in _OPENAI_EXCLUDE):
        return False
    if _OPENAI_SNAPSHOT_RE.search(mid):
        return False
    return True


# ── OpenRouter filter ─────────────────────────────────
# Skip providers we already have direct keys for (duplicates)
# and filter to text-capable models only.
_OPENROUTER_DIRECT_PROVIDERS = {"openai", "google", "anthropic", "x-ai", "z-ai"}

# Niche / roleplay-only orgs we don't need in a general dropdown
_OPENROUTER_SKIP_ORGS = {
    "sao10k", "thedrummer", "neversleep", "undi95", "gryphe",
    "mancer", "alpindale", "anthracite-org", "alfredpros", "raifle",
    "cognitivecomputations",
}


def _openrouter_chat_filter(m: dict) -> bool:
    """Keep text-gen models from providers not available via direct API keys."""
    # Must be text-capable
    modality = str(m.get("architecture", {}).get("modality", ""))
    if "text" not in modality:
        return False
    mid = m.get("id", "")
    org = mid.split("/")[0] if "/" in mid else ""
    # Skip providers we already have direct API access to
    if org in _OPENROUTER_DIRECT_PROVIDERS:
        return False
    # Skip niche roleplay-focused orgs
    if org in _OPENROUTER_SKIP_ORGS:
        return False
    return True


# ── Local Model Base URLs ────────────────────────────
# Ollama default:       http://localhost:11434
# LM Studio default:   http://localhost:1234
# vLLM / llamacpp:     user-configured

OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
LOCAL_API_BASE = os.getenv("LOCAL_API_BASE", "")  # OpenAI-compatible server


async def _fetch_local_models() -> list[str]:
    """
    Discover models from local inference servers (Ollama + OpenAI-compatible).
    Returns LiteLLM-prefixed model IDs.  Falls back to [] if no server is running.
    """
    if _is_cache_valid("local"):
        return _cache["local"]["models"]

    discovered: list[str] = []

    # ── Ollama ───────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_API_BASE}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            for m in data.get("models", []):
                name = m.get("name", "")
                if name:
                    # Strip :latest tag for cleaner display
                    if name.endswith(":latest"):
                        name = name[: -len(":latest")]
                    discovered.append(f"ollama_chat/{name}")
    except Exception:
        pass  # Ollama not running — skip silently

    # ── OpenAI-compatible local server (LM Studio, vLLM, etc.) ──
    if LOCAL_API_BASE:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{LOCAL_API_BASE}/v1/models")
                resp.raise_for_status()
                data = resp.json()
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    if model_id:
                        full_id = f"openai/{model_id}"
                        if full_id not in discovered:
                            discovered.append(full_id)
        except Exception:
            pass  # Local server not running — skip silently

    if discovered:
        discovered.sort()
        _cache["local"] = {"models": discovered, "fetched_at": time.time()}
        print(f"🔍 model_registry: discovered {len(discovered)} local models")

    return discovered


_PROVIDER_API_CONFIG: dict[str, dict] = {
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
        "env_key": "GEMINI_API_KEY",
        "auth": "query",           # ?key=...
        "prefix": "gemini/",
        "model_path": "models",    # response.models[]
        "id_field": "name",        # models[].name = "models/gemini-2.5-flash"
        "id_strip": "models/",     # strip this prefix from name
        "filter": _gemini_chat_filter,
    },
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "env_key": "OPENAI_API_KEY",
        "auth": "bearer",
        "prefix": "openai/",
        "model_path": "data",
        "id_field": "id",
        "filter": _openai_chat_filter,
    },
    "claude": {
        "url": "https://api.anthropic.com/v1/models",
        "env_key": "ANTHROPIC_API_KEY",
        "auth": "x-api-key",
        "prefix": "anthropic/",
        "model_path": "data",
        "id_field": "id",
        "filter": lambda _: True,
    },
    "grok": {
        "url": "https://api.x.ai/v1/models",
        "env_key": "XAI_API_KEY",
        "auth": "bearer",
        "prefix": "xai/",
        "model_path": "data",
        "id_field": "id",
        "filter": lambda _: True,
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/models",
        "env_key": "OPENROUTER_API_KEY",
        "auth": "bearer",
        "prefix": "openrouter/",
        "model_path": "data",
        "id_field": "id",
        # Only keep text-generation models, skip image/embedding/moderation
        "filter": _openrouter_chat_filter,
        # No hard limit — smart filter keeps it manageable
    },
}

# ── TTL Cache ─────────────────────────────────────────

_CACHE_TTL_SECONDS = int(os.getenv("MODEL_CACHE_TTL", "3600"))  # 1 hour default

_cache: dict[str, dict] = {}
# _cache[provider] = {"models": [...], "fetched_at": float}


def _is_cache_valid(provider: str) -> bool:
    entry = _cache.get(provider)
    if not entry:
        return False
    return (time.time() - entry["fetched_at"]) < _CACHE_TTL_SECONDS


def invalidate_cache(provider: str | None = None):
    """Clear cached discovery results. None = clear all."""
    if provider:
        _cache.pop(provider, None)
    else:
        _cache.clear()


# ── Async Discovery ──────────────────────────────────

async def _fetch_provider_models(provider: str) -> list[str]:
    """
    Fetch the live model list from a single provider's API.
    Returns a list of LiteLLM-prefixed model IDs.
    Falls back to [] on any error.
    """
    config = _PROVIDER_API_CONFIG.get(provider)
    if not config:
        return []

    api_key = os.getenv(config["env_key"], "")
    if not api_key:
        return []

    # Check cache
    if _is_cache_valid(provider):
        return _cache[provider]["models"]

    try:
        headers: dict[str, str] = {}
        params: dict[str, str] = {}

        if config["auth"] == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        elif config["auth"] == "x-api-key":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        elif config["auth"] == "query":
            params["key"] = api_key

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(config["url"], headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        # Extract model list from response
        model_path = config.get("model_path", "data")
        raw_models = data if isinstance(data, list) else data.get(model_path, [])

        # Apply provider-specific filter
        model_filter = config.get("filter", lambda _: True)
        filtered = [m for m in raw_models if model_filter(m)]

        # Apply limit (for noisy providers like OpenRouter)
        limit = config.get("limit")
        if limit:
            filtered = filtered[:limit]

        # Extract model ID and add prefix
        prefix = config.get("prefix", "")
        id_field = config.get("id_field", "id")
        id_strip = config.get("id_strip", "")

        discovered: list[str] = []
        for m in filtered:
            model_id = m.get(id_field, "") if isinstance(m, dict) else str(m)
            if id_strip and model_id.startswith(id_strip):
                model_id = model_id[len(id_strip):]
            if model_id:
                full_id = f"{prefix}{model_id}"
                discovered.append(full_id)

        # Sort OpenRouter models by org/name for clean dropdown grouping
        if provider == "openrouter":
            discovered.sort()

        # Cache
        _cache[provider] = {"models": discovered, "fetched_at": time.time()}
        print(f"🔍 model_registry: discovered {len(discovered)} models from {provider}")
        return discovered

    except Exception as exc:
        print(f"⚠️  model_registry: {provider} discovery failed: {exc}")
        return []


async def discover_all_models() -> dict[str, list[str]]:
    """
    Fetch live model lists from ALL configured providers in parallel.
    Returns provider → [model_id, ...], merged with curated list.
    Curated models always appear first; discovered ones are appended.
    """
    # Start with curated copy
    merged: dict[str, list[str]] = {k: list(v) for k, v in _CURATED_MODELS.items()}

    # Run all provider fetches in parallel
    providers = list(_PROVIDER_API_CONFIG.keys())
    results = await asyncio.gather(
        *[_fetch_provider_models(p) for p in providers],
        return_exceptions=True,
    )

    for provider, result in zip(providers, results):
        if isinstance(result, Exception):
            print(f"⚠️  model_registry: {provider} discovery raised: {result}")
            continue
        if not result:
            continue

        existing = set(merged.get(provider, []))
        for model_id in result:
            if model_id not in existing:
                merged.setdefault(provider, []).append(model_id)
                existing.add(model_id)

    # ── Local models (Ollama + OpenAI-compatible) ──
    local_models = await _fetch_local_models()
    if local_models:
        existing = set(merged.get("local", []))
        for model_id in local_models:
            if model_id not in existing:
                merged.setdefault("local", []).append(model_id)
                existing.add(model_id)

    return merged


# ── Public API ────────────────────────────────────────

def get_available_models() -> dict[str, list[str]]:
    """
    Return the canonical curated model list (synchronous).
    For live discovery, use `get_available_models_async()`.
    """
    return {k: list(v) for k, v in _CURATED_MODELS.items()}


async def get_available_models_async(
    *,
    live: Optional[bool] = None,
) -> dict[str, list[str]]:
    """
    Return the canonical model list, extended with live provider API
    discovery by default.  Results are cached for MODEL_CACHE_TTL seconds.

    Parameters
    ----------
    live : bool, optional
        If True, fetch live lists from provider APIs.
        Defaults to True unless MODEL_DISCOVERY == "off".

    Returns
    -------
    dict   provider → [model_id, ...]
    """
    if live is None:
        live = os.getenv("MODEL_DISCOVERY", "").lower() != "off"

    if live:
        return await discover_all_models()

    return get_available_models()


def get_default_model(provider: str = "gemini") -> str:
    """Return the first (recommended) model for a provider."""
    provider_models = _CURATED_MODELS.get(provider, [])
    if provider_models:
        return provider_models[0]
    # Fallback across all providers
    for models in _CURATED_MODELS.values():
        if models:
            return models[0]
    return "gemini/gemini-2.5-flash"


def get_provider_names() -> dict[str, str]:
    """Return provider key → display name mapping."""
    return dict(PROVIDER_NAMES)


def is_valid_model(model_id: str) -> bool:
    """Check if a model ID is in the curated list."""
    for models in _CURATED_MODELS.values():
        if model_id in models:
            return True
    return False


def get_configured_providers() -> list[str]:
    """
    Return provider keys that have API keys configured.
    Useful for the frontend to dim/hide unconfigured providers.
    """
    configured = []
    for provider, config in _PROVIDER_API_CONFIG.items():
        if os.getenv(config["env_key"], ""):
            configured.append(provider)
    # Always include elevenlabs if it has models (TTS, no discovery)
    if "elevenlabs" not in configured and _CURATED_MODELS.get("elevenlabs"):
        configured.append("elevenlabs")
    # Include "local" only if user explicitly set a local API base,
    # or if discovery already found models (cache is populated).
    _ollama_explicit = os.getenv("OLLAMA_API_BASE", "")
    _local_explicit = os.getenv("LOCAL_API_BASE", "")
    if _ollama_explicit or _local_explicit or _is_cache_valid("local"):
        configured.append("local")
    return configured

DEFAULT_LLM_TIMEOUT = float(os.getenv("LITELLM_TIMEOUT", "600"))
LOCAL_LLM_TIMEOUT = float(os.getenv("LITELLM_LOCAL_TIMEOUT", "3600"))

def get_llm_timeout(model: str, api_base: str | None = None) -> float:
    def _norm(x: str | None) -> str:
        return (x or "").rstrip("/")

    if _norm(api_base) in {_norm(LOCAL_API_BASE), _norm(OLLAMA_API_BASE)}:
        return LOCAL_LLM_TIMEOUT

    lower = (model or "").lower()
    if lower.startswith(("ollama/", "ollama_chat/")):
        return LOCAL_LLM_TIMEOUT

    return DEFAULT_LLM_TIMEOUT
