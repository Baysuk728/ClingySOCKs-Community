"""
Synthesizer: Post-Merge Narrative Unification.

After all chunks are processed via Pass 1 + Pass 2,
the synthesizer produces unified narratives, deduplicates
items, and detects narrative arcs.
"""

import json
import re

import litellm

from src.config import (
    SYNTHESIS_MODEL, NARRATIVE_TEMPERATURE, MAX_OUTPUT_TOKENS,
    GEMINI_API_KEY, OPENAI_API_KEY,
)
from src.prompts.synthesis import build_synthesis_prompt, SYNTHESIS_SYSTEM_INSTRUCTION
from src.pipeline.context_window import ContextWindow


async def run_synthesis(
    context_window: ContextWindow,
    existing_narratives: dict[str, str],
    agent_name: str,
    user_name: str,
) -> dict:
    """
    Run post-merge synthesis on all chunk results.

    This is the final LLM pass that:
    - Unifies chunk narratives into coherent scope-based narratives
    - Deduplicates life events and lexicon
    - Detects narrative arcs

    Returns the synthesis result dict.
    """
    print(f"\n🔮 Running Synthesis Pass ({context_window.chunk_count} chunks)...")

    chunk_narratives = context_window.get_all_rolling_summaries()
    all_events = context_window.get_all_life_events()
    all_lexicon = context_window.get_all_lexicon()

    # Don't run synthesis if there's nothing to synthesize
    if not chunk_narratives:
        print("   ℹ️ No narratives to synthesize")
        return {}

    # For single chunk (no merge needed), just format the results
    if context_window.chunk_count == 1:
        print("   ℹ️ Single chunk — skipping synthesis LLM call")
        # Use a truncated version of the narrative as the bridge
        bridge_text = chunk_narratives[0][:500] if chunk_narratives[0] else None
        return {
            "narratives": {
                "recent": chunk_narratives[0],
                "seasonal": None,
                "lifetime": None,
                "bridge": bridge_text,
            },
            "deduplicated_events": [],
            "deduplicated_lexicon": [],
            "detected_arcs": [],
            "mythology_synthesis": {},
        }

    prompt = build_synthesis_prompt(
        chunk_narratives=chunk_narratives,
        all_life_events=all_events,
        all_lexicon=all_lexicon,
        existing_narratives=existing_narratives,
        agent_name=agent_name,
        user_name=user_name,
    )

    # LiteLLM automatically uses os.environ["GEMINI_API_KEY"] and ["OPENAI_API_KEY"]

    try:
        response = await litellm.acompletion(
            model=SYNTHESIS_MODEL,
            messages=[
                {"role": "system", "content": SYNTHESIS_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            temperature=NARRATIVE_TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
        )

        raw_content = response.choices[0].message.content
        data = _parse_json_response(raw_content)

        usage = response.usage
        if usage:
            print(f"   Synthesis tokens: {usage.prompt_tokens} in → {usage.completion_tokens} out")

        arcs = data.get("detected_arcs", [])
        dedup_events = data.get("deduplicated_events", [])
        dedup_lexicon = data.get("deduplicated_lexicon", [])
        print(f"   ✅ Synthesis: {len(arcs)} arcs detected, {len(dedup_events)} event merges, {len(dedup_lexicon)} lexicon merges")

        return data

    except Exception as e:
        print(f"   ❌ Synthesis failed: {e}")
        return {
            "narratives": {
                "recent": chunk_narratives[-1] if chunk_narratives else "",
                "seasonal": None,
                "lifetime": None,
            },
            "deduplicated_events": [],
            "deduplicated_lexicon": [],
            "detected_arcs": [],
        }


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, using shared utility."""
    from src.pipeline.json_utils import parse_json_response
    return parse_json_response(raw)
