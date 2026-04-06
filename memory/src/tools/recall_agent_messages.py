"""
recall_agent_messages tool — retrieve inter-agent communication history.

Allows an agent to recall past consultations and broadcasts with peer agents.
"""

import json
from src.db.session import get_session
from src.db.models import AgentMessage, Entity


def recall_agent_messages(
    entity_id: str,
    target_entity_id: str | None = None,
    message_type: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Recall inter-agent messages involving this entity.

    Args:
        entity_id: The requesting agent's entity_id
        target_entity_id: Optional filter for a specific peer agent
        message_type: Optional filter: 'consult' | 'broadcast' | 'response'
        limit: Max results (default 20)

    Returns:
        dict with 'messages' list and 'count'
    """
    with get_session() as session:
        from sqlalchemy import or_

        query = session.query(AgentMessage).filter(
            or_(
                AgentMessage.from_entity_id == entity_id,
                AgentMessage.to_entity_id == entity_id,
            )
        )

        if target_entity_id:
            query = query.filter(
                or_(
                    AgentMessage.from_entity_id == target_entity_id,
                    AgentMessage.to_entity_id == target_entity_id,
                )
            )

        if message_type:
            query = query.filter(AgentMessage.message_type == message_type)

        query = query.order_by(AgentMessage.created_at.desc()).limit(limit)
        messages = query.all()

        # Resolve entity names
        entity_names = {}
        entity_ids_needed = set()
        for m in messages:
            entity_ids_needed.add(m.from_entity_id)
            entity_ids_needed.add(m.to_entity_id)
        for eid in entity_ids_needed:
            ent = session.get(Entity, eid)
            entity_names[eid] = ent.name if ent else eid

        result_messages = []
        for m in messages:
            result_messages.append({
                "id": m.id,
                "from": entity_names.get(m.from_entity_id, m.from_entity_id),
                "from_entity_id": m.from_entity_id,
                "to": entity_names.get(m.to_entity_id, m.to_entity_id),
                "to_entity_id": m.to_entity_id,
                "content": m.content[:500],  # Truncate for context window
                "type": m.message_type,
                "conversation_id": m.conversation_id,
                "timestamp": m.created_at.isoformat() if m.created_at else None,
            })

        return {
            "messages": result_messages,
            "count": len(result_messages),
        }
