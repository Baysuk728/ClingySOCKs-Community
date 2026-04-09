"""
Persistent Threads — Cross-session intentions and ongoing concerns.

Different from conversations or unresolved_threads — these represent
things the agent is actively thinking about across sessions:
- Ongoing concerns ("need to follow up on auth migration")
- Intentions ("want to explore more about user's stress patterns")
- Active investigations ("tracking mood pattern changes")

Threads get injected into the orient/ground boot context so the agent
picks them back up naturally.

Inspired by Resonant Mind's mind_thread concept.
Self-contained — uses existing MemoryBlock infrastructure with a
dedicated category.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from src.db.models import MemoryBlock
from src.db.session import get_session


# Thread status values
THREAD_ACTIVE = "active"
THREAD_PAUSED = "paused"
THREAD_RESOLVED = "resolved"

# Category used for persistent threads in memory_block table
THREAD_CATEGORY = "persistent_thread"


def list_threads(
    entity_id: str,
    status: str = THREAD_ACTIVE,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    List persistent threads for an entity.
    
    Args:
        entity_id: Entity ID
        status: Filter by status (active, paused, resolved, all)
        limit: Max results
    """
    with get_session() as session:
        query = session.query(MemoryBlock).filter(
            MemoryBlock.entity_id == entity_id,
            MemoryBlock.category == THREAD_CATEGORY,
        )

        if status != "all":
            query = query.filter(MemoryBlock.status == status)

        query = query.order_by(MemoryBlock.created_at.desc()).limit(limit)
        threads = query.all()

        return [
            {
                "id": t.id,
                "title": t.title,
                "content": t.content,
                "status": t.status,
                "pinned": getattr(t, "pinned", False),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if hasattr(t, "updated_at") and t.updated_at else None,
            }
            for t in threads
        ]


def create_thread(
    entity_id: str,
    title: str,
    content: str,
    pinned: bool = True,
) -> dict[str, Any]:
    """
    Create a new persistent thread.
    
    Threads are pinned by default so they appear in warm memory.
    
    Args:
        entity_id: Entity ID
        title: Short thread title (e.g., "Follow up on auth migration")
        content: Detailed thread content / notes
        pinned: Whether to pin (appears in warm memory)
    """
    with get_session() as session:
        thread = MemoryBlock(
            entity_id=entity_id,
            title=title,
            content=content,
            category=THREAD_CATEGORY,
            status=THREAD_ACTIVE,
        )
        if hasattr(thread, "pinned"):
            thread.pinned = pinned

        session.add(thread)
        session.commit()

        return {
            "id": thread.id,
            "title": thread.title,
            "status": THREAD_ACTIVE,
            "message": f"Thread created: {title}",
        }


def update_thread(
    entity_id: str,
    thread_id: int,
    content: Optional[str] = None,
    title: Optional[str] = None,
    status: Optional[str] = None,
    pinned: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Update a persistent thread.
    
    Args:
        entity_id: Entity ID
        thread_id: Thread (memory_block) ID
        content: New content (appends a note if starts with "+")
        title: New title
        status: New status (active, paused, resolved)
        pinned: Update pin state
    """
    with get_session() as session:
        thread = session.query(MemoryBlock).filter(
            MemoryBlock.id == thread_id,
            MemoryBlock.entity_id == entity_id,
            MemoryBlock.category == THREAD_CATEGORY,
        ).first()

        if not thread:
            return {"error": f"Thread {thread_id} not found"}

        if title:
            thread.title = title

        if content:
            if content.startswith("+"):
                # Append mode
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                thread.content = (thread.content or "") + f"\n\n[{timestamp}] {content[1:].strip()}"
            else:
                thread.content = content

        if status:
            if status not in (THREAD_ACTIVE, THREAD_PAUSED, THREAD_RESOLVED):
                return {"error": f"Invalid status: {status}. Use active, paused, or resolved."}
            thread.status = status

        if pinned is not None and hasattr(thread, "pinned"):
            thread.pinned = pinned

        session.commit()

        return {
            "id": thread.id,
            "title": thread.title,
            "status": thread.status,
            "message": f"Thread updated: {thread.title}",
        }


def resolve_thread(entity_id: str, thread_id: int, resolution_note: str = "") -> dict[str, Any]:
    """
    Mark a thread as resolved.
    
    Args:
        entity_id: Entity ID
        thread_id: Thread (memory_block) ID
        resolution_note: Optional note about the resolution
    """
    content_update = None
    if resolution_note:
        content_update = f"+Resolved: {resolution_note}"

    return update_thread(
        entity_id, thread_id,
        content=content_update,
        status=THREAD_RESOLVED,
        pinned=False,
    )


def get_active_thread_summary(entity_id: str, max_threads: int = 5) -> str:
    """
    Get a compact text summary of active threads for context injection.
    
    Used by orient/ground boot sequence.
    """
    threads = list_threads(entity_id, status=THREAD_ACTIVE, limit=max_threads)

    if not threads:
        return ""

    lines = ["Active threads:"]
    for t in threads:
        lines.append(f"- {t['title']}")
        if t.get("content"):
            # Show last line of content as latest update
            last_line = t["content"].strip().split("\n")[-1][:80]
            lines.append(f"  └ {last_line}")

    return "\n".join(lines)
