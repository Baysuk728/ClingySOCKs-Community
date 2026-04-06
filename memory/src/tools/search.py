"""
Agent Memory Tool — Search (pgvector semantic + ILIKE fallback).

When EMBEDDINGS_ENABLED is True, uses pgvector cosine similarity.
Otherwise falls back to ILIKE text search.

Supports searching across all memory types including chat messages.
Results include source_conversation_id when available.
"""

from typing import Any
from sqlalchemy import or_

from src.config import EMBEDDINGS_ENABLED
from src.db.models import (
    Lexicon, InsideJoke, LifeEvent, Artifact, EmotionalPattern,
    StateNeed, Permission, UnresolvedThread, Narrative, EchoDream,
    Relationship, MemoryEmbedding, Message, MemoryBlock,
)
from src.db.session import get_session
from src.memory_registry import normalize_type

try:
    from src.services.memory_decay import reinforce_memory_by_id, resurrect_archived
except ImportError:
    reinforce_memory_by_id = None
    resurrect_archived = None


# Types → (Model, text_columns, entity_field, needs_relationship)
# Keys are canonical (singular) from the memory registry.
_SEARCH_CONFIG = {
    "lexicon": (Lexicon, ["term", "definition", "origin"], "entity_id", False),
    "inside_joke": (InsideJoke, ["phrase", "origin"], None, True),
    "life_event": (LifeEvent, ["title", "narrative"], "entity_id", False),
    "artifact": (Artifact, ["title", "context", "full_content"], "entity_id", False),
    "emotional_pattern": (EmotionalPattern, ["name", "trigger_what", "trigger_why"], "entity_id", False),
    "state_need": (StateNeed, ["state", "needs"], "entity_id", False),
    "permission": (Permission, ["permission", "context"], "entity_id", False),
    "unresolved_thread": (UnresolvedThread, ["thread", "what_user_needs"], "entity_id", False),
    "narrative": (Narrative, ["content"], "entity_id", False),
    "echo_dream": (EchoDream, ["whisper", "truth_root", "setting_description"], "entity_id", False),
    "memory_block": (MemoryBlock, ["title", "content", "category"], "entity_id", False),
}


