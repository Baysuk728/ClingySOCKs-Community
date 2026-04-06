"""
Chat route — LLM chat with warm memory injection and tool awareness.

Supports:
- Warm memory auto-injection into system prompt
- Streaming responses via Server-Sent Events (SSE)
- Thinking / reasoning extraction (for thinking models)
- Memory tool calls during conversation
"""

import json
import os
import time
from typing import Optional, Union

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import require_api_key
import uuid
from datetime import datetime, timezone
from src.db.session import get_session
from src.db.models import Message, Conversation, Entity

router = APIRouter(dependencies=[Depends(require_api_key)])

def _save_message_to_db(entity_id: str, chat_id: str, sender_id: str, content: str, user_id: str = "unknown", tool_calls=None, tool_results=None, force_id=None):
    if not chat_id:
        return
    try:
        with get_session() as session:
            # Lazily create entity if missing
            entity = session.get(Entity, entity_id)
            if not entity:
                entity = Entity(
                    id=entity_id,
                    entity_type="agent",
                    name=entity_id.capitalize(),
                    owner_user_id=user_id,
                    schema_version="2.0"
                )
                session.add(entity)
                session.flush()

            conv = session.get(Conversation, chat_id)
            if not conv:
                conv = Conversation(
                    id=chat_id,
                    entity_id=entity_id,
                    title=f"Chat {chat_id[:8]}",
                    message_count=0
                )
                session.add(conv)
                session.flush()
                
            last_msg = session.query(Message).filter_by(conversation_id=chat_id).order_by(Message.message_index.desc()).first()
            idx = (last_msg.message_index + 1) if last_msg else 0
            
            m_id = force_id or str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            
            def serialize_tc(tc):
                if hasattr(tc, "model_dump"): return tc.model_dump()
                if hasattr(tc, "dict"): return tc.dict()
                return dict(tc) if isinstance(tc, dict) else tc

            msg = Message(
                id=m_id,
                conversation_id=chat_id,
                sender_id=sender_id,
                content=content or "",
                timestamp=now,
                message_index=idx,
                tool_calls=[json.dumps(serialize_tc(tc)) for tc in tool_calls] if tool_calls else None,
                tool_results=[json.dumps(tr) for tr in tool_results] if tool_results else None
            )
            session.add(msg)
            conv.updated_at = now
            conv.message_count = idx + 1
            session.commit()
    except Exception as e:
        print(f"❌ DB SAVE ERROR: {e}")

def _save_shadow_logs(entity_id: str, profile):
    try:
        if not profile: return
        with get_session() as session:
            from src.db.models import ShadowLog
            now = datetime.now(timezone.utc)
            from src.services.imperfection_engine import FrictionProfile
            
            # Save any active channels
            if profile.stubbornness > 0:
                session.add(ShadowLog(entity_id=entity_id, channel="stubbornness", intensity=profile.stubbornness, trigger_description=profile.stubbornness_topic, created_at=now))
            if profile.engagement < 1.0:
                session.add(ShadowLog(entity_id=entity_id, channel="disengagement", intensity=1.0 - profile.engagement, trigger_description="low_energy", created_at=now))
            if profile.opinion_pressure > 0:
                session.add(ShadowLog(entity_id=entity_id, channel="opinion_surge", intensity=profile.opinion_pressure, trigger_description=profile.opinion_queue[0] if profile.opinion_queue else "unknown", created_at=now))
            if profile.emotional_bleed:
                session.add(ShadowLog(entity_id=entity_id, channel="emotional_bleed", intensity=abs(profile.bleed_valence), trigger_description="mood_residue", created_at=now))
            session.commit()
    except Exception as e:
        print(f"❌ SHADOWLOG SAVE ERROR: {e}")

# ─── Request / Response Models ────────────────────────

# ─── Request / Response Models ────────────────────────

class ChatMessage(BaseModel):
    id: Optional[str] = Field(None, description="Frontend message ID")
    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: Union[str, list] = Field(..., description="Text string or multimodal content parts (OpenAI vision format)")
    timestamp: Optional[float] = Field(None, description="Unix timestamp for silence gap calculation")

    def text_content(self) -> str:
        """Extract plain text from content, whether string or multimodal parts."""
        if isinstance(self.content, str):
            return self.content
        # Multimodal: extract text parts
        return " ".join(
            part.get("text", "") for part in self.content
            if isinstance(part, dict) and part.get("type") == "text"
        )


class ChatRequest(BaseModel):
    entity_id: str = Field(..., description="Entity whose memory to use")
    user_id: Optional[str] = Field("default-user", description="User ID for dossier lookup")
    chat_id: Optional[str] = Field(None, description="Chat ID for backfilling history")
    messages: list[ChatMessage] = Field(..., description="Conversation history")
    model: Optional[str] = Field(None, description="LiteLLM model identifier")
    system_prompt: Optional[str] = Field(None, description="Static system instruction")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, ge=1, le=32000)
    stream: bool = Field(True, description="Stream response via SSE")
    tools_enabled: bool = Field(True, description="Allow agent to use memory tools")


class ChatResponse(BaseModel):
    content: str
    thinking: Optional[str] = None
    tool_calls: list[dict] = Field(default_factory=list)
    model: str
    usage: Optional[dict] = None
    context_metadata: Optional[dict] = None


