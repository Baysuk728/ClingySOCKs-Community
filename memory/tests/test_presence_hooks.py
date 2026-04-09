"""Tests for Presence Hooks (presence_hooks.py)."""

import pytest
from datetime import datetime, timezone


class TestUpdatePresence:
    """update_presence() — track user online/offline state."""

    def test_set_online(self):
        from src.services.presence_hooks import update_presence, _presence_state
        result = update_presence("agent-1", "user-1", "online")

        assert result["state"] == "online"
        assert result["entity_id"] == "agent-1"
        assert result["user_id"] == "user-1"

    def test_transition_offline_to_online(self):
        from src.services.presence_hooks import update_presence
        update_presence("agent-1", "user-2", "offline")
        result = update_presence("agent-1", "user-2", "online")

        assert result["transition"] == "offline→online"

    def test_no_transition_same_state(self):
        from src.services.presence_hooks import update_presence
        update_presence("agent-1", "user-3", "online")
        result = update_presence("agent-1", "user-3", "online")

        assert result["transition"] is None

    def test_message_count_increments(self):
        from src.services.presence_hooks import update_presence, increment_message_count, get_presence
        update_presence("agent-1", "user-4", "online")
        increment_message_count("agent-1", "user-4")
        increment_message_count("agent-1", "user-4")

        presence = get_presence("agent-1", "user-4")
        assert presence["messages_this_session"] >= 2


class TestGetPresence:
    """get_presence() — retrieve current state."""

    def test_unknown_user(self):
        from src.services.presence_hooks import get_presence
        result = get_presence("agent-unknown", "user-unknown")

        assert result["state"] == "unknown"

    def test_known_user(self):
        from src.services.presence_hooks import update_presence, get_presence
        update_presence("agent-2", "user-5", "online")
        result = get_presence("agent-2", "user-5")

        assert result["state"] == "online"


class TestBuildPresenceContext:
    """build_presence_context() — structured context for injection."""

    def test_includes_time(self, patch_session):
        from src.services.presence_hooks import build_presence_context
        ctx = build_presence_context("test-entity")

        assert "time" in ctx
        assert "now" in ctx["time"]
        assert "day_of_week" in ctx["time"]
        assert "time_of_day" in ctx["time"]

    def test_includes_presence_state(self, patch_session):
        from src.services.presence_hooks import update_presence, build_presence_context
        update_presence("test-entity", "user", "online")
        ctx = build_presence_context("test-entity", "user")

        assert "presence" in ctx
        assert ctx["presence"]["state"] == "online"

    def test_includes_transition_info(self, patch_session):
        from src.services.presence_hooks import update_presence, build_presence_context
        update_presence("test-entity", "user-t", "offline")
        update_presence("test-entity", "user-t", "online")
        ctx = build_presence_context("test-entity", "user-t")

        assert ctx["presence"].get("transition") == "offline→online"


class TestFormatPresenceContext:
    """format_presence_context() — compact text string."""

    def test_format_returns_string(self, patch_session):
        from src.services.presence_hooks import format_presence_context
        text = format_presence_context("test-entity")

        assert isinstance(text, str)
        assert len(text) > 0

    def test_format_includes_time(self, patch_session):
        from src.services.presence_hooks import format_presence_context
        text = format_presence_context("test-entity")

        # Should include day of week
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        assert any(day in text for day in days)

    def test_format_includes_transition(self, patch_session):
        from src.services.presence_hooks import update_presence, format_presence_context
        update_presence("test-entity", "user-fmt", "offline")
        update_presence("test-entity", "user-fmt", "online")
        text = format_presence_context("test-entity", "user-fmt")

        assert "→" in text or "online" in text


class TestTimeOfDay:
    """_time_of_day() — descriptive time labels."""

    def test_morning(self):
        from src.services.presence_hooks import _time_of_day
        assert _time_of_day(8) == "morning"

    def test_afternoon(self):
        from src.services.presence_hooks import _time_of_day
        assert _time_of_day(14) == "afternoon"

    def test_evening(self):
        from src.services.presence_hooks import _time_of_day
        assert _time_of_day(19) == "evening"

    def test_night(self):
        from src.services.presence_hooks import _time_of_day
        assert _time_of_day(2) == "night"
