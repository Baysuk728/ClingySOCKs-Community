"""
ClingySOCKs Memory MCP Server — Expose memory tools via Model Context Protocol.

Allows Claude Code, Cursor, Windsurf, Gemini CLI, and other MCP-compatible
tools to query and write ClingySOCKs memories natively.

27 tools exposed:
- orient / ground / boot — Session initialization
- recall_memory — Structured retrieval by type
- search_memories — Semantic search
- write_memory — Create/update/resolve memories
- graph_traverse — Knowledge graph BFS
- memory_query — Unified recall + search
- timeline — Chronological topic trace
- get_stats — Memory statistics
- subconscious_status — Daemon findings

Runs as a standalone MCP server process.
Register in your .mcp.json or claude mcp add.

Usage:
    python -m memory.McpServers.MemoryMCP

    Or via claude:
    claude mcp add clingysocks -- python -m memory.McpServers.MemoryMCP
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `src.*` imports work
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv(_project_root / ".env")

from mcp.server.fastmcp import FastMCP

# Fix UTF-8 encoding for Windows
if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")


mcp = FastMCP("ClingySOCKs Memory")

# Default entity — can be overridden per-call or via env
DEFAULT_ENTITY_ID = os.getenv("MCP_DEFAULT_ENTITY_ID", "")


def _resolve_entity(entity_id: str | None = None) -> str:
    """Resolve entity_id from argument or default."""
    eid = entity_id or DEFAULT_ENTITY_ID
    if not eid:
        raise ValueError(
            "entity_id is required. Set MCP_DEFAULT_ENTITY_ID in .env "
            "or pass entity_id to each call."
        )
    return eid


# ── Boot Sequence ────────────────────────────────────

@mcp.tool()
def orient(entity_id: str | None = None) -> dict:
    """
    Session initialization — identity anchor.
    
    Returns compact identity context: agent name, user profile,
    relationship state, current mood, time context.
    Call this first when starting a new session.
    
    Args:
        entity_id: Agent entity ID (optional if MCP_DEFAULT_ENTITY_ID is set)
    """
    from src.services.orient_ground import orient as _orient
    return _orient(_resolve_entity(entity_id))


@mcp.tool()
def ground(entity_id: str | None = None) -> dict:
    """
    Session initialization — active context grounding.
    
    Returns active threads, pinned notes, recent activity,
    and current narrative. Call after orient().
    
    Args:
        entity_id: Agent entity ID
    """
    from src.services.orient_ground import ground as _ground
    return _ground(_resolve_entity(entity_id))


@mcp.tool()
def boot(entity_id: str | None = None) -> dict:
    """
    Full boot sequence — orient + ground combined.
    
    Returns complete session context in one call.
    
    Args:
        entity_id: Agent entity ID
    """
    from src.services.orient_ground import boot_context
    return boot_context(_resolve_entity(entity_id))


# ── Memory Tools ─────────────────────────────────────

@mcp.tool()
def recall_memory(
    memory_type: str,
    entity_id: str | None = None,
    query: str | None = None,
    limit: int = 10,
    status: str = "active",
) -> dict:
    """
    Retrieve structured memories by type.
    
    Args:
        memory_type: Type of memory (lexicon, life_event, artifact, emotional_pattern, etc.)
        entity_id: Agent entity ID
        query: Optional text filter
        limit: Max results (default 10)
        status: Filter by status — active, resolved, deprecated, all
    """
    import asyncio
    from src.tools.recall import recall_memory as _recall

    eid = _resolve_entity(entity_id)
    result = asyncio.get_event_loop().run_until_complete(
        _recall(eid, memory_type, query=query, limit=limit, status=status)
    )
    return {"items": result, "count": len(result)}


@mcp.tool()
def search_memories(
    query: str,
    entity_id: str | None = None,
    memory_types: list[str] | None = None,
    limit: int = 10,
) -> dict:
    """
    Semantic search across all memory types.
    
    Uses pgvector cosine similarity when embeddings are enabled,
    falls back to text search otherwise.
    
    Args:
        query: Natural language search query
        entity_id: Agent entity ID
        memory_types: Optional list of types to search
        limit: Max results
    """
    import asyncio
    from src.tools.search import search_memories as _search

    eid = _resolve_entity(entity_id)
    result = asyncio.get_event_loop().run_until_complete(
        _search(eid, query, memory_types=memory_types, limit=limit)
    )
    return {"results": result, "count": len(result)}


@mcp.tool()
def write_memory(
    action: str,
    memory_type: str,
    data: dict,
    entity_id: str | None = None,
) -> dict:
    """
    Create, update, or resolve a memory item.
    
    Args:
        action: create, update, or resolve
        memory_type: Type to write (lexicon, life_event, permission, ritual, etc.)
        data: Memory data fields
        entity_id: Agent entity ID
    """
    import asyncio
    from src.tools.write import write_memory as _write

    eid = _resolve_entity(entity_id)
    result = asyncio.get_event_loop().run_until_complete(
        _write(eid, action, memory_type, data)
    )
    return result


@mcp.tool()
def graph_traverse(
    start_node_type: str,
    start_node_id: str,
    entity_id: str | None = None,
    max_depth: int = 2,
    edge_types: list[str] | None = None,
) -> dict:
    """
    Explore the knowledge graph from a starting node.
    
    BFS traversal following edges up to max_depth hops.
    
    Args:
        start_node_type: Type of starting node (e.g., life_event, person)
        start_node_id: Database ID of starting node
        entity_id: Agent entity ID
        max_depth: Max hops (1-3 recommended)
        edge_types: Optional filter for edge relationship types
    """
    from src.tools.graph import graph_traverse as _traverse

    eid = _resolve_entity(entity_id)
    return _traverse(eid, start_node_type, start_node_id, max_depth, edge_types)


@mcp.tool()
def memory_query(
    entity_id: str | None = None,
    query: str | None = None,
    memory_type: str | None = None,
    limit: int = 10,
    status: str = "active",
    search_mode: str = "auto",
) -> dict:
    """
    Unified memory query — structured recall OR semantic search.
    
    Provide memory_type without query for structured recall.
    Provide query for semantic search. Use search_mode to force a mode.
    
    Args:
        entity_id: Agent entity ID
        query: Search text (triggers semantic mode)
        memory_type: Single type to query
        limit: Max results
        status: Status filter for recall mode
        search_mode: auto, exact, or semantic
    """
    import asyncio
    from src.tools.query import memory_query as _query

    eid = _resolve_entity(entity_id)
    result = asyncio.get_event_loop().run_until_complete(
        _query(eid, query=query, memory_type=memory_type, limit=limit,
               status=status, search_mode=search_mode)
    )
    return result


@mcp.tool()
def get_memory_stats(entity_id: str | None = None) -> dict:
    """
    Get memory statistics — item counts per type, embedding count, last harvest.
    
    Args:
        entity_id: Agent entity ID
    """
    from src.db.session import get_session
    from src.memory_registry import MEMORY_TYPES, resolve_model

    eid = _resolve_entity(entity_id)
    stats = {}

    with get_session() as session:
        for key, defn in MEMORY_TYPES.items():
            try:
                model = resolve_model(key)
                if model and hasattr(model, "entity_id"):
                    count = session.query(model).filter_by(entity_id=eid).count()
                    if count > 0:
                        stats[key] = count
            except Exception:
                continue

    return {"entity_id": eid, "memory_counts": stats, "total": sum(stats.values())}


# ── Timeline ─────────────────────────────────────────

@mcp.tool()
def timeline(
    topic: str,
    entity_id: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Trace a topic chronologically through all memory types.
    
    Returns a time-ordered narrative of everything related to the topic.
    
    Args:
        topic: The topic to trace (e.g., "auth decisions", "relationship with Sam")
        entity_id: Agent entity ID
        limit: Max events to return
    """
    import asyncio
    from src.services.timeline import trace_timeline

    eid = _resolve_entity(entity_id)
    return asyncio.get_event_loop().run_until_complete(
        trace_timeline(eid, topic, limit=limit)
    )


# ── Subconscious ─────────────────────────────────────

@mcp.tool()
def subconscious_status(entity_id: str | None = None) -> dict:
    """
    Get the latest subconscious daemon findings.
    
    Returns orphan memories, co-surfacing patterns, connection proposals,
    and mood trends from the last daemon cycle.
    
    Args:
        entity_id: Agent entity ID
    """
    from src.services.subconscious_daemon import subconscious_daemon

    eid = _resolve_entity(entity_id)
    results = subconscious_daemon.get_last_results(eid)
    if not results:
        return {"status": "no_data", "message": "No subconscious cycle has run yet for this entity."}
    return results


# ── Entry Point ──────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