# ─── Tool Execution ──────────────────────────────────

from src.tools.recall import recall_memory
from src.tools.write import write_memory
from src.tools.search import search_memories
from src.tools.query import memory_query
from src.tools.graph import graph_traverse
from src.tools.schemas import ALL_TOOL_SCHEMAS as MEMORY_TOOLS



def _try_parse_text_tool_calls(content: str) -> list[dict] | None:
    """
    Some models (Mistral, older Llama variants) output tool calls as JSON text
    in the content field instead of using the structured tool_calls API.

    Detects these patterns:
      [{"name": "tool_name", "arguments": {...}}]
      {"name": "tool_name", "arguments": {...}}
      [{"name": "tool_name", "parameters": {...}}]

    Returns a list of {"name": str, "arguments": str (JSON)} dicts, or None.
    """
    stripped = content.strip()
    if not stripped or stripped[0] not in ('[', '{'):
        return None

    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

    candidates = parsed if isinstance(parsed, list) else [parsed]

    result = []
    for item in candidates:
        if not isinstance(item, dict):
            return None
        # Support {"name": ..., "arguments": ...} and {"name": ..., "parameters": ...}
        name = item.get("name")
        if not name and isinstance(item.get("function"), dict):
            name = item["function"].get("name")
        args = item.get("arguments") or item.get("parameters") or {}
        if not name:
            return None
        result.append({
            "name": name,
            "arguments": args if isinstance(args, str) else json.dumps(args),
        })

    return result if result else None


async def execute_tool_call(entity_id: str, tool_name: str, args: dict) -> str:
    """Execute a tool call and return JSON string result."""
    from src.edition import has_feature, Feature as EditionFeature
    try:
            
        # Otherwise, handle built-in memory tools
        if tool_name == "memory_query":
            result = await memory_query(entity_id, **args)
        elif tool_name == "recall_memory":
            # Legacy: route through unified query in exact mode
            result = await memory_query(entity_id, search_mode="exact", **args)
        elif tool_name == "write_memory":
            if "source" not in args:
                args["source"] = "agent"
            result = write_memory(entity_id, **args)
        elif tool_name == "search_memories":
            # Legacy: route through unified query in semantic mode
            result = await memory_query(entity_id, search_mode="semantic", **args)
        elif tool_name == "graph_traverse":
            result = graph_traverse(entity_id, **args)
        elif tool_name == "send_message":
            from src.tools.send_message import send_message
            result = await send_message(entity_id, **args)
        elif tool_name == "delegate_task":
            from src.tools.delegate import delegate_task as _delegate
            result = await _delegate(source_entity_id=entity_id, **args)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})

