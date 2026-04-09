"""Tests for Timeline Service (timeline.py)."""

import pytest


class TestTraceTimeline:
    """trace_timeline() — chronological topic tracing across memory types."""

    @pytest.mark.asyncio
    async def test_trace_finds_life_events(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth")

        assert result["topic"] == "auth"
        assert result["event_count"] > 0

        types = [e["type"] for e in result["timeline"]]
        assert "life_event" in types

    @pytest.mark.asyncio
    async def test_trace_finds_factual_entities(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth")

        types = [e["type"] for e in result["timeline"]]
        # Should find FactualEntity "Auth System"
        factual_types = [t for t in types if t.startswith("factual:")]
        assert len(factual_types) >= 1

    @pytest.mark.asyncio
    async def test_trace_chronological_order(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth")

        timestamps = [
            e["timestamp"] for e in result["timeline"]
            if e.get("timestamp")
        ]
        # Should be sorted ascending
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_trace_respects_limit(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth", limit=2)

        assert result["event_count"] <= 2

    @pytest.mark.asyncio
    async def test_trace_includes_messages(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth", include_messages=True)

        types = [e["type"] for e in result["timeline"]]
        assert "message" in types

    @pytest.mark.asyncio
    async def test_trace_excludes_messages_by_default(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth", include_messages=False)

        types = [e["type"] for e in result["timeline"]]
        assert "message" not in types

    @pytest.mark.asyncio
    async def test_trace_no_results(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "zzz_nonexistent_topic_zzz")

        assert result["event_count"] == 0
        assert result["timeline"] == []

    @pytest.mark.asyncio
    async def test_trace_finds_lexicon(self, seed_memories):
        """Should find the PKCE lexicon entry when searching for 'auth'."""
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth")

        # PKCE definition mentions "auth" — should appear
        types = [e["type"] for e in result["timeline"]]
        assert "lexicon" in types

    @pytest.mark.asyncio
    async def test_trace_event_structure(self, seed_memories):
        from src.services.timeline import trace_timeline
        result = await trace_timeline(seed_memories, "auth")

        for event in result["timeline"]:
            assert "type" in event
            assert "id" in event
            assert "label" in event
            assert "timestamp" in event
            # No internal fields leaked
            assert "timestamp_raw" not in event
