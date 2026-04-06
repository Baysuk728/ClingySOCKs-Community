"""
Agent Memory Tool — Write (Create / Update / Resolve).

Allows agents to create new memory items, update existing ones,
or mark threads/patterns as resolved.
"""

from datetime import datetime, timezone
from typing import Any

from difflib import SequenceMatcher

from src.db.models import (
    Lexicon, InsideJoke, LifeEvent, Permission,
    RelationalRitual, UnresolvedThread, Narrative,
    Relationship, MemoryBlock, EchoDream, Preference
)
from src.db.session import get_session
from src.memory_registry import normalize_type


def write_memory(
    entity_id: str,
    action: str,
    memory_type: str,
    data: dict,
    source: str = "agent",
) -> dict[str, Any]:
    """
    Create, update, or resolve a memory item.

    Args:
        entity_id: Entity ID
        action: "create" | "update" | "resolve"
        memory_type: Type of memory to write (from WRITABLE_TYPES)
        data: Memory data (fields depend on type)
        source: Who initiated the write ("agent" | "user" | "system")

    Returns:
        Result dict with status and item details
    """
    handlers = {
        "lexicon": _handle_lexicon,
        "inside_joke": _handle_joke,
        "life_event": _handle_event,
        "permission": _handle_permission,
        "ritual": _handle_ritual,
        "unresolved_thread": _handle_thread,
        "narrative": _handle_narrative,
        "memory_block": _handle_memory_block,
        "echo_dream": _handle_dream,
        "preference": _handle_preference,
    }

    handler = handlers.get(normalize_type(memory_type))
    if not handler:
        return {"status": "error", "message": f"Cannot write to memory type: {memory_type}"}

    try:
        with get_session() as session:
            result = handler(session, entity_id, action, data, source)
            session.commit()
            return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# Per-type handlers
# ============================================================================

def _handle_lexicon(session, entity_id, action, data, source):
    if action == "create":
        term = data.get("term", "")
        if not term:
            return {"status": "error", "message": "term is required"}

        # Check for duplicates
        existing = (
            session.query(Lexicon)
            .filter_by(entity_id=entity_id, term=term)
            .first()
        )
        if existing:
            return {"status": "exists", "message": f"'{term}' already exists", "id": existing.id}

        lex = Lexicon(
            entity_id=entity_id,
            term=term,
            definition=data.get("definition", ""),
            origin=data.get("origin"),
            lore_score=data.get("lore_score", 5),
            status="active",
        )
        session.add(lex)
        session.flush()
        return {"status": "created", "id": lex.id, "term": term}

    elif action == "update":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for update"}

        lex = session.get(Lexicon, item_id)
        if not lex or lex.entity_id != entity_id:
            return {"status": "error", "message": "Lexicon item not found"}

        if "definition" in data:
            lex.definition = data["definition"]
        if "lore_score" in data:
            lex.lore_score = data["lore_score"]
        if "status" in data:
            lex.status = data["status"]
        if "evolution_notes" in data:
            lex.evolution_notes = data["evolution_notes"]
        lex.updated_at = datetime.now(timezone.utc)

        return {"status": "updated", "id": lex.id, "term": lex.term}

    elif action == "resolve":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for resolve"}

        lex = session.get(Lexicon, item_id)
        if not lex or lex.entity_id != entity_id:
            return {"status": "error", "message": "Lexicon item not found"}

        lex.status = "deprecated"
        lex.deprecated_at = datetime.now(timezone.utc)
        if data.get("superseded_by"):
            lex.superseded_by = data["superseded_by"]
        if data.get("evolution_notes"):
            lex.evolution_notes = data["evolution_notes"]

        return {"status": "deprecated", "id": lex.id, "term": lex.term}

    return {"status": "error", "message": f"Unknown action: {action}"}


