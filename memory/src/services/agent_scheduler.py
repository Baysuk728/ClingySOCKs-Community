"""
Agent Self-Scheduling — Let the agent create its own routines and reminders.

Extends the existing AgentTask model with scheduling capabilities:
- One-shot scheduled tasks (reminders, follow-ups)
- Recurring routines (daily check-ins, weekly reviews)
- Condition-based triggers (on user return, on mood shift)

The scheduler runs as an async background loop that checks for
due tasks and executes them via the existing chat pipeline.

Inspired by Resonant's Orchestrator (routines, pulse, impulses, timers).
Self-contained — builds on existing AgentTask infrastructure.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from src.db.models import Entity
from src.db.session import get_session

logger = logging.getLogger("clingysocks.scheduler")


# ── Schedule Data Structures ─────────────────────────

# Stored as JSON in a new "schedules" table or as memory_blocks
# with category="schedule" to stay self-contained without schema changes.

SCHEDULE_CATEGORY = "agent_schedule"


def create_schedule(
    entity_id: str,
    title: str,
    prompt: str,
    schedule_type: str = "once",
    run_at: Optional[str] = None,
    cron_expr: Optional[str] = None,
    interval_minutes: Optional[int] = None,
    condition: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a scheduled task for the agent.
    
    Args:
        entity_id: Entity ID
        title: Short title (e.g., "Morning check-in")
        prompt: What the agent should do when triggered
        schedule_type: "once", "recurring", "condition"
        run_at: ISO datetime for one-shot tasks
        cron_expr: Cron-like pattern for recurring (simplified: "daily", "weekly", "hourly", or "HH:MM")
        interval_minutes: Simple interval-based recurrence
        condition: Trigger condition ("user_return", "mood_shift", "idle_hours:N")
    """
    import json
    from src.db.models import MemoryBlock

    schedule_data = {
        "schedule_type": schedule_type,
        "prompt": prompt,
        "run_at": run_at,
        "cron_expr": cron_expr,
        "interval_minutes": interval_minutes,
        "condition": condition,
        "last_run": None,
        "run_count": 0,
        "enabled": True,
    }

    with get_session() as session:
        block = MemoryBlock(
            entity_id=entity_id,
            title=title,
            content=json.dumps(schedule_data),
            category=SCHEDULE_CATEGORY,
            status="active",
        )
        if hasattr(block, "pinned"):
            block.pinned = False
        session.add(block)
        session.commit()

        return {
            "id": block.id,
            "title": title,
            "schedule_type": schedule_type,
            "message": f"Schedule created: {title}",
        }


def list_schedules(entity_id: str, enabled_only: bool = True) -> list[dict[str, Any]]:
    """List all schedules for an entity."""
    import json
    from src.db.models import MemoryBlock

    with get_session() as session:
        query = session.query(MemoryBlock).filter(
            MemoryBlock.entity_id == entity_id,
            MemoryBlock.category == SCHEDULE_CATEGORY,
        )
        if enabled_only:
            query = query.filter(MemoryBlock.status == "active")

        blocks = query.all()
        results = []

        for block in blocks:
            try:
                data = json.loads(block.content) if block.content else {}
            except json.JSONDecodeError:
                data = {}

            results.append({
                "id": block.id,
                "title": block.title,
                "schedule_type": data.get("schedule_type", "once"),
                "prompt": data.get("prompt", ""),
                "run_at": data.get("run_at"),
                "cron_expr": data.get("cron_expr"),
                "interval_minutes": data.get("interval_minutes"),
                "condition": data.get("condition"),
                "last_run": data.get("last_run"),
                "run_count": data.get("run_count", 0),
                "enabled": data.get("enabled", True),
            })

        return results


def disable_schedule(entity_id: str, schedule_id: int) -> dict[str, Any]:
    """Disable a scheduled task."""
    from src.db.models import MemoryBlock

    with get_session() as session:
        block = session.query(MemoryBlock).filter(
            MemoryBlock.id == schedule_id,
            MemoryBlock.entity_id == entity_id,
            MemoryBlock.category == SCHEDULE_CATEGORY,
        ).first()

        if not block:
            return {"error": f"Schedule {schedule_id} not found"}

        block.status = "archived"
        session.commit()
        return {"id": schedule_id, "message": "Schedule disabled"}


def _mark_schedule_run(session, block, now: datetime):
    """Mark a schedule as having been run."""
    import json
    try:
        data = json.loads(block.content) if block.content else {}
        data["last_run"] = now.isoformat()
        data["run_count"] = data.get("run_count", 0) + 1

        # Disable one-shot schedules after running
        if data.get("schedule_type") == "once":
            data["enabled"] = False
            block.status = "archived"

        block.content = json.dumps(data)
    except Exception:
        pass


