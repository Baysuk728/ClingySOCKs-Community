"""Tests for Agent Self-Scheduling (agent_scheduler.py)."""

import json
import pytest
from datetime import datetime, timezone, timedelta


class TestCreateSchedule:
    """create_schedule() — create one-shot and recurring schedules."""

    def test_create_oneshot_schedule(self, seed_entity):
        from src.services.agent_scheduler import create_schedule
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        result = create_schedule(
            seed_entity,
            title="Reminder: check logs",
            prompt="Check the deployment logs",
            schedule_type="once",
            run_at=future,
        )

        assert "id" in result
        assert result["schedule_type"] == "once"
        assert result["title"] == "Reminder: check logs"

    def test_create_recurring_schedule(self, seed_entity):
        from src.services.agent_scheduler import create_schedule
        result = create_schedule(
            seed_entity,
            title="Daily check-in",
            prompt="How are you doing today?",
            schedule_type="recurring",
            cron_expr="daily",
        )

        assert result["schedule_type"] == "recurring"

    def test_create_interval_schedule(self, seed_entity):
        from src.services.agent_scheduler import create_schedule
        result = create_schedule(
            seed_entity,
            title="Hourly pulse",
            prompt="Quick status check",
            schedule_type="recurring",
            interval_minutes=60,
        )

        assert "id" in result


class TestListSchedules:
    """list_schedules() — list active schedules."""

    def test_list_empty(self, seed_entity):
        from src.services.agent_scheduler import list_schedules
        result = list_schedules(seed_entity)
        assert result == []

    def test_list_after_create(self, seed_entity):
        from src.services.agent_scheduler import create_schedule, list_schedules
        create_schedule(seed_entity, title="Task A", prompt="Do A")
        create_schedule(seed_entity, title="Task B", prompt="Do B")

        schedules = list_schedules(seed_entity)
        assert len(schedules) == 2

    def test_list_schedule_data_structure(self, seed_entity):
        from src.services.agent_scheduler import create_schedule, list_schedules
        create_schedule(
            seed_entity,
            title="Test task",
            prompt="Test prompt",
            schedule_type="recurring",
            interval_minutes=30,
        )

        schedules = list_schedules(seed_entity)
        s = schedules[0]
        assert s["title"] == "Test task"
        assert s["prompt"] == "Test prompt"
        assert s["schedule_type"] == "recurring"
        assert s["interval_minutes"] == 30
        assert s["enabled"] is True


class TestDisableSchedule:
    """disable_schedule() — disable a scheduled task."""

    def test_disable_existing(self, seed_entity):
        from src.services.agent_scheduler import create_schedule, disable_schedule, list_schedules
        result = create_schedule(seed_entity, title="Task", prompt="Do it")

        disable_result = disable_schedule(seed_entity, result["id"])
        assert "message" in disable_result

        # Should not appear in enabled-only list
        schedules = list_schedules(seed_entity, enabled_only=True)
        assert len(schedules) == 0

    def test_disable_nonexistent(self, seed_entity):
        from src.services.agent_scheduler import disable_schedule
        result = disable_schedule(seed_entity, 99999)
        assert "error" in result


class TestGetDueSchedules:
    """get_due_schedules() — find schedules that should run now."""

    def test_oneshot_past_due(self, seed_entity):
        from src.services.agent_scheduler import create_schedule, get_due_schedules

        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        create_schedule(
            seed_entity,
            title="Past due task",
            prompt="Should be due",
            schedule_type="once",
            run_at=past,
        )

        due = get_due_schedules(seed_entity)
        assert len(due) == 1
        assert due[0]["title"] == "Past due task"

    def test_oneshot_future_not_due(self, seed_entity):
        from src.services.agent_scheduler import create_schedule, get_due_schedules

        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        create_schedule(
            seed_entity,
            title="Future task",
            prompt="Not yet",
            schedule_type="once",
            run_at=future,
        )

        due = get_due_schedules(seed_entity)
        assert len(due) == 0

    def test_oneshot_doesnt_fire_twice(self, seed_entity):
        from src.services.agent_scheduler import create_schedule, get_due_schedules

        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        create_schedule(seed_entity, title="Once only", prompt="Run once", schedule_type="once", run_at=past)

        # First check — should fire
        due1 = get_due_schedules(seed_entity)
        assert len(due1) == 1

        # Second check — already ran, shouldn't fire again
        due2 = get_due_schedules(seed_entity)
        assert len(due2) == 0

    def test_recurring_interval_due(self, seed_entity):
        from src.services.agent_scheduler import create_schedule, get_due_schedules

        create_schedule(
            seed_entity,
            title="Frequent check",
            prompt="Check now",
            schedule_type="recurring",
            interval_minutes=1,  # Very short for testing
        )

        # First run — never run before, should be due
        due = get_due_schedules(seed_entity)
        assert len(due) == 1


class TestSimpleCron:
    """_check_simple_cron() — simplified cron expressions."""

    def test_daily_no_previous_run(self):
        from src.services.agent_scheduler import _check_simple_cron
        now = datetime.now(timezone.utc)
        assert _check_simple_cron("daily", now, None) is True

    def test_hourly_no_previous_run(self):
        from src.services.agent_scheduler import _check_simple_cron
        now = datetime.now(timezone.utc)
        assert _check_simple_cron("hourly", now, None) is True

    def test_weekly_no_previous_run(self):
        from src.services.agent_scheduler import _check_simple_cron
        now = datetime.now(timezone.utc)
        assert _check_simple_cron("weekly", now, None) is True

    def test_daily_ran_recently(self):
        from src.services.agent_scheduler import _check_simple_cron
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=2)).isoformat()
        assert _check_simple_cron("daily", now, recent) is False

    def test_daily_ran_long_ago(self):
        from src.services.agent_scheduler import _check_simple_cron
        now = datetime.now(timezone.utc)
        old = (now - timedelta(hours=25)).isoformat()
        assert _check_simple_cron("daily", now, old) is True