@router.post("/{entity_id}")
async def chat(entity_id: str, req: ChatRequest):
    """
    Chat with an LLM that has access to the entity's memory.
    Uses new ContextBuilder for rich context assembly.
    """
    import traceback
    try:
        print(f"🔥 DEBUG: Chat endpoint hit for entity {entity_id}")
        import litellm
        from api.chat_context import build_context, ChatMessage as ContextMessage

        print(f"🔥 DEBUG: 1. Fetching Configuration from PostgreSQL...")
        # 1. Fetch persona config from shared loader (single source of truth)
        from src.persona_config import aload_persona_config

        cfg = await aload_persona_config(
            entity_id,
            user_id=req.user_id or None,
            model_override=req.model or None,
            temperature_override=None,  # req.temperature handled below
        )

        # Apply persona values — request overrides take precedence
        model = cfg.model
        sys_prompt = req.system_prompt or cfg.system_prompt
        if req.temperature == 0.7 and cfg.temperature != 0.7:
            # Frontend sends 0.7 as default — use persona temp if different
            req.temperature = cfg.temperature
        top_p = cfg.top_p
        top_k = cfg.top_k
        frequency_penalty = cfg.frequency_penalty
        presence_penalty = cfg.presence_penalty

        # Sanitize sampling params for the target provider
        from src.persona_config import sanitize_sampling_params
        _sampling = sanitize_sampling_params(
            model, top_p=top_p, top_k=top_k,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )

        context_config = cfg.to_context_config()
        max_backfill = cfg.max_history_messages

        # Backfill History from PostgreSQL (if frontend sent few messages)
        pg_history = []
        try:
            if len(req.messages) < max_backfill:
                with get_session() as session:
                    print(f"🔥 PostgreSQL: Fetching global history backfill...")
                    recent_msgs = (
                        session.query(Message)
                        .join(Conversation)
                        .filter(Conversation.entity_id == entity_id)
                        .order_by(Message.timestamp.desc())
                        .limit(max_backfill)
                        .all()
                    )
                    for m in reversed(recent_msgs):
                        pg_history.append({
                            "role": "user" if m.sender_id == "user" else "assistant",
                            "content": m.content,
                            "timestamp": int(m.timestamp.timestamp() * 1000) if m.timestamp else 0
                        })
                    if pg_history:
                        print(f"✅ Loaded {len(pg_history)} messages from PostgreSQL history")
        except Exception as e:
            print(f"⚠️ History backfill failed: {e}")
            traceback.print_exc()

        print(f"🔥 DEBUG: 2. Building Context...")

        # 2. Build Context — merge history
        final_ctx_messages = []

        # PostgreSQL history (older)
        for msg in pg_history:
            role = msg['role']
            if role == 'model': role = 'assistant'
            final_ctx_messages.append(ContextMessage(
                role=role,
                content=msg['content'],
                timestamp=msg['timestamp']
            ))

        # Request messages (newer) — deduplicate against history
        if req.messages:
            for i, req_msg in enumerate(req.messages):
                is_duplicate = False
                if final_ctx_messages and i == 0:
                    last_hist = final_ctx_messages[-1]
                    if last_hist.content == req_msg.content:
                        is_duplicate = True
                if not is_duplicate:
                    role = req_msg.role
                    if role == 'model': role = 'assistant'
                    final_ctx_messages.append(ContextMessage(
                        role=role,
                        content=req_msg.content,
                        timestamp=req_msg.timestamp
                    ))

        # 1b. Phase 4 Imperfection Engine — gated: pro+
        friction_directives = ""
        active_friction_profile = None
        from src.edition import has_feature, Feature as EditionFeature
        if has_feature(EditionFeature.IMPERFECTION_ENGINE):
            try:
                with get_session() as session:
                    from src.services.imperfection_engine import resolve_friction, format_friction_directives

                    context_topic = ""
                    if final_ctx_messages and final_ctx_messages[-1].role == "user":
                        context_topic = final_ctx_messages[-1].text_content()[:100]

                    active_friction_profile = resolve_friction(session, entity_id, context_topic)
                    friction_directives = format_friction_directives(active_friction_profile)
            except Exception as e:
                print(f"⚠️ Friction Engine Failed: {e}")

        print(f"🔥 DEBUG: Calling build_context with {len(final_ctx_messages)} messages")
        context = build_context(
            entity_id=entity_id,
            user_id=req.user_id or "default",
            messages=final_ctx_messages,
            system_prompt=sys_prompt,
            config=context_config,
            friction_directives=friction_directives
        )
        print(f"🔥 DEBUG: Context built. Metadata: {context.metadata}")

        # Inject model name into dynamic preamble (alongside local time)
        # context.dynamic_preamble += f"Active Model: {model}\n"
        
        # 2. Assemble Final Prompt — structured for provider-level context caching
        #
        # HOW IMPLICIT CACHING WORKS:
        # - Gemini:  Automatically caches identical prompt prefixes (free storage)
        # - OpenAI:  Automatically caches identical prompt prefixes ≥1024 tokens (50% discount)
        # - Anthropic: Explicit cache_control breakpoints (90% read discount)
        # - Grok/Mistral: No caching yet, but prefix ordering still saves if they add it
        #
        # STRUCTURE: [stable system + warm memory] → [dynamic metadata] → [history]
        # The stable prefix (~12K tokens) is identical between requests → cached
        # Only dynamic metadata (~50 tokens) + new history messages are fresh input
        
        # Stable cacheable prefix: persona + warm memory + voice anchors + integrity frame
        stable_parts = [context.system_instruction, context.context_primer]
        if context.voice_anchors:
            stable_parts.append(context.voice_anchors)
        if context.integrity_frame:
            stable_parts.append(context.integrity_frame)
        stable_system = "\n\n".join(p for p in stable_parts if p)
        
        is_anthropic = any(x in model.lower() for x in ["claude", "anthropic"])
        
        combined_dynamic = context.dynamic_preamble
        if context.friction_directives:
            combined_dynamic += f"━━━ FRICTION DIRECTIVES ━━━\n{context.friction_directives}\n\n"
        
        if is_anthropic:
            # Anthropic: Use content blocks with explicit cache_control breakpoint
            # This marks the stable system content as cacheable
            final_messages = [{
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": stable_system,
                        "cache_control": {"type": "ephemeral"}
                    },
                    {
                        "type": "text",
                        "text": combined_dynamic
                    }
                ]
            }]
        else:
            # Gemini/OpenAI/others: Stable prefix first, dynamic metadata appended at end
            # Provider implicit caching matches longest identical prefix automatically
            final_system_msg = stable_system + "\n\n" + combined_dynamic
            final_messages = [{"role": "system", "content": final_system_msg}]
        
        final_messages.extend(context.history)

        print(f"🔥 DEBUG: 3. Preparing LLM Call (Streaming={req.stream})...")
        # 3. Prepare Litellm Args
        kwargs = {
            "model": model,
            "messages": final_messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": req.stream
        }
        # BYOK: inject user's API key if resolved from vault
        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key

        # Local models: inject api_base for Ollama / OpenAI-compatible servers
        _lower_model = model.lower()
        _is_local = _lower_model.startswith(("ollama_chat/", "ollama/"))
        if _is_local:
            from src.model_registry import OLLAMA_API_BASE
            kwargs["api_base"] = OLLAMA_API_BASE
        elif _lower_model.startswith("openai/") and not cfg.api_key:
            from src.model_registry import LOCAL_API_BASE
            if LOCAL_API_BASE:
                kwargs["api_base"] = LOCAL_API_BASE

        # Request usage stats in streaming mode (needed for cache hit detection)
        # Note: Gemini handles this automatically; OpenAI/Anthropic need the option
        # Local models (Ollama) don't support stream_options
        if req.stream and not "gemini" in _lower_model and not _is_local:
            kwargs["stream_options"] = {"include_usage": True}
        kwargs.update(_sampling)
        
        # Add model and config to context metadata for tracking
        context.metadata["model"] = model
        context.metadata["llm_config"] = {
            "temperature": req.temperature,
            **_sampling,
        }

        # Gemini safety settings — disable all content filters
        # ClingySOCKs handles emotional, relational, and intimate content
        # that default Gemini safety filters would incorrectly block
        if "gemini" in model.lower():
            kwargs["safety_settings"] = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
            ]
        
        # Add tools if enabled
        if req.tools_enabled:
            from src.tools.schemas import get_tool_schemas
            tools = get_tool_schemas()  # Edition-aware tool list
            
                
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            print(f"🔧 Tools enabled: {[t['function']['name'] for t in tools]}")

        target_chat_id = req.chat_id or str(uuid.uuid4())

        # ─── Debug Dump ───────────────────────────────────
        # Write full LLM payload to file for debugging
        try:
            import os as _os
            from datetime import datetime as _dt
            log_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "logs")
            _os.makedirs(log_dir, exist_ok=True)
            log_path = _os.path.join(log_dir, "llm_debug.log")

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"TIMESTAMP: {_dt.now().isoformat()}\n")
                f.write(f"ENTITY_ID: {entity_id}\n")
                f.write(f"CHAT_ID: {target_chat_id}\n")
                f.write(f"MODEL: {model}\n")
                f.write(f"TEMPERATURE: {req.temperature}\n")
                f.write(f"MAX_TOKENS: {req.max_tokens}\n")
                f.write(f"STREAM: {req.stream}\n")
                f.write(f"TOOLS_ENABLED: {req.tools_enabled}\n")

                # System prompt (from context builder)
                f.write(f"\n--- SYSTEM INSTRUCTION ---\n")
                f.write(context.system_instruction or "(empty)")
                f.write(f"\n--- CONTEXT PRIMER (warm memory — CACHEABLE) ---\n")
                f.write(context.context_primer or "(empty)")
                if context.voice_anchors:
                    f.write(f"\n\n--- VOICE ANCHORS (style examples — CACHEABLE) ---\n")
                    f.write(context.voice_anchors)
                if context.integrity_frame:
                    f.write(f"\n\n--- INTEGRITY FRAME (anti-sycophancy — CACHEABLE) ---\n")
                    f.write(context.integrity_frame)
                f.write(f"\n\n--- DYNAMIC PREAMBLE (timestamp/gap — NOT cached) ---\n")
                f.write(context.dynamic_preamble or "(empty)")

                # History messages
                f.write(f"\n\n--- HISTORY ({len(context.history)} messages) ---\n")
                for i, msg in enumerate(context.history):
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    # Truncate long messages for readability
                    preview = content[:500] + "..." if len(content) > 500 else content
                    f.write(f"  [{i}] {role}: {preview}\n")

                # Tools
                if kwargs.get("tools"):
                    tool_names = [t['function']['name'] for t in kwargs['tools']]
                    f.write(f"\n--- TOOLS ({len(tool_names)}) ---\n")
                    f.write(f"  {', '.join(tool_names)}\n")

                # Safety settings
                if kwargs.get("safety_settings"):
                    f.write(f"\n--- SAFETY SETTINGS ---\n")
                    for s in kwargs["safety_settings"]:
                        f.write(f"  {s['category']}: {s['threshold']}\n")

                # Context metadata
                f.write(f"\n--- CONTEXT METADATA ---\n")
                f.write(f"  {context.metadata}\n")
                f.write(f"{'='*80}\n")

            print(f"📝 Debug log written to {log_path}")
        except Exception as log_err:
            print(f"⚠️ Failed to write debug log: {log_err}")
        
        # Save USER message to database
        if req.messages:
            last_msg = req.messages[-1]
            if last_msg.role == "user":
                _save_message_to_db(entity_id, target_chat_id, "user", last_msg.text_content(), user_id=req.user_id, force_id=last_msg.id)

        # Save Phase 4 Shadow logs — gated: pro+
        if active_friction_profile and has_feature(EditionFeature.SHADOW_LOGS):
            _save_shadow_logs(entity_id, active_friction_profile)

        if req.stream:
            return _stream_response(entity_id, target_chat_id, kwargs, model, req.tools_enabled, context.metadata)
        else:
            return await _sync_response(entity_id, target_chat_id, kwargs, model, req.tools_enabled, context.metadata)

    except Exception as e:
        print(f"❌ CHAT ENDPOINT CRITICAL ERROR: {e}")
        traceback.print_exc()
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Critical Backend Error: {str(e)}")

