"""
Orient + Ground Boot Sequence — Session identity anchoring.

Provides a compact, tiered context injection for the start of each session:

1. **Orient** (~50-100 tokens): Identity anchor — who is this agent, who is the user,
   core relationship state. Always injected.
2. **Ground** (~100-200 tokens): Active threads, recent activity, current mood.
   Injected on first message of a session.

Inspired by Resonant Mind's mind_orient + mind_ground pattern and
MemPalace's L0+L1 memory stack (~170 tokens total).

Self-contained module — reads from existing DB models.
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from src.db.models import (
    Entity, PersonaIdentity, Relationship, UserProfile,
    UnresolvedThread, MoodState, Narrative, MemoryBlock,
    Conversation, Message,
)
from src.db.session import get_session


def orient(entity_id: str) -> dict[str, Any]:
    """
    Layer 0 — Identity anchor. Always loaded.
    
    Returns compact identity context:
    - Agent name + core personality
    - User name + key traits
    - Relationship summary
    - Time context
    """
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            return {"error": f"Entity {entity_id} not found"}

        persona = session.query(PersonaIdentity).filter_by(
            entity_id=entity_id
        ).first()

        # User profile
        profile = session.query(UserProfile).filter_by(
            entity_id=entity_id
        ).first()

        # Primary relationship
        rel = session.query(Relationship).filter_by(
            entity_id=entity_id
        ).first()

        # Current mood
        mood = session.query(MoodState).filter_by(
            entity_id=entity_id
        ).order_by(MoodState.timestamp.desc()).first()

        result = {
            "agent": {
                "name": entity.name,
                "personality": (persona.system_prompt[:200] + "...") if persona and persona.system_prompt and len(persona.system_prompt) > 200 else (persona.system_prompt if persona else None),
                "model": persona.model if persona else None,
            },
            "user": {},
            "relationship": {},
            "time": {
                "now": datetime.now(timezone.utc).isoformat(),
                "entity_age_days": (datetime.now(timezone.utc) - (entity.created_at.replace(tzinfo=timezone.utc) if entity.created_at and entity.created_at.tzinfo is None else entity.created_at)).days if entity.created_at else 0,
            },
        }

        if profile:
            result["user"] = {
                "name": getattr(profile, "preferred_name", None) or getattr(profile, "name", None),
                "neurotype": getattr(profile, "neurotype", None),
                "attachment_style": getattr(profile, "attachment_style", None),
            }
            # Remove None values
            result["user"] = {k: v for k, v in result["user"].items() if v}

        if rel:
            result["relationship"] = {
                "style": getattr(rel, "style_type", None),
                "trust_level": getattr(rel, "trust_level", None),
                "emotional_bank": getattr(rel, "emotional_bank", None),
            }
            result["relationship"] = {k: v for k, v in result["relationship"].items() if v}

        if mood:
            result["mood"] = {
                "energy": round(mood.energy_f or 0, 2),
                "warmth": round(mood.warmth or 0, 2),
                "chaos": round(mood.chaos or 0, 2),
            }

        return result


def ground(entity_id: str) -> dict[str, Any]:
    """
    Layer 1 — Active context grounding. Loaded on session start.
    
    Returns:
    - Active threads (unresolved_threads with status=open)
    - Recent activity summary
    - Pinned memory blocks
    - Current narrative scope
    """
    with get_session() as session:
        # Active threads
        threads = session.query(UnresolvedThread).filter_by(
            entity_id=entity_id,
        ).filter(
            UnresolvedThread.status.in_(["open", "processing"])
        ).order_by(UnresolvedThread.created_at.desc()).limit(5).all()

        active_threads = [
            {
                "id": t.id,
                "thread": t.thread,
                "status": t.status,
                "weight": t.emotional_weight,
            }
            for t in threads
        ]

        # Pinned memory blocks
        pinned_blocks = session.query(MemoryBlock).filter_by(
            entity_id=entity_id,
            status="active",
            pinned=True,
        ).all() if hasattr(MemoryBlock, "pinned") else []

        pinned = [
            {
                "id": b.id,
                "title": b.title,
                "category": getattr(b, "category", None),
                "preview": (b.content[:100] + "...") if b.content and len(b.content) > 100 else b.content,
            }
            for b in pinned_blocks
        ]

        # Recent activity: last conversation timestamp
        last_msg = session.query(Message.timestamp).join(
            Conversation, Message.conversation_id == Conversation.id
        ).filter(
            Conversation.entity_id == entity_id
        ).order_by(Message.timestamp.desc()).first()

        # Current narrative
        current_narrative = session.query(Narrative).filter_by(
            entity_id=entity_id,
            is_current=True,
        ).filter(
            Narrative.scope == "recent"
        ).first() if hasattr(Narrative, "is_current") else None

        # Time since last interaction
        time_away = None
        if last_msg and last_msg[0]:
            ts = last_msg[0]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - ts
            if delta.total_seconds() > 3600:
                hours = delta.total_seconds() / 3600
                if hours > 24:
                    time_away = f"{int(hours / 24)} days"
                else:
                    time_away = f"{int(hours)} hours"

        return {
            "active_threads": active_threads,
            "pinned_blocks": pinned,
            "time_since_last_interaction": time_away,
            "narrative_summary": current_narrative.content[:300] if current_narrative and current_narrative.content else None,
        }


def boot_context(entity_id: str) -> dict[str, Any]:
    """
    Full boot sequence — Orient (L0) + Ground (L1) + Persistent Threads.
    
    Returns combined context for session initialization.
    Designed to be injected into the system prompt preamble.
    """
    result = {
        "orient": orient(entity_id),
        "ground": ground(entity_id),
    }

    # Include persistent threads if available
    try:
        from src.services.persistent_threads import get_active_thread_summary
        thread_summary = get_active_thread_summary(entity_id)
        if thread_summary:
            result["persistent_threads"] = thread_summary
    except Exception:
        pass

    return result


def format_boot_context(entity_id: str, max_tokens: int = 300) -> str:
    """
    Format boot context as a compact text string for system prompt injection.
    
    Target: ~170-300 tokens (like MemPalace's L0+L1 layer).
    """
    ctx = boot_context(entity_id)
    o = ctx.get("orient", {})
    g = ctx.get("ground", {})

    lines = []

    # Identity anchor
    agent_name = o.get("agent", {}).get("name", "Agent")
    user_name = o.get("user", {}).get("name")
    lines.append(f"You are {agent_name}.")
    if user_name:
        lines.append(f"User: {user_name}.")

    # Relationship
    rel = o.get("relationship", {})
    if rel.get("style"):
        lines.append(f"Relationship: {rel['style']}.")
    if rel.get("trust_level"):
        lines.append(f"Trust: {rel['trust_level']}.")

    # Mood
    mood = o.get("mood")
    if mood:
        descriptors = []
        if mood.get("energy", 0) > 0.6:
            descriptors.append("energetic")
        elif mood.get("energy", 0) < 0.3:
            descriptors.append("low energy")
        if mood.get("warmth", 0) > 0.6:
            descriptors.append("warm")
        if mood.get("chaos", 0) > 0.5:
            descriptors.append("chaotic")
        if descriptors:
            lines.append(f"Current mood: {', '.join(descriptors)}.")

    # Time away
    time_away = g.get("time_since_last_interaction")
    if time_away:
        lines.append(f"Last interaction: {time_away} ago.")

    # Active threads
    threads = g.get("active_threads", [])
    if threads:
        thread_strs = [t["thread"][:60] for t in threads[:3]]
        lines.append(f"Active threads: {'; '.join(thread_strs)}.")

    # Pinned blocks
    pinned = g.get("pinned_blocks", [])
    if pinned:
        block_strs = [b["title"] for b in pinned[:3]]
        lines.append(f"Pinned notes: {', '.join(block_strs)}.")

    # Persistent threads (cross-session intentions)
    pt = ctx.get("persistent_threads")
    if pt:
        lines.append(pt)

    return " ".join(lines)
