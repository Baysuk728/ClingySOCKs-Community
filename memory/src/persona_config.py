"""
Persona Config Loader — Single Source of Truth

Loads persona operational configuration (model, temperature, sampling params,
context budgets) from the `persona_identity` table.  Every consumer — chat,
agent loop, agent invoke, heartbeat — should call `load_persona_config()`
instead of querying PersonaIdentity directly.

This eliminates field duplication, inconsistent defaults, and missing
model normalization across the codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from src.db.models import PersonaIdentity
from src.db.session import get_session
from src.model_registry import get_default_model

# ── Defaults ──────────────────────────────────────────

DEFAULT_MODEL = os.getenv("CHAT_MODEL", get_default_model("gemini"))
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_WARM_MEMORY = 8_000
DEFAULT_MAX_HISTORY_CHARS = 12_000
DEFAULT_MAX_HISTORY_MESSAGES = 20


# ── Data Class ────────────────────────────────────────

@dataclass
class PersonaConfig:
    """All operational settings for a persona, with safe defaults."""

    entity_id: str

    # LLM
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None

    # System prompt
    system_prompt: Optional[str] = None

    # Context budgets
    max_context_chars: Optional[int] = None  # Total context budget (None = unlimited)
    max_warm_memory: int = DEFAULT_MAX_WARM_MEMORY
    max_history_chars: int = DEFAULT_MAX_HISTORY_CHARS
    max_history_messages: int = DEFAULT_MAX_HISTORY_MESSAGES

    # Identity (read-only, informational)
    voice_id: Optional[str] = None
    tts_provider: Optional[str] = None

    # BYOK — resolved API key for this persona's model
    api_key: Optional[str] = None

    # Whether the persona actually exists in the DB
    found: bool = False

    # ── Convenience accessors ─────────────────────────

    def to_context_config(self):
        """Return an api.chat_context.ContextConfig populated from this config."""
        from api.chat_context import ContextConfig
        return ContextConfig(
            max_context_chars=self.max_context_chars,
            max_warm_memory=self.max_warm_memory,
            max_history=self.max_history_chars,
            max_history_messages=self.max_history_messages,
        )

    def litellm_kwargs(self, **overrides) -> dict:
        """
        Build the provider-agnostic kwargs dict for litellm.acompletion().

        Use like:  response = await litellm.acompletion(**cfg.litellm_kwargs(), messages=msgs)

        Includes drop_params=True so LiteLLM silently drops any parameters
        the target provider doesn't support (e.g. Anthropic doesn't accept
        presence_penalty / frequency_penalty).
        """
        kw: dict = {
            "model": self.model,
            "temperature": self.temperature,
            "drop_params": True,
        }
        # Include API key if resolved from vault
        if self.api_key:
            kw["api_key"] = self.api_key

        # Local models — set api_base for Ollama / OpenAI-compatible servers
        provider = _detect_provider(self.model)
        if provider == "ollama":
            from src.model_registry import OLLAMA_API_BASE
            kw["api_base"] = OLLAMA_API_BASE
        elif self.model.startswith("openai/") and not self.api_key:
            # OpenAI-prefixed model with no API key → likely a local server
            from src.model_registry import LOCAL_API_BASE
            if LOCAL_API_BASE:
                kw["api_base"] = LOCAL_API_BASE

        # Only include sampling params the provider actually supports
        kw.update(sanitize_sampling_params(
            self.model,
            top_p=self.top_p,
            top_k=self.top_k,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
        ))
        kw.update(overrides)
        return kw


# ── Loader ────────────────────────────────────────────

def load_persona_config(
    entity_id: str,
    *,
    user_id: Optional[str] = None,
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
) -> PersonaConfig:
    """
    Load persona config from PostgreSQL.  This is the **single source of truth**
    for model, temperature, sampling params, and context budgets.

    Parameters
    ----------
    entity_id : str
        The persona entity ID.
    user_id : str, optional
        User ID for BYOK key resolution via vault.
        If None, falls back to env-var API keys (dev/self-host mode).
    model_override : str, optional
        Force a specific model (ignores DB value).
    temperature_override : float, optional
        Force a specific temperature (ignores DB value).

    Returns
    -------
    PersonaConfig with DB values merged over safe defaults.
    """
    cfg = PersonaConfig(entity_id=entity_id)

    with get_session() as session:
        persona = session.get(PersonaIdentity, entity_id)
        if persona:
            cfg.found = True

            # LLM
            if persona.model:
                cfg.model = persona.model
            if persona.temperature is not None:
                cfg.temperature = persona.temperature
            if persona.top_p is not None:
                cfg.top_p = persona.top_p
            if persona.top_k is not None:
                cfg.top_k = persona.top_k
            if persona.frequency_penalty is not None:
                cfg.frequency_penalty = persona.frequency_penalty
            if persona.presence_penalty is not None:
                cfg.presence_penalty = persona.presence_penalty

            # System prompt
            if persona.system_prompt:
                cfg.system_prompt = persona.system_prompt

            # Context budgets
            if persona.max_context_chars is not None:
                cfg.max_context_chars = persona.max_context_chars
            if persona.max_warm_memory:
                cfg.max_warm_memory = persona.max_warm_memory
            if persona.max_history_chars:
                cfg.max_history_chars = persona.max_history_chars
            if persona.max_history_messages:
                cfg.max_history_messages = persona.max_history_messages

            # Identity
            cfg.voice_id = persona.voice_id
            cfg.tts_provider = persona.tts_provider
        else:
            print(f"⚠️ PersonaConfig: No persona found for {entity_id}")

    # Apply overrides
    if model_override:
        cfg.model = model_override
    if temperature_override is not None:
        cfg.temperature = temperature_override

    # Model normalization — ensure LiteLLM provider prefix is present
    cfg.model = normalize_model(cfg.model)

    # BYOK — Resolve API key from vault (if user_id provided)
    if user_id:
        try:
            import asyncio
            from src.integrations.vault_factory import get_vault
            _vault = get_vault()

            # Resolve API key + possibly rewrite model for OpenRouter fallback
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — can't await directly from sync.
                # Schedule a coroutine and use a future. The callers should use
                # load_persona_config_async() instead, but this works as a safety net.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    overrides = pool.submit(
                        asyncio.run,
                        _vault.resolve_for_litellm(user_id, cfg.model)
                    ).result(timeout=10)
            else:
                overrides = asyncio.run(_vault.resolve_for_litellm(user_id, cfg.model))

            cfg.api_key = overrides.get("api_key")
            if "model" in overrides:
                cfg.model = overrides["model"]
                print(f"🔑 BYOK: Model rewritten to {cfg.model} (OpenRouter fallback)")
        except ValueError as e:
            # No key found — will fall back to env vars at call time
            print(f"⚠️ BYOK: {e}")
        except Exception as e:
            print(f"⚠️ BYOK: Key resolution failed: {e}")

    print(f"🧠 PersonaConfig [{entity_id[:8]}…]: model={cfg.model}, temp={cfg.temperature}, "
          f"warm={cfg.max_warm_memory}, hist={cfg.max_history_chars}/{cfg.max_history_messages}msg"
          f"{', sys_prompt=' + str(len(cfg.system_prompt)) + 'ch' if cfg.system_prompt else ''}"
          f"{', BYOK' if cfg.api_key else ''}")

    return cfg


async def aload_persona_config(
    entity_id: str,
    *,
    user_id: Optional[str] = None,
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
) -> PersonaConfig:
    """
    Async version of load_persona_config.

    Preferred in async contexts (FastAPI routes, agent loop) because it
    can await the vault key resolution directly without thread pool hacks.
    """
    # The DB query part is synchronous (SQLAlchemy) — reuse the sync loader
    # but skip the vault resolution (we'll do it async below)
    cfg = PersonaConfig(entity_id=entity_id)

    with get_session() as session:
        persona = session.get(PersonaIdentity, entity_id)
        if persona:
            cfg.found = True
            if persona.model:
                cfg.model = persona.model
            if persona.temperature is not None:
                cfg.temperature = persona.temperature
            if persona.top_p is not None:
                cfg.top_p = persona.top_p
            if persona.top_k is not None:
                cfg.top_k = persona.top_k
            if persona.frequency_penalty is not None:
                cfg.frequency_penalty = persona.frequency_penalty
            if persona.presence_penalty is not None:
                cfg.presence_penalty = persona.presence_penalty
            if persona.system_prompt:
                cfg.system_prompt = persona.system_prompt
            if persona.max_context_chars is not None:
                cfg.max_context_chars = persona.max_context_chars
            if persona.max_warm_memory:
                cfg.max_warm_memory = persona.max_warm_memory
            if persona.max_history_chars:
                cfg.max_history_chars = persona.max_history_chars
            if persona.max_history_messages:
                cfg.max_history_messages = persona.max_history_messages
            cfg.voice_id = persona.voice_id
            cfg.tts_provider = persona.tts_provider
        else:
            print(f"⚠️ PersonaConfig: No persona found for {entity_id}")

    # Apply overrides
    if model_override:
        cfg.model = model_override
    if temperature_override is not None:
        cfg.temperature = temperature_override

    cfg.model = normalize_model(cfg.model)

    # BYOK — Async vault resolution
    if user_id:
        try:
            from src.integrations.vault_factory import get_vault
            _vault = get_vault()
            overrides = await _vault.resolve_for_litellm(user_id, cfg.model)
            cfg.api_key = overrides.get("api_key")
            if "model" in overrides:
                cfg.model = overrides["model"]
                print(f"🔑 BYOK: Model rewritten to {cfg.model} (OpenRouter fallback)")
        except ValueError as e:
            # In local/dev mode, fall back to env vars
            print(f"⚠️ BYOK: {e} (will use env vars as fallback)")
        except Exception as e:
            print(f"⚠️ BYOK: Key resolution failed: {e} (continuing with env vars)")

    print(f"🧠 PersonaConfig [{entity_id[:8]}…]: model={cfg.model}, temp={cfg.temperature}, "
          f"warm={cfg.max_warm_memory}, hist={cfg.max_history_chars}/{cfg.max_history_messages}msg"
          f"{', sys_prompt=' + str(len(cfg.system_prompt)) + 'ch' if cfg.system_prompt else ''}"
          f"{', BYOK' if cfg.api_key else ''}")

    return cfg


# ── Model Normalization ───────────────────────────────

_MODEL_PREFIX_MAP = {
    "gemini": "gemini/",
    "gpt-": "openai/",
    "o1-": "openai/",
    "o3-": "openai/",
    "o4-": "openai/",
    "claude": "anthropic/",
    "grok": "xai/",
    "openrouter/": "openrouter/",   # already prefixed — no-op guard
    "ollama_chat/": "ollama_chat/", # already prefixed — no-op guard
    "ollama/": "ollama/",           # already prefixed — no-op guard
}


def normalize_model(model: str) -> str:
    """
    Ensure model string has a LiteLLM provider prefix.

    Without a prefix LiteLLM defaults to Vertex AI (needs GCP credentials).
    Examples:
      "gemini-2.5-flash"  →  "gemini/gemini-2.5-flash"
      "gpt-4o"            →  "openai/gpt-4o"
      "gemini/gemini-2.5-flash"  →  unchanged
    """
    if "/" in model:
        return model

    lower = model.lower()
    for pattern, prefix in _MODEL_PREFIX_MAP.items():
        if lower.startswith(pattern):
            return prefix + model

    return model  # Unknown model — pass through as-is


# ── Provider-Aware Param Sanitizer ────────────────────

# Which sampling params each provider family actually accepts.
# Params not listed are silently dropped for that provider.
_PROVIDER_SUPPORTED_PARAMS: dict[str, set[str]] = {
    "gemini":    {"top_p", "top_k", "frequency_penalty", "presence_penalty"},
    "openai":    {"top_p", "frequency_penalty", "presence_penalty"},
    "anthropic": {"top_k"},        # Anthropic rejects top_p + temperature together
    "xai":       {"top_p", "frequency_penalty", "presence_penalty"},
    "openrouter":{"top_p", "top_k", "frequency_penalty", "presence_penalty"},
    "ollama":    {"top_p", "top_k"},  # Ollama supports top_p and top_k
}


def _detect_provider(model: str) -> str:
    """Detect provider family from a LiteLLM model string."""
    lower = model.lower()
    if lower.startswith(("ollama_chat/", "ollama/")):
        return "ollama"
    if "anthropic/" in lower or lower.startswith("claude"):
        return "anthropic"
    if "openai/" in lower or lower.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    if "gemini/" in lower or lower.startswith("gemini"):
        return "gemini"
    if "xai/" in lower or lower.startswith("grok"):
        return "xai"
    if "openrouter/" in lower:
        return "openrouter"
    return "unknown"


def sanitize_sampling_params(
    model: str,
    *,
    top_p: float | None = None,
    top_k: int | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
) -> dict[str, float | int]:
    """
    Return only the sampling params the provider actually supports.

    Usage::

        extras = sanitize_sampling_params(
            model, top_p=cfg.top_p, top_k=cfg.top_k,
            frequency_penalty=cfg.frequency_penalty,
            presence_penalty=cfg.presence_penalty,
        )
        kwargs.update(extras)

    Provider support matrix:
      - Gemini:    top_p, top_k, frequency_penalty, presence_penalty
      - OpenAI:    top_p, frequency_penalty, presence_penalty  (NO top_k)
      - Anthropic:  top_k only  (temperature+top_p conflict, freq/presence unsupported)
      - xAI/Grok:  top_p, frequency_penalty, presence_penalty  (NO top_k)
      - OpenRouter: all (passes through to underlying model)
    """
    provider = _detect_provider(model)
    supported = _PROVIDER_SUPPORTED_PARAMS.get(provider, {"top_p", "top_k", "frequency_penalty", "presence_penalty"})

    result: dict[str, float | int] = {}
    if top_p is not None and "top_p" in supported:
        result["top_p"] = top_p
    if top_k is not None and "top_k" in supported:
        result["top_k"] = top_k
    if frequency_penalty is not None and "frequency_penalty" in supported:
        result["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None and "presence_penalty" in supported:
        result["presence_penalty"] = presence_penalty

    return result