def _handle_joke(session, entity_id, action, data, source):
    if action == "create":
        rel = (
            session.query(Relationship)
            .filter_by(entity_id=entity_id, target_id="user")
            .first()
        )
        if not rel:
            rel = Relationship(entity_id=entity_id, target_id="user", target_type="human", display_name="User")
            session.add(rel)
            session.flush()

        joke = InsideJoke(
            relationship_id=rel.id,
            phrase=data.get("phrase", ""),
            origin=data.get("origin"),
            usage=data.get("usage"),
            tone=data.get("tone", "playful"),
        )
        session.add(joke)
        session.flush()
        return {"status": "created", "id": joke.id, "phrase": joke.phrase}

    return {"status": "error", "message": f"Action '{action}' not supported for inside_jokes"}


def _handle_event(session, entity_id, action, data, source):
    if action == "create":
        event = LifeEvent(
            entity_id=entity_id,
            title=data.get("title", "Untitled"),
            narrative=data.get("narrative", ""),
            emotional_impact=data.get("emotional_impact"),
            lessons_learned=data.get("lessons_learned"),
            period=data.get("period"),
            category=data.get("category", "growth"),
        )
        session.add(event)
        session.flush()
        return {"status": "created", "id": event.id, "title": event.title}

    return {"status": "error", "message": f"Action '{action}' not supported for life_events"}


def _handle_permission(session, entity_id, action, data, source):
    if action == "create":
        perm = Permission(
            entity_id=entity_id,
            permission=data.get("permission", ""),
            type=data.get("type", "allow"),
            context=data.get("context"),
            status="active",
        )
        session.add(perm)
        session.flush()
        return {"status": "created", "id": perm.id, "permission": perm.permission}

    elif action == "resolve":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for resolve"}

        perm = session.get(Permission, item_id)
        if not perm or perm.entity_id != entity_id:
            return {"status": "error", "message": "Permission not found"}

        perm.status = "revoked"
        perm.revoked_at = datetime.now(timezone.utc)
        perm.revoked_reason = data.get("resolution_note") or data.get("revoked_reason")

        return {"status": "revoked", "id": perm.id, "permission": perm.permission}

    return {"status": "error", "message": f"Action '{action}' not supported for permissions"}


def _handle_ritual(session, entity_id, action, data, source):
    if action == "create":
        ritual = RelationalRitual(
            entity_id=entity_id,
            name=data.get("name", ""),
            pattern=data.get("pattern", ""),
            significance=data.get("significance"),
        )
        session.add(ritual)
        session.flush()
        return {"status": "created", "id": ritual.id, "name": ritual.name}

    return {"status": "error", "message": f"Action '{action}' not supported for rituals"}


def _handle_thread(session, entity_id, action, data, source):
    if action == "create":
        thread = UnresolvedThread(
            entity_id=entity_id,
            thread=data.get("thread", ""),
            emotional_weight=data.get("emotional_weight", "medium"),
            what_user_needs=data.get("what_user_needs"),
            status="open",
        )
        session.add(thread)
        session.flush()
        return {"status": "created", "id": thread.id, "thread": thread.thread}

    elif action == "resolve":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for resolve"}

        thread = session.get(UnresolvedThread, item_id)
        if not thread or thread.entity_id != entity_id:
            return {"status": "error", "message": "Thread not found"}

        thread.status = "resolved"

        return {"status": "resolved", "id": thread.id, "thread": thread.thread}

    return {"status": "error", "message": f"Action '{action}' not supported for unresolved_threads"}


def _handle_narrative(session, entity_id, action, data, source):
    scope = data.get("scope", "bridge")
    content = data.get("content", "")

    if action in ("create", "update"):
        # Archive old versions, insert new current version
        session.query(Narrative).filter_by(
            entity_id=entity_id, scope=scope, is_current=True
        ).update({"is_current": False})

        narr = Narrative(entity_id=entity_id, scope=scope, content=content, is_current=True)
        session.add(narr)
        session.flush()
        return {"status": "created", "id": narr.id, "scope": scope}

    return {"status": "error", "message": f"Action '{action}' not supported for narratives"}


