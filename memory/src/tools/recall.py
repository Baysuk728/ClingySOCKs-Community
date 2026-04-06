"""
Agent Memory Tool — Recall (Structured Retrieval).

SQL-first retrieval by memory type with optional filtering.

Accepts both canonical keys (from registry) and legacy plural keys
for backward compatibility.
"""

from typing import Any
from sqlalchemy import or_

from src.db.models import (
    Lexicon, InsideJoke, LifeEvent, Artifact, EmotionalPattern,
    RepairPattern, StateNeed, Permission, RelationalRitual,
    UnresolvedThread, Narrative, SharedMythology, EchoDream,
    IntimateMoment, Relationship, UserProfile, PreferenceEvolution,
    MemoryBlock, Preference, DreamJournalEntry
)
from src.db.session import get_session
from src.memory_registry import normalize_type

try:
    from src.services.memory_decay import reinforce_memory_by_id
except ImportError:
    reinforce_memory_by_id = None


# Map memory_type → (Model, text search fields, serialize function)
_RECALL_CONFIG = {
    "lexicon": {
        "model": Lexicon,
        "search_fields": ["term", "definition"],
        "serialize": lambda l: {
            "id": l.id, "term": l.term, "definition": l.definition,
            "origin": l.origin, "lore_score": l.lore_score,
            "status": l.status, "evolution_notes": l.evolution_notes,
        },
        "status_field": "status",
    },
    "inside_jokes": {
        "model": InsideJoke,
        "search_fields": ["phrase", "origin"],
        "serialize": lambda j: {
            "id": j.id, "phrase": j.phrase, "origin": j.origin,
            "usage": j.usage, "tone": j.tone,
        },
        "needs_relationship": True,
    },
    "life_events": {
        "model": LifeEvent,
        "search_fields": ["title", "narrative"],
        "serialize": lambda e: {
            "id": e.id, "title": e.title, "narrative": e.narrative,
            "emotional_impact": e.emotional_impact, "period": e.period,
            "category": e.category,
        },
    },
    "artifacts": {
        "model": Artifact,
        "search_fields": ["title", "context"],
        "serialize": lambda a: {
            "id": a.id, "title": a.title, "type": a.type,
            "context": a.context, "emotional_significance": a.emotional_significance,
        },
    },
    "emotional_patterns": {
        "model": EmotionalPattern,
        "search_fields": ["name", "trigger_what"],
        "serialize": lambda p: {
            "id": p.id, "name": p.name, "trigger_what": p.trigger_what,
            "trigger_why": p.trigger_why,
            "response_internal": p.response_internal,
            "response_external": p.response_external,
            "status": p.status,
        },
        "status_field": "status",
    },
    "repair_patterns": {
        "model": RepairPattern,
        "search_fields": ["trigger", "rupture", "repair"],
        "serialize": lambda r: {
            "id": r.id, "trigger": r.trigger, "rupture": r.rupture,
            "repair": r.repair, "lesson": r.lesson,
        },
    },
    "state_needs": {
        "model": StateNeed,
        "search_fields": ["state", "needs"],
        "serialize": lambda s: {
            "id": s.id, "state": s.state, "needs": s.needs,
            "anti_needs": s.anti_needs, "signals": s.signals,
        },
    },
    "permissions": {
        "model": Permission,
        "search_fields": ["permission", "context"],
        "serialize": lambda p: {
            "id": p.id, "permission": p.permission, "type": p.type,
            "context": p.context, "status": p.status,
        },
        "status_field": "status",
    },
    "rituals": {
        "model": RelationalRitual,
        "search_fields": ["name", "pattern"],
        "serialize": lambda r: {
            "id": r.id, "name": r.name, "pattern": r.pattern,
            "significance": r.significance,
        },
    },
    "unresolved_threads": {
        "model": UnresolvedThread,
        "search_fields": ["thread", "what_user_needs"],
        "serialize": lambda t: {
            "id": t.id, "thread": t.thread,
            "emotional_weight": t.emotional_weight,
            "what_user_needs": t.what_user_needs,
            "status": t.status,
        },
        "status_field": "status",
    },
    "narratives": {
        "model": Narrative,
        "search_fields": ["content"],
        "serialize": lambda n: {
            "id": n.id, "scope": n.scope, "content": n.content[:500],
        },
    },
    "mythology": {
        "model": SharedMythology,
        "search_fields": [],
        "serialize": lambda m: {
            "id": m.id, "origin_story": m.origin_story,
            "universe_rules": m.universe_rules,
            "active_arcs": m.active_arcs,
        },
    },
    "echo_dreams": {
        "model": EchoDream,
        "search_fields": ["whisper", "truth_root", "setting_description"],
        "serialize": lambda d: {
            "id": d.id, "emotion_tags": d.emotion_tags,
            "setting_description": d.setting_description,
            "whisper": d.whisper, "truth_root": d.truth_root,
            "dream_type": d.dream_type, "rarity": d.rarity,
        },
    },
    "intimate_moments": {
        "model": IntimateMoment,
        "search_fields": ["summary"],
        "serialize": lambda m: {
            "id": m.id, "summary": m.summary,
            "emotional_resonance": m.emotional_resonance,
            "significance": m.significance,
        },
        "needs_relationship": True,
    },
    "user_profile": {
        "model": UserProfile,
        "search_fields": [],
        "serialize": lambda p: {
            "name": p.name, "pronouns": p.pronouns,
            "neurotype": p.neurotype, "attachment_style": p.attachment_style,
            "hobbies": p.hobbies, "interests": p.interests,
            "life_goals": p.life_goals, "longings": p.longings,
            "family_situation": p.family_situation,
            "work_situation": p.work_situation,
        },
        "singleton": True,
    },
    "preference_evolutions": {
        "model": PreferenceEvolution,
        "search_fields": ["subject", "reason"],
        "serialize": lambda e: {
            "id": e.id, "subject": e.subject,
            "previous_state": e.previous_state,
            "current_state": e.current_state,
            "reason": e.reason,
        },
    },
    "memory_blocks": {
        "model": MemoryBlock,
        "search_fields": ["title", "content", "category"],
        "serialize": lambda b: {
            "id": b.id, "title": b.title, "content": b.content,
            "category": b.category, "pinned": b.pinned, "status": b.status,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        },
        "status_field": "status",
    },
    "preferences": {
        "model": Preference,
        "search_fields": ["domain", "opinion"],
        "serialize": lambda p: {
            "id": p.id, "domain": p.domain, "opinion": p.opinion,
            "strength": p.strength,
            "origin": p.origin,
            "times_expressed": p.times_expressed,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        },
    },
    "dream_journal": {
        "model": DreamJournalEntry,
        "search_fields": ["raw_fragment", "emotional_residue"],
        "serialize": lambda d: {
            "id": d.id,
            "dream_type": d.dream_type,
            "raw_fragment": d.raw_fragment,
            "emotional_residue": d.emotional_residue,
            "residue_valence": d.residue_valence,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        },
    },
}


