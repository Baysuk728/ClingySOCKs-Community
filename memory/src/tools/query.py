"""
Agent Memory Tool — Unified Query (Structured + Semantic).

Single entry point replacing recall_memory + search_memories.
Supports three modes:
  - "exact":    SQL retrieval by type with optional text filter (old recall_memory)
  - "semantic": pgvector cosine similarity across types (old search_memories)
  - "auto":     Semantic if query provided, exact if only memory_type given
"""

from typing import Any

from src.memory_registry import normalize_type


async def memory_query(
    entity_id: str,
    query: str | None = None,
    memory_type: str | None = None,
    memory_types: list[str] | None = None,
    limit: int = 10,
    status: str = "active",
    search_mode: str = "auto",
) -> list[dict[str, Any]]:
    """
    Unified memory retrieval combining structured recall and semantic search.

    Args:
        entity_id: Entity to query
        query: Search text (required for semantic mode, optional for exact)
        memory_type: Single type for structured recall
        memory_types: List of types to search (None = all)
        limit: Max results
        status: Status filter (exact mode only)
        search_mode: "exact", "semantic", or "auto"

    Returns:
        List of memory items with unified fields including _type and optional similarity.
    """
    # Resolve effective mode
    mode = _resolve_mode(search_mode, query, memory_type)

    if mode == "exact":
        return _exact_query(entity_id, query, memory_type, memory_types, limit, status)
    else:
        return await _semantic_query(entity_id, query, memory_type, memory_types, limit)


def _resolve_mode(search_mode: str, query: str | None, memory_type: str | None) -> str:
    """Determine the effective search mode."""
    if search_mode == "exact":
        return "exact"
    if search_mode == "semantic":
        return "semantic"
    # auto: use semantic if query provided, exact if only type specified
    if query and query.strip():
        return "semantic"
    return "exact"


# ---------------------------------------------------------------------------
# Exact mode — structured SQL retrieval (was recall_memory)
# ---------------------------------------------------------------------------

def _exact_query(
    entity_id: str,
    query: str | None,
    memory_type: str | None,
    memory_types: list[str] | None,
    limit: int,
    status: str,
) -> list[dict[str, Any]]:
    """SQL-first retrieval by type with optional ILIKE text filter."""
    from src.tools.recall import recall_memory, _RECALL_CONFIG

    # If a single type is specified, delegate directly
    if memory_type:
        return recall_memory(entity_id, memory_type, query=query, limit=limit, status=status)

    # If multiple types specified, query each and merge
    types_to_query = memory_types or list(_RECALL_CONFIG.keys())
    all_results = []

    for mt in types_to_query:
        items = recall_memory(entity_id, mt, query=query, limit=limit, status=status)
        # Skip error responses
        if items and not (len(items) == 1 and "error" in items[0]):
            all_results.extend(items)

    # Sort by created_at if available, take top N
    all_results.sort(
        key=lambda x: x.get("updated_at") or x.get("created_at") or "",
        reverse=True,
    )
    return all_results[:limit]


# ---------------------------------------------------------------------------
# Semantic mode — pgvector similarity (was search_memories)
# ---------------------------------------------------------------------------

async def _semantic_query(
    entity_id: str,
    query: str | None,
    memory_type: str | None,
    memory_types: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """pgvector cosine similarity search with ILIKE fallback."""
    from src.tools.search import search_memories

    if not query or not query.strip():
        return [{"error": "query is required for semantic search mode"}]

    # Merge single type into types list
    effective_types = memory_types
    if memory_type and not memory_types:
        effective_types = [memory_type]

    return await search_memories(
        entity_id=entity_id,
        query=query,
        memory_types=effective_types,
        limit=limit,
    )
