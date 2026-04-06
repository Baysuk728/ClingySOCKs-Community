"""
Database Setup & Embedding Utility for ClingySOCKs Memory.

Usage:
  python -m scripts.setup_db --init
  python -m scripts.setup_db --embed agent-id
  python -m scripts.setup_db --init --embed agent-id
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.db.session import init_db
from src.pipeline.embeddings import embed_entity_memories, EMBEDDINGS_ENABLED

async def run_embed(entity_id: str):
    print(f"🚀 Starting embedding generation for entity: {entity_id}")
    if not EMBEDDINGS_ENABLED:
        print("⚠️  WARNING: EMBEDDINGS_ENABLED is False in config.py or .env")
        print("    Enable it to generate embeddings.")
        return

    stats = await embed_entity_memories(entity_id)
    print(f"✨ Embedding complete! Stats: {stats}")

def main():
    parser = argparse.ArgumentParser(description="ClingySOCKs Memory Setup")
    parser.add_argument("--init", action="store_true", help="Initialize database tables & extensions")
    parser.add_argument("--embed", type=str, help="Entity ID to generate embeddings for", metavar="ENTITY_ID")
    
    args = parser.parse_args()

    if args.init:
        print("📦 Initializing database...")
        init_db()
        print("✅ Database initialized.")

    if args.embed:
        asyncio.run(run_embed(args.embed))

    if not args.init and not args.embed:
        parser.print_help()

if __name__ == "__main__":
    main()