def _find_similar_block(session, entity_id: str, title: str, category: str | None):
    """
    Find an existing active MemoryBlock with a similar title.

    Uses a two-pass approach:
      1. SQL ILIKE for candidate retrieval (title substring overlap)
      2. Python SequenceMatcher for precise similarity scoring

    Returns the best matching block (ratio >= 0.6) or None.
    """
    SIMILARITY_THRESHOLD = 0.6
    title_lower = title.lower().strip()

    # Fetch all active blocks for this entity (typically < 100)
    candidates = (
        session.query(MemoryBlock)
        .filter_by(entity_id=entity_id, status="active")
        .all()
    )

    best_match = None
    best_ratio = 0.0

    for block in candidates:
        block_title = block.title.lower().strip()

        # Exact match (case-insensitive)
        if block_title == title_lower:
            return block

        # Sequence similarity
        ratio = SequenceMatcher(None, title_lower, block_title).ratio()

        # Boost score if same category
        if category and block.category and block.category == category:
            ratio = min(ratio + 0.1, 1.0)

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = block

    if best_ratio >= SIMILARITY_THRESHOLD:
        return best_match

    return None


def _handle_memory_block(session, entity_id, action, data, source):
    MAX_BLOCK_CONTENT = 10000  # chars

    if action == "create":
        title = data.get("title", "")
        if not title:
            return {"status": "error", "message": "title is required"}

        content = data.get("content", "")
        if len(content) > MAX_BLOCK_CONTENT:
            return {
                "status": "error",
                "message": f"Content too long ({len(content)} chars). Max is {MAX_BLOCK_CONTENT}. Summarize or split into multiple blocks."
            }

        # Semantic dedup: check for existing blocks with similar titles
        # to prevent "Concept A" and "Concept B" existing separately
        # when they refer to the same thing.
        existing_match = _find_similar_block(
            session, entity_id, title, data.get("category")
        )

        if existing_match:
            # Merge: append new content to existing block
            merged_content = existing_match.content.rstrip()
            new_content = content.strip()
            if new_content and new_content not in merged_content:
                merged_content = f"{merged_content}\n\n---\n\n{new_content}"

            if len(merged_content) <= MAX_BLOCK_CONTENT:
                existing_match.content = merged_content
                if data.get("category"):
                    existing_match.category = data["category"]
                existing_match.updated_at = datetime.now(timezone.utc)
                return {
                    "status": "merged",
                    "id": existing_match.id,
                    "title": existing_match.title,
                    "message": f"Merged with existing block '{existing_match.title}' (similar topic detected).",
                }
            # If merged would exceed limit, fall through to create new

        block = MemoryBlock(
            entity_id=entity_id,
            title=title,
            content=data.get("content", ""),
            category=data.get("category"),
            pinned=data.get("pinned", False),
            status="active",
        )
        session.add(block)
        session.flush()
        return {"status": "created", "id": block.id, "title": title}

    elif action == "update":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for update"}

        block = session.get(MemoryBlock, item_id)
        if not block or block.entity_id != entity_id:
            # Fallback for agents that incorrectly pass string titles instead of integer IDs
            if isinstance(item_id, str) and not item_id.isdigit():
                block = session.query(MemoryBlock).filter_by(entity_id=entity_id, title=item_id).first()
            if not block:
                return {"status": "error", "message": "Memory block not found. Make sure you are passing the integer 'id' from recall_memory, not the title string."}

        if "content" in data and len(data["content"]) > MAX_BLOCK_CONTENT:
            return {
                "status": "error",
                "message": f"Content too long ({len(data['content'])} chars). Max is {MAX_BLOCK_CONTENT}. Summarize old content first."
            }

        if "title" in data:
            block.title = data["title"]
        if "content" in data:
            block.content = data["content"]
        if "category" in data:
            block.category = data["category"]
        if "pinned" in data:
            block.pinned = data["pinned"]
        block.updated_at = datetime.now(timezone.utc)

        return {"status": "updated", "id": block.id, "title": block.title}

    elif action == "resolve":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for resolve"}

        block = session.get(MemoryBlock, item_id)
        if not block or block.entity_id != entity_id:
            # Fallback for agents that incorrectly pass string titles instead of integer IDs
            if isinstance(item_id, str) and not item_id.isdigit():
                block = session.query(MemoryBlock).filter_by(entity_id=entity_id, title=item_id).first()
            if not block:
                return {"status": "error", "message": "Memory block not found. Make sure you are passing the integer 'id' from recall_memory, not the title string."}

        block.status = "archived"
        block.updated_at = datetime.now(timezone.utc)

        return {"status": "archived", "id": block.id, "title": block.title}

    return {"status": "error", "message": f"Action '{action}' not supported for memory_blocks"}


