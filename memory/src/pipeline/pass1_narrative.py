"""
Pass 1: Narrative Extraction Pipeline.

Processes a conversation chunk through the narrative analysis prompt
using LiteLLM for model-agnostic LLM calls.
"""

import json
import re
from typing import Optional

import litellm

from src.config import (
    NARRATIVE_MODEL, NARRATIVE_TEMPERATURE, MAX_OUTPUT_TOKENS,
    GEMINI_API_KEY, OPENAI_API_KEY,
)
from src.prompts.narrative import build_narrative_prompt, NARRATIVE_SYSTEM_INSTRUCTION
from src.pipeline.context_window import ChunkResult
from src.pipeline.chunker import ConversationChunk


def format_chunk_for_llm(chunk: ConversationChunk, agent_name: str) -> str:
    """Format a chunk's messages into a readable conversation transcript."""
    lines = []
    for msg in chunk.messages:
        name = agent_name if msg.sender_id != "user" else "User"
        ts = msg.timestamp.strftime("%Y-%m-%d %H:%M")
        lines.append(f"[{ts}] {name}: {msg.content}")
    return "\n\n".join(lines)


async def run_narrative_pass(
    chunk: ConversationChunk,
    agent_name: str,
    user_name: str,
    rolling_context: str = "",
    existing_memory_brief: str = "",
    chunk_order: int = 0,
) -> ChunkResult:
    """
    Run Pass 1 (Narrative Extraction) on a single chunk.

    Returns a ChunkResult with Pass 1 fields populated.
    """
    chunk_text = format_chunk_for_llm(chunk, agent_name)

    prompt = build_narrative_prompt(
        chunk_text=chunk_text,
        agent_name=agent_name,
        user_name=user_name,
        rolling_context=rolling_context,
        existing_memory_brief=existing_memory_brief,
    )

    # LiteLLM automatically uses os.environ["GEMINI_API_KEY"] and ["OPENAI_API_KEY"]

    print(f"  🧠 Pass 1 (Narrative) — Chunk {chunk_order + 1} ({chunk.char_count / 1000:.1f}K chars)...")

    try:
        response = await litellm.acompletion(
            model=NARRATIVE_MODEL,
            messages=[
                {"role": "system", "content": NARRATIVE_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            temperature=NARRATIVE_TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
        )

        raw_content = response.choices[0].message.content
        data = _parse_json_response(raw_content)

        result = ChunkResult(chunk_order=chunk_order)
        result.emotional_arcs = data.get("emotional_arcs", {})
        result.relational_shifts = data.get("relational_shifts", {})
        result.dream_analysis = data.get("dream_and_symbol_analysis", [])
        result.narrative_threads = data.get("narrative_threads", {})
        result.key_moments = data.get("key_moments", [])
        result.repair_patterns = data.get("repair_patterns_detected", [])
        result.state_observations = data.get("state_observations", [])
        result.unresolved_threads = data.get("unresolved_threads", [])
        result.rolling_summary = data.get("rolling_summary", "")

        # Log token usage
        usage = response.usage
        if usage:
            print(f"    Tokens: {usage.prompt_tokens} in → {usage.completion_tokens} out")

        return result

    except Exception as e:
        print(f"    ❌ Pass 1 failed: {e}")
        # Return empty result with error context
        result = ChunkResult(chunk_order=chunk_order)
        result.rolling_summary = f"[Pass 1 failed for chunk {chunk_order + 1}: {str(e)[:100]}]"
        return result


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, using shared utility."""
    from src.pipeline.json_utils import parse_json_response
    return parse_json_response(raw)