# ─── Streaming Response (SSE) ────────────────────────

def _stream_response(entity_id: str, chat_id: str, kwargs: dict, model: str, tools_enabled: bool, context_metadata: Optional[dict] = None):
    """Stream chat completion via Server-Sent Events."""
    import litellm
    # litellm.set_verbose=True

    async def generate():
        # print(f"🔥 DEBUG: STREAM STARTED for {model}")
        try:
            # Initial event with metadata
            start_payload = {'type': 'start', 'model': model}
            if context_metadata:
                start_payload['context_metadata'] = context_metadata
            
            yield f"data: {json.dumps(start_payload)}\n\n"

            # print(f"🔥 DEBUG: Calling litellm.completion...")
            # stream=True is already in kwargs from caller
            response = await litellm.acompletion(**kwargs)
            # print(f"🔥 DEBUG: litellm.completion returned iterator")

            full_content = ""
            thinking_content = ""
            tool_calls_buffer: dict[int, dict] = {}
            stream_usage = None  # Capture usage from final stream chunk

            in_thought = False
            content_buffer = ""

            async for chunk in response:
                # Capture usage from streaming chunks (LiteLLM sends it in the last chunk)
                if hasattr(chunk, 'usage') and chunk.usage:
                    stream_usage = chunk.usage
                    
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                
                # Check for tool_calls specifically to debug signature
                if delta.tool_calls:
                     print(f"🔥 DEBUG: Tool Call delta: {delta}")

                # Thinking content (for models that support it)
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    thinking_content += delta.reasoning_content
                    yield f"data: {json.dumps({'type': 'thinking', 'content': delta.reasoning_content})}\n\n"

                # Regular content
                if delta.content:
                    c = delta.content
                    content_buffer += c
                    
                    while True:
                        if not in_thought:
                            if "<thought>" in content_buffer:
                                pre, post = content_buffer.split("<thought>", 1)
                                if pre:
                                    full_content += pre
                                    yield f"data: {json.dumps({'type': 'content', 'content': pre})}\n\n"
                                in_thought = True
                                content_buffer = post
                            elif "<" in content_buffer and content_buffer.rfind("<") > len(content_buffer) - 9:
                                pre = content_buffer[:content_buffer.rfind("<")]
                                if pre:
                                    full_content += pre
                                    yield f"data: {json.dumps({'type': 'content', 'content': pre})}\n\n"
                                content_buffer = content_buffer[content_buffer.rfind("<"):]
                                break
                            else:
                                full_content += content_buffer
                                yield f"data: {json.dumps({'type': 'content', 'content': content_buffer})}\n\n"
                                content_buffer = ""
                                break
                        else:
                            if "</thought>" in content_buffer:
                                pre, post = content_buffer.split("</thought>", 1)
                                if pre:
                                    thinking_content += pre
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': pre})}\n\n"
                                in_thought = False
                                content_buffer = post
                            elif "<" in content_buffer and content_buffer.rfind("<") > len(content_buffer) - 10:
                                pre = content_buffer[:content_buffer.rfind("<")]
                                if pre:
                                    thinking_content += pre
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': pre})}\n\n"
                                content_buffer = content_buffer[content_buffer.rfind("<"):]
                                break
                            else:
                                thinking_content += content_buffer
                                yield f"data: {json.dumps({'type': 'thinking', 'content': content_buffer})}\n\n"
                                content_buffer = ""
                                break

                # Tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id or f"call_{idx}",
                                "name": tc.function.name if tc.function and tc.function.name else "",
                                "arguments": "",
                                "thought_signature": None
                            }
                        if tc.function and tc.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc.function.arguments
                            
                        # Capture thought_signature for Gemini thinking models
                        # LiteLLM puts it in provider_specific_fields on the tool call delta
                        if hasattr(tc, 'provider_specific_fields') and tc.provider_specific_fields:
                            sig = tc.provider_specific_fields.get('thought_signature')
                            if sig:
                                tool_calls_buffer[idx]["thought_signature"] = sig
                                print(f"🔥 DEBUG: Captured thought_signature for tool call {idx}")

            # Flush remaining buffer
            if content_buffer:
                if in_thought:
                    thinking_content += content_buffer
                    yield f"data: {json.dumps({'type': 'thinking', 'content': content_buffer})}\n\n"
                else:
                    full_content += content_buffer
                    yield f"data: {json.dumps({'type': 'content', 'content': content_buffer})}\n\n"

            # ─── Multi-round tool call loop ─────────────────────
            # Fallback: some models (e.g. Mistral, older Llama) don't use the
            # structured tool_calls API in streaming mode — they emit the tool
            # call as a JSON object / array in the content field instead.
            # Detect that and re-route it so the tool actually executes.
            if not tool_calls_buffer and tools_enabled and full_content.strip():
                parsed_text_tc = _try_parse_text_tool_calls(full_content)
                if parsed_text_tc:
                    print(f"🔧 Text-encoded tool calls detected in content (model used text instead of structured API) — re-routing")
                    # Suppress the raw JSON from the chat window
                    yield f"data: {json.dumps({'type': 'content_replace', 'content': ''})}\n\n"
                    full_content = ""
                    for i, tc in enumerate(parsed_text_tc):
                        tool_calls_buffer[i] = {
                            "id": f"text_call_{i}",
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                            "thought_signature": None,
                        }

            # The model may chain tool calls (e.g. recall → write → respond).
            # We loop until the model produces content or hits MAX_TOOL_ROUNDS.
            MAX_TOOL_ROUNDS = 5
            all_tool_calls_log = []   # For DB save
            all_tool_results_log = [] # For DB save
            round_messages = list(kwargs["messages"])  # Running message list
            current_tc_buffer = dict(tool_calls_buffer)  # First round comes from initial stream
            round_num = 0

            while current_tc_buffer and tools_enabled and round_num < MAX_TOOL_ROUNDS:
                round_num += 1
                print(f"🔧 TOOL ROUND {round_num}: Processing {len(current_tc_buffer)} tool calls")

                # Execute tool calls for this round
                round_tool_results = []
                round_tc_payload = []
                round_thinking = thinking_content if round_num == 1 else ""

                for idx, tc in sorted(current_tc_buffer.items()):
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'arguments': tc['arguments']})}\n\n"

                    try:
                        args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    result = await execute_tool_call(entity_id, tc["name"], args)
                    round_tool_results.append({
                        "tool_call_id": tc["id"],
                        "role": "tool",
                        "content": result,
                    })
                    all_tool_results_log.append({"name": tc["name"], "result": result})

                    yield f"data: {json.dumps({'type': 'tool_result', 'name': tc['name'], 'result': result})}\n\n"

                # Build assistant message with tool calls for this round
                tc_payload = []
                for tc in current_tc_buffer.values():
                    func_data = {"name": tc["name"], "arguments": tc["arguments"]}
                    if tc.get("thought_signature"):
                        func_data["thought_signature"] = tc["thought_signature"]
                    tc_payload.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": func_data
                    })
                all_tool_calls_log.extend(tc_payload)

                # Build the assistant message for this round's follow-up
                assistant_msg = {
                    "role": "assistant",
                    "content": full_content or None,
                    "tool_calls": tc_payload
                }
                # Attach thinking/reasoning for Gemini thinking models
                sigs = [tc.get("thought_signature") for tc in current_tc_buffer.values() if tc.get("thought_signature")]
                if round_thinking or sigs:
                    psf = {}
                    if round_thinking:
                        psf["reasoning_content"] = round_thinking
                    if sigs:
                        psf["thought_signatures"] = sigs
                    assistant_msg["provider_specific_fields"] = psf

                # Append this round's messages to the running conversation
                round_messages.append(assistant_msg)
                round_messages.extend(round_tool_results)

                # Call the model for the next round (with tools still available for chaining)
                followup_kwargs = {**kwargs, "messages": round_messages, "stream": True}

                # On the last allowed round, strip tools so the model MUST produce text
                if round_num >= MAX_TOOL_ROUNDS - 1:
                    followup_kwargs.pop("tools", None)
                    followup_kwargs.pop("tool_choice", None)
                    print(f"⚠️ Round {round_num}: final round — tools removed, forcing text response")

                print(f"🔥 DEBUG: Round {round_num} follow-up — {len(round_messages)} messages, tools={'tools' in followup_kwargs}")

                followup_response = await litellm.acompletion(**followup_kwargs)

                # Stream the follow-up, collecting content + thinking + any new tool calls
                followup_content = ""
                followup_thinking = ""
                followup_in_thought = False
                followup_buf = ""
                new_tc_buffer: dict[int, dict] = {}
                fu_chunk_count = 0
                fu_finish_reason = None

                async for fu_chunk in followup_response:
                    fu_chunk_count += 1
                    choice = fu_chunk.choices[0] if fu_chunk.choices else None
                    if not choice:
                        continue
                    fu_delta = choice.delta
                    if choice.finish_reason:
                        fu_finish_reason = choice.finish_reason
                    if not fu_delta:
                        continue

                    # Debug first few chunks
                    if fu_chunk_count <= 3:
                        has_tc = bool(fu_delta.tool_calls)
                        has_content = bool(fu_delta.content)
                        has_reason = bool(hasattr(fu_delta, 'reasoning_content') and fu_delta.reasoning_content)
                        print(f"🔥 DEBUG: Round {round_num} chunk #{fu_chunk_count}: content={has_content}, reasoning={has_reason}, tool_calls={has_tc}, finish={choice.finish_reason}")

                    # Reasoning/thinking
                    if hasattr(fu_delta, 'reasoning_content') and fu_delta.reasoning_content:
                        followup_thinking += fu_delta.reasoning_content
                        thinking_content += fu_delta.reasoning_content
                        yield f"data: {json.dumps({'type': 'thinking', 'content': fu_delta.reasoning_content})}\n\n"

                    # Regular content with <thought> tag handling
                    if fu_delta.content:
                        followup_buf += fu_delta.content
                        while True:
                            if not followup_in_thought:
                                if "<thought>" in followup_buf:
                                    pre, post = followup_buf.split("<thought>", 1)
                                    if pre:
                                        followup_content += pre
                                        yield f"data: {json.dumps({'type': 'content', 'content': pre})}\n\n"
                                    followup_in_thought = True
                                    followup_buf = post
                                else:
                                    followup_content += followup_buf
                                    if followup_buf:
                                        yield f"data: {json.dumps({'type': 'content', 'content': followup_buf})}\n\n"
                                    followup_buf = ""
                                    break
                            else:
                                if "</thought>" in followup_buf:
                                    pre, post = followup_buf.split("</thought>", 1)
                                    if pre:
                                        thinking_content += pre
                                        yield f"data: {json.dumps({'type': 'thinking', 'content': pre})}\n\n"
                                    followup_in_thought = False
                                    followup_buf = post
                                else:
                                    thinking_content += followup_buf
                                    if followup_buf:
                                        yield f"data: {json.dumps({'type': 'thinking', 'content': followup_buf})}\n\n"
                                    followup_buf = ""
                                    break

                    # Accumulate new tool calls from this round's response
                    if fu_delta.tool_calls:
                        for tc in fu_delta.tool_calls:
                            idx = tc.index
                            if idx not in new_tc_buffer:
                                new_tc_buffer[idx] = {
                                    "id": tc.id or f"call_{round_num}_{idx}",
                                    "name": tc.function.name if tc.function and tc.function.name else "",
                                    "arguments": "",
                                    "thought_signature": None
                                }
                            if tc.function and tc.function.arguments:
                                new_tc_buffer[idx]["arguments"] += tc.function.arguments
                            if hasattr(tc, 'provider_specific_fields') and tc.provider_specific_fields:
                                sig = tc.provider_specific_fields.get('thought_signature')
                                if sig:
                                    new_tc_buffer[idx]["thought_signature"] = sig

                # Flush remaining buffer
                if followup_buf:
                    if followup_in_thought:
                        thinking_content += followup_buf
                        yield f"data: {json.dumps({'type': 'thinking', 'content': followup_buf})}\n\n"
                    else:
                        followup_content += followup_buf
                        yield f"data: {json.dumps({'type': 'content', 'content': followup_buf})}\n\n"

                full_content += followup_content
                print(f"🔥 DEBUG: Round {round_num} done — content: {len(followup_content)} chars, thinking: {len(followup_thinking)} chars, new_tools: {len(new_tc_buffer)}, chunks: {fu_chunk_count}, finish: {fu_finish_reason}")

                # Prepare next round (if the model made more tool calls)
                current_tc_buffer = new_tc_buffer
                # Update thinking for the next round's assistant message
                thinking_content_for_next = followup_thinking

            if round_num >= MAX_TOOL_ROUNDS and current_tc_buffer:
                print(f"⚠️ Hit MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}), forcing end with accumulated content")

            # ─── End of tool loop ────────────────────────────────

            # Done event
            print(f"🔥 DEBUG: STREAM DONE. Content len: {len(full_content)}, tool_rounds: {round_num if tool_calls_buffer else 0}")
            
            # ─── Cache Statistics ─────────────────────────────
            # Log provider-level context caching information from usage stats.
            # Each provider reports cache hits differently:
            #   Gemini:    usage.prompt_tokens_details.cached_tokens
            #   OpenAI:    usage.prompt_tokens_details.cached_tokens  
            #   Anthropic: usage.cache_read_input_tokens / cache_creation_input_tokens
            cache_info = {}
            if stream_usage:
                usage_dict = stream_usage if isinstance(stream_usage, dict) else (stream_usage.model_dump() if hasattr(stream_usage, 'model_dump') else {})
                
                # Anthropic-style cache fields
                cache_read = usage_dict.get("cache_read_input_tokens", 0)
                cache_creation = usage_dict.get("cache_creation_input_tokens", 0)
                
                # OpenAI/Gemini-style cache fields (nested in prompt_tokens_details)
                ptd = usage_dict.get("prompt_tokens_details") or {}
                if isinstance(ptd, dict):
                    cached_tokens = ptd.get("cached_tokens", 0)
                elif hasattr(ptd, 'cached_tokens'):
                    cached_tokens = ptd.cached_tokens or 0
                else:
                    cached_tokens = 0
                
                prompt_tokens = usage_dict.get("prompt_tokens", 0)
                completion_tokens = usage_dict.get("completion_tokens", 0)
                
                total_cached = cache_read + cached_tokens
                if total_cached > 0:
                    cache_pct = round(total_cached / max(prompt_tokens, 1) * 100, 1)
                    print(f"💰 CACHE HIT: {total_cached}/{prompt_tokens} prompt tokens cached ({cache_pct}%) — saving ~{cache_pct}% input cost")
                    cache_info = {"cached_tokens": total_cached, "prompt_tokens": prompt_tokens, "cache_pct": cache_pct}
                elif cache_creation > 0:
                    print(f"💰 CACHE WRITE: {cache_creation} tokens written to cache (will be cached on next request)")
                    cache_info = {"cache_creation_tokens": cache_creation, "prompt_tokens": prompt_tokens}
                else:
                    print(f"📊 Usage: {prompt_tokens} prompt + {completion_tokens} completion tokens (no cache data reported)")
            
            # Save ASSISTANT message to database
            _save_message_to_db(entity_id, chat_id, entity_id, full_content, 
                              tool_calls=all_tool_calls_log or None, 
                              tool_results=all_tool_results_log or None)
            
            done_payload = {'type': 'done', 'full_content': full_content, 'thinking': thinking_content or None}
            if cache_info:
                done_payload['cache_info'] = cache_info
            if stream_usage:
                usage_dict = stream_usage if isinstance(stream_usage, dict) else (stream_usage.model_dump() if hasattr(stream_usage, 'model_dump') else {})
                done_payload['usage'] = {
                    'prompt_tokens': usage_dict.get('prompt_tokens', 0),
                    'completion_tokens': usage_dict.get('completion_tokens', 0),
                    'total_tokens': usage_dict.get('total_tokens', 0),
                }
            yield f"data: {json.dumps(done_payload)}\n\n"

        except Exception as e:
            print(f"❌ STREAM ERROR: {e}")
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