async def search_memories(
    entity_id: str,
    query: str,
    memory_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Search across memory types using semantic similarity (pgvector)
    or ILIKE text search as fallback.

    Args:
        entity_id: Entity ID
        query: Search text / natural language query
        memory_types: Optional list of types to search (None = all including messages)
        limit: Max results

    Returns:
        List of matched items with type annotations, similarity scores,
        and source_conversation_id when available
    """
    if not query or not query.strip():
        return [{"error": "query is required"}]

    results = []
    
    # Optional resurrection check if we are doing across-the-board search or specific searches
    # Resurrected items are automatically added to results with high relevance
    _resurrection_types = {"life_event", "life_events", "artifact", "artifacts", "memory_block", "memory_blocks"}
    if resurrect_archived and EMBEDDINGS_ENABLED and (not memory_types or any(normalize_type(t) in {"life_event", "artifact", "memory_block"} for t in memory_types)):
        # Run resurrection in background (it will return restored items)
        try:
            resurrected = await resurrect_archived(entity_id, query)
            for item in resurrected:
                # Add a marker so the agent knows it hit a core deep memory
                item["_notice"] = "This memory was fading but your search brought it back to the surface."
                results.append(item)
        except Exception as e:
            # Print exception but don't fail search
            print(f"  ⚠️ Archive resurrection failed: {e}")

    if EMBEDDINGS_ENABLED:
        search_results = _semantic_search(entity_id, query, memory_types, limit)
    else:
        search_results = _ilike_search(entity_id, query, memory_types, limit)
        
    results.extend(search_results)
    
    # Sort by similarity/relevance if not empty
    if results and "similarity" in results[0]:
        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        # Apply limit after merge
        results = results[:limit]

    return results


def _semantic_search(
    entity_id: str,
    query: str,
    memory_types: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """
    pgvector cosine similarity search.

    Embeds the query, then finds nearest neighbors in memory_embeddings table.
    For message results, enriches with conversation_id, sender_id, timestamp.
    """
    from src.pipeline.embeddings import generate_embedding

    try:
        query_vector = generate_embedding(query)
    except Exception as e:
        print(f"  ⚠️ Embedding query failed, falling back to ILIKE: {e}")
        return _ilike_search(entity_id, query, memory_types, limit)

    results = []

    with get_session() as session:
        # Build query against memory_embeddings
        q = (
            session.query(
                MemoryEmbedding.memory_type,
                MemoryEmbedding.memory_id,
                MemoryEmbedding.text_preview,
                MemoryEmbedding.embedding.cosine_distance(query_vector).label("distance"),
            )
            .filter(MemoryEmbedding.entity_id == entity_id)
        )

        # Filter by memory types if specified.
        # Expand to include both canonical and legacy keys so we match
        # embeddings stored under either convention (old data vs new data).
        if memory_types:
            from src.memory_registry import MEMORY_TYPES as _REG, _LEGACY_MAP
            expanded = set()
            for mt in memory_types:
                canon = normalize_type(mt)
                expanded.add(canon)
                expanded.add(mt)
                # Also add the legacy key if it exists
                defn = _REG.get(canon)
                if defn and defn.legacy_key:
                    expanded.add(defn.legacy_key)
            q = q.filter(MemoryEmbedding.memory_type.in_(list(expanded)))

        # Order by similarity (lower distance = more similar)
        q = q.order_by("distance").limit(limit)

        rows = q.all()

        for row in rows:
            similarity = round(1.0 - row.distance, 4)
            canonical = normalize_type(row.memory_type)
            result = {
                "memory_type": row.memory_type,
                "_type": canonical,
                "id": row.memory_id,
                "text_preview": row.text_preview,
                "similarity": similarity,
            }

            # Enrich with source data
            if row.memory_type == "messages":
                msg = session.get(Message, row.memory_id)
                if msg:
                    result["conversation_id"] = msg.conversation_id
                    result["sender_id"] = msg.sender_id
                    result["timestamp"] = msg.timestamp.isoformat() if msg.timestamp else None
                    result["content"] = msg.content[:500]
            else:
                # Add source_conversation_id for other memory types
                _enrich_source(session, row.memory_type, row.memory_id, result)
                # Apply reinforcement (decay system — paid tier)
                if reinforce_memory_by_id:
                    reinforce_memory_by_id(row.memory_type, row.memory_id, entity_id)

            results.append(result)

    return results


def _enrich_source(session, memory_type: str, memory_id: str, result: dict):
    """Add source_conversation_id to a result if the model has it."""
    config = _SEARCH_CONFIG.get(normalize_type(memory_type))
    if not config:
        return

    Model = config[0]
    if not hasattr(Model, "source_conversation_id"):
        return

    item = session.get(Model, memory_id)
    if item and item.source_conversation_id:
        result["source_conversation_id"] = item.source_conversation_id


def _ilike_search(
    entity_id: str,
    query: str,
    memory_types: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """
    ILIKE fallback search (original implementation).
    Used when EMBEDDINGS_ENABLED is False or embedding generation fails.
    Now includes messages search.
    """
    types_to_search = memory_types or (list(_SEARCH_CONFIG.keys()) + ["messages"])
    results = []

    with get_session() as session:
        # For relationship-linked models
        rel = (
            session.query(Relationship)
            .filter_by(entity_id=entity_id, target_id="user")
            .first()
        )

        # --- Standard memory types ---
        for mem_type in types_to_search:
            if mem_type == "messages":
                continue  # Handle below

            config = _SEARCH_CONFIG.get(normalize_type(mem_type))
            if not config:
                continue

            Model, text_cols, entity_field, needs_rel = config

            # Build base query
            if needs_rel:
                if not rel:
                    continue
                q = session.query(Model).filter_by(relationship_id=rel.id)
            else:
                q = session.query(Model).filter_by(**{entity_field: entity_id})

            # Build ILIKE filters
            search_filters = []
            for col_name in text_cols:
                col = getattr(Model, col_name, None)
                if col is not None:
                    search_filters.append(col.ilike(f"%{query}%"))

            if not search_filters:
                continue

            q = q.filter(or_(*search_filters))

            if hasattr(Model, "created_at"):
                q = q.order_by(Model.created_at.desc())

            matches = q.limit(limit).all()

            for item in matches:
                result = {
                    "memory_type": mem_type,
                    "id": getattr(item, "id", None),
                }

                # Add source_conversation_id
                if hasattr(item, "source_conversation_id") and item.source_conversation_id:
                    result["source_conversation_id"] = item.source_conversation_id

                # Add the most relevant text fields
                for col_name in text_cols:
                    val = getattr(item, col_name, None)
                    if val:
                        result[col_name] = val[:300] if isinstance(val, str) else val

                results.append(result)
                
                # Apply reinforcement (decay system — paid tier)
                if reinforce_memory_by_id and hasattr(item, "id"):
                    reinforce_memory_by_id(mem_type, item.id, entity_id)

        # --- Messages (ILIKE) ---
        if "messages" in types_to_search:
            from src.db.models import Conversation

            conv_ids = [
                c.id for c in
                session.query(Conversation.id)
                .filter_by(entity_id=entity_id)
                .all()
            ]

            if conv_ids:
                msg_q = (
                    session.query(Message)
                    .filter(
                        Message.conversation_id.in_(conv_ids),
                        Message.content.ilike(f"%{query}%"),
                    )
                    .order_by(Message.timestamp.desc())
                    .limit(limit)
                )

                for msg in msg_q.all():
                    results.append({
                        "memory_type": "messages",
                        "id": msg.id,
                        "conversation_id": msg.conversation_id,
                        "sender_id": msg.sender_id,
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                        "content": msg.content[:500],
                    })

    return results
