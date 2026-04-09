"""Tests for Orient/Ground boot sequence (orient_ground.py)."""

import pytest


class TestOrient:
    """orient() — identity anchor returning agent/user/relationship/mood."""

    def test_orient_returns_agent_info(self, seed_entity):
        from src.services.orient_ground import orient
        result = orient(seed_entity)

        assert "agent" in result
        assert result["agent"]["name"] is not None

    def test_orient_returns_user_info(self, seed_entity):
        from src.services.orient_ground import orient
        result = orient(seed_entity)

        assert "user" in result

    def test_orient_returns_relationship(self, seed_entity):
        from src.services.orient_ground import orient
        result = orient(seed_entity)

        assert "relationship" in result

    def test_orient_returns_mood(self, seed_memories):
        from src.services.orient_ground import orient
        result = orient(seed_memories)

        assert "mood" in result
        # MoodState was seeded — should have data
        if result["mood"]:
            assert "primary_mood" in result["mood"] or "energy" in result["mood"]

    def test_orient_missing_entity(self, patch_session):
        """orient() should not crash for a non-existent entity."""
        from src.services.orient_ground import orient
        result = orient("nonexistent-entity-999")
        assert isinstance(result, dict)


class TestGround:
    """ground() — active threads, pinned notes, recent activity."""

    def test_ground_returns_active_threads(self, seed_memories):
        from src.services.orient_ground import ground
        result = ground(seed_memories)

        assert "active_threads" in result
        threads = result["active_threads"]
        assert isinstance(threads, list)
        assert len(threads) >= 1  # We seeded one unresolved thread

    def test_ground_returns_pinned_blocks(self, seed_memories):
        from src.services.orient_ground import ground
        result = ground(seed_memories)

        assert "pinned_blocks" in result
        blocks = result["pinned_blocks"]
        assert isinstance(blocks, list)
        assert len(blocks) >= 1  # We seeded one pinned block

    def test_ground_empty_entity(self, patch_session):
        """ground() should return empty lists for unknown entity."""
        from src.services.orient_ground import ground
        result = ground("nonexistent-entity")
        assert isinstance(result, dict)


class TestBootContext:
    """boot_context() — combined orient + ground."""

    def test_boot_context_has_both(self, seed_memories):
        from src.services.orient_ground import boot_context
        result = boot_context(seed_memories)

        assert "orient" in result
        assert "ground" in result

    def test_boot_context_includes_persistent_threads(self, seed_memories):
        """After creating a persistent thread, boot_context should include it."""
        from src.services.persistent_threads import create_thread
        create_thread(seed_memories, title="Follow up on auth", content="Check test coverage")

        from src.services.orient_ground import boot_context
        result = boot_context(seed_memories)

        # persistent_threads key should be present (non-empty string)
        assert "persistent_threads" in result
        assert "Follow up on auth" in result["persistent_threads"]


class TestFormatBootContext:
    """format_boot_context() — compact text string for prompt injection."""

    def test_format_returns_string(self, seed_memories):
        from src.services.orient_ground import format_boot_context
        text = format_boot_context(seed_memories)

        assert isinstance(text, str)
        assert len(text) > 0

    def test_format_includes_agent_name(self, seed_memories):
        from src.services.orient_ground import format_boot_context
        text = format_boot_context(seed_memories)

        assert "You are" in text

    def test_format_compact_size(self, seed_memories):
        """Output should be reasonably compact (under 2000 chars)."""
        from src.services.orient_ground import format_boot_context
        text = format_boot_context(seed_memories)

        assert len(text) < 2000
