"""
Pydantic schemas for API request/response models.
"""

from pydantic import BaseModel, Field
from typing import Any


# ============================================================================
# Memory Endpoints
# ============================================================================

class RecallRequest(BaseModel):
    """Request body for /memory/{entity_id}/recall"""
    type: str = Field(..., description="Memory type: lexicon, life_events, artifacts, etc.")
    query: str | None = Field(None, description="Optional text search filter")
    status: str = Field("active", description="Status filter: active, resolved, deprecated, or all")
    limit: int = Field(10, ge=1, le=100)


class WriteRequest(BaseModel):
    """Request body for /memory/{entity_id}/write"""
    type: str = Field(..., description="Memory type to write")
    action: str = Field("create", description="create, update, or resolve")
    data: dict[str, Any] = Field(..., description="Memory item data")
    source: str = Field("user", description="Who initiated: agent, user, or system")


class SearchRequest(BaseModel):
    """Request body for /memory/{entity_id}/search"""
    query: str = Field(..., min_length=1, description="Search query (natural language)")
    types: list[str] | None = Field(None, description="Optional: filter to specific types")
    limit: int = Field(10, ge=1, le=50)


class MemoryQueryRequest(BaseModel):
    """Request body for /memory/{entity_id}/query"""
    query: str | None = Field(None, description="Search text (enables semantic mode)")
    memory_type: str | None = Field(None, description="Single memory type to query")
    memory_types: list[str] | None = Field(None, description="Multiple types to search across")
    limit: int = Field(10, ge=1, le=100)
    status: str = Field("active", description="Status filter (exact mode only)")
    search_mode: str = Field("auto", description="auto, exact, or semantic")


class GraphRequest(BaseModel):
    """Request body for /memory/{entity_id}/graph"""
    start_node_id: str = Field(..., description="Starting node ID")
    start_node_type: str = Field(..., description="Starting node type")
    depth: int = Field(2, ge=1, le=5)
    edge_types: list[str] | None = Field(None, description="Filter by edge type")


# ============================================================================
# Harvest Endpoints
# ============================================================================

class HarvestRequest(BaseModel):
    """Request body for /harvest/{entity_id}"""
    dry_run: bool = Field(False, description="If true, analyze without storing")


# ============================================================================
# Sync Endpoints
# ============================================================================

class SyncMessage(BaseModel):
    """A single message to sync to the database."""
    id: str
    conversation_id: str
    sender_id: str
    content: str
    timestamp: str  # ISO 8601
    message_index: int


class SyncMessagesRequest(BaseModel):
    """Request body for /sync/messages"""
    entity_id: str
    conversation_title: str | None = None
    messages: list[SyncMessage]


# ============================================================================
# Admin Endpoints
# ============================================================================

class EmbedRequest(BaseModel):
    """Request body for /memory/{entity_id}/embed"""
    types: list[str] | None = Field(None, description="Memory types to embed (None = all)")
    force: bool = Field(False, description="Force re-embed even if unchanged")


# ============================================================================
# Response Models
# ============================================================================

class ApiResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool = True
    data: Any = None
    error: str | None = None


class StatsResponse(BaseModel):
    """Response for /memory/{entity_id}/stats"""
    entity_id: str
    counts: dict[str, int]
    embedding_count: int
    last_harvest: str | None = None
