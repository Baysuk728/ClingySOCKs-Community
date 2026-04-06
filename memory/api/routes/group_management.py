"""
Group Conversation Management routes.

Endpoints for creating and managing multi-agent group conversations:
- POST /groups/create              — Create a new group conversation
- POST /groups/{id}/join           — Add an agent to a group
- POST /groups/{id}/leave          — Remove an agent from a group
- GET  /groups/{id}/participants   — List participants in a group
- GET  /groups/for/{entity_id}     — List all groups an agent belongs to
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import require_api_key
from src.db.session import get_session
from src.db.models import (
    Conversation, ConversationParticipant, Entity,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


# ─── Schemas ──────────────────────────────────────────

class CreateGroupRequest(BaseModel):
    title: str = Field(..., description="Group conversation title")
    entity_ids: list[str] = Field(..., min_length=1, description="Entity IDs of participating agents")
    creator_entity_id: str = Field(..., description="Entity ID of the creating agent (becomes moderator)")
    user_id: str = Field("default-user")


class JoinGroupRequest(BaseModel):
    entity_id: str
    role: str = Field("participant", description="'participant' | 'moderator' | 'observer'")


class LeaveGroupRequest(BaseModel):
    entity_id: str


# ─── Create Group ────────────────────────────────────

@router.post("/create")
async def create_group(req: CreateGroupRequest):
    """Create a new group conversation with multiple agent participants."""
    import uuid

    with get_session() as session:
        # Validate all entities exist
        for eid in req.entity_ids:
            entity = session.get(Entity, eid)
            if not entity:
                raise HTTPException(status_code=404, detail=f"Entity '{eid}' not found")

        # Ensure creator is in the participant list
        all_participants = list(set(req.entity_ids))
        if req.creator_entity_id not in all_participants:
            all_participants.insert(0, req.creator_entity_id)

        # Create conversation
        conv_id = str(uuid.uuid4())
        conv = Conversation(
            id=conv_id,
            entity_id=req.creator_entity_id,  # Creator as entity_id (backward compat)
            title=req.title,
            chat_type="group",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(conv)
        session.flush()

        # Add all participants
        for eid in all_participants:
            role = "moderator" if eid == req.creator_entity_id else "participant"
            participant = ConversationParticipant(
                conversation_id=conv_id,
                entity_id=eid,
                role=role,
            )
            session.add(participant)

        session.commit()

        return {
            "conversation_id": conv_id,
            "title": req.title,
            "chat_type": "group",
            "participants": [
                {"entity_id": eid, "role": "moderator" if eid == req.creator_entity_id else "participant"}
                for eid in all_participants
            ],
        }


# ─── Join Group ──────────────────────────────────────

@router.post("/{conversation_id}/join")
async def join_group(conversation_id: str, req: JoinGroupRequest):
    """Add an agent to an existing group conversation."""
    with get_session() as session:
        conv = session.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conv.chat_type != "group":
            raise HTTPException(status_code=400, detail="Not a group conversation")

        entity = session.get(Entity, req.entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity '{req.entity_id}' not found")

        # Check if already a participant
        existing = (
            session.query(ConversationParticipant)
            .filter_by(conversation_id=conversation_id, entity_id=req.entity_id)
            .first()
        )
        if existing:
            if existing.left_at:
                # Re-join: clear left_at
                existing.left_at = None
                existing.role = req.role
                session.commit()
                return {"status": "rejoined", "entity_id": req.entity_id, "role": req.role}
            return {"status": "already_member", "entity_id": req.entity_id}

        participant = ConversationParticipant(
            conversation_id=conversation_id,
            entity_id=req.entity_id,
            role=req.role,
        )
        session.add(participant)
        session.commit()

        return {"status": "joined", "entity_id": req.entity_id, "role": req.role}


# ─── Leave Group ─────────────────────────────────────

@router.post("/{conversation_id}/leave")
async def leave_group(conversation_id: str, req: LeaveGroupRequest):
    """Remove an agent from a group conversation (soft-delete via left_at)."""
    with get_session() as session:
        participant = (
            session.query(ConversationParticipant)
            .filter_by(conversation_id=conversation_id, entity_id=req.entity_id)
            .first()
        )
        if not participant:
            raise HTTPException(status_code=404, detail="Participant not found")

        participant.left_at = datetime.now(timezone.utc)
        session.commit()

        return {"status": "left", "entity_id": req.entity_id}


# ─── List Participants ───────────────────────────────

@router.get("/{conversation_id}/participants")
async def list_participants(conversation_id: str):
    """List all participants in a group conversation."""
    with get_session() as session:
        conv = session.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        participants = (
            session.query(ConversationParticipant)
            .filter_by(conversation_id=conversation_id)
            .all()
        )

        result = []
        for p in participants:
            entity = session.get(Entity, p.entity_id)
            result.append({
                "entity_id": p.entity_id,
                "name": entity.name if entity else p.entity_id,
                "role": p.role,
                "joined_at": p.joined_at.isoformat() if p.joined_at else None,
                "left_at": p.left_at.isoformat() if p.left_at else None,
                "active": p.left_at is None,
            })

        return {
            "conversation_id": conversation_id,
            "chat_type": conv.chat_type,
            "title": conv.title,
            "participants": result,
        }


# ─── List Groups for Agent ───────────────────────────

@router.get("/for/{entity_id}")
async def list_groups_for_agent(entity_id: str):
    """List all group conversations an agent belongs to."""
    with get_session() as session:
        participants = (
            session.query(ConversationParticipant)
            .filter_by(entity_id=entity_id)
            .filter(ConversationParticipant.left_at.is_(None))
            .all()
        )

        groups = []
        for p in participants:
            conv = session.get(Conversation, p.conversation_id)
            if not conv or conv.chat_type != "group":
                continue

            # Get all active participants
            all_participants = (
                session.query(ConversationParticipant)
                .filter_by(conversation_id=conv.id)
                .filter(ConversationParticipant.left_at.is_(None))
                .all()
            )
            participant_ids = [pp.entity_id for pp in all_participants]

            groups.append({
                "conversation_id": conv.id,
                "title": conv.title,
                "role": p.role,
                "participant_count": len(participant_ids),
                "participants": participant_ids,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            })

        return {"entity_id": entity_id, "groups": groups}
