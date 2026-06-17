"""
Harvest routes — trigger harvest and check status.
"""

import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks

from api.auth import require_api_key
from api.schemas import HarvestRequest, ApiResponse


router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/{entity_id}")
async def trigger_harvest(
    entity_id: str,
    req: HarvestRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a harvest for the given entity.
    Runs in background — returns immediately with status.
    """
    import os
    from fastapi import HTTPException

    from src.harvest import harvest_entity
    from src.db.session import get_session
    from src.db.models import Entity, UserProfile, Conversation
    from src.config import NARRATIVE_MODEL, EXTRACTION_MODEL, SYNTHESIS_MODEL
    from src.model_registry import _PROVIDER_API_CONFIG

    agent_name = "Agent"
    user_name = "User"
    owner_user_id = None

    # Look up the entity (and its owner) up front — the owner is needed to check
    # for a per-user BYOK key, and to resolve the agent/user display names.
    try:
        with get_session() as session:
            entity = session.get(Entity, entity_id)
            if not entity:
                return ApiResponse(success=False, error=f"Entity '{entity_id}' not found")

            agent_name = entity.name or "Agent"
            owner_user_id = entity.owner_user_id
            if owner_user_id:
                user = session.get(UserProfile, owner_user_id)
                if user and user.display_name:
                    user_name = user.display_name

            # Guard against concurrent harvests, but allow manual overrides if requested.
            already_running = (
                session.query(Conversation)
                .filter_by(entity_id=entity_id, harvest_status="processing")
                .first()
            )
            if already_running and not req.dry_run:
                # Manual trigger → assume the user wants to clear a stuck run.
                print(f"⚠️ Resetting stuck harvest status ('processing') for entity {entity_id}")
                session.query(Conversation).filter_by(
                    entity_id=entity_id,
                    harvest_status="processing"
                ).update({"harvest_status": "pending"})
                session.commit()
    except Exception as e:
        print(f"⚠️ Warning: Could not look up entity for harvest: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate entity state")

    # Validate that each harvest stage has a usable key — either a server env
    # key OR the owner's BYOK key in the vault (the harvest pipeline now resolves
    # the owner's key the same way the chat path does).
    stages = {
        "Narrative Pass": NARRATIVE_MODEL,
        "Extraction Pass": EXTRACTION_MODEL,
        "Synthesis Pass": SYNTHESIS_MODEL,
    }
    missing_models = []
    checked_models = set()
    for stage_name, model_id in stages.items():
        if not model_id or model_id in checked_models:
            continue
        checked_models.add(model_id)

        provider = model_id.split('/')[0] if '/' in model_id else None
        if provider in ("ollama_chat", "local"):
            continue  # local models need no API key

        # 1) Server-level env key for this provider?
        config = _PROVIDER_API_CONFIG.get(provider) if provider else None
        if config and os.getenv(config["env_key"]):
            continue
        # 2) Owner's BYOK key (the vault resolver also covers OpenRouter + env fallback)?
        if owner_user_id:
            try:
                from src.integrations.vault_factory import get_vault
                resolved = await get_vault().resolve_for_litellm(owner_user_id, model_id)
                if resolved.get("api_key"):
                    continue
            except Exception:
                pass
        missing_models.append(model_id)

    if missing_models:
        raise HTTPException(
            status_code=400,
            detail=(
                "Harvesting can't start: no API key found for "
                f"{', '.join(sorted(set(missing_models)))}. Add the matching key in "
                "Settings → API Keys (BYOK), or set it in the server environment, then retry."
            ),
        )

    async def _run():
        await harvest_entity(
            entity_id=entity_id, 
            agent_name=agent_name, 
            user_name=user_name, 
            dry_run=req.dry_run
        )

    background_tasks.add_task(asyncio.to_thread, lambda: asyncio.run(_run()))

    return ApiResponse(data={
        "message": f"Harvest {'(dry run) ' if req.dry_run else ''}started for {entity_id}",
        "entity_id": entity_id,
        "dry_run": req.dry_run,
    })


@router.get("/{entity_id}/status")
async def harvest_status(entity_id: str):
    """
    Get the latest harvest status for an entity.
    """
    from src.db.session import get_session
    from src.db.models import HarvestLog, Entity
    from sqlalchemy import func

    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            return ApiResponse(success=False, error=f"Entity '{entity_id}' not found")

        # Get latest harvest log
        latest = (
            session.query(HarvestLog)
            .filter_by(entity_id=entity_id)
            .order_by(HarvestLog.timestamp.desc())
            .first()
        )

        # Count total harvests
        total = (
            session.query(func.count(HarvestLog.id))
            .filter_by(entity_id=entity_id, success=True)
            .scalar() or 0
        )

    data = {
        "entity_id": entity_id,
        "entity_name": entity.name,
        "last_harvest": entity.last_harvest.isoformat() if entity.last_harvest else None,
        "total_harvests": total,
    }

    if latest:
        data["latest_log"] = {
            "conversation_id": latest.conversation_id,
            "items_extracted": latest.items_extracted,
            "success": latest.success,
            "error": latest.error,
            "timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
        }

    return ApiResponse(data=data)
@router.get("/{entity_id}/progress")
async def get_harvest_progress(entity_id: str):
    """
    Get the live metadata for a running harvest.
    """
    from src.db.session import get_session
    from src.db.models import HarvestProgress

    with get_session() as session:
        prog = session.get(HarvestProgress, entity_id)
        if not prog:
            return ApiResponse(data={
                "status": "idle",
                "progress_percent": 0,
                "current_step": "No harvest in progress"
            })
            
        return ApiResponse(data={
            "entity_id": entity_id,
            "status": prog.status,
            "progress_percent": prog.progress_percent,
            "current_step": prog.current_step,
            "total_chunks": prog.total_chunks,
            "completed_chunks": prog.completed_chunks,
            "error_message": prog.error_message,
            "last_updated": prog.last_updated.isoformat() if prog.last_updated else None
        })
