"""
OpenClaw Integration — Inbound webhook for external agent messages.

Provides endpoints for:
  POST /openclaw/inbound     — OpenClaw sends a message to a ClingySOCKs agent
  GET  /openclaw/agents      — List available ClingySOCKs agents for OpenClaw to talk to
  POST /openclaw/broadcast   — OpenClaw broadcasts to all agents in a conversation

The inbound endpoint triggers the target agent's LLM with full memory context,
just like consult_agent does for internal peers.
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from src.tools.consult_agent import consult_agent
from src.db.session import get_session
from src.db.models import Entity


router = APIRouter()

# Auth: require a shared secret so only OpenClaw can call these endpoints
_OPENCLAW_WEBHOOK_TOKEN = os.getenv("OPENCLAW_WEBHOOK_TOKEN", "")


def _check_auth(authorization: str | None):
    """Validate the inbound webhook token."""
    if not _OPENCLAW_WEBHOOK_TOKEN:
        # No token configured — allow all (dev mode)
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    expected = f"Bearer {_OPENCLAW_WEBHOOK_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=403, detail="Invalid webhook token")


# ─── Request / Response Models ────────────────────────

class InboundMessage(BaseModel):
    """Message from OpenClaw to a ClingySOCKs agent."""
    target_entity_id: str = Field(..., description="ClingySOCKs entity to receive the message")
    message: str = Field(..., description="The message content")
    sender_name: str = Field("OpenClaw", description="Display name of the sender")
    sender_id: str = Field("openclaw", description="Identifier of the sending agent")
    conversation_context: Optional[str] = Field(None, description="Context from OpenClaw's conversation")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for logging")


class InboundResponse(BaseModel):
    """Response from the ClingySOCKs agent back to OpenClaw."""
    response: str
    agent_name: str
    agent_entity_id: str
    consultation_id: str | None = None
    error: str | None = None


# ─── Endpoints ────────────────────────────────────────

@router.post("/inbound", response_model=InboundResponse)
async def receive_message(
    msg: InboundMessage,
    authorization: Optional[str] = Header(None),
):
    """
    Receive a message from OpenClaw and route it to a ClingySOCKs agent.

    The target agent gets the message enriched with its own persona/memory
    context and responds in a single turn (same as consult_agent).
    """
    _check_auth(authorization)

    # Validate target entity exists and ensure sender proxy entity exists
    with get_session() as session:
        entity = session.get(Entity, msg.target_entity_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{msg.target_entity_id}' not found. Use GET /openclaw/agents to list available agents.",
            )
        entity_name = entity.name
        
        # Check if the external sender exists in the database to satisfy AgentMessage FK constraints
        source_id = f"external:{msg.sender_id}"
        source_entity = session.get(Entity, source_id)
        if not source_entity:
            from datetime import datetime, timezone
            source_entity = Entity(
                id=source_id,
                name=msg.sender_name,
                entity_type="external_agent",
                owner_user_id=entity.owner_user_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(source_entity)
            session.commit()

    # Use consult_agent to get the target's contextualized response.
    # We pass the OpenClaw sender as the "source" — it won't have a DB entity,
    # so consult_agent will use the ID string as the source name.
    result = await consult_agent(
        source_entity_id=f"external:{msg.sender_id}",
        target_entity_id=msg.target_entity_id,
        question=msg.message,
        share_context=bool(msg.conversation_context),
        conversation_context=msg.conversation_context,
        conversation_id=msg.conversation_id,
    )

    if "error" in result:
        return InboundResponse(
            response="",
            agent_name=entity_name,
            agent_entity_id=msg.target_entity_id,
            error=result["error"],
        )

    return InboundResponse(
        response=result.get("response", ""),
        agent_name=result.get("target_name", entity_name),
        agent_entity_id=msg.target_entity_id,
        consultation_id=result.get("consultation_id"),
    )


@router.get("/agents")
async def list_agents(authorization: Optional[str] = Header(None)):
    """
    List ClingySOCKs agents that OpenClaw can talk to.

    Returns agent entity IDs and names so OpenClaw can target messages.
    """
    _check_auth(authorization)

    with get_session() as session:
        entities = (
            session.query(Entity)
            .filter(Entity.entity_type == "agent")
            .all()
        )
        return {
            "agents": [
                {"entity_id": e.id, "name": e.name}
                for e in entities
            ]
        }
