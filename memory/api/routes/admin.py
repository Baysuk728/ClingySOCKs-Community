"""
Admin routes — embedding management, entity listing.
"""

from fastapi import APIRouter, Depends

from api.auth import require_api_key
from api.schemas import EmbedRequest, ApiResponse


router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/embed/{entity_id}")
async def trigger_embed(entity_id: str, req: EmbedRequest):
    """
    Trigger embedding generation for an entity's memories.
    Runs synchronously — may take a few minutes for large datasets.
    """
    from src.pipeline.embeddings import embed_entity_memories

    stats = await embed_entity_memories(
        entity_id=entity_id,
        memory_types=req.types,
        force_reembed=req.force,
    )

    return ApiResponse(data={
        "entity_id": entity_id,
        "stats": stats,
    })


@router.get("/entities")
async def list_entities():
    """
    List all entities in the database.
    """
    from src.db.session import get_session
    from src.db.models import Entity

    with get_session() as session:
        entities = session.query(Entity).all()
        data = []
        for e in entities:
            data.append({
                "id": e.id,
                "name": e.name,
                "entity_type": e.entity_type,
                "last_harvest": e.last_harvest.isoformat() if e.last_harvest else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            })

    return ApiResponse(data=data)


@router.get("/shadow_logs/{entity_id}")
async def get_shadow_logs(entity_id: str, limit: int = 50):
    """
    Fetch recent friction states (ShadowLogs) for an entity.
    """
    from src.db.session import get_session
    from src.db.models import ShadowLog

    with get_session() as session:
        logs = session.query(ShadowLog).filter_by(entity_id=entity_id).order_by(ShadowLog.created_at.desc()).limit(limit).all()
        data = []
        for l in logs:
            data.append({
                "id": l.id,
                "channel": l.channel,
                "intensity": l.intensity,
                "trigger": l.trigger,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            })

    return ApiResponse(data=data)


from pydantic import BaseModel, Field
from typing import Optional


class ServerConfigUpdate(BaseModel):
    key: str = Field(..., description="Config key, e.g. 'public_base_url'")
    value: str = Field(..., description="Config value")


@router.put("/config")
async def save_server_config(req: ServerConfigUpdate):
    """Save a server-level config value to PostgreSQL.

    Persisted in oauth_tokens table and loaded into os.environ at startup
    so MCP subprocesses inherit the value.

    Valid keys: public_base_url
    """
    from src.integrations.oauth_store import save_config
    try:
        save_config(req.key, req.value)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(data={"key": req.key, "saved": True, "note": "Restart required for MCP subprocesses to pick up the new value."})


class LLMConfigUpdate(BaseModel):
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, ge=0)
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)

@router.put("/entities/{entity_id}/config")
@router.put("/entities/{entity_id}/temperature") # Keep as alias for backwards compatibility
async def update_llm_config(entity_id: str, req: LLMConfigUpdate):
    """
    Dynamically update an agent's LLM parameters.
    """
    from src.db.session import get_session
    from src.db.models import PersonaIdentity
    
    with get_session() as session:
        persona = session.get(PersonaIdentity, entity_id)
        if not persona:
            # If no persona exists yet, create a default one
            persona = PersonaIdentity(entity_id=entity_id)
            session.add(persona)
        
        updated_fields = {}
        if req.temperature is not None:
            persona.temperature = req.temperature
            updated_fields["temperature"] = req.temperature
        if req.top_p is not None:
            persona.top_p = req.top_p
            updated_fields["top_p"] = req.top_p
        if req.top_k is not None:
            persona.top_k = req.top_k
            updated_fields["top_k"] = req.top_k
        if req.frequency_penalty is not None:
            persona.frequency_penalty = req.frequency_penalty
            updated_fields["frequency_penalty"] = req.frequency_penalty
        if req.presence_penalty is not None:
            persona.presence_penalty = req.presence_penalty
            updated_fields["presence_penalty"] = req.presence_penalty
            
        session.commit()
        
    return ApiResponse(data={
        "entity_id": entity_id,
        "updated_params": updated_fields,
        "message": "LLM config updated successfully"
    })