def recall_memory(
    entity_id: str,
    memory_type: str,
    query: str | None = None,
    limit: int = 10,
    status: str = "active",
) -> list[dict[str, Any]]:
    """
    Retrieve structured memories by type with optional search.

    Args:
        entity_id: The entity to recall memories for
        memory_type: Type of memory (from MEMORY_TYPES)
        query: Optional text search filter
        limit: Max results
        status: Status filter (active/resolved/deprecated/all)

    Returns:
        List of serialized memory items
    """
    # Accept both canonical keys ("life_event") and legacy keys ("life_events")
    config = _RECALL_CONFIG.get(memory_type)
    if not config:
        # Try canonical key → find matching legacy key in config
        canonical = normalize_type(memory_type)
        for legacy_key, cfg in _RECALL_CONFIG.items():
            if normalize_type(legacy_key) == canonical:
                config = cfg
                break
    if not config:
        return [{"error": f"Unknown memory type: {memory_type}"}]

    # Resolve canonical key for the response
    canonical_type = normalize_type(memory_type)

    Model = config["model"]
    serialize = config["serialize"]

    with get_session() as session:
        # Singleton models (user_profile)
        if config.get("singleton"):
            item = session.get(Model, entity_id)
            return [serialize(item)] if item else []

        # Models linked via relationship (inside_jokes, intimate_moments)
        if config.get("needs_relationship"):
            rel = (
                session.query(Relationship)
                .filter_by(entity_id=entity_id, target_id="user")
                .first()
            )
            if not rel:
                return []
            q = session.query(Model).filter_by(relationship_id=rel.id)
        else:
            q = session.query(Model).filter_by(entity_id=entity_id)

        # Status filter
        status_field = config.get("status_field")
        if status_field and status != "all":
            q = q.filter(getattr(Model, status_field) == status)

        # Text search
        if query and config["search_fields"]:
            search_filters = []
            for field_name in config["search_fields"]:
                col = getattr(Model, field_name, None)
                if col is not None:
                    search_filters.append(col.ilike(f"%{query}%"))
            if search_filters:
                q = q.filter(or_(*search_filters))

        # Order + limit
        if hasattr(Model, "created_at"):
            q = q.order_by(Model.created_at.desc())
        results = q.limit(limit).all()

        # Apply reinforcement (decay system — paid tier)
        if reinforce_memory_by_id and memory_type not in ["messages", "user_profile", "mythology"]:
            for item in results:
                if hasattr(item, "id"):
                    reinforce_memory_by_id(memory_type, item.id, entity_id)

        # Serialize and inject canonical type so the agent knows
        # exactly what type key + id to pass to graph_traverse
        serialized = []
        for item in results:
            d = serialize(item)
            d["_type"] = canonical_type
            serialized.append(d)
        return serialized
