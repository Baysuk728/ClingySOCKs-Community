"""
Subconscious Daemon — Background "dreaming" processor.

Runs periodically to:
1. Detect orphan memories (no edges, no reinforcement)
2. Find co-surfacing patterns (entities that appear together across types)
3. Generate connection proposals (suggested edges for review)
4. Analyze mood trends over time

Inspired by Resonant Mind's subconscious daemon concept.
Self-contained module — no changes to existing pipeline required.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import func, and_, or_, text

from src.db.models import (
    Edge, FactualEntity, LifeEvent, Artifact, EmotionalPattern,
    MemoryBlock, Lexicon, EchoDream, Narrative, UnresolvedThread,
    MoodState, Entity, HarvestLog,
)
from src.db.session import get_session
from src.memory_registry import graphable_types, MEMORY_TYPES, resolve_model

logger = logging.getLogger("clingysocks.subconscious")


# ── Orphan Detection ─────────────────────────────────

def find_orphan_memories(entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Find memories that have no edges and haven't been reinforced recently.
    These are "forgotten" items the daemon can surface or propose connections for.
    """
    orphans = []

    with get_session() as session:
        # Get all edge-connected IDs for this entity
        connected_from = set(
            r[0] for r in
            session.query(Edge.from_id).filter_by(entity_id=entity_id).all()
        )
        connected_to = set(
            r[0] for r in
            session.query(Edge.to_id).filter_by(entity_id=entity_id).all()
        )
        connected_ids = connected_from | connected_to

        # Check graphable types for items with no edges
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        for defn in graphable_types():
            try:
                model = resolve_model(defn.key)
                if model is None:
                    continue

                # Build query based on entity_id presence
                if hasattr(model, "entity_id"):
                    query = session.query(model).filter(
                        model.entity_id == entity_id
                    )
                else:
                    continue

                # Filter to items not recently reinforced
                if hasattr(model, "last_reinforced_at"):
                    query = query.filter(
                        or_(
                            model.last_reinforced_at.is_(None),
                            model.last_reinforced_at < cutoff,
                        )
                    )

                items = query.limit(limit * 2).all()

                for item in items:
                    item_id = str(getattr(item, "id", ""))
                    if item_id and item_id not in connected_ids:
                        label = ""
                        if hasattr(item, defn.label_field):
                            label = getattr(item, defn.label_field, "")
                        orphans.append({
                            "type": defn.key,
                            "id": item_id,
                            "label": label or item_id,
                            "created_at": str(getattr(item, "created_at", "")),
                        })

                        if len(orphans) >= limit:
                            return orphans

            except Exception as e:
                logger.debug(f"Skipping {defn.key} in orphan scan: {e}")
                continue

    return orphans


# ── Co-Surfacing Pattern Detection ───────────────────

