"""
Enhanced Memory Routes — New capabilities from competitive analysis.

Exposes:
- Orient/Ground boot sequence
- 3-pool memory surfacing  
- Timeline trace
- Contradiction detection
- Persistent threads
- Agent scheduling
- Presence hooks
- Subconscious daemon status
"""

from fastapi import APIRouter, Depends, Query
from typing import Any, Optional

from api.auth import require_api_key
from api.schemas import ApiResponse

router = APIRouter(dependencies=[Depends(require_api_key)])


# ── Orient / Ground Boot ─────────────────────────────

@router.get("/{entity_id}/orient")
async def orient_entity(entity_id: str):
    """
    Session initialization — identity anchor.
    Returns compact identity context: agent name, user profile,
    relationship state, current mood.
    """
    from src.services.orient_ground import orient
    return ApiResponse(data=orient(entity_id))


@router.get("/{entity_id}/ground")
async def ground_entity(entity_id: str):
    """
    Session initialization — active context grounding.
    Returns active threads, pinned notes, recent activity.
    """
    from src.services.orient_ground import ground
    return ApiResponse(data=ground(entity_id))


@router.get("/{entity_id}/boot")
async def boot_entity(entity_id: str):
    """
    Full boot sequence — orient + ground combined.
    Returns complete session context.
    """
    from src.services.orient_ground import boot_context
    return ApiResponse(data=boot_context(entity_id))


@router.get("/{entity_id}/boot/text")
async def boot_entity_text(entity_id: str):
    """
    Formatted boot context as compact text (~170-300 tokens).
    Ready for system prompt injection.
    """
    from src.services.orient_ground import format_boot_context
    text = format_boot_context(entity_id)
    return ApiResponse(data={"text": text, "char_count": len(text)})


# ── 3-Pool Memory Surfacing ──────────────────────────

@router.post("/{entity_id}/surface")
async def surface_memories(
    entity_id: str,
    req: dict,
):
    """
    Surface memories from three pools: relevance, novelty, and edge.
    
    Body: { "query": "...", "limit": 15 }
    """
    from src.services.memory_surfacing import surface_memories as _surface

    query = req.get("query", "")
    limit = req.get("limit", 15)

    if not query:
        return ApiResponse(data={"error": "query is required"})

    results = await _surface(entity_id, query, total_limit=limit)
    return ApiResponse(data=results)


# ── Timeline ─────────────────────────────────────────

@router.get("/{entity_id}/timeline")
async def trace_timeline(
    entity_id: str,
    topic: str = Query(..., description="Topic to trace through time"),
    limit: int = Query(20, description="Max events"),
    include_messages: bool = Query(False, description="Include raw chat messages"),
):
    """
    Trace a topic chronologically through all memory types.
    """
    from src.services.timeline import trace_timeline as _trace
    results = await _trace(entity_id, topic, limit=limit, include_messages=include_messages)
    return ApiResponse(data=results)


# ── Contradiction Detection ──────────────────────────

@router.get("/{entity_id}/contradictions")
async def check_contradictions(
    entity_id: str,
    scope: str = Query("all", pattern="^(all|edges|entities|temporal)$"),
):
    """
    Detect contradictions in the knowledge graph.
    
    Scopes: all, edges, entities, temporal
    """
    from src.services.contradiction_detector import contradiction_report
    return ApiResponse(data=contradiction_report(entity_id))


# ── Persistent Threads ───────────────────────────────

@router.get("/{entity_id}/threads")
async def list_threads(
    entity_id: str,
    status: str = Query("active", pattern="^(active|paused|resolved|all)$"),
    limit: int = Query(10),
):
    """List persistent threads (ongoing intentions/concerns)."""
    from src.services.persistent_threads import list_threads as _list
    return ApiResponse(data=_list(entity_id, status=status, limit=limit))


@router.post("/{entity_id}/threads")
async def create_thread(entity_id: str, req: dict):
    """
    Create a new persistent thread.
    
    Body: { "title": "...", "content": "...", "pinned": true }
    """
    from src.services.persistent_threads import create_thread as _create
    return ApiResponse(data=_create(
        entity_id,
        title=req.get("title", "Untitled thread"),
        content=req.get("content", ""),
        pinned=req.get("pinned", True),
    ))


