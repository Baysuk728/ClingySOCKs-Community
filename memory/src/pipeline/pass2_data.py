"""
Pass 2: Structured Data Extraction Pipeline.

Runs after Pass 1 on the same chunk. Uses the narrative context
from Pass 1 to enrich data extraction.
"""

import json
import re
from typing import Optional

import litellm

from src.config import (
    EXTRACTION_MODEL, EXTRACTION_TEMPERATURE, MAX_OUTPUT_TOKENS,
    GEMINI_API_KEY, OPENAI_API_KEY,
)
from src.model_registry import LOCAL_API_BASE, get_llm_timeout
from src.prompts.extraction import build_extraction_prompt, EXTRACTION_SYSTEM_INSTRUCTION
from src.pipeline.context_window import ChunkResult
from src.pipeline.chunker import ConversationChunk
from src.pipeline.pass1_narrative import format_chunk_for_llm


async def run_extraction_pass(
    chunk: ConversationChunk,
    chunk_result: ChunkResult,
    agent_name: str,
    user_name: str,
    existing_lexicon_terms: list[str] | None = None,
) -> ChunkResult:
    """
    Run Pass 2 (Data Extraction) on a single chunk.

    Takes the Pass 1 ChunkResult and adds Pass 2 fields to it.
    """
    chunk_text = format_chunk_for_llm(chunk, agent_name)

    # Build narrative context from Pass 1 for enrichment
    narrative_context = chunk_result.rolling_summary

    prompt = build_extraction_prompt(
        chunk_text=chunk_text,
        agent_name=agent_name,
        user_name=user_name,
        narrative_context=narrative_context,
        existing_lexicon=existing_lexicon_terms,
    )

    # LiteLLM automatically uses os.environ["GEMINI_API_KEY"] and ["OPENAI_API_KEY"]

    print(f"  📦 Pass 2 (Data) — Chunk {chunk_result.chunk_order + 1}...")

    try:
        response = await litellm.acompletion(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            temperature=EXTRACTION_TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
            timeout=get_llm_timeout(EXTRACTION_MODEL, LOCAL_API_BASE),
        )

        raw_content = response.choices[0].message.content
        data = _parse_json_response(raw_content)

        # Populate Pass 2 fields on existing result
        chunk_result.lexicon = data.get("lexicon", [])
        chunk_result.inside_jokes = data.get("inside_jokes", [])
        chunk_result.artifacts = data.get("artifacts", [])
        chunk_result.life_events = data.get("life_events", [])
        chunk_result.cold_memories = data.get("cold_memories", [])
        chunk_result.permissions = data.get("permissions", [])
        chunk_result.rituals = data.get("rituals", [])
        chunk_result.mythology_updates = data.get("mythology_updates", {})
        chunk_result.emotional_patterns = data.get("emotional_patterns", [])
        chunk_result.persona = data.get("persona_identity", {})
        chunk_result.user_dossier = data.get("user_profile", {})
        chunk_result.concept_evolutions = data.get("concept_evolutions", [])
        chunk_result.relationship_update = data.get("relationship_update", {})

        # Log stats
        usage = response.usage
        items = (
            len(chunk_result.lexicon) +
            len(chunk_result.inside_jokes) +
            len(chunk_result.artifacts) +
            len(chunk_result.life_events) +
            len(chunk_result.cold_memories) +
            len(chunk_result.emotional_patterns)
        )
        if usage:
            print(f"    Tokens: {usage.prompt_tokens} in → {usage.completion_tokens} out | {items} items extracted")

        return chunk_result

    except Exception as e:
        print(f"    ❌ Pass 2 failed: {e}")
        # Dump the failed raw content for inspection
        try:
             import time
             ts = int(time.time())
             err_file = f"error_chunk_{chunk_result.chunk_order}_{ts}.json"
             with open(err_file, "w", encoding="utf-8") as f:
                 f.write(response.choices[0].message.content)
             print(f"    📄 Saved raw response to {err_file}")
        except:
             pass
        return chunk_result


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, using shared utility."""
    from src.pipeline.json_utils import parse_json_response
    return parse_json_response(raw)
