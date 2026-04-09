"""
3-Pool Memory Surfacing — Multi-perspective search results.

Instead of returning only relevance-ranked results, surfaces memories
from three pools:

1. **Relevance** — Standard semantic/text match (what you asked for)
2. **Novelty** — Items not seen recently (diversifies recall)
3. **Edge** — Loosely associated via graph connections (serendipity)

Inspired by Resonant Mind's 3-pool surfacing concept.
Self-contained — wraps existing search and recall tools.
"""

from typing import Any
from datetime import datetime, timezone, timedelta

from sqlalchemy import or_, and_

from src.db.models import (
    Edge, MemoryEmbedding,
)
from src.db.session import get_session
from src.config import EMBEDDINGS_ENABLED
from src.memory_registry import normalize_type, MEMORY_TYPES, resolve_model


async def surface_memories(
    entity_id: str,
    query: str,
    total_limit: int = 15,
    relevance_ratio: float = 0.6,
    novelty_ratio: float = 0.2,
    edge_ratio: float = 0.2,
) -> dict[str, Any]:
    """
    Surface memories from three pools.
    
    Args:
        entity_id: Entity ID
        query: Search query
        total_limit: Total results to return
        relevance_ratio: Fraction from relevance pool (default 60%)
        novelty_ratio: Fraction from novelty pool (default 20%)
        edge_ratio: Fraction from edge pool (default 20%)
        
    Returns:
        Dict with categorized results from each pool
    """
    relevance_count = max(1, int(total_limit * relevance_ratio))
    novelty_count = max(1, int(total_limit * novelty_ratio))
    edge_count = max(1, int(total_limit * edge_ratio))

    results = {
        "query": query,
        "pools": {
            "relevance": [],
            "novelty": [],
            "edge": [],
        },
        "total": 0,
    }

    # Pool 1: Relevance — standard search
    try:
        from src.tools.search import search_memories
        relevance_results = await search_memories(
            entity_id, query, limit=relevance_count
        )
        results["pools"]["relevance"] = relevance_results
    except Exception as e:
        results["pools"]["relevance_error"] = str(e)

    # Pool 2: Novelty — items not reinforced recently
    try:
        novelty_items = _get_novelty_pool(entity_id, query, limit=novelty_count)
        results["pools"]["novelty"] = novelty_items
    except Exception as e:
        results["pools"]["novelty_error"] = str(e)

    # Pool 3: Edge — loosely connected items
    try:
        edge_items = _get_edge_pool(entity_id, query, results["pools"]["relevance"], limit=edge_count)
        results["pools"]["edge"] = edge_items
    except Exception as e:
        results["pools"]["edge_error"] = str(e)

    results["total"] = (
        len(results["pools"].get("relevance", []))
        + len(results["pools"].get("novelty", []))
        + len(results["pools"].get("edge", []))
    )

    return results


def _get_novelty_pool(
    entity_id: str,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Get memories that haven't been surfaced recently.
    These might be relevant but forgotten — adding diversity to recall.
    """
    novelty_items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    with get_session() as session:
        # Look for items with low reinforcement_count or old last_reinforced_at
        # across multiple types
        search_types = ["life_event", "artifact", "lexicon", "memory_block", "echo_dream"]

        for type_key in search_types:
            defn = MEMORY_TYPES.get(type_key)
            if not defn:
                continue

            try:
                model = resolve_model(type_key)
                if not model or not hasattr(model, "entity_id"):
                    continue

                q = session.query(model).filter(model.entity_id == entity_id)

                # Prefer items not recently reinforced
                if hasattr(model, "last_reinforced_at"):
                    q = q.filter(
                        or_(
                            model.last_reinforced_at.is_(None),
                            model.last_reinforced_at < cutoff,
                        )
                    )

                # Text filter — basic ILIKE match to stay somewhat relevant
                if hasattr(model, defn.label_field):
                    label_col = getattr(model, defn.label_field)
                    q = q.filter(label_col.ilike(f"%{query[:30]}%"))

                # Order by least recently reinforced
                if hasattr(model, "last_reinforced_at"):
                    q = q.order_by(model.last_reinforced_at.asc().nullsfirst())
                elif hasattr(model, "created_at"):
                    q = q.order_by(model.created_at.asc())

                items = q.limit(2).all()

                for item in items:
                    label = getattr(item, defn.label_field, str(item.id))
                    novelty_items.append({
                        "_type": type_key,
                        "_pool": "novelty",
                        "id": str(item.id),
                        "label": label,
                        "created_at": str(getattr(item, "created_at", "")),
                        "last_reinforced_at": str(getattr(item, "last_reinforced_at", "never")),
                    })

                    if len(novelty_items) >= limit:
                        return novelty_items

            except Exception:
                continue

    return novelty_items


def _get_edge_pool(
    entity_id: str,
    query: str,
    relevance_results: list[dict],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Get loosely associated memories via graph edges.
    Start from relevance results and walk one hop outward.
    """
    edge_items = []
    seen_ids = set()

    # Collect IDs from relevance results to exclude
    for r in relevance_results:
        if isinstance(r, dict):
            rid = r.get("id", r.get("memory_id", ""))
            if rid:
                seen_ids.add(str(rid))

    with get_session() as session:
        # For each relevance result, find its neighbors
        for r in relevance_results[:5]:  # Only check first 5
            if not isinstance(r, dict):
                continue

            r_id = str(r.get("id", r.get("memory_id", "")))
            r_type = r.get("_type", r.get("memory_type", ""))

            if not r_id or not r_type:
                continue

            # Find edges from/to this item
            neighbors = session.query(Edge).filter(
                Edge.entity_id == entity_id,
                Edge.status == "active",
                or_(
                    and_(Edge.from_id == r_id, Edge.from_type == r_type),
                    and_(Edge.to_id == r_id, Edge.to_type == r_type),
                )
            ).limit(5).all()

            for edge in neighbors:
                # Get the other end
                if edge.from_id == r_id and edge.from_type == r_type:
                    other_id, other_type = edge.to_id, edge.to_type
                else:
                    other_id, other_type = edge.from_id, edge.from_type

                if other_id in seen_ids:
                    continue
                seen_ids.add(other_id)

                edge_items.append({
                    "_type": other_type,
                    "_pool": "edge",
                    "id": other_id,
                    "relation": edge.relation,
                    "via": f"{r_type}:{r_id}",
                    "edge_strength": edge.strength,
                    "context": edge.context,
                })

                if len(edge_items) >= limit:
                    return edge_items

    return edge_items