@router.put("/{entity_id}/threads/{thread_id}")
async def update_thread(entity_id: str, thread_id: int, req: dict):
    """
    Update a persistent thread.
    
    Body: { "title": "...", "content": "...", "status": "resolved", "pinned": false }
    Prefix content with "+" to append instead of replace.
    """
    from src.services.persistent_threads import update_thread as _update
    return ApiResponse(data=_update(
        entity_id, thread_id,
        title=req.get("title"),
        content=req.get("content"),
        status=req.get("status"),
        pinned=req.get("pinned"),
    ))


@router.delete("/{entity_id}/threads/{thread_id}")
async def resolve_thread(
    entity_id: str,
    thread_id: int,
    note: str = Query("", description="Resolution note"),
):
    """Resolve (close) a persistent thread."""
    from src.services.persistent_threads import resolve_thread as _resolve
    return ApiResponse(data=_resolve(entity_id, thread_id, resolution_note=note))


# ── Agent Scheduling ─────────────────────────────────

@router.get("/{entity_id}/schedules")
async def list_schedules(entity_id: str):
    """List agent's scheduled tasks."""
    from src.services.agent_scheduler import list_schedules as _list
    return ApiResponse(data=_list(entity_id))


@router.post("/{entity_id}/schedules")
async def create_schedule(entity_id: str, req: dict):
    """
    Create a scheduled task for the agent.
    
    Body: {
        "title": "Morning check-in",
        "prompt": "Check in with the user",
        "schedule_type": "recurring",
        "cron_expr": "daily",
        "interval_minutes": 60
    }
    """
    from src.services.agent_scheduler import create_schedule as _create
    return ApiResponse(data=_create(
        entity_id,
        title=req.get("title", "Scheduled task"),
        prompt=req.get("prompt", ""),
        schedule_type=req.get("schedule_type", "once"),
        run_at=req.get("run_at"),
        cron_expr=req.get("cron_expr"),
        interval_minutes=req.get("interval_minutes"),
        condition=req.get("condition"),
    ))


@router.delete("/{entity_id}/schedules/{schedule_id}")
async def disable_schedule(entity_id: str, schedule_id: int):
    """Disable a scheduled task."""
    from src.services.agent_scheduler import disable_schedule as _disable
    return ApiResponse(data=_disable(entity_id, schedule_id))


# ── Presence ─────────────────────────────────────────

@router.get("/{entity_id}/presence")
async def get_presence(entity_id: str, user_id: str = Query("user")):
    """Get current presence state for a user."""
    from src.services.presence_hooks import get_presence as _get
    return ApiResponse(data=_get(entity_id, user_id))


@router.post("/{entity_id}/presence")
async def update_presence(entity_id: str, req: dict):
    """
    Update user presence state.
    
    Body: { "user_id": "user", "state": "online" }
    """
    from src.services.presence_hooks import update_presence as _update
    return ApiResponse(data=_update(
        entity_id,
        user_id=req.get("user_id", "user"),
        state=req.get("state", "online"),
    ))


@router.get("/{entity_id}/presence/context")
async def presence_context(entity_id: str, user_id: str = Query("user")):
    """Get formatted presence context for prompt injection."""
    from src.services.presence_hooks import format_presence_context
    text = format_presence_context(entity_id, user_id)
    return ApiResponse(data={"text": text})


# ── Subconscious Daemon ──────────────────────────────

@router.get("/{entity_id}/subconscious")
async def subconscious_status(entity_id: str):
    """Get the latest subconscious daemon findings."""
    from src.services.subconscious_daemon import subconscious_daemon
    results = subconscious_daemon.get_last_results(entity_id)
    if not results:
        return ApiResponse(data={"status": "no_data", "message": "No subconscious cycle has run yet."})
    return ApiResponse(data=results)


@router.post("/{entity_id}/subconscious/run")
async def trigger_subconscious(entity_id: str):
    """Manually trigger a subconscious processing cycle."""
    from src.services.subconscious_daemon import run_subconscious_cycle
    results = await run_subconscious_cycle(entity_id)
    return ApiResponse(data=results)