# ─── Sync Response ───────────────────────────────────

async def _sync_response(entity_id: str, chat_id: str, kwargs: dict, model: str, tools_enabled: bool, metadata: Optional[dict] = None):
    """Non-streaming chat completion."""
    import litellm

    import re
    
    response = await litellm.acompletion(**kwargs)
    choice = response.choices[0]

    content = choice.message.content or ""
    thinking = getattr(choice.message, 'reasoning_content', None) or ""
    
    # Extract <thought> tags for models that output it in content
    thoughts = re.findall(r'<thought>(.*?)</thought>', content, flags=re.DOTALL)
    if thoughts:
        thinking += "\n\n".join(thoughts)
        content = re.sub(r'<thought>.*?</thought>', '', content, flags=re.DOTALL).strip()
    if '<thought>' in content:
        content = content.split('<thought>')[0].strip()
        
    if not thinking:
        thinking = None

    tool_call_results = []

    # Handle tool calls — multi-round loop (model may chain recall → write → respond)
    MAX_SYNC_ROUNDS = 5
    current_message = choice.message
    round_messages = list(kwargs["messages"])
    round_num = 0

    # Fallback: some models (Mistral etc.) output tool calls as JSON text in content
    if not current_message.tool_calls and tools_enabled and content.strip():
        parsed_text_tc = _try_parse_text_tool_calls(content)
        if parsed_text_tc:
            print(f"🔧 Sync: text-encoded tool calls detected — re-routing")
            content = ""
            for tc in parsed_text_tc:
                try:
                    args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
                except (json.JSONDecodeError, ValueError):
                    args = {}
                result = await execute_tool_call(entity_id, tc["name"], args)
                tool_call_results.append({
                    "name": tc["name"],
                    "arguments": args,
                    "result": json.loads(result),
                })
            if tool_call_results:
                tc_payload = [
                    {"id": f"text_call_{i}", "type": "function",
                     "function": {"name": tr["name"], "arguments": json.dumps(tr["arguments"])}}
                    for i, tr in enumerate(tool_call_results)
                ]
                round_messages.append({"role": "assistant", "content": None, "tool_calls": tc_payload})
                round_messages.extend([
                    {"role": "tool", "tool_call_id": f"text_call_{i}", "content": json.dumps(tr["result"])}
                    for i, tr in enumerate(tool_call_results)
                ])
                followup_kwargs = {**kwargs, "messages": round_messages, "stream": False}
                followup = await litellm.acompletion(**followup_kwargs)
                content = followup.choices[0].message.content or ""
                round_num = 1  # mark that we did a tool round

    while current_message.tool_calls and tools_enabled and round_num < MAX_SYNC_ROUNDS:
        round_num += 1
        print(f"🔧 SYNC TOOL ROUND {round_num}: {len(current_message.tool_calls)} tool calls")

        # Execute tool calls
        tool_raw_results = []
        for tc in current_message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result = await execute_tool_call(entity_id, tc.function.name, args)
            tool_raw_results.append(result)
            tool_call_results.append({
                "name": tc.function.name,
                "arguments": args,
                "result": json.loads(result),
            })

        # Build tool result messages
        followup_tool_messages = []
        for i, tc in enumerate(current_message.tool_calls):
            followup_tool_messages.append({"tool_call_id": tc.id, "role": "tool", "content": tool_raw_results[i]})

        # Reconstruct assistant message preserving provider_specific_fields
        assistant_msg = current_message.model_dump()
        for idx, tc in enumerate(current_message.tool_calls):
            if hasattr(tc, 'provider_specific_fields') and tc.provider_specific_fields:
                sig = tc.provider_specific_fields.get('thought_signature')
                if sig and "function" in assistant_msg["tool_calls"][idx]:
                    assistant_msg["tool_calls"][idx]["function"]["thought_signature"] = sig

        round_messages.append(assistant_msg)
        round_messages.extend(followup_tool_messages)

        # Follow-up call — keep tools available for chaining
        followup_kwargs = {**kwargs, "messages": round_messages, "stream": False}

        # On the last allowed round, strip tools so the model MUST produce text
        if round_num >= MAX_SYNC_ROUNDS - 1:
            followup_kwargs.pop("tools", None)
            followup_kwargs.pop("tool_choice", None)
            print(f"⚠️ Sync round {round_num}: final round — tools removed, forcing text response")

        followup = await litellm.acompletion(**followup_kwargs)
        current_message = followup.choices[0].message
        content = current_message.content or ""
        
        # For thinking models: if content is empty, check reasoning_content
        if not content and not current_message.tool_calls:
            followup_reasoning = getattr(current_message, 'reasoning_content', None)
            if followup_reasoning:
                import re as _re2
                content = _re2.sub(r'<thought>.*?</thought>', '', followup_reasoning, flags=_re2.DOTALL).strip()
                print(f"⚠️ Sync follow-up round {round_num}: used reasoning_content as fallback ({len(content)} chars)")

    if round_num > 0:
        # Save assistant message from tool follow-up
        _save_message_to_db(entity_id, chat_id, entity_id, content, tool_calls=tool_call_results, tool_results=tool_call_results)
    else:
        # Save simple assistant message
        _save_message_to_db(entity_id, chat_id, entity_id, content)

    return ChatResponse(
        content=content,
        thinking=thinking,
        tool_calls=tool_call_results,
        model=model,
        usage=response.usage.model_dump() if response.usage else None,
        context_metadata=metadata,
    )
