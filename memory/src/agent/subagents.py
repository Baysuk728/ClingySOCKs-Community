"""
SubAgent Registry — loads and resolves specialist subagent configurations.

SubAgents are lightweight, functional workers (not personas). They:
- Have a focused system prompt for their domain
- Only see tools matching their tool_scope patterns
- Run through the same ReAct agent loop as regular tasks
- Do NOT have memory, mood, or personality
"""

import fnmatch
import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubAgentConfig:
    """Configuration for a specialist subagent."""
    id: str                       # e.g., "content_creator"
    name: str                     # e.g., "ContentCreator"
    description: str              # What it does (shown to companion for delegation)
    system_prompt: str            # Focused instruction
    tool_scope: list[str]         # Glob patterns like ["CanvaMCP__*", "MediaMCP__*"]
    max_steps: int = 10
    temperature: float = 0.7


# ─── Registry ──────────────────────────────────────────

_registry: dict[str, SubAgentConfig] | None = None
_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "subagents.json")


def _load_registry() -> dict[str, SubAgentConfig]:
    """Load subagent configs from subagents.json."""
    global _registry
    if _registry is not None:
        return _registry

    _registry = {}
    if not os.path.exists(_config_path):
        print(f"⚠️ SubAgent config not found at {_config_path}")
        return _registry

    try:
        with open(_config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for agent_id, cfg in data.get("subagents", {}).items():
            _registry[agent_id] = SubAgentConfig(
                id=agent_id,
                name=cfg["name"],
                description=cfg["description"],
                system_prompt=cfg["system_prompt"],
                tool_scope=cfg.get("tool_scope", ["*"]),
                max_steps=cfg.get("max_steps", 10),
                temperature=cfg.get("temperature", 0.7),
            )
        print(f"✅ Loaded {len(_registry)} subagent configs: {list(_registry.keys())}")
    except Exception as e:
        print(f"❌ Failed to load subagent config: {e}")

    return _registry


def get_subagent(agent_id: str) -> Optional[SubAgentConfig]:
    """Get a specific subagent config by ID."""
    return _load_registry().get(agent_id)


def list_subagents() -> list[SubAgentConfig]:
    """List all registered subagents."""
    return list(_load_registry().values())


def reload_registry():
    """Force reload of subagent configs (e.g., after editing subagents.json)."""
    global _registry
    _registry = None
    _load_registry()


def filter_tools_by_scope(all_tools: list[dict], scope_patterns: list[str]) -> list[dict]:
    """
    Filter a list of LiteLLM tool schemas to only those matching the scope patterns.

    Each tool has {"type": "function", "function": {"name": "ServerName__tool_name", ...}}.
    Scope patterns like "CanvaMCP__*" use fnmatch glob matching against the tool name.
    """
    filtered = []
    for tool in all_tools:
        tool_name = tool.get("function", {}).get("name", "")
        for pattern in scope_patterns:
            if fnmatch.fnmatch(tool_name, pattern):
                filtered.append(tool)
                break
    return filtered
