"""
Conversations API route.

Fetch a list of conversations for a user directly from PostgreSQL.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from api.auth import require_api_key
from src.db.session import get_session
from src.db.models import Conversation, Entity

router = APIRouter(dependencies=[Depends(require_api_key)])


def _compute_harvest_state(
    harvest_status: str | None,
    message_count: int,
    last_harvested_index: int,
) -> str:
    """
    Map DB harvest fields to frontend HarvestState enum.
    
    Returns one of: 'not_harvested', 'delta_detected', 'processing',
                     'harvested', 'partially_harvested'
    """
    status = harvest_status or "pending"
    
    if status == "processing":
        return "processing"
    
    if status == "error":
        return "partially_harvested"
    
    if status == "done":
        # Check if new messages arrived after last harvest
        if message_count > (last_harvested_index + 1):
            return "delta_detected"
        return "harvested"
    
    # status == "pending" 
    if last_harvested_index >= 0:
        # Was harvested before, but new messages arrived
        return "delta_detected"
    
    # Never harvested
    return "not_harvested"

@router.get("/")
def get_conversations(
    user_id: str = Query(..., description="The user's ID to fetch conversations for"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Fetch all conversations for a specific user, sorted by updatedAt descending.
    Matches the ConversationSummary interface expected by the frontend.
    """
    with get_session() as session:
        # Join Conversation with Entity to filter by the user who owns the entity
        convs = (
            session.query(Conversation)
            .join(Entity, Conversation.entity_id == Entity.id)
            .filter(Entity.owner_user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        
        results = []
        for c in convs:
            # Compute frontend-friendly harvest state from DB fields
            harvest_state = _compute_harvest_state(
                c.harvest_status, c.message_count, c.last_harvested_index
            )
            results.append({
                "id": c.id,
                "title": c.title,
                "participants": [c.entity_id, user_id], 
                "messageCount": c.message_count,
                # Convert datetime to ms timestamp for frontend
                "updatedAt": int(c.updated_at.timestamp() * 1000) if c.updated_at else 0,
                "harvestStatus": c.harvest_status or "not_harvested",
                "harvestState": harvest_state,
                "lastHarvestAt": None, 
                "lastHarvestedMessageIndex": c.last_harvested_index,
                "entityId": c.entity_id,
                "source": getattr(c, 'source', None),
                "isArchived": False,
                "isGroup": False
            })
            
        return {"conversations": results}


@router.post("/")
def create_conversation(payload: dict):
    """
    Create a new conversation in PostgreSQL.
    Body: { entity_id, title, participants? }
    Returns: { id, title }
    """
    import uuid
    from datetime import datetime, timezone

    entity_id = payload.get("entity_id")
    title = payload.get("title", "New Chat")

    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id is required")

    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

        conv_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        conv = Conversation(
            id=conv_id,
            entity_id=entity_id,
            title=title,
            created_at=now,
            updated_at=now,
            message_count=0,
            harvest_status="pending",
        )
        session.add(conv)
        session.commit()

    return {
        "id": conv_id,
        "title": title,
        "entity_id": entity_id,
    }


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str):
    """
    Delete a conversation and all its messages from PostgreSQL.
    """
    from src.db.models import Message as MessageModel

    with get_session() as session:
        conv = session.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")

        # Delete all messages first (cascade)
        session.query(MessageModel).filter_by(conversation_id=conversation_id).delete()
        session.delete(conv)
        session.commit()

    return {"success": True, "deleted": conversation_id}
