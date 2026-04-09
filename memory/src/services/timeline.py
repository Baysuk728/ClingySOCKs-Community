"""
Timeline Service — Chronological topic tracing across all memory types.

Traces a topic through time, returning a chronologically ordered
narrative of everything related to it across all memory types.

Useful for queries like:
- "Give me the history of our auth decisions"
- "Timeline of my relationship with stress"
- "What happened with the migration project?"

Self-contained module — uses existing search infrastructure.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_

from src.db.models import (
    LifeEvent, Artifact, EmotionalPattern, Narrative,
    Lexicon, Permission, UnresolvedThread, MemoryBlock,
    Edge, FactualEntity, EchoDream, Message, Conversation,
)
from src.db.session import get_session
from src.memory_registry import MEMORY_TYPES, resolve_model


async def trace_timeline(
    entity_id: str,
    topic: str,
    limit: int = 20,
    include_messages: bool = False,
) -> dict[str, Any]:
    """
    Trace a topic chronologically through all memory types.
    
    Args:
        entity_id: Entity ID
        topic: The topic to trace
        limit: Max events
        include_messages: Whether to include raw chat messages
        
    Returns:
        Chronologically ordered list of events across types
    """
    events = []
    search_term = f"%{topic}%"

    with get_session() as session:
        # Search across all text-searchable types
        _search_configs = [
            ("life_event", LifeEvent, ["title", "narrative"], "entity_id"),
            ("artifact", Artifact, ["title", "context"], "entity_id"),
            ("emotional_pattern", EmotionalPattern, ["name", "trigger_what", "trigger_why"], "entity_id"),
            ("narrative", Narrative, ["content"], "entity_id"),
            ("lexicon", Lexicon, ["term", "definition"], "entity_id"),
            ("permission", Permission, ["permission", "context"], "entity_id"),
            ("unresolved_thread", UnresolvedThread, ["thread", "what_user_needs"], "entity_id"),
            ("memory_block", MemoryBlock, ["title", "content"], "entity_id"),
            ("echo_dream", EchoDream, ["whisper", "truth_root"], "entity_id"),
        ]

        for type_key, model, search_fields, entity_field in _search_configs:
            try:
                # Build ILIKE filter across search fields
                text_filters = [
                    getattr(model, field).ilike(search_term)
                    for field in search_fields
                    if hasattr(model, field)
                ]

                if not text_filters:
                    continue

                query = session.query(model).filter(
                    getattr(model, entity_field) == entity_id,
                    or_(*text_filters),
                ).order_by(model.created_at.asc()).limit(limit)

                items = query.all()

                for item in items:
                    # Extract the best label/content
                    defn = MEMORY_TYPES.get(type_key)
                    label = ""
                    content = ""

                    if hasattr(item, "title"):
                        label = item.title or ""
                    elif hasattr(item, "term"):
                        label = item.term or ""
                    elif hasattr(item, "name"):
                        label = item.name or ""
                    elif hasattr(item, "thread"):
                        label = item.thread or ""
                    elif hasattr(item, "permission"):
                        label = item.permission or ""

                    if hasattr(item, "narrative"):
                        content = item.narrative or ""
                    elif hasattr(item, "content"):
                        content = item.content or ""
                    elif hasattr(item, "definition"):
                        content = item.definition or ""
                    elif hasattr(item, "whisper"):
                        content = item.whisper or ""

                    events.append({
                        "type": type_key,
                        "id": str(item.id),
                        "label": label[:100],
                        "content": content[:300] if content else "",
                        "timestamp": item.created_at.isoformat() if item.created_at else None,
                        "timestamp_raw": item.created_at,
                    })

            except Exception:
                continue

        # Optionally include factual entities
        try:
            factual = session.query(FactualEntity).filter(
                FactualEntity.entity_id == entity_id,
                or_(
                    FactualEntity.name.ilike(search_term),
                    FactualEntity.description.ilike(search_term),
                )
            ).limit(limit).all()

            for fe in factual:
                events.append({
                    "type": f"factual:{fe.type}",
                    "id": fe.id,
                    "label": fe.name,
                    "content": (fe.description or "")[:300],
                    "timestamp": fe.created_at.isoformat() if fe.created_at else None,
                    "timestamp_raw": fe.created_at,
                })
        except Exception:
            pass

        # Include messages if requested
        if include_messages:
            try:
                messages = session.query(Message).join(
                    Conversation, Message.conversation_id == Conversation.id
                ).filter(
                    Conversation.entity_id == entity_id,
                    Message.content.ilike(search_term),
                ).order_by(Message.timestamp.asc()).limit(limit).all()

                for msg in messages:
                    events.append({
                        "type": "message",
                        "id": str(msg.id),
                        "label": f"[{msg.sender_id}] {(msg.content or '')[:60]}",
                        "content": (msg.content or "")[:300],
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                        "timestamp_raw": msg.timestamp,
                    })
            except Exception:
                pass

    # Sort by timestamp
    events.sort(key=lambda e: e.get("timestamp_raw") or datetime.min.replace(tzinfo=timezone.utc))

    # Clean up internal fields
    for event in events:
        event.pop("timestamp_raw", None)

    # Trim to limit
    events = events[:limit]

    return {
        "topic": topic,
        "entity_id": entity_id,
        "event_count": len(events),
        "timeline": events,
    }
