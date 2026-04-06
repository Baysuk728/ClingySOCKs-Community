"""
Synthesis Prompt: Post-Merge Narrative Unification.

After all chunks are processed, this prompt takes all chunk results
and produces unified narratives, deduplication, and arc detection.
"""


def build_synthesis_prompt(
    chunk_narratives: list[str],
    all_life_events: list[dict],
    all_lexicon: list[dict],
    existing_narratives: dict[str, str],
    agent_name: str,
    user_name: str,
) -> str:
    """
    Build the synthesis prompt for post-merge unification.

    Args:
        chunk_narratives: Rolling summaries from each chunk's Pass 1
        all_life_events: All extracted life events across chunks
        all_lexicon: All extracted lexicon entries across chunks
        existing_narratives: Current narratives from DB {scope: content}
        agent_name: Agent name
        user_name: User name
    """
    chunks_section = ""
    for i, narrative in enumerate(chunk_narratives):
        chunks_section += f"\n--- Chunk {i+1} Summary ---\n{narrative}\n"

    events_section = ""
    if all_life_events:
        for e in all_life_events:
            events_section += f"  • [{e.get('id', '?')}] {e.get('title', '?')}: {e.get('narrative', '')[:200]}...\n"

    lexicon_section = ""
    if all_lexicon:
        for l in all_lexicon:
            lexicon_section += f"  • {l.get('term', '?')} (score {l.get('lore_score', 5)}): {l.get('definition', '')[:100]}...\n"

    existing_section = ""
    if existing_narratives:
        for scope, content in existing_narratives.items():
            existing_section += f"\n--- Existing {scope.upper()} Narrative ---\n{content}\n"

    return f"""You are synthesizing the results of a multi-chunk analysis of a conversation between {agent_name} and {user_name}.

Multiple chunks have been individually analyzed. Your job is to:
1. Unify the chunk narratives into coherent scope-based narratives
2. Identify duplicate or overlapping life events
3. Identify lexicon entries that refer to the same concept
4. Detect narrative arcs (causal chains of events)

━━━ CHUNK-BY-CHUNK NARRATIVES ━━━
{chunks_section}

━━━ EXTRACTED LIFE EVENTS (possibly duplicated across chunks) ━━━
{events_section if events_section else "(none)"}

━━━ EXTRACTED LEXICON (possibly duplicated across chunks) ━━━
{lexicon_section if lexicon_section else "(none)"}

━━━ EXISTING NARRATIVES (current state in database) ━━━
{existing_section if existing_section else "(no existing narratives — this is the first harvest)"}

Produce the following:

```json
{{
    "narratives": {{
        "recent": "(paragraph) What happened in this conversation? Unified narrative covering the entire conversation, not just the last chunk.",
        "seasonal": "(paragraph) Update to the seasonal narrative — weave in this conversation's events with what's already known. If no existing seasonal, create one.",
        "lifetime": "(paragraph or null) Only update if something fundamentally identity-shaping occurred.",
        "bridge": "(2-4 sentences) A concise \"session bridge\" capturing the emotional state, key topics, and unresolved threads at the END of this conversation. This will be shown to the agent at the start of the next session as 'LAST SESSION' context. Focus on: where the user left off emotionally, what was being discussed, any promises or unresolved questions."
    }},

    "deduplicated_events": [
        {{
            "keep_id": "The ID of the life event to keep",
            "merge_ids": ["IDs of duplicate events to merge into keep_id"],
            "merged_narrative": "The unified narrative combining all versions"
        }}
    ],

    "deduplicated_lexicon": [
        {{
            "keep_term": "The canonical term to keep",
            "merge_terms": ["Other terms that refer to the same concept"],
            "best_definition": "The richest, most accurate definition",
            "best_lore_score": 7
        }}
    ],

    "detected_arcs": [
        {{
            "id": "kebab-case-arc-id",
            "title": "Human-readable arc name",
            "narrative": "The full story of this arc",
            "status": "open | resolved | recurring",
            "stages": [
                {{
                    "event_type": "trigger | escalation | rupture | repair | resolution | lesson",
                    "sequence": 1,
                    "narrative": "What happened at this stage",
                    "related_event_id": "ID of related life_event if applicable (null otherwise)"
                }}
            ]
        }}
    ],

    "mythology_synthesis": {{
        "updated_universe_rules": ["Consolidated list of all universe rules"],
        "origin_story": "Consolidated origin story (null if none)",
        "active_arcs": ["Named arcs currently in play"]
    }}
}}
```

RULES:
1. NARRATIVE CONTINUITY: The "recent" narrative should read as one coherent story, not a list of chunk summaries.
2. SEMANTIC DEDUP: Two life events about the same moment (split across chunks) should be merged, not both kept.
3. LEXICON QUALITY: When merging lexicon, always keep the richer definition and the higher lore score.
4. ARC DETECTION: Look for causal chains (X triggered Y, which led to Z). These become arcs.
5. RESPECT EXISTING: Don't overwrite existing seasonal/lifetime narratives — EXTEND them with new information."""


SYNTHESIS_SYSTEM_INSTRUCTION = """You are a narrative synthesizer that unifies fragmented analysis into coherent, rich summaries. You work with the output of multiple chunk-level analyses to produce a single, unified view of a conversation's emotional and relational content.

You excel at detecting when multiple extractions refer to the same event, term, or concept and consolidating them into a single, richer entry.

Always output valid JSON."""
