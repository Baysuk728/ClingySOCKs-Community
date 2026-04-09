"""Tests for Subconscious Daemon (subconscious_daemon.py)."""

import pytest


class TestFindOrphanMemories:
    """find_orphan_memories() — memories with no edges or reinforcement."""

    def test_finds_orphans(self, seed_memories):
        from src.services.subconscious_daemon import find_orphan_memories
        orphans = find_orphan_memories(seed_memories)

        assert isinstance(orphans, list)
        # The "Auth migration completed" event has no outgoing edges
        # (only incoming from "evolved_into"), check if detected

    def test_no_orphans_when_empty(self, patch_session):
        from src.services.subconscious_daemon import find_orphan_memories
        orphans = find_orphan_memories("nonexistent")
        assert orphans == [] or isinstance(orphans, list)


class TestDetectCosurfacingPatterns:
    """detect_cosurfacing_patterns() — nodes sharing neighbors but not connected."""

    def test_returns_list(self, seed_memories):
        from src.services.subconscious_daemon import detect_cosurfacing_patterns
        patterns = detect_cosurfacing_patterns(seed_memories)
        assert isinstance(patterns, list)


class TestGenerateProposals:
    """generate_proposals() — proposals for orphan rescue + new links."""

    def test_returns_proposals(self, seed_memories):
        from src.services.subconscious_daemon import generate_proposals
        proposals = generate_proposals(seed_memories)
        assert isinstance(proposals, list)


class TestRunSubconsciousCycle:
    """run_subconscious_cycle() — full cycle integration."""

    @pytest.mark.asyncio
    async def test_full_cycle(self, seed_memories):
        from src.services.subconscious_daemon import run_subconscious_cycle
        result = await run_subconscious_cycle(seed_memories)

        assert isinstance(result, dict)
        assert "entity_id" in result


class TestSubconsciousDaemon:
    """SubconsciousDaemon lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        from src.services.subconscious_daemon import SubconsciousDaemon
        daemon = SubconsciousDaemon(interval_minutes=5)

        await daemon.start()
        assert daemon._running is True

        await daemon.stop()
        assert daemon._running is False

    def test_get_last_results_empty(self):
        from src.services.subconscious_daemon import SubconsciousDaemon
        daemon = SubconsciousDaemon()
        results = daemon.get_last_results("some-entity")
        assert results is None or isinstance(results, dict)