def detect_cosurfacing_patterns(
    entity_id: str,
    min_cooccurrences: int = 3,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Find entities/memories that frequently appear together in edges
    but aren't directly connected. These are implicit patterns.
    """
    patterns = []

    with get_session() as session:
        # Find nodes that share many neighbors but aren't directly connected
        # Strategy: for each node, find its neighbors; look for neighbor overlap

        edges = session.query(Edge).filter_by(
            entity_id=entity_id, status="active"
        ).all()

        # Build adjacency list
        neighbors: dict[str, set[str]] = {}
        for edge in edges:
            from_key = f"{edge.from_type}:{edge.from_id}"
            to_key = f"{edge.to_type}:{edge.to_id}"
            neighbors.setdefault(from_key, set()).add(to_key)
            neighbors.setdefault(to_key, set()).add(from_key)

        # Find pairs with shared neighbors but no direct edge
        direct_edges = set()
        for edge in edges:
            from_key = f"{edge.from_type}:{edge.from_id}"
            to_key = f"{edge.to_type}:{edge.to_id}"
            direct_edges.add((from_key, to_key))
            direct_edges.add((to_key, from_key))

        node_keys = list(neighbors.keys())
        seen_pairs = set()

        for i, node_a in enumerate(node_keys):
            for node_b in node_keys[i + 1:]:
                if (node_a, node_b) in direct_edges:
                    continue

                shared = neighbors.get(node_a, set()) & neighbors.get(node_b, set())
                if len(shared) >= min_cooccurrences:
                    pair_key = tuple(sorted([node_a, node_b]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        patterns.append({
                            "node_a": node_a,
                            "node_b": node_b,
                            "shared_neighbors": len(shared),
                            "suggestion": f"These share {len(shared)} connections — consider linking them.",
                        })

                        if len(patterns) >= limit:
                            return patterns

    return patterns


# ── Connection Proposals ─────────────────────────────

def generate_proposals(entity_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Generate actionable connection proposals from orphans and patterns.
    These are stored in the daemon_proposals table for user review.
    """
    proposals = []

    # From orphans: suggest connecting to similar-typed items
    orphans = find_orphan_memories(entity_id, limit=5)
    for orphan in orphans:
        proposals.append({
            "type": "orphan_rescue",
            "source_type": orphan["type"],
            "source_id": orphan["id"],
            "source_label": orphan["label"],
            "reason": f"'{orphan['label']}' has no connections — it may relate to other {orphan['type']}s.",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # From co-surfacing: suggest explicit edges
    patterns = detect_cosurfacing_patterns(entity_id, limit=5)
    for pattern in patterns:
        proposals.append({
            "type": "cosurfacing_link",
            "node_a": pattern["node_a"],
            "node_b": pattern["node_b"],
            "reason": pattern["suggestion"],
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    return proposals[:limit]


# ── Mood Trend Analysis ──────────────────────────────

def analyze_mood_trends(entity_id: str, days: int = 7) -> dict[str, Any]:
    """
    Analyze mood trends over the last N days.
    Returns averages, direction, and notable shifts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with get_session() as session:
        states = session.query(MoodState).filter(
            MoodState.entity_id == entity_id,
            MoodState.timestamp >= cutoff,
        ).order_by(MoodState.timestamp.asc()).all()

        if not states:
            return {"status": "no_data", "message": "No mood data in the requested period."}

        dimensions = ["energy_f", "warmth", "protectiveness", "chaos", "melancholy"]
        averages = {}
        trends = {}

        for dim in dimensions:
            values = [getattr(s, dim, 0.0) or 0.0 for s in states]
            averages[dim] = round(sum(values) / len(values), 3)

            # Trend: compare first half vs second half
            mid = len(values) // 2
            if mid > 0:
                first_half = sum(values[:mid]) / mid
                second_half = sum(values[mid:]) / max(1, len(values) - mid)
                delta = second_half - first_half
                if delta > 0.1:
                    trends[dim] = "rising"
                elif delta < -0.1:
                    trends[dim] = "falling"
                else:
                    trends[dim] = "stable"
            else:
                trends[dim] = "insufficient_data"

        return {
            "period_days": days,
            "data_points": len(states),
            "averages": averages,
            "trends": trends,
            "latest": {
                dim: round(getattr(states[-1], dim, 0.0) or 0.0, 3)
                for dim in dimensions
            } if states else {},
        }


# ── Full Daemon Run ──────────────────────────────────

async def run_subconscious_cycle(entity_id: str) -> dict[str, Any]:
    """
    Run a full subconscious processing cycle for an entity.
    Returns a summary of findings.
    """
    logger.info(f"🧠 Subconscious cycle starting for {entity_id}")

    results = {
        "entity_id": entity_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "orphans": [],
        "patterns": [],
        "proposals": [],
        "mood_trends": {},
    }

    try:
        results["orphans"] = find_orphan_memories(entity_id)
        logger.info(f"  Found {len(results['orphans'])} orphan memories")
    except Exception as e:
        logger.error(f"  Orphan detection failed: {e}")
        results["orphans_error"] = str(e)

    try:
        results["patterns"] = detect_cosurfacing_patterns(entity_id)
        logger.info(f"  Found {len(results['patterns'])} co-surfacing patterns")
    except Exception as e:
        logger.error(f"  Pattern detection failed: {e}")
        results["patterns_error"] = str(e)

    try:
        results["proposals"] = generate_proposals(entity_id)
        logger.info(f"  Generated {len(results['proposals'])} proposals")
    except Exception as e:
        logger.error(f"  Proposal generation failed: {e}")
        results["proposals_error"] = str(e)

    try:
        results["mood_trends"] = analyze_mood_trends(entity_id)
    except Exception as e:
        logger.error(f"  Mood analysis failed: {e}")
        results["mood_trends_error"] = str(e)

    logger.info(f"🧠 Subconscious cycle complete for {entity_id}")
    return results


# ── Daemon Scheduler ─────────────────────────────────

class SubconsciousDaemon:
    """
    Background daemon that runs subconscious cycles periodically.
    
    Usage:
        daemon = SubconsciousDaemon(interval_minutes=30)
        await daemon.start()
        ...
        await daemon.stop()
    """

    def __init__(self, interval_minutes: int = 30):
        self.interval = interval_minutes * 60  # Convert to seconds
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_results: dict[str, dict] = {}

    async def start(self):
        """Start the daemon loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"🧠 Subconscious daemon started (every {self.interval // 60}m)")

    async def stop(self):
        """Stop the daemon loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🧠 Subconscious daemon stopped")

    async def _loop(self):
        """Main daemon loop — process all active entities."""
        while self._running:
            try:
                entity_ids = self._get_active_entities()
                for eid in entity_ids:
                    if not self._running:
                        break
                    try:
                        result = await run_subconscious_cycle(eid)
                        self._last_results[eid] = result
                    except Exception as e:
                        logger.error(f"Subconscious cycle failed for {eid}: {e}")
            except Exception as e:
                logger.error(f"Subconscious daemon loop error: {e}")

            await asyncio.sleep(self.interval)

    def _get_active_entities(self) -> list[str]:
        """Get all entity IDs that have had recent activity."""
        try:
            with get_session() as session:
                # Entities with harvest in last 7 days or recent conversations
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                entities = session.query(Entity.id).filter(
                    or_(
                        Entity.last_harvest >= cutoff,
                        Entity.created_at >= cutoff,
                    )
                ).all()
                return [e[0] for e in entities]
        except Exception:
            return []

    def get_last_results(self, entity_id: str | None = None) -> dict:
        """Get results from the last cycle."""
        if entity_id:
            return self._last_results.get(entity_id, {})
        return self._last_results


# Module-level singleton
subconscious_daemon = SubconsciousDaemon()
