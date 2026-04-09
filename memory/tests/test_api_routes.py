"""Tests for Enhanced Memory API Routes (enhanced_memory.py)."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def app():
    """Create a FastAPI test app with the enhanced memory router."""
    from fastapi import FastAPI
    from api.routes.enhanced_memory import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/enhanced")
    return test_app


@pytest.fixture
def client(app):
    """Synchronous test client."""
    from fastapi.testclient import TestClient
    return TestClient(app)


class TestBootEndpoints:
    """GET /enhanced/{entity_id}/orient, /ground, /boot, /boot/text"""

    def test_orient_endpoint(self, client, seed_memories):
        with patch("src.services.orient_ground.orient", return_value={"agent": {"name": "Test"}}):
            resp = client.get(f"/enhanced/{seed_memories}/orient")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    def test_ground_endpoint(self, client, seed_memories):
        with patch("src.services.orient_ground.ground", return_value={"active_threads": []}):
            resp = client.get(f"/enhanced/{seed_memories}/ground")
            assert resp.status_code == 200

    def test_boot_endpoint(self, client, seed_memories):
        with patch("src.services.orient_ground.boot_context", return_value={"orient": {}, "ground": {}}):
            resp = client.get(f"/enhanced/{seed_memories}/boot")
            assert resp.status_code == 200

    def test_boot_text_endpoint(self, client, seed_memories):
        with patch("src.services.orient_ground.format_boot_context", return_value="You are TestAgent."):
            resp = client.get(f"/enhanced/{seed_memories}/boot/text")
            assert resp.status_code == 200
            data = resp.json()
            assert "text" in data["data"]
            assert "char_count" in data["data"]


class TestSurfaceEndpoint:
    """POST /enhanced/{entity_id}/surface"""

    def test_surface_requires_query(self, client, seed_memories):
        resp = client.post(f"/enhanced/{seed_memories}/surface", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in str(data)

    def test_surface_with_query(self, client, seed_memories):
        mock_result = {"relevance": [], "novelty": [], "edge": []}
        with patch("src.services.memory_surfacing.surface_memories", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post(f"/enhanced/{seed_memories}/surface", json={"query": "auth", "limit": 10})
            assert resp.status_code == 200


class TestTimelineEndpoint:
    """GET /enhanced/{entity_id}/timeline"""

    def test_timeline_requires_topic(self, client, seed_memories):
        resp = client.get(f"/enhanced/{seed_memories}/timeline")
        assert resp.status_code == 422  # Missing required query param

    def test_timeline_with_topic(self, client, seed_memories):
        mock_result = {"topic": "auth", "entity_id": seed_memories, "event_count": 0, "timeline": []}
        with patch("src.services.timeline.trace_timeline", new_callable=AsyncMock, return_value=mock_result):
            resp = client.get(f"/enhanced/{seed_memories}/timeline?topic=auth")
            assert resp.status_code == 200


class TestThreadEndpoints:
    """CRUD /enhanced/{entity_id}/threads"""

    def test_create_thread(self, client, seed_memories):
        with patch("src.services.persistent_threads.create_thread",
                    return_value={"id": 1, "title": "Test", "status": "active"}):
            resp = client.post(f"/enhanced/{seed_memories}/threads",
                               json={"title": "Test thread", "content": "Test content"})
            assert resp.status_code == 200

    def test_list_threads(self, client, seed_memories):
        with patch("src.services.persistent_threads.list_threads", return_value=[]):
            resp = client.get(f"/enhanced/{seed_memories}/threads")
            assert resp.status_code == 200

    def test_update_thread(self, client, seed_memories):
        with patch("src.services.persistent_threads.update_thread",
                    return_value={"id": 1, "title": "Updated", "status": "active"}):
            resp = client.put(f"/enhanced/{seed_memories}/threads/1",
                              json={"content": "+New note"})
            assert resp.status_code == 200

    def test_resolve_thread(self, client, seed_memories):
        with patch("src.services.persistent_threads.resolve_thread",
                    return_value={"id": 1, "status": "resolved"}):
            resp = client.delete(f"/enhanced/{seed_memories}/threads/1?note=Done")
            assert resp.status_code == 200


class TestScheduleEndpoints:
    """CRUD /enhanced/{entity_id}/schedules"""

    def test_list_schedules(self, client, seed_memories):
        with patch("src.services.agent_scheduler.list_schedules", return_value=[]):
            resp = client.get(f"/enhanced/{seed_memories}/schedules")
            assert resp.status_code == 200

    def test_create_schedule(self, client, seed_memories):
        with patch("src.services.agent_scheduler.create_schedule",
                    return_value={"id": 1, "title": "Task", "schedule_type": "once"}):
            resp = client.post(f"/enhanced/{seed_memories}/schedules",
                               json={"title": "Test", "prompt": "Do it"})
            assert resp.status_code == 200

    def test_disable_schedule(self, client, seed_memories):
        with patch("src.services.agent_scheduler.disable_schedule",
                    return_value={"id": 1, "message": "Disabled"}):
            resp = client.delete(f"/enhanced/{seed_memories}/schedules/1")
            assert resp.status_code == 200


class TestPresenceEndpoints:
    """GET/POST /enhanced/{entity_id}/presence"""

    def test_get_presence(self, client, seed_memories):
        with patch("src.services.presence_hooks.get_presence",
                    return_value={"state": "unknown"}):
            resp = client.get(f"/enhanced/{seed_memories}/presence")
            assert resp.status_code == 200

    def test_update_presence(self, client, seed_memories):
        with patch("src.services.presence_hooks.update_presence",
                    return_value={"state": "online", "transition": "offline→online"}):
            resp = client.post(f"/enhanced/{seed_memories}/presence",
                               json={"user_id": "user", "state": "online"})
            assert resp.status_code == 200

    def test_presence_context(self, client, seed_memories):
        with patch("src.services.presence_hooks.format_presence_context",
                    return_value="[2026-04-09 12:00 UTC] Wednesday afternoon"):
            resp = client.get(f"/enhanced/{seed_memories}/presence/context")
            assert resp.status_code == 200
            data = resp.json()
            assert "text" in data["data"]


class TestSubconsciousEndpoints:
    """GET/POST /enhanced/{entity_id}/subconscious"""

    def test_subconscious_status_no_data(self, client, seed_memories):
        from src.services.subconscious_daemon import SubconsciousDaemon
        with patch("src.services.subconscious_daemon.subconscious_daemon") as mock_daemon:
            mock_daemon.get_last_results.return_value = None
            resp = client.get(f"/enhanced/{seed_memories}/subconscious")
            assert resp.status_code == 200

    def test_trigger_subconscious(self, client, seed_memories):
        with patch("src.services.subconscious_daemon.run_subconscious_cycle",
                    new_callable=AsyncMock,
                    return_value={"entity_id": seed_memories, "orphans": 0}):
            resp = client.post(f"/enhanced/{seed_memories}/subconscious/run")
            assert resp.status_code == 200
