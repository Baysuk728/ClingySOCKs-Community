"""
Group Chat route — multi-agent conversation orchestrator.

Enables conversations with multiple AI agents responding to a single
user message. Supports sequential and concurrent turn strategies.

Each agent gets:
- Its own persona/warm memory context
- The FULL group conversation history (messages from user + all agents)
- Access to all tools including consult_agent and broadcast_agents
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import require_api_key
from src.db.session import get_session
from src.db.models import (
    Message, Conversation, Entity, ConversationParticipant,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


# ─── Request / Response Models ────────────────────────

class ChatMessage(BaseModel):
    id: Optional[str] = Field(None)
    role: str
    content: str
    sender_id: Optional[str] = Field(None, description="Entity ID of the sender (for group messages)")
    timestamp: Optional[float] = None


class GroupChatRequest(BaseModel):
    user_id: str = Field("default-user")
    messages: list[ChatMessage] = Field(..., description="Full conversation history")
    responding_agents: list[str] | None = Field(
        None, description="Subset of participants to respond. None = all active participants."
    )
    turn_strategy: str = Field(
        "sequential", description="'sequential' | 'concurrent' | 'addressed'"
    )
    max_tokens: int = Field(4096, ge=1, le=32000)
    tools_enabled: bool = Field(True)
    stream: bool = Field(True)


# ─── Helpers ──────────────────────────────────────────

def _get_active_participants(conversation_id: str, exclude_entity_id: str | None = None) -> list[str]:
    """Get active participant entity_ids for a conversation."""
    with get_session() as session:
        query = (
            session.query(ConversationParticipant.entity_id)
            .filter_by(conversation_id=conversation_id)
            .filter(ConversationParticipant.left_at.is_(None))
        )
        if exclude_entity_id:
            query = query.filter(ConversationParticipant.entity_id != exclude_entity_id)
        return [row[0] for row in query.all()]


def _save_message(entity_id: str, chat_id: str, sender_id: str, content: str,
                  user_id: str = "unknown", tool_calls=None, tool_results=None, force_id=None):
    """Save a message to the conversation (shared with single-agent chat route)."""
    if not chat_id:
        return
    try:
        with get_session() as session:
            # Ensure conversation exists
            conv = session.get(Conversation, chat_id)
            if not conv:
                conv = Conversation(
                    id=chat_id,
                    entity_id=entity_id,
                    title=f"Group Chat {chat_id[:8]}",
                    chat_type="group",
                    message_count=0,
                )
                session.add(conv)
                session.flush()

            last_msg = (
                session.query(Message)
                .filter_by(conversation_id=chat_id)
                .order_by(Message.message_index.desc())
                .first()
            )
            idx = (last_msg.message_index + 1) if last_msg else 0

            msg = Message(
                id=force_id or str(uuid.uuid4()),
                conversation_id=chat_id,
                sender_id=sender_id,
                content=content or "",
                timestamp=datetime.now(timezone.utc),
                message_index=idx,
                tool_calls=[json.dumps(tc) for tc in tool_calls] if tool_calls else None,
                tool_results=[json.dumps(tr) for tr in tool_results] if tool_results else None,
            )
            session.add(msg)
            conv.updated_at = datetime.now(timezone.utc)
            conv.message_count = idx + 1
            session.commit()
    except Exception as e:
        print(f"❌ GROUP CHAT DB SAVE ERROR: {e}")


def _parse_addressed_agents(content: str, participant_names: dict[str, str]) -> list[str]:
    """
    Parse @mentions in a message to determine addressed agents.

    Args:
        content: The user's message
        participant_names: {entity_id: name} mapping

    Returns:
        List of entity_ids that were @mentioned, or empty if none
    """
    mentioned = []
    content_lower = content.lower()
    for entity_id, name in participant_names.items():
        if f"@{name.lower()}" in content_lower:
            mentioned.append(entity_id)
    return mentioned


# ─── Group Chat Endpoint ─────────────────────────────

@router.post("/{conversation_id}")
async def group_chat(conversation_id: str, req: GroupChatRequest):
    """
    Chat with multiple agents in a group conversation.

    Each responding agent gets the full group history and responds
    with its own persona, memory, and mood context.
    """
    import traceback
    try:
        import litellm
        from api.chat_context import build_context, ChatMessage as ContextMessage
        from src.persona_config import aload_persona_config, sanitize_sampling_params
        from api.routes.chat import execute_tool_call

        # 1. Determine responding agents
        if req.responding_agents:
            responding = req.responding_agents
        else:
            responding = _get_active_participants(conversation_id)

        if not responding:
            # Fallback: check conversation's entity_id
            with get_session() as session:
                conv = session.get(Conversation, conversation_id)
                if conv and conv.entity_id:
                    responding = [conv.entity_id]
                else:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=400, detail="No agents in this conversation")

        # Handle @mention addressing
        if req.turn_strategy == "addressed" and req.messages:
            last_msg = req.messages[-1]
            if last_msg.role == "user":
                # Build name→id mapping
                with get_session() as session:
                    name_map = {}
                    for eid in responding:
                        entity = session.get(Entity, eid)
                        if entity:
                            name_map[eid] = entity.name
                mentioned = _parse_addressed_agents(last_msg.content, name_map)
                if mentioned:
                    responding = mentioned
                # If no @mentions found, all agents respond

        # Save user message
        if req.messages:
            last_msg = req.messages[-1]
            if last_msg.role == "user":
                _save_message(
                    responding[0], conversation_id, "user", last_msg.content,
                    user_id=req.user_id, force_id=last_msg.id
                )

        print(f"🔥 GROUP CHAT: {len(responding)} agents responding in '{req.turn_strategy}' mode")

        if req.stream:
            return _stream_group_response(
                conversation_id, responding, req, execute_tool_call
            )
        else:
            return await _sync_group_response(
                conversation_id, responding, req, execute_tool_call
            )

    except Exception as e:
        print(f"❌ GROUP CHAT CRITICAL ERROR: {e}")
        traceback.print_exc()
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Group chat error: {str(e)}")


# ─── Streaming Group Response ────────────────────────

def _stream_group_response(conversation_id: str, responding: list[str],
                           req: GroupChatRequest, execute_tool_call):
    """Stream group chat responses via SSE, one agent at a time (sequential)."""
    import litellm
    from api.chat_context import build_context, ChatMessage as ContextMessage
    from src.persona_config import aload_persona_config, sanitize_sampling_params
    from src.tools.schemas import ALL_TOOL_SCHEMAS as MEMORY_TOOLS
    from src.integrations.mcp_client import mcp_manager

    async def generate():
        try:
            yield f"data: {json.dumps({'type': 'group_start', 'agents': responding, 'strategy': req.turn_strategy})}\n\n"

            for agent_idx, entity_id in enumerate(responding):
                yield f"data: {json.dumps({'type': 'agent_start', 'entity_id': entity_id, 'index': agent_idx})}\n\n"

                try:
                    # Load this agent's config
                    cfg = await aload_persona_config(entity_id, user_id=req.user_id)
                    model = cfg.model
                    context_config = cfg.to_context_config()

                    # Build context messages (include all group messages)
                    ctx_messages = []
                    for msg in req.messages:
                        role = msg.role
                        if role == "model":
                            role = "assistant"
                        ctx_messages.append(ContextMessage(
                            role=role,
                            content=msg.content,
                            timestamp=msg.timestamp,
                        ))

                    # Build this agent's full context
                    context = build_context(
                        entity_id=entity_id,
                        user_id=req.user_id,
                        messages=ctx_messages,
                        system_prompt=cfg.system_prompt,
                        config=context_config,
                    )

                    # Assemble prompt
                    stable_parts = [context.system_instruction, context.context_primer]
                    if context.voice_anchors:
                        stable_parts.append(context.voice_anchors)
                    if context.integrity_frame:
                        stable_parts.append(context.integrity_frame)
                    stable_system = "\n\n".join(p for p in stable_parts if p)

                    # Add group chat awareness to dynamic preamble
                    group_preamble = (
                        f"{context.dynamic_preamble}"
                        f"━━━ GROUP CONVERSATION ━━━\n"
                        f"You are in a group conversation with the user and other agents.\n"
                        f"Responding agents: {', '.join(responding)}\n"
                        f"You are: {entity_id}\n"
                        f"━━━━━━━━━━━━\n\n"
                    )

                    is_anthropic = any(x in model.lower() for x in ["claude", "anthropic"])
                    if is_anthropic:
                        final_messages = [{
                            "role": "system",
                            "content": [
                                {"type": "text", "text": stable_system, "cache_control": {"type": "ephemeral"}},
                                {"type": "text", "text": group_preamble},
                            ]
                        }]
                    else:
                        final_messages = [{"role": "system", "content": stable_system + "\n\n" + group_preamble}]

                    final_messages.extend(context.history)

                    # Prepare LLM kwargs
                    sampling = sanitize_sampling_params(
                        model, top_p=cfg.top_p, top_k=cfg.top_k,
                        frequency_penalty=cfg.frequency_penalty,
                        presence_penalty=cfg.presence_penalty,
                    )
                    kwargs = {
                        "model": model,
                        "messages": final_messages,
                        "temperature": cfg.temperature,
                        "max_tokens": req.max_tokens,
                        "stream": True,
                    }
                    if cfg.api_key:
                        kwargs["api_key"] = cfg.api_key
                    kwargs.update(sampling)

                    if "gemini" in model.lower():
                        kwargs["safety_settings"] = [
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
                        ]

                    # Add tools
                    if req.tools_enabled:
                        tools = list(MEMORY_TOOLS)
                        mcp_tools = await mcp_manager.get_all_tools()
                        if mcp_tools:
                            tools.extend(mcp_tools)
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = "auto"

                    # Stream this agent's response
                    response = await litellm.acompletion(**kwargs)
                    full_content = ""
                    tool_calls_buffer: dict[int, dict] = {}

                    async for chunk in response:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        if not delta:
                            continue

                        if delta.content:
                            full_content += delta.content
                            yield f"data: {json.dumps({'type': 'content', 'content': delta.content, 'entity_id': entity_id})}\n\n"

                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                idx = tc.index
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {
                                        "id": tc.id or f"call_{idx}",
                                        "name": tc.function.name if tc.function and tc.function.name else "",
                                        "arguments": "",
                                    }
                                if tc.function and tc.function.arguments:
                                    tool_calls_buffer[idx]["arguments"] += tc.function.arguments

                    # Execute tool calls (single round for group chat to keep it manageable)
                    if tool_calls_buffer and req.tools_enabled:
                        for idx, tc in sorted(tool_calls_buffer.items()):
                            yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'arguments': tc['arguments'], 'entity_id': entity_id})}\n\n"
                            try:
                                args = json.loads(tc["arguments"])
                            except json.JSONDecodeError:
                                args = {}
                            result = await execute_tool_call(entity_id, tc["name"], args)
                            yield f"data: {json.dumps({'type': 'tool_result', 'name': tc['name'], 'result': result, 'entity_id': entity_id})}\n\n"

                        # Follow-up call after tool execution
                        tool_results_msgs = []
                        tc_payload = []
                        for tc in tool_calls_buffer.values():
                            tc_payload.append({
                                "id": tc["id"], "type": "function",
                                "function": {"name": tc["name"], "arguments": tc["arguments"]},
                            })
                        final_messages.append({"role": "assistant", "content": full_content or None, "tool_calls": tc_payload})
                        for tc in tool_calls_buffer.values():
                            try:
                                args = json.loads(tc["arguments"])
                            except json.JSONDecodeError:
                                args = {}
                            result = await execute_tool_call(entity_id, tc["name"], args)
                            tool_results_msgs.append({"tool_call_id": tc["id"], "role": "tool", "content": result})
                        final_messages.extend(tool_results_msgs)

                        followup_kwargs = {**kwargs, "messages": final_messages, "stream": True}
                        followup_kwargs.pop("tools", None)  # No more tools for followup
                        followup_kwargs.pop("tool_choice", None)

                        followup_response = await litellm.acompletion(**followup_kwargs)
                        followup_content = ""
                        async for fu_chunk in followup_response:
                            fu_delta = fu_chunk.choices[0].delta if fu_chunk.choices else None
                            if fu_delta and fu_delta.content:
                                followup_content += fu_delta.content
                                yield f"data: {json.dumps({'type': 'content', 'content': fu_delta.content, 'entity_id': entity_id})}\n\n"
                        full_content += followup_content

                    # Save agent response
                    _save_message(entity_id, conversation_id, entity_id, full_content, user_id=req.user_id)

                    yield f"data: {json.dumps({'type': 'agent_done', 'entity_id': entity_id, 'content': full_content})}\n\n"

                except Exception as agent_err:
                    print(f"❌ Agent {entity_id} failed: {agent_err}")
                    import traceback
                    traceback.print_exc()
                    yield f"data: {json.dumps({'type': 'agent_error', 'entity_id': entity_id, 'error': str(agent_err)})}\n\n"

            yield f"data: {json.dumps({'type': 'group_done', 'agents_responded': len(responding)})}\n\n"

        except Exception as e:
            print(f"❌ GROUP STREAM ERROR: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Sync Group Response ─────────────────────────────

async def _sync_group_response(conversation_id: str, responding: list[str],
                               req: GroupChatRequest, execute_tool_call):
    """Non-streaming group chat response."""
    import litellm
    from api.chat_context import build_context, ChatMessage as ContextMessage
    from src.persona_config import aload_persona_config, sanitize_sampling_params

    results = []
    for entity_id in responding:
        try:
            cfg = await aload_persona_config(entity_id, user_id=req.user_id)

            ctx_messages = [
                ContextMessage(role=m.role if m.role != "model" else "assistant",
                              content=m.content, timestamp=m.timestamp)
                for m in req.messages
            ]

            context = build_context(
                entity_id=entity_id,
                user_id=req.user_id,
                messages=ctx_messages,
                system_prompt=cfg.system_prompt,
                config=context_config if 'context_config' in dir() else cfg.to_context_config(),
            )

            stable_parts = [context.system_instruction, context.context_primer]
            if context.voice_anchors:
                stable_parts.append(context.voice_anchors)
            stable_system = "\n\n".join(p for p in stable_parts if p)

            group_preamble = (
                f"{context.dynamic_preamble}"
                f"━━━ GROUP CONVERSATION ━━━\n"
                f"Responding agents: {', '.join(responding)}\nYou are: {entity_id}\n━━━━━━━━━━━━\n\n"
            )

            final_messages = [{"role": "system", "content": stable_system + "\n\n" + group_preamble}]
            final_messages.extend(context.history)

            sampling = sanitize_sampling_params(
                cfg.model, top_p=cfg.top_p, top_k=cfg.top_k,
                frequency_penalty=cfg.frequency_penalty,
                presence_penalty=cfg.presence_penalty,
            )
            kwargs = {
                "model": cfg.model, "messages": final_messages,
                "temperature": cfg.temperature, "max_tokens": req.max_tokens,
                "stream": False,
            }
            if cfg.api_key:
                kwargs["api_key"] = cfg.api_key
            kwargs.update(sampling)

            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content or ""

            _save_message(entity_id, conversation_id, entity_id, content, user_id=req.user_id)
            results.append({"entity_id": entity_id, "content": content})

        except Exception as e:
            results.append({"entity_id": entity_id, "error": str(e)})

    return {"conversation_id": conversation_id, "responses": results}
