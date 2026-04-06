"""
ClingySOCKs Community Edition — Feature configuration.

This is the free, open-source edition. Advanced features (mood engine,
dream engine, imperfection engine, autonomous agent) are available in
paid tiers at https://clingysocks.com (update with your actual URL).
"""

from __future__ import annotations

from enum import Enum
from fastapi import HTTPException


class Feature(str, Enum):
    """Feature flags. Only used for compatibility — community has core features only."""
    MOOD_ENGINE = "mood_engine"
    MEMORY_DECAY = "memory_decay"
    PREFERENCE_ENGINE = "preference_engine"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    DREAM_ENGINE = "dream_engine"
    IMPERFECTION_ENGINE = "imperfection_engine"
    HEARTBEAT = "heartbeat"
    AGENT_TASKS = "agent_tasks"
    SHADOW_LOGS = "shadow_logs"
    SOCIAL_MCP = "social_mcp"
    WEB_SEARCH_MCP = "web_search_mcp"
    MEDIA_MCP = "media_mcp"
    REMOTE_MCP = "remote_mcp"


EDITION = "community"


def has_feature(feature: Feature) -> bool:
    """Community edition — paid features return False."""
    return False


def get_edition() -> str:
    return "community"


def get_edition_index() -> int:
    return 0


def get_available_features() -> list[str]:
    return []


def get_feature_tier(feature: Feature) -> str:
    return "standard"


def require_feature(feature: Feature):
    """FastAPI dependency — returns 403 for any gated feature."""
    async def _check():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "feature_not_available",
                "feature": feature.value,
                "current_tier": "community",
                "message": f"'{feature.value}' is available in paid tiers. "
                           f"Visit https://clingysocks.com for more info.",
            },
        )
    return _check
