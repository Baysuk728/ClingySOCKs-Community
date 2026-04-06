"""
broadcast_agents tool — fan-out message to all peer agents in a group conversation.

Sends a message to every other agent participating in a group conversation
and collects their responses. Each agent responds independently with their
own persona/memory context.
"""

import asyncio
import json

from src.db.session import get_session
from src.db.models import ConversationParticipant, Conversation
from src.tools.consult_agent import consult_agent


async def broadcast_agents(
    source_entity_id: str,
    message: str,
    conversation_id: str,
    conversation_context: str | None = None,
) -> dict:
    """
    Broadcast a message to all other agents in a group conversation.

    Args:
        source_entity_id: The agent sending the broadcast
        message: The message to broadcast
        conversation_id: The group conversation ID
        conversation_context: Optional context from the source's current conversation

    Returns:
        dict with 'responses' (list of per-agent responses) and metadata
    """
    # Find all participants in this conversation (excluding source)
    with get_session() as session:
        conv = session.get(Conversation, conversation_id)
        if not conv:
            return {"error": f"Conversation '{conversation_id}' not found."}

        participants = (
            session.query(ConversationParticipant)
            .filter_by(conversation_id=conversation_id)
            .filter(ConversationParticipant.left_at.is_(None))  # Only active participants
            .filter(ConversationParticipant.entity_id != source_entity_id)
            .all()
        )

        if not participants:
            # Fallback: if no participant rows exist yet, use the conversation's entity_id
            if conv.entity_id and conv.entity_id != source_entity_id:
                peer_ids = [conv.entity_id]
            else:
                return {"error": "No other agents in this conversation."}
        else:
            peer_ids = [p.entity_id for p in participants]

    # Consult all peers concurrently
    tasks = [
        consult_agent(
            source_entity_id=source_entity_id,
            target_entity_id=peer_id,
            question=message,
            share_context=bool(conversation_context),
            conversation_context=conversation_context,
            conversation_id=conversation_id,
        )
        for peer_id in peer_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    responses = []
    for peer_id, result in zip(peer_ids, results):
        if isinstance(result, Exception):
            responses.append({
                "entity_id": peer_id,
                "error": str(result),
            })
        elif isinstance(result, dict) and "error" in result:
            responses.append({
                "entity_id": peer_id,
                "error": result["error"],
            })
        else:
            responses.append({
                "entity_id": peer_id,
                "name": result.get("target_name", peer_id),
                "response": result.get("response", ""),
            })

    return {
        "broadcast_to": len(peer_ids),
        "responses": responses,
        "conversation_id": conversation_id,
    }
