"""Tests for Persistent Threads (persistent_threads.py)."""

import pytest


class TestCreateThread:
    """create_thread() — create cross-session intentions."""

    def test_create_basic_thread(self, seed_entity):
        from src.services.persistent_threads import create_thread
        result = create_thread(seed_entity, title="Follow up on deploy", content="Check Railway logs")

        assert "id" in result
        assert result["title"] == "Follow up on deploy"
        assert result["status"] == "active"

    def test_create_pinned_by_default(self, seed_entity):
        from src.services.persistent_threads import create_thread, list_threads
        create_thread(seed_entity, title="Pinned thread", content="Should be pinned")

        threads = list_threads(seed_entity)
        assert len(threads) == 1
        # pinned should be True by default
        assert threads[0].get("pinned") is True


class TestListThreads:
    """list_threads() — list persistent threads with status filter."""

    def test_list_active_threads(self, seed_entity):
        from src.services.persistent_threads import create_thread, list_threads

        create_thread(seed_entity, title="Thread A", content="Active")
        create_thread(seed_entity, title="Thread B", content="Also active")

        threads = list_threads(seed_entity, status="active")
        assert len(threads) == 2

    def test_list_all_statuses(self, seed_entity):
        from src.services.persistent_threads import create_thread, update_thread, list_threads

        result = create_thread(seed_entity, title="Will resolve", content="Test")
        update_thread(seed_entity, result["id"], status="resolved")
        create_thread(seed_entity, title="Still active", content="Test")

        all_threads = list_threads(seed_entity, status="all")
        assert len(all_threads) == 2

        active = list_threads(seed_entity, status="active")
        assert len(active) == 1

    def test_list_respects_limit(self, seed_entity):
        from src.services.persistent_threads import create_thread, list_threads

        for i in range(5):
            create_thread(seed_entity, title=f"Thread {i}", content="Test")

        threads = list_threads(seed_entity, limit=3)
        assert len(threads) == 3


class TestUpdateThread:
    """update_thread() — modify title, content, status, pin state."""

    def test_update_title(self, seed_entity):
        from src.services.persistent_threads import create_thread, update_thread, list_threads
        result = create_thread(seed_entity, title="Old title", content="Content")

        update_thread(seed_entity, result["id"], title="New title")
        threads = list_threads(seed_entity)
        assert threads[0]["title"] == "New title"

    def test_append_content(self, seed_entity):
        from src.services.persistent_threads import create_thread, update_thread, list_threads
        result = create_thread(seed_entity, title="Thread", content="Initial content")

        update_thread(seed_entity, result["id"], content="+Added this note")
        threads = list_threads(seed_entity)
        assert "Initial content" in threads[0]["content"]
        assert "Added this note" in threads[0]["content"]

    def test_replace_content(self, seed_entity):
        from src.services.persistent_threads import create_thread, update_thread, list_threads
        result = create_thread(seed_entity, title="Thread", content="Old content")

        update_thread(seed_entity, result["id"], content="Completely new content")
        threads = list_threads(seed_entity)
        assert threads[0]["content"] == "Completely new content"

    def test_update_nonexistent_thread(self, seed_entity):
        from src.services.persistent_threads import update_thread
        result = update_thread(seed_entity, 99999, content="Won't work")
        assert "error" in result

    def test_invalid_status(self, seed_entity):
        from src.services.persistent_threads import create_thread, update_thread
        result = create_thread(seed_entity, title="Thread", content="Test")
        update_result = update_thread(seed_entity, result["id"], status="bogus")
        assert "error" in update_result


class TestResolveThread:
    """resolve_thread() — mark as resolved with optional note."""

    def test_resolve_with_note(self, seed_entity):
        from src.services.persistent_threads import create_thread, resolve_thread, list_threads
        result = create_thread(seed_entity, title="Thread", content="Initial")

        resolve_thread(seed_entity, result["id"], resolution_note="Done!")

        resolved = list_threads(seed_entity, status="resolved")
        assert len(resolved) == 1
        assert "Done!" in resolved[0]["content"]

    def test_resolve_removes_from_active(self, seed_entity):
        from src.services.persistent_threads import create_thread, resolve_thread, list_threads
        result = create_thread(seed_entity, title="Thread", content="Initial")
        resolve_thread(seed_entity, result["id"])

        active = list_threads(seed_entity, status="active")
        assert len(active) == 0


class TestGetActiveThreadSummary:
    """get_active_thread_summary() — compact text for context injection."""

    def test_empty_summary(self, seed_entity):
        from src.services.persistent_threads import get_active_thread_summary
        summary = get_active_thread_summary(seed_entity)
        assert summary == ""

    def test_summary_with_threads(self, seed_entity):
        from src.services.persistent_threads import create_thread, get_active_thread_summary
        create_thread(seed_entity, title="Check auth", content="Review test coverage")
        create_thread(seed_entity, title="Deploy staging", content="After auth review")

        summary = get_active_thread_summary(seed_entity)
        assert "Active threads:" in summary
        assert "Check auth" in summary
        assert "Deploy staging" in summary
