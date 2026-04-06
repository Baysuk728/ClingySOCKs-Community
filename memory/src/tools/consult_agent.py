"""
consult_agent tool — enables inter-agent communication.

Allows one agent to ask another agent a question, with the target agent
receiving the question enriched with their own persona/memory context.
The target responds in a single turn (no tool calls) to keep consultation
lightweight and avoid recursive agent loops.
"""

import json
import uuid
from datetime import datetime, timezone

import litellm

from src.db.session import get_session
from src.db.models import AgentMessage, Entity
from src.persona_config import aload_persona_config


# Maximum tokens for a consultation response (keep it concise)
CONSULT_MAX_TOKENS = 2048

# System frame for the consulted agent
CONSULT_SYSTEM_FRAME = """You are being consulted by a peer agent ({source_name}) who wants your perspective.

Answer their question using your own knowledge, personality, and memory context.
Be concise but thorough. This is a single-turn consultation — give your best answer now.

The question comes from a conversation context, but respond as yourself with your own voice."""


async def consult_agent(
    source_entity_id: str,
    target_entity_id: str,
    question: str,
    share_context: bool = True,
    conversation_context: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    """
    Execute a consult_agent tool call.

    Args:
        source_entity_id: The agent asking the question
        target_entity_id: The agent being consulted
        question: The question to ask
        share_context: Whether to include source's conversation context
        conversation_context: Brief summary of the source's current conversation (if share_context)
        conversation_id: The conversation this consultation originated from

    Returns:
        dict with 'response', 'target_name', and metadata
    """
    # Validate target exists
    with get_session() as session:
        target_entity = session.get(Entity, target_entity_id)
        if not target_entity:
            return {"error": f"Agent '{target_entity_id}' not found."}

        source_entity = session.get(Entity, source_entity_id)
        source_name = source_entity.name if source_entity else source_entity_id
        target_name = target_entity.name
        target_owner = target_entity.owner_user_id

    # Load target agent's full config (persona, model, memory context)
    target_cfg = await aload_persona_config(target_entity_id, user_id=target_owner)

    # Build the target agent's context
    from api.chat_context import build_context, ChatMessage as ContextMessage

    target_context = build_context(
        entity_id=target_entity_id,
        user_id=target_owner,
        messages=[],  # No conversation history for consultation
        system_prompt=target_cfg.system_prompt,
        config=target_cfg.to_context_config(),
    )

    # Assemble the system prompt with warm memory
    stable_parts = [target_context.system_instruction, target_context.context_primer]
    if target_context.voice_anchors:
        stable_parts.append(target_context.voice_anchors)
    stable_system = "\n\n".join(p for p in stable_parts if p)

    consult_frame = CONSULT_SYSTEM_FRAME.format(source_name=source_name)
    full_system = f"{stable_system}\n\n{consult_frame}"

    # Build the question message
    question_content = question
    if share_context and conversation_context:
        question_content = (
            f"[Context from my current conversation: {conversation_context}]\n\n"
            f"My question: {question}"
        )

    messages = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": question_content},
    ]

    # Call the target agent's LLM (single turn, no tools, no streaming)
    kwargs = {
        "model": target_cfg.model,
        "messages": messages,
        "temperature": target_cfg.temperature,
        "max_tokens": CONSULT_MAX_TOKENS,
        "stream": False,
    }
    if target_cfg.api_key:
        kwargs["api_key"] = target_cfg.api_key

    # Sanitize sampling params
    from src.persona_config import sanitize_sampling_params
    sampling = sanitize_sampling_params(
        target_cfg.model,
        top_p=target_cfg.top_p,
        top_k=target_cfg.top_k,
        frequency_penalty=target_cfg.frequency_penalty,
        presence_penalty=target_cfg.presence_penalty,
    )
    kwargs.update(sampling)

    # Gemini safety settings
    if "gemini" in target_cfg.model.lower():
        kwargs["safety_settings"] = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
        ]

    try:
        response = await litellm.acompletion(**kwargs)
        agent_response = response.choices[0].message.content or ""
    except Exception as e:
        return {"error": f"Consultation failed: {str(e)}"}

    # Log the inter-agent exchange
    question_msg_id = str(uuid.uuid4())
    response_msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    try:
        with get_session() as session:
            # Log the question
            session.add(AgentMessage(
                id=question_msg_id,
                conversation_id=conversation_id,
                from_entity_id=source_entity_id,
                to_entity_id=target_entity_id,
                content=question,
                message_type="consult",
                created_at=now,
            ))
            # Log the response
            session.add(AgentMessage(
                id=response_msg_id,
                conversation_id=conversation_id,
                from_entity_id=target_entity_id,
                to_entity_id=source_entity_id,
                content=agent_response,
                message_type="response",
                in_response_to=question_msg_id,
                created_at=now,
            ))
            session.commit()
    except Exception as e:
        print(f"⚠️ Failed to log agent message: {e}")

    return {
        "response": agent_response,
        "target_name": target_name,
        "target_entity_id": target_entity_id,
        "consultation_id": question_msg_id,
    }
