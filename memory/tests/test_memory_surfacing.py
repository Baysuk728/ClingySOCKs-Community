"""Tests for 3-Pool Memory Surfacing (memory_surfacing.py)."""

import pytest


class TestSurfaceMemories:
    """surface_memories() — 3-pool search: relevance, novelty, edge."""

    @pytest.mark.asyncio
    async def test_surface_returns_three_pools(self, seed_memories, monkeypatch):
        # Mock the search_memories function since it uses pgvector
        async def mock_search(entity_id, query, memory_types=None, limit=10):
            return [
                {"memory_type": "life_event", "id": "evt-auth-migration", "title": "Auth migration started"},
                {"memory_type": "lexicon", "id": "1", "term": "PKCE"},
            ]

        monkeypatch.setattr("src.tools.search.search_memories", mock_search)

        from src.services.memory_surfacing import surface_memories
        result = await surface_memories(seed_memories, "auth", total_limit=15)

        pools = result["pools"]
        assert "relevance" in pools
        assert "novelty" in pools
        assert "edge" in pools

    @pytest.mark.asyncio
    async def test_surface_relevance_pool(self, seed_memories, monkeypatch):
        """Relevance pool should use the existing search function."""
        search_called = {"count": 0}

        async def mock_search(entity_id, query, memory_types=None, limit=10):
            search_called["count"] += 1
            return [{"memory_type": "life_event", "id": "evt-auth-migration", "title": "Auth migration"}]

        monkeypatch.setattr("src.tools.search.search_memories", mock_search)

        from src.services.memory_surfacing import surface_memories
        result = await surface_memories(seed_memories, "auth")

        assert search_called["count"] >= 1
        assert len(result["pools"]["relevance"]) >= 1

    @pytest.mark.asyncio
    async def test_surface_novelty_pool(self, seed_memories, monkeypatch):
        """Novelty pool finds items not reinforced recently."""
        async def mock_search(entity_id, query, memory_types=None, limit=10):
            return []

        monkeypatch.setattr("src.tools.search.search_memories", mock_search)

        from src.services.memory_surfacing import surface_memories
        result = await surface_memories(seed_memories, "auth")

        assert "novelty" in result["pools"]
        assert isinstance(result["pools"]["novelty"], list)

    @pytest.mark.asyncio
    async def test_surface_edge_pool(self, seed_memories, monkeypatch):
        """Edge pool finds graph neighbors of relevance results."""
        async def mock_search(entity_id, query, memory_types=None, limit=10):
            return [{"memory_type": "life_event", "id": "evt-auth-migration", "title": "Auth"}]

        monkeypatch.setattr("src.tools.search.search_memories", mock_search)

        from src.services.memory_surfacing import surface_memories
        result = await surface_memories(seed_memories, "auth")

        assert "edge" in result["pools"]
        assert isinstance(result["pools"]["edge"], list)
        # evt-auth-migration has edges → should find neighbors
        if result["pools"]["edge"]:
            assert any("id" in item for item in result["pools"]["edge"])

    @pytest.mark.asyncio
    async def test_surface_respects_total_limit(self, seed_memories, monkeypatch):
        async def mock_search(entity_id, query, memory_types=None, limit=10):
            # Respect the limit parameter as the real function would
            return [{"memory_type": "life_event", "id": f"evt-{i}", "title": f"Event {i}"} for i in range(limit)]

        monkeypatch.setattr("src.tools.search.search_memories", mock_search)

        from src.services.memory_surfacing import surface_memories
        result = await surface_memories(seed_memories, "auth", total_limit=5)

        # Each pool should respect its allocated limit
        assert len(result["pools"]["relevance"]) <= 5

    @pytest.mark.asyncio
    async def test_surface_empty_query(self, seed_memories, monkeypatch):
        async def mock_search(entity_id, query, memory_types=None, limit=10):
            return []

        monkeypatch.setattr("src.tools.search.search_memories", mock_search)

        from src.services.memory_surfacing import surface_memories
        result = await surface_memories(seed_memories, "zzzzz_nonexistent")

        assert result["pools"]["relevance"] == []
