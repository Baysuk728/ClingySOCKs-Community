"""
Memory routes — warm, recall, write, search, graph, stats.

All endpoints require entity_id path parameter.
"""

from fastapi import APIRouter, Depends, Query
from typing import Any

from api.auth import require_api_key
from api.schemas import (
    RecallRequest, WriteRequest, SearchRequest, GraphRequest,
    MemoryQueryRequest, ApiResponse, StatsResponse,
)


router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/{entity_id}/warm")
async def get_warm_memory(
    entity_id: str,
    level: str = Query("standard", pattern="^(concise|standard|detailed|full)$"),
    budget: int | None = Query(None, description="Override character budget"),
):
    """
    Assemble warm memory for agent system prompt injection.
    Returns formatted text ready to inject.
    """
    from src.warmth.builder import build_warm_memory
    from src.warmth.formatter import format_warm_memory

    raw = build_warm_memory(entity_id, level=level)
    formatted = format_warm_memory(raw, max_chars=budget)

    return ApiResponse(data={
        "level": level,
        "char_count": len(formatted),
        "content": formatted,
    })


@router.post("/{entity_id}/query")
async def query_memory(entity_id: str, req: MemoryQueryRequest):
    """
    Unified memory query — structured recall or semantic search.
    """
    from src.tools.query import memory_query

    results = await memory_query(
        entity_id=entity_id,
        query=req.query,
        memory_type=req.memory_type,
        memory_types=req.memory_types,
        limit=req.limit,
        status=req.status,
        search_mode=req.search_mode,
    )

    return ApiResponse(data=results)


@router.post("/{entity_id}/recall")
async def recall_memory(entity_id: str, req: RecallRequest):
    """
    Structured memory recall by type with optional filters.
    """
    from src.tools.recall import recall_memory as do_recall

    results = do_recall(
        entity_id=entity_id,
        memory_type=req.type,
        query=req.query,
        limit=req.limit,
        status=req.status,
    )

    return ApiResponse(data=results)


@router.post("/{entity_id}/write")
async def write_memory(entity_id: str, req: WriteRequest):
    """
    Create, update, or resolve a memory item.
    """
    from src.tools.write import write_memory as do_write

    result = do_write(
        entity_id=entity_id,
        action=req.action,
        memory_type=req.type,
        data=req.data,
        source=req.source,
    )

    return ApiResponse(data=result)


@router.post("/{entity_id}/search")
async def search_memory(entity_id: str, req: SearchRequest):
    """
    Semantic search across memory types.
    Uses pgvector cosine similarity if enabled, ILIKE fallback otherwise.
    """
    from src.tools.search import search_memories

    results = await search_memories(
        entity_id=entity_id,
        query=req.query,
        memory_types=req.types,
        limit=req.limit,
    )

    return ApiResponse(data=results)


@router.post("/{entity_id}/graph")
async def graph_traverse(entity_id: str, req: GraphRequest):
    """
    Traverse the knowledge graph from a starting node.
    """
    from src.tools.graph import graph_traverse as do_graph

    results = do_graph(
        entity_id=entity_id,
        start_node_type=req.start_node_type,
        start_node_id=req.start_node_id,
        max_depth=req.depth,
        edge_types=req.edge_types,
    )

    return ApiResponse(data=results)


@router.get("/{entity_id}/stats")
async def get_stats(entity_id: str):
    """
    Get memory statistics: item counts per type, embedding count, last harvest.
    """
    from src.db.session import get_session
    from src.db.models import (
        Entity, MemoryEmbedding, HarvestLog,
        Lexicon, LifeEvent, Artifact, EmotionalPattern, RepairPattern,
        StateNeed, Permission, UnresolvedThread, Narrative, EchoDream,
        InsideJoke, IntimateMoment, RelationalRitual, Relationship,
        UserProfile,
    )
    from sqlalchemy import func

    type_models = {
        "lexicon": Lexicon,
        "life_events": LifeEvent,
        "artifacts": Artifact,
        "emotional_patterns": EmotionalPattern,
        "repair_patterns": RepairPattern,
        "state_needs": StateNeed,
        "permissions": Permission,
        "unresolved_threads": UnresolvedThread,
        "narratives": Narrative,
        "echo_dreams": EchoDream,
        "rituals": RelationalRitual,
    }

    with get_session() as session:
        # Count per type (all use entity_id FK)
        counts = {}
        for name, Model in type_models.items():
            counts[name] = session.query(func.count(Model.id)).filter_by(entity_id=entity_id).scalar() or 0

        # UserProfile is a singleton (PK = entity_id, no .id column)
        counts["user_profiles"] = 1 if session.get(UserProfile, entity_id) else 0

        # Relationship-linked types (use relationship_id, not entity_id)
        rel = session.query(Relationship).filter_by(entity_id=entity_id, target_id="user").first()
        if rel:
            counts["inside_jokes"] = session.query(func.count(InsideJoke.id)).filter_by(relationship_id=rel.id).scalar() or 0
            counts["intimate_moments"] = session.query(func.count(IntimateMoment.id)).filter_by(relationship_id=rel.id).scalar() or 0
        else:
            counts["inside_jokes"] = 0
            counts["intimate_moments"] = 0

        # Embedding count
        emb_count = session.query(func.count(MemoryEmbedding.id)).filter_by(entity_id=entity_id).scalar() or 0

        # Last harvest
        last_harvest = (
            session.query(HarvestLog.timestamp)
            .filter_by(entity_id=entity_id, success=True)
            .order_by(HarvestLog.timestamp.desc())
            .first()
        )

        entity = session.get(Entity, entity_id)

    return StatsResponse(
        entity_id=entity_id,
        counts=counts,
        embedding_count=emb_count,
        last_harvest=last_harvest[0].isoformat() if last_harvest else None,
    )
