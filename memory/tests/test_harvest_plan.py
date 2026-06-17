"""
Tests for per-entity harvest planning and the conversation selector.

- resolve_harvest_plan(): derive a cheap model + key from the persona's chat
  provider, with env-var override and local-model reuse.
- _harvest_overrides(): only inject the chat key when the harvest model is the
  same provider as chat.
- The "due conversations" selector (via the batch wrapper) must not re-select a
  fully-harvested conversation — the off-by-one regression.
"""

from types import SimpleNamespace

import pytest

from src.harvest import resolve_harvest_plan, _harvest_overrides


@pytest.fixture
def mock_persona(monkeypatch):
    """Patch aload_persona_config to return a fake chat config (model + key)."""
    def _set(model, api_key=None):
        async def _fake_aload(entity_id, user_id=None, **kwargs):
            return SimpleNamespace(model=model, api_key=api_key)
        monkeypatch.setattr("src.persona_config.aload_persona_config", _fake_aload)
    return _set


@pytest.fixture(autouse=True)
def _clear_model_env(monkeypatch):
    """Harvest model env overrides off by default so auto-derivation is tested."""
    for k in ("NARRATIVE_MODEL", "EXTRACTION_MODEL", "SYNTHESIS_MODEL"):
        monkeypatch.delenv(k, raising=False)


class TestResolveHarvestPlan:
    async def test_openai_chat_gets_cheap_harvest_model(self, mock_persona):
        mock_persona("openai/gpt-4o", api_key="sk-test")
        plan = await resolve_harvest_plan("e1", "u1")
        assert plan["narrative"] == "openai/gpt-4o-mini"
        assert plan["extraction"] == "openai/gpt-4o-mini"
        assert plan["synthesis"] == "openai/gpt-4o-mini"
        assert plan["api_key"] == "sk-test"
        assert plan["chat_provider"] == "openai"

    async def test_gemini_chat_maps_to_flash(self, mock_persona):
        mock_persona("gemini/gemini-2.5-pro", api_key=None)
        plan = await resolve_harvest_plan("e1", "u1")
        assert plan["narrative"] == "gemini/gemini-2.5-flash"
        assert plan["chat_provider"] == "gemini"

    async def test_env_override_wins_per_stage(self, mock_persona, monkeypatch):
        mock_persona("openai/gpt-4o", api_key="sk-test")
        monkeypatch.setenv("NARRATIVE_MODEL", "gemini/gemini-2.5-pro")
        plan = await resolve_harvest_plan("e1", "u1")
        assert plan["narrative"] == "gemini/gemini-2.5-pro"   # pinned by env
        assert plan["extraction"] == "openai/gpt-4o-mini"      # still auto-derived

    async def test_local_chat_reuses_itself(self, mock_persona):
        mock_persona("ollama_chat/llama3.1", api_key=None)
        plan = await resolve_harvest_plan("e1", "u1")
        assert plan["narrative"] == "ollama_chat/llama3.1"
        assert plan["chat_provider"] == "local"

    async def test_persona_load_failure_falls_back(self, monkeypatch):
        async def _boom(entity_id, user_id=None, **kwargs):
            raise RuntimeError("no persona")
        monkeypatch.setattr("src.persona_config.aload_persona_config", _boom)
        plan = await resolve_harvest_plan("e1", "u1")
        # Must not crash; falls back to a usable (global default) model.
        assert plan["narrative"]
        assert plan["extraction"]
        assert plan["synthesis"]


class TestHarvestOverrides:
    def test_same_provider_injects_key(self):
        plan = {"api_key": "sk-x", "chat_provider": "openai"}
        assert _harvest_overrides("openai/gpt-4o-mini", plan) == {"api_key": "sk-x"}

    def test_different_provider_does_not_inject_key(self):
        # A power-user-pinned cross-provider model must not get the chat key.
        plan = {"api_key": "sk-x", "chat_provider": "openai"}
        assert _harvest_overrides("gemini/gemini-2.5-flash", plan) is None

    def test_no_key_returns_none(self):
        plan = {"api_key": None, "chat_provider": "openai"}
        assert _harvest_overrides("openai/gpt-4o-mini", plan) is None


class TestDueConversationSelector:
    """The batch wrapper shares the harvest selector logic; assert the
    off-by-one fix so finished conversations are not re-selected forever."""

    def test_finished_conversation_is_not_reselected(self, patch_session):
        from src.db.session import get_session
        from src.db.models import Entity, Conversation
        from scripts.run_harvest_all import _collect_targets

        with get_session() as s:
            # Fully harvested: 3 messages (idx 0..2), cursor at 2 → nothing new.
            s.add(Entity(id="ent-done", entity_type="agent", name="Done", owner_user_id="u"))
            s.add(Conversation(
                id="c-done", entity_id="ent-done", title="t",
                message_count=3, last_harvested_index=2, harvest_status="done",
            ))
            # Partially harvested: 10 messages, cursor at 4 → has new work.
            s.add(Entity(id="ent-partial", entity_type="agent", name="Partial", owner_user_id="u"))
            s.add(Conversation(
                id="c-partial", entity_id="ent-partial", title="t",
                message_count=10, last_harvested_index=4, harvest_status="done",
            ))
            # Pending (never harvested) → due.
            s.add(Entity(id="ent-pending", entity_type="agent", name="Pending", owner_user_id="u"))
            s.add(Conversation(
                id="c-pending", entity_id="ent-pending", title="t",
                message_count=5, last_harvested_index=-1, harvest_status="pending",
            ))

        due = {t["id"] for t in _collect_targets(process_all=False)}
        assert "ent-done" not in due       # 3 > 2 + 1 is False → not re-selected
        assert "ent-partial" in due        # 10 > 4 + 1 is True
        assert "ent-pending" in due        # pending status
