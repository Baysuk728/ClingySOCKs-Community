"""
External Agent Registry — connects ClingySOCKs agents to external AI agents.

Loads external_agents.json and provides:
  - Registry lookup for configured external agents
  - consult_external_agent() — sends a message to an external agent
    via its OpenAI-compatible Chat Completions endpoint and returns the response.

Currently supports OpenClaw, but the config is generic enough for any
agent that exposes an OpenAI-compatible /v1/chat/completions endpoint.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.db.session import get_session
from src.db.models import AgentMessage


# ─── Config Loading ──────────────────────────────────

_CONFIG_PATH = Path(__file__).parent.parent.parent / "external_agents.json"
_AGENTS: dict[str, dict[str, Any]] = {}


def _load_config():
    """Load external_agents.json into memory."""
    global _AGENTS
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _AGENTS = data.get("agents", {})
            print(f"🌐 Loaded {len(_AGENTS)} external agent(s): {list(_AGENTS.keys())}")
        except Exception as e:
            print(f"⚠️ Failed to load external_agents.json: {e}")
    else:
        print("ℹ️  No external_agents.json found — external agent integration disabled")


# Load on import
_load_config()


def get_external_agent(agent_id: str) -> dict[str, Any] | None:
    """Get config for an external agent by ID."""
    agent = _AGENTS.get(agent_id)
    if agent and agent.get("enabled", True):
        return agent
    return None


def list_external_agents() -> list[dict[str, Any]]:
    """List all enabled external agents."""
    return [
        {"id": aid, **cfg}
        for aid, cfg in _AGENTS.items()
        if cfg.get("enabled", True)
    ]


def reload_config():
    """Reload external_agents.json (e.g., after config change)."""
    _load_config()


# ─── Consult External Agent ─────────────────────────

async def consult_external_agent(
    source_entity_id: str,
    external_agent_id: str,
    message: str,
    target_agent_id: str | None = None,
    conversation_context: str | None = None,
    conversation_id: str | None = None,
    system_prompt: str | None = None,
) -> dict:
    """
    Send a message to an external agent and get its response.

    Uses the agent's OpenAI-compatible Chat Completions endpoint.
    The external agent maintains session state via the configured session_key.

    Args:
        source_entity_id: The ClingySOCKs entity sending the message.
        external_agent_id: ID from external_agents.json (e.g., "openclaw").
        message: The message to send.
        target_agent_id: Specific agent on the external platform to target.
            For OpenClaw, this routes via model field (e.g., "openclaw/<agentId>").
            If omitted, routes to the platform's default agent.
        conversation_context: Optional context from the source's current conversation.
        conversation_id: The conversation this originated from (for logging).
        system_prompt: Optional system prompt override.

    Returns:
        dict with 'response', 'agent_name', and metadata.
    """
    agent_cfg = get_external_agent(external_agent_id)
    if not agent_cfg:
        available = [a["id"] for a in list_external_agents()]
        return {
            "error": f"External agent '{external_agent_id}' not found or disabled.",
            "available_agents": available,
        }

    gateway_url = agent_cfg["gateway_url"]
    api_path = agent_cfg.get("api_path", "/v1/chat/completions")
    base_model = agent_cfg.get("model", "openclaw")
    # Route to a specific agent on the platform (e.g., "openclaw/research-agent")
    model = f"{base_model}/{target_agent_id}" if target_agent_id else base_model
    session_key = agent_cfg.get("session_key", "clingysocks")
    timeout = agent_cfg.get("timeout_sec", 30)
    agent_name = agent_cfg.get("name", external_agent_id)

    # Resolve auth token
    token = None
    auth_mode = agent_cfg.get("auth_mode", "none")
    if auth_mode == "token":
        env_var = agent_cfg.get("auth_env_var", "")
        token = os.environ.get(env_var)
        if not token:
            return {"error": f"Auth token not found in env var '{env_var}'. Set it in .env."}

    # Build the message content
    content = message
    if conversation_context:
        content = (
            f"[Context from my current conversation: {conversation_context}]\n\n"
            f"{message}"
        )

    # Build the request payload (OpenAI Chat Completions format)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})

    payload = {
        "model": model,
        "messages": messages,
        "user": f"{session_key}/{source_entity_id}",
        "stream": False,
    }

    url = f"{gateway_url.rstrip('/')}{api_path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"🌐 Consulting external agent [{agent_name}] at {url}")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return {"error": f"External agent '{agent_name}' timed out after {timeout}s."}
    except httpx.HTTPStatusError as e:
        return {"error": f"External agent '{agent_name}' returned HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except httpx.ConnectError:
        return {"error": f"Cannot reach external agent '{agent_name}' at {gateway_url}. Check Docker networking and port mapping."}
    except Exception as e:
        return {"error": f"Failed to consult external agent '{agent_name}': {str(e)}"}

    # Parse OpenAI-compatible response
    try:
        agent_response = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return {"error": f"Unexpected response format from '{agent_name}': {json.dumps(data)[:300]}"}

    # Log the inter-agent exchange
    question_msg_id = str(uuid.uuid4())
    response_msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    try:
        with get_session() as session:
            session.add(AgentMessage(
                id=question_msg_id,
                conversation_id=conversation_id,
                from_entity_id=source_entity_id,
                to_entity_id=f"external:{external_agent_id}",
                content=message,
                message_type="consult_external",
                created_at=now,
            ))
            session.add(AgentMessage(
                id=response_msg_id,
                conversation_id=conversation_id,
                from_entity_id=f"external:{external_agent_id}",
                to_entity_id=source_entity_id,
                content=agent_response,
                message_type="response",
                in_response_to=question_msg_id,
                created_at=now,
            ))
            session.commit()
    except Exception as e:
        print(f"⚠️ Failed to log external agent message: {e}")

    return {
        "response": agent_response,
        "agent_name": agent_name,
        "agent_id": external_agent_id,
        "consultation_id": question_msg_id,
    }
