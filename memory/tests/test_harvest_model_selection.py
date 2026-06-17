"""
Unit tests for harvest model selection.

Pure logic — no DB, no network. Guards the "cheap-model-from-chat-provider"
behavior: harvest must auto-pick a cheap model for each provider and must NOT
fall back to the pricey flagship (e.g. gpt-4o).
"""

import pytest

from src.model_registry import (
    provider_from_model,
    get_harvest_model,
    get_default_model,
    is_valid_model,
    _HARVEST_MODELS,
)


class TestProviderFromModel:
    @pytest.mark.parametrize("model,expected", [
        ("gemini/gemini-2.5-flash", "gemini"),
        ("openai/gpt-4o", "openai"),
        ("openai/gpt-4o-mini", "openai"),
        ("anthropic/claude-opus-4-6", "claude"),
        ("xai/grok-2-1212", "grok"),
        ("openrouter/openai/gpt-4o", "openrouter"),
        ("ollama_chat/llama3.1", "local"),
        ("ollama/llama3", "local"),
        ("local/mistralai/ministral-3-14b", "local"),
        ("no-prefix-model", None),
        ("", None),
        (None, None),
    ])
    def test_provider_detection(self, model, expected):
        assert provider_from_model(model) == expected


class TestHarvestModel:
    @pytest.mark.parametrize("provider,expected", [
        ("gemini", "gemini/gemini-2.5-flash"),
        ("openai", "openai/gpt-4o-mini"),
        ("claude", "anthropic/claude-haiku-4-5-20250414"),
        ("grok", "xai/grok-2-1212"),
        ("openrouter", "openrouter/openai/gpt-4o-mini"),
    ])
    def test_cheap_model_per_provider(self, provider, expected):
        assert get_harvest_model(provider) == expected

    def test_openai_harvest_is_not_the_flagship(self):
        # The whole point of the feature: an OpenAI persona must NOT harvest with
        # the expensive flagship — it must drop to the cheap tier.
        assert get_harvest_model("openai") == "openai/gpt-4o-mini"
        assert get_harvest_model("openai") != get_default_model("openai")

    def test_unknown_provider_falls_back_gracefully(self):
        # Unmapped/None provider must never crash — fall back to a default model.
        assert get_harvest_model("local") == get_default_model("local")
        assert get_harvest_model(None) == get_default_model("gemini")

    def test_all_harvest_models_are_in_the_curated_catalogue(self):
        # Every cheap model we point at must be a real, curated model id, so a
        # typo can never resolve harvest to a nonexistent model.
        for provider, model in _HARVEST_MODELS.items():
            assert is_valid_model(model), f"{provider} -> {model} not in curated list"

    def test_end_to_end_chat_to_harvest(self):
        # The real flow: chat model -> provider -> cheap harvest model.
        assert get_harvest_model(provider_from_model("openai/gpt-4o")) == "openai/gpt-4o-mini"
        assert get_harvest_model(provider_from_model("anthropic/claude-opus-4-6")) == \
            "anthropic/claude-haiku-4-5-20250414"