# ── Schedule Checker (runs in background) ────────────

def get_due_schedules(entity_id: str) -> list[dict[str, Any]]:
    """
    Check which schedules are due to run now.
    Called by the scheduler loop.
    """
    import json
    from src.db.models import MemoryBlock

    now = datetime.now(timezone.utc)
    due = []

    with get_session() as session:
        blocks = session.query(MemoryBlock).filter(
            MemoryBlock.entity_id == entity_id,
            MemoryBlock.category == SCHEDULE_CATEGORY,
            MemoryBlock.status == "active",
        ).all()

        for block in blocks:
            try:
                data = json.loads(block.content) if block.content else {}
            except json.JSONDecodeError:
                continue

            if not data.get("enabled", True):
                continue

            is_due = False
            schedule_type = data.get("schedule_type", "once")

            if schedule_type == "once":
                run_at = data.get("run_at")
                if run_at:
                    try:
                        target = datetime.fromisoformat(run_at)
                        if target.tzinfo is None:
                            target = target.replace(tzinfo=timezone.utc)
                        if now >= target and not data.get("last_run"):
                            is_due = True
                    except (ValueError, TypeError):
                        pass

            elif schedule_type == "recurring":
                interval = data.get("interval_minutes")
                cron_expr = data.get("cron_expr")
                last_run = data.get("last_run")

                if interval:
                    if last_run:
                        try:
                            last = datetime.fromisoformat(last_run)
                            if last.tzinfo is None:
                                last = last.replace(tzinfo=timezone.utc)
                            if (now - last).total_seconds() >= interval * 60:
                                is_due = True
                        except (ValueError, TypeError):
                            is_due = True
                    else:
                        is_due = True

                elif cron_expr:
                    is_due = _check_simple_cron(cron_expr, now, last_run)

            if is_due:
                due.append({
                    "id": block.id,
                    "title": block.title,
                    "prompt": data.get("prompt", ""),
                    "schedule_type": schedule_type,
                })

                # Mark as run
                _mark_schedule_run(session, block, now)

        session.commit()

    return due


def _check_simple_cron(cron_expr: str, now: datetime, last_run: str | None) -> bool:
    """
    Simplified cron check supporting: "daily", "weekly", "hourly", "HH:MM".
    """
    if last_run:
        try:
            last = datetime.fromisoformat(last_run)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            last = None
    else:
        last = None

    if cron_expr == "hourly":
        return last is None or (now - last).total_seconds() >= 3600
    elif cron_expr == "daily":
        return last is None or (now - last).total_seconds() >= 86400
    elif cron_expr == "weekly":
        return last is None or (now - last).total_seconds() >= 604800
    elif ":" in cron_expr:
        # HH:MM format — run once per day at that time
        try:
            hour, minute = map(int, cron_expr.split(":"))
            if now.hour == hour and now.minute == minute:
                if last is None or last.date() < now.date():
                    return True
        except (ValueError, TypeError):
            pass
    return False


# ── Scheduler Daemon ─────────────────────────────────

class AgentScheduler:
    """
    Background scheduler that checks for due tasks and triggers them.
    
    Integrates with the WebSocket push system to deliver scheduled
    agent messages.
    
    Usage:
        scheduler = AgentScheduler(check_interval_seconds=60)
        await scheduler.start()
    """

    def __init__(self, check_interval_seconds: int = 60):
        self.interval = check_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"⏰ Agent scheduler started (checking every {self.interval}s)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏰ Agent scheduler stopped")

    async def _loop(self):
        while self._running:
            try:
                entity_ids = self._get_scheduled_entities()
                for eid in entity_ids:
                    if not self._running:
                        break
                    due = get_due_schedules(eid)
                    for task in due:
                        await self._execute_scheduled(eid, task)
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")

            await asyncio.sleep(self.interval)

    def _get_scheduled_entities(self) -> list[str]:
        """Get entities that have active schedules."""
        from src.db.models import MemoryBlock
        try:
            with get_session() as session:
                results = session.query(MemoryBlock.entity_id).filter(
                    MemoryBlock.category == SCHEDULE_CATEGORY,
                    MemoryBlock.status == "active",
                ).distinct().all()
                return [r[0] for r in results]
        except Exception:
            return []

    async def _execute_scheduled(self, entity_id: str, task: dict):
        """Execute a scheduled task by pushing a message via WebSocket."""
        logger.info(f"⏰ Executing scheduled task: {task['title']} for {entity_id}")

        try:
            from api.ws_manager import ws_manager
            await ws_manager.push_message(entity_id, {
                "type": "scheduled_task",
                "task_id": task["id"],
                "title": task["title"],
                "prompt": task["prompt"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error(f"Failed to execute scheduled task {task['id']}: {e}")


# Module-level singleton
agent_scheduler = AgentScheduler()
