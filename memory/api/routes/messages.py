"""
Messages API route.

Fetch chat messages directly from the database.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException

from api.auth import require_api_key
from src.db.session import get_session
from src.db.models import Message, Conversation, Entity

router = APIRouter(dependencies=[Depends(require_api_key)])

@router.get("/{conversation_id}")
def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Fetch chronological message history for a given conversation directly from PostgreSQL.
    """
    with get_session() as session:
        # Total count for pagination
        from sqlalchemy import func
        total = session.query(func.count(Message.id)).filter(Message.conversation_id == conversation_id).scalar() or 0

        # Query messages, ordered descending so we get most recent first based on limit
        messages_desc = (
            session.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        
        # Reverse to return them in natural chronological order
        results = []
        for msg in reversed(messages_desc):
            results.append({
                "id": msg.id,
                "chatId": msg.conversation_id,
                "senderId": msg.sender_id,
                "content": msg.content,
                "timestamp": int(msg.timestamp.timestamp() * 1000) if msg.timestamp else 0,
                "is_harvested": msg.is_harvested,
                "tool_calls": msg.tool_calls or [],
                "tool_results": msg.tool_results or []
            })

        return {"messages": results, "total": total, "offset": offset, "limit": limit}
