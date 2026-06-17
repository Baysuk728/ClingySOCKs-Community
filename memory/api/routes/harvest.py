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

    from src.harvest import harvest_entity, resolve_harvest_plan
    from src.db.session import get_session
    from src.db.models import Entity, UserProfile, Conversation
    from src.model_registry import _PROVIDER_API_CONFIG, provider_from_model

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

    # Resolve the SAME plan the harvest will use (cheap models derived from the
    # persona's chat provider, reusing the chat key) and validate each model has
    # a usable key before kicking off the background job.
    plan = await resolve_harvest_plan(entity_id, owner_user_id)
    models = {plan["narrative"], plan["extraction"], plan["synthesis"]}

    missing_models = []
    for model_id in models:
        provider = provider_from_model(model_id)
        if provider == "local":
            continue  # local models need no API key

        # 1) Key already resolved from the persona/BYOK (same provider as chat)?
        if plan.get("api_key") and provider == plan.get("chat_provider"):
            continue
        # 2) Server-level env key for this provider?
        config = _PROVIDER_API_CONFIG.get(provider) if provider else None
        if config and os.getenv(config["env_key"]):
            continue
        # 3) Owner's BYOK key (vault resolver also covers OpenRouter + env fallback)?
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
                f"{', '.join(sorted(set(missing_models)))}. Add a key for your "
                "persona's provider in Settings → API Keys (BYOK), or set it in the "
                "server environment, then retry."
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
