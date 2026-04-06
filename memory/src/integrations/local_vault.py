"""
Local Key Vault — PostgreSQL-backed API key storage for self-hosted deployments.

Drop-in replacement for the cloud-backed KeyVault.
Same public interface: get_llm_key(), resolve_for_litellm(), get_tts_key(), etc.
All keys stored in the api_keys table using AES-256-GCM encryption.

Falls back to environment variables when no keys are stored (dev convenience).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Optional

from src.integrations.crypto import decrypt, encrypt, mask_key, EncryptedData


# ── Cache Configuration ───────────────────────────────
_CACHE_TTL_SECONDS = 300  # 5 minutes


# ── Provider ↔ Env Var Mapping ────────────────────────
_PROVIDER_ENV_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "google_tts": "GOOGLE_TTS_API_KEY",
}

# Model prefix → provider name
_MODEL_TO_PROVIDER: dict[str, str] = {
    "gemini/": "gemini",
    "openai/": "openai",
    "gpt-": "openai",
    "o1-": "openai",
    "o3-": "openai",
    "o4-": "openai",
    "anthropic/": "anthropic",
    "claude": "anthropic",
    "xai/": "xai",
    "grok": "xai",
    "openrouter/": "openrouter",
    "ollama_chat/": "ollama",
    "ollama/": "ollama",
}

_PROVIDER_TO_OPENROUTER_PREFIX: dict[str, str] = {
    "gemini": "openrouter/google/",
    "openai": "openrouter/openai/",
    "anthropic": "openrouter/anthropic/",
    "xai": "openrouter/xai/",
}


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: dict, ttl: float = _CACHE_TTL_SECONDS):
        self.value = value
        self.expires_at = time.monotonic() + ttl

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at


class LocalKeyVault:
    """
    PostgreSQL-backed key vault for self-hosted deployments.

    Same interface as the cloud-backed KeyVault but reads from the api_keys table.
    Falls back to environment variables for convenience.
    """

    _instance: Optional[LocalKeyVault] = None

    def __new__(cls) -> LocalKeyVault:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    # ── Public API (same as KeyVault) ──────────────────

    async def get_llm_key(self, user_id: str, model: str) -> str:
        provider = self._detect_provider(model)

        # Local models (Ollama, etc.) don't need API keys
        if provider == "ollama":
            return ""

        keys = await self._load_keys(user_id)

        if provider and provider in keys:
            return keys[provider]
        if "openrouter" in keys:
            return keys["openrouter"]

        # Env var fallback (always allowed for self-hosted)
        if provider:
            env_var = _PROVIDER_ENV_VARS.get(provider)
            if env_var:
                val = os.getenv(env_var, "")
                if val:
                    return val
        or_env = os.getenv("OPENROUTER_API_KEY", "")
        if or_env:
            return or_env

        raise ValueError(
            f"No API key configured for model '{model}' (provider: {provider}). "
            f"Add a key in Settings → API Keys or set the environment variable."
        )

    async def resolve_for_litellm(self, user_id: str, model: str) -> dict:
        provider = self._detect_provider(model)

        # Local models (Ollama, etc.) don't need API keys
        if provider == "ollama":
            return {}

        keys = await self._load_keys(user_id)
        result: dict = {}

        if provider and provider in keys:
            result["api_key"] = keys[provider]
            return result

        if "openrouter" in keys:
            result["api_key"] = keys["openrouter"]
            if not model.lower().startswith("openrouter/"):
                result["model"] = self._rewrite_for_openrouter(model, provider)
            return result

        # Env var fallback
        if provider:
            env_var = _PROVIDER_ENV_VARS.get(provider)
            if env_var and os.getenv(env_var, ""):
                result["api_key"] = os.getenv(env_var)
                return result

        or_env = os.getenv("OPENROUTER_API_KEY", "")
        if or_env:
            result["api_key"] = or_env
            if not model.lower().startswith("openrouter/"):
                result["model"] = self._rewrite_for_openrouter(model, provider)
            return result

        raise ValueError(f"No API key for model '{model}'. Add a key in Settings → API Keys.")

    async def get_tts_key(self, user_id: str, provider: str) -> Optional[str]:
        keys = await self._load_keys(user_id)
        provider_key = provider.lower().replace("-", "_")
        if provider_key == "google":
            provider_key = "google_tts"
        if provider_key == "openai_tts":
            provider_key = "openai"

        if provider_key in keys:
            return keys[provider_key]

        env_var = _PROVIDER_ENV_VARS.get(provider_key)
        if env_var:
            val = os.getenv(env_var, "")
            if val:
                return val
        return None

    async def get_search_key(self, user_id: str) -> tuple[Optional[str], Optional[str]]:
        keys = await self._load_keys(user_id)
        if "search" in keys:
            return keys["search"], keys.get("_search_provider", "exa")

        for prov, env_var in [
            ("exa", "EXA_API_KEY"),
            ("tavily", "TAVILY_API_KEY"),
            ("brave", "BRAVE_SEARCH_API_KEY"),
            ("serpapi", "SERPAPI_KEY"),
        ]:
            val = os.getenv(env_var, "")
            if val:
                return val, prov
        return None, None

    async def get_database_url(self, user_id: str) -> Optional[str]:
        """Not applicable for self-hosted — database is configured via DATABASE_URL env var."""
        return None

    async def get_all_keys_masked(self, user_id: str) -> dict:
        keys = await self._load_keys(user_id)
        masked = {}
        for provider, key in keys.items():
            if provider.startswith("_"):
                continue
            masked[provider] = mask_key(key)
        return masked

    async def invalidate_cache(self, user_id: str) -> None:
        async with self._lock:
            keys_to_remove = [k for k in self._cache if k.endswith(f":{user_id}")]
            for k in keys_to_remove:
                del self._cache[k]

    # ── Key CRUD (PostgreSQL) ─────────────────────────

    async def save_key(self, user_id: str, provider: str, api_key: str,
                       search_provider: Optional[str] = None) -> str:
        """Encrypt and save a key to the api_keys table. Returns masked key."""
        from src.db.session import get_session
        from src.db.auth_models import ApiKeyEntry

        encrypted = encrypt(api_key)
        masked = mask_key(api_key)
        encrypted_json = json.dumps(encrypted)

        with get_session() as session:
            existing = (
                session.query(ApiKeyEntry)
                .filter_by(user_id=user_id, provider=provider)
                .first()
            )
            if existing:
                existing.encrypted_key = encrypted_json
                existing.masked_key = masked
                existing.search_provider = search_provider
            else:
                entry = ApiKeyEntry(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    provider=provider,
                    encrypted_key=encrypted_json,
                    masked_key=masked,
                    search_provider=search_provider,
                )
                session.add(entry)

        await self.invalidate_cache(user_id)
        return masked

    async def delete_key(self, user_id: str, provider: str) -> None:
        """Delete a key from the api_keys table."""
        from src.db.session import get_session
        from src.db.auth_models import ApiKeyEntry

        with get_session() as session:
            session.query(ApiKeyEntry).filter_by(
                user_id=user_id, provider=provider
            ).delete()

        await self.invalidate_cache(user_id)

    async def list_keys_masked(self, user_id: str) -> dict:
        """List all keys for a user, masked for display."""
        from src.db.session import get_session
        from src.db.auth_models import ApiKeyEntry

        with get_session() as session:
            entries = session.query(ApiKeyEntry).filter_by(user_id=user_id).all()
            result = {}
            for entry in entries:
                result[entry.provider] = {
                    "maskedKey": entry.masked_key or "••••••••",
                    "updatedAt": str(entry.updated_at or ""),
                }
                if entry.provider == "search" and entry.search_provider:
                    result[entry.provider]["searchProvider"] = entry.search_provider
            return result

    # ── Internal ──────────────────────────────────────

    async def _load_keys(self, user_id: str) -> dict[str, str]:
        cache_key = f"keys:{user_id}"

        async with self._lock:
            entry = self._cache.get(cache_key)
            if entry and not entry.expired:
                return entry.value

        keys: dict[str, str] = {}
        try:
            from src.db.session import get_session
            from src.db.auth_models import ApiKeyEntry

            with get_session() as session:
                entries = session.query(ApiKeyEntry).filter_by(user_id=user_id).all()
                for entry in entries:
                    try:
                        encrypted = json.loads(entry.encrypted_key)
                        keys[entry.provider] = decrypt(encrypted)
                        if entry.provider == "search" and entry.search_provider:
                            keys["_search_provider"] = entry.search_provider
                    except Exception as e:
                        print(f"⚠️ LocalVault: Failed to decrypt {entry.provider} key: {e}")
        except Exception as e:
            print(f"⚠️ LocalVault: Failed to load keys for {user_id}: {e}")

        async with self._lock:
            self._cache[cache_key] = _CacheEntry(keys)

        return keys

    @staticmethod
    def _detect_provider(model: str) -> Optional[str]:
        lower = model.lower()
        for prefix, provider in _MODEL_TO_PROVIDER.items():
            if lower.startswith(prefix):
                return provider
        return None

    @staticmethod
    def _rewrite_for_openrouter(model: str, provider: Optional[str]) -> str:
        bare_model = model
        for prefix in ["gemini/", "openai/", "anthropic/", "xai/"]:
            if model.lower().startswith(prefix):
                bare_model = model[len(prefix):]
                break
        if provider and provider in _PROVIDER_TO_OPENROUTER_PREFIX:
            return _PROVIDER_TO_OPENROUTER_PREFIX[provider] + bare_model
        return f"openrouter/{bare_model}"


# ── Module-Level Singleton ────────────────────────────
local_vault = LocalKeyVault()
