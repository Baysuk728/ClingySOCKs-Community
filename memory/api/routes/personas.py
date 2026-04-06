"""
Persona CRUD routes — manage agent personas.

Endpoints:
  GET    /personas?owner_user_id=...     List personas
  GET    /personas/{entity_id}           Get single persona
  POST   /personas                       Create persona
  PUT    /personas/{entity_id}           Update persona
  DELETE /personas/{entity_id}           Delete persona
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from api.auth import require_api_key
from src.db.session import get_session
from src.db.models import Entity, PersonaIdentity


router = APIRouter(dependencies=[Depends(require_api_key)])


# --- Request / Response Models ---

class PersonaCreateRequest(BaseModel):
    entity_id: str                       # e.g. "agent-id"
    name: str
    owner_user_id: str                   # Identity UID
    model: Optional[str] = None
    provider: Optional[str] = "gemini"
    temperature: Optional[float] = 0.7
    avatar: Optional[str] = None
    system_prompt: Optional[str] = None
    voice_id: Optional[str] = None
    tts_provider: Optional[str] = "google"
    role_description: Optional[str] = "Emergent AI"
    description: Optional[str] = None          # Rich character identity narrative
    # Context
    max_context_chars: Optional[int] = None
    max_warm_memory: Optional[int] = None
    max_history_chars: Optional[int] = None
    max_history_messages: Optional[int] = None


class PersonaUpdateRequest(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    avatar: Optional[str] = None
    system_prompt: Optional[str] = None
    voice_id: Optional[str] = None
    tts_provider: Optional[str] = None
    role_description: Optional[str] = None
    description: Optional[str] = None
    # Allow editing harvested identity fields too
    core: Optional[str] = None
    archetype: Optional[str] = None
    traits: Optional[list[str]] = None
    voice_style: Optional[str] = None
    values_core: Optional[list[str]] = None
    values_boundaries: Optional[str] = None
    # Context
    max_context_chars: Optional[int] = None
    max_warm_memory: Optional[int] = None
    max_history_chars: Optional[int] = None
    max_history_messages: Optional[int] = None


class PersonaResponse(BaseModel):
    entity_id: str
    name: str
    owner_user_id: str
    # Operational config
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: float = 0.7
    avatar: Optional[str] = None
    system_prompt: Optional[str] = None
    voice_id: Optional[str] = None
    tts_provider: Optional[str] = None
    role_description: Optional[str] = None
    description: Optional[str] = None
    # Harvested identity
    core: Optional[str] = None
    archetype: Optional[str] = None
    traits: list[str] = []
    voice_style: Optional[str] = None
    values_core: list[str] = []
    values_boundaries: Optional[str] = None
    # Context
    max_context_chars: Optional[int] = None
    max_warm_memory: Optional[int] = None
    max_history_chars: Optional[int] = None
    max_history_messages: Optional[int] = None


def _persona_to_response(entity: Entity, persona: PersonaIdentity | None) -> dict:
    """Convert Entity + PersonaIdentity to response dict."""
    return {
        "entity_id": entity.id,
        "name": entity.name,
        "owner_user_id": entity.owner_user_id,
        # Operational
        "model": persona.model if persona else None,
        "provider": persona.provider if persona else None,
        "temperature": persona.temperature if persona else 0.7,
        "avatar": persona.avatar if persona else None,
        "system_prompt": persona.system_prompt if persona else None,
        "voice_id": persona.voice_id if persona else None,
        "tts_provider": persona.tts_provider if persona else None,
        "role_description": persona.role_description if persona else None,
        # Harvested identity
        "core": persona.core if persona else None,
        "archetype": persona.archetype if persona else None,
        "traits": persona.traits if persona else [],
        "voice_style": persona.voice_style if persona else None,
        "values_core": persona.values_core if persona else [],
        "values_boundaries": persona.values_boundaries if persona else None,
        "description": persona.description if persona else None,
        # Context
        "max_context_chars": persona.max_context_chars if persona else None,
        "max_warm_memory": persona.max_warm_memory if persona else None,
        "max_history_chars": persona.max_history_chars if persona else None,
        "max_history_messages": persona.max_history_messages if persona else None,
    }


# --- Endpoints ---

@router.get("/personas")
async def list_personas(owner_user_id: str):
    """List all personas for a user."""
    with get_session() as session:
        entities = (
            session.query(Entity)
            .filter_by(entity_type="agent", owner_user_id=owner_user_id)
            .all()
        )
        results = []
        for entity in entities:
            persona = session.query(PersonaIdentity).get(entity.id)
            results.append(_persona_to_response(entity, persona))

    return {"success": True, "personas": results}


@router.get("/personas/{entity_id}")
async def get_persona(entity_id: str):
    """Get a single persona by entity_id."""
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
        persona = session.query(PersonaIdentity).get(entity_id)

    return {"success": True, "persona": _persona_to_response(entity, persona)}


@router.post("/personas")
async def create_persona(req: PersonaCreateRequest):
    """Create a new persona (Entity + PersonaIdentity row)."""
    with get_session() as session:
        # Check if entity already exists
        existing = session.get(Entity, req.entity_id)
        if existing:
            raise HTTPException(status_code=409, detail=f"Entity {req.entity_id} already exists")

        # Create entity
        entity = Entity(
            id=req.entity_id,
            entity_type="agent",
            name=req.name,
            owner_user_id=req.owner_user_id,
        )
        session.add(entity)

        # Create persona identity with config
        persona = PersonaIdentity(
            entity_id=req.entity_id,
            model=req.model,
            provider=req.provider,
            temperature=req.temperature or 0.7,
            avatar=req.avatar,
            system_prompt=req.system_prompt,
            voice_id=req.voice_id,
            tts_provider=req.tts_provider,
            role_description=req.role_description,
            description=req.description,
            max_warm_memory=req.max_warm_memory,
            max_history_chars=req.max_history_chars,
            max_history_messages=req.max_history_messages,
        )
        session.add(persona)
        session.commit()

        return {"success": True, "persona": _persona_to_response(entity, persona)}


@router.put("/personas/{entity_id}")
async def update_persona(entity_id: str, req: PersonaUpdateRequest):
    """Update an existing persona's config and/or identity fields."""
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        # Update entity name if provided
        if req.name is not None:
            entity.name = req.name

        # Get or create persona identity
        persona = session.query(PersonaIdentity).get(entity_id)
        if not persona:
            persona = PersonaIdentity(entity_id=entity_id)
            session.add(persona)

        # Update operational config fields
        update_fields = [
            "model", "provider", "temperature", "avatar",
            "system_prompt", "voice_id", "tts_provider", "role_description",
            "description",
            # Context
            "max_warm_memory", "max_history_chars", "max_history_messages",
            # Harvested fields (user-editable)
            "core", "archetype", "traits", "voice_style",
            "values_core", "values_boundaries",
        ]
        for field in update_fields:
            value = getattr(req, field, None)
            if value is not None:
                # Treat empty strings as "no change" for text fields
                # so that omitting a field in the request doesn't erase it
                if isinstance(value, str) and value.strip() == "":
                    continue
                setattr(persona, field, value)

        persona.updated_at = datetime.now(timezone.utc)
        session.commit()

        return {"success": True, "persona": _persona_to_response(entity, persona)}


@router.delete("/personas/{entity_id}")
async def delete_persona(entity_id: str):
    """Delete a persona and its entity."""
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        # Delete persona identity if exists
        persona = session.query(PersonaIdentity).get(entity_id)
        if persona:
            session.delete(persona)

        # Delete entity (cascades will handle related data)
        session.delete(entity)
        session.commit()

    return {"success": True, "deleted": entity_id}