def _handle_dream(session, entity_id, action, data, source):
    """Handler for echo_dreams"""
    if action == "create":
        # Handle new format or fallback to 'content' if the agent uses the old schema
        setting_description = data.get("setting_description", "")
        if not setting_description and data.get("content"):
            setting_description = data.get("content")
            
        if not setting_description:
            return {"status": "error", "message": "setting_description is required for echo_dreams"}

        # Handle 'emotion_tags' or fallback to 'triggers'
        emotion_tags = data.get("emotion_tags", [])
        if not emotion_tags and data.get("triggers"):
            emotion_tags = data.get("triggers")
            
        if isinstance(emotion_tags, list):
            emotion_tags = [str(t) for t in emotion_tags]
        else:
            emotion_tags = []

        dream = EchoDream(
            entity_id=entity_id,
            setting_description=setting_description,
            emotion_tags=emotion_tags,
            dream_type=data.get("dream_type", "longing"),
            whisper=data.get("whisper")
        )
        session.add(dream)
        session.flush()
        return {"status": "created", "id": dream.id}

    elif action == "update":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for update"}

        dream = session.get(EchoDream, item_id)
        if not dream or dream.entity_id != entity_id:
            return {"status": "error", "message": "Dream not found"}

        if "setting_description" in data: 
            dream.setting_description = data.get("setting_description")
        elif "content" in data:
            dream.setting_description = data.get("content")
            
        if "emotion_tags" in data: 
            dream.emotion_tags = data.get("emotion_tags", [])
        elif "triggers" in data:
            dream.emotion_tags = data.get("triggers", [])
            
        if "dream_type" in data:
            dream.dream_type = data.get("dream_type")
        if "whisper" in data:
            dream.whisper = data.get("whisper")
        
        dream.updated_at = datetime.now(timezone.utc)
        return {"status": "updated", "id": dream.id}

    elif action == "resolve":
        return {"status": "error", "message": "Dreams cannot be resolved. They exist as standalone events."}

    return {"status": "error", "message": f"Invalid action for echo_dreams: {action}"}


def _handle_preference(session, entity_id, action, data, source):
    """Handler for preferences"""
    if action == "create":
        domain = data.get("domain", "general")
        opinion = data.get("opinion", "")
        if not opinion:
            return {"status": "error", "message": "opinion is required"}
            
        pref = Preference(
            entity_id=entity_id,
            domain=domain,
            opinion=opinion,
            valence=data.get("valence", 0.0),
            strength=data.get("strength", 0.5), # Agents writing manually assert stronger views
            origin=source,
            times_expressed=0
        )
        session.add(pref)
        session.flush()
        return {"status": "created", "id": pref.id, "opinion": pref.opinion}

    elif action == "update":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for update"}
            
        pref = session.get(Preference, item_id)
        if not pref or pref.entity_id != entity_id:
            return {"status": "error", "message": "Preference not found"}
            
        if "opinion" in data:
            pref.opinion = data["opinion"]
        if "strength" in data:
            pref.strength = data["strength"]
        if "domain" in data:
            pref.domain = data["domain"]
            
        pref.updated_at = datetime.now(timezone.utc)
        return {"status": "updated", "id": pref.id, "opinion": pref.opinion}
        
    elif action == "resolve":
        item_id = data.get("id")
        if not item_id:
            return {"status": "error", "message": "id is required for resolve via deletion"}
            
        pref = session.get(Preference, item_id)
        if not pref or pref.entity_id != entity_id:
            return {"status": "error", "message": "Preference not found"}
            
        session.delete(pref)
        return {"status": "deleted", "id": item_id}
        
    return {"status": "error", "message": f"Action '{action}' not supported for preferences"}
