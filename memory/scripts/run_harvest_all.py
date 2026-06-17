"""
Run Harvest for ALL entities (batch / scheduled wrapper).

Harvests every agent that has conversations needing work — pending, errored, or
with new unharvested messages — one after another in a single process. Designed
to be the start command of a scheduled (cron) job: it runs once, processes every
due agent, prints a summary, and exits (non-zero if any agent failed).

Because each agent's own per-chunk checkpoints make harvest resumable, this is
safe to run on a schedule: an agent interrupted last time picks up where it left
off, and a fully-harvested agent is a fast no-op.

Usage:
    python scripts/run_harvest_all.py             # only agents with work to do
    python scripts/run_harvest_all.py --all       # every agent, even if idle
    python scripts/run_harvest_all.py --dry-run    # extract but don't store
"""

import sys
import os
import argparse
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_

from src.db.session import check_connection, get_session
from src.db.models import Entity, Conversation, UserProfile
from src.harvest import harvest_entity


def _collect_targets(process_all: bool) -> list[dict]:
    """Return [{id, agent_name, user_name}] for the agents to harvest.

    Without --all, only agents that have at least one conversation that is
    pending/errored OR has unharvested messages. The message_index is 0-based
    and last_harvested_index holds the last harvested index (default -1), so a
    conversation has new work when message_count > last_harvested_index + 1.
    """
    with get_session() as session:
        if process_all:
            entity_ids = [row[0] for row in session.query(Entity.id).all()]
        else:
            rows = (
                session.query(Conversation.entity_id)
                .filter(or_(
                    Conversation.harvest_status.in_(["pending", "error"]),
                    Conversation.message_count > Conversation.last_harvested_index + 1,
                ))
                .distinct()
                .all()
            )
            entity_ids = [r[0] for r in rows]

        targets = []
        for eid in entity_ids:
            ent = session.get(Entity, eid)
            if not ent:
                continue
            user_name = "User"
            profile = session.get(UserProfile, eid)
            if profile and getattr(profile, "name", None):
                user_name = profile.name
            targets.append({
                "id": eid,
                "agent_name": ent.name or "Agent",
                "user_name": user_name,
            })
        return targets


async def _run_all(targets: list[dict], dry_run: bool) -> int:
    """Harvest each target sequentially in one event loop. Returns failure count."""
    failures = 0
    total = len(targets)
    for i, t in enumerate(targets, 1):
        print(f"\n[{i}/{total}] Harvesting {t['agent_name']} ({t['id']})")
        try:
            stats = await harvest_entity(
                entity_id=t["id"],
                agent_name=t["agent_name"],
                user_name=t["user_name"],
                dry_run=dry_run,
            )
            if stats.get("errors"):
                failures += 1
                print(f"   ⚠️ {t['agent_name']} finished with {len(stats['errors'])} error(s)")
        except Exception as e:
            failures += 1
            print(f"   ❌ {t['agent_name']} crashed: {str(e)[:300]}")
    return failures


def main():
    parser = argparse.ArgumentParser(description="Harvest all agents with pending work")
    parser.add_argument("--all", action="store_true",
                        help="Harvest every agent, even ones with no pending work")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run extraction without storing results")
    args = parser.parse_args()

    print("🔍 Checking database connection...")
    if not check_connection():
        print("\n💡 Database not reachable. Check DATABASE_URL / Postgres service.")
        sys.exit(1)
    print("✅ Connected")

    targets = _collect_targets(process_all=args.all)
    if not targets:
        print("✨ Nothing to harvest — all agents are up to date.")
        sys.exit(0)

    print(f"🌾 {len(targets)} agent(s) to harvest"
          f"{' (ALL)' if args.all else ' (with pending work)'}")

    failures = asyncio.run(_run_all(targets, dry_run=args.dry_run))

    print(f"\n{'='*60}")
    print(f"📊 Batch harvest complete — {len(targets) - failures}/{len(targets)} clean, "
          f"{failures} with errors")
    print(f"{'='*60}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
