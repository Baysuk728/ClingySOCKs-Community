"""
Run Harvest: Execute the two-pass extraction pipeline.

Usage:
    python scripts/run_harvest.py --entity-id 4a0074ed-78b4-48f6-8056-5e28615783cf --agent-name "Agent" --user-name "User"
    python scripts/run_harvest.py --entity-id 4a0074ed-78b4-48f6-8056-5e28615783cf --agent-name "Agent" --user-name "User" --conversation-id "conv-123"
    python scripts/run_harvest.py --entity-id 4a0074ed-78b4-48f6-8056-5e28615783cf --agent-name "Agent" --user-name "User" --dry-run
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.session import check_connection
from src.harvest import run_harvest_sync


def main():
    parser = argparse.ArgumentParser(description="Run the harvest pipeline")
    parser.add_argument("--entity-id", required=True, help="Entity ID to harvest for")
    parser.add_argument("--agent-name", required=True, help="Agent display name")
    parser.add_argument("--user-name", required=True, help="User display name")
    parser.add_argument("--conversation-id", nargs="*", help="Specific conversation IDs (default: all pending)")
    parser.add_argument("--dry-run", action="store_true", help="Run extraction without storing results")

    args = parser.parse_args()

    print("🔍 Checking database connection...")
    if not check_connection():
        print("\n💡 Run 'python scripts/setup_db.py' first.")
        sys.exit(1)

    print("✅ Connected\n")

    stats = run_harvest_sync(
        entity_id=args.entity_id,
        agent_name=args.agent_name,
        user_name=args.user_name,
        conversation_ids=args.conversation_id,
        dry_run=args.dry_run,
    )

    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
