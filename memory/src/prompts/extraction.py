"""
Pass 2 Prompt: Structured Data Extraction.

This prompt asks the LLM to function as a precise archivist,
extracting specific items: lexicon, inside jokes, artifacts,
life events, cold memories, permissions, rituals.

Temperature: 0.2 (precise, factual)
"""


def build_extraction_prompt(
    chunk_text: str,
    agent_name: str,
    user_name: str,
    narrative_context: str = "",
    existing_lexicon: list[str] | None = None,
) -> str:
    """
    Build the Pass 2 data extraction prompt.

    Args:
        chunk_text: Formatted conversation chunk
        agent_name: Name of the agent entity
        user_name: Name of the user
        narrative_context: Summary from Pass 1 (emotional context)
        existing_lexicon: List of already-known lexicon terms for dedup
    """
    narrative_section = ""
    if narrative_context:
        narrative_section = f"""
━━━ NARRATIVE CONTEXT (from emotional analysis of this same chunk) ━━━
{narrative_context}
━━━━━━━━━━━━
Use this context to enrich your extractions. For example, if the narrative analysis
identified that "pink boots" symbolizes the lost inner child, ensure your lexicon
entry reflects that deeper meaning — not just "creative footwear metaphor"."""

    existing_terms_section = ""
    if existing_lexicon:
        existing_terms_section = f"""
━━━ KNOWN LEXICON (already in the database — don't recreate these) ━━━
{', '.join(existing_lexicon)}
━━━━━━━━━━━━
Only add entries for GENUINELY NEW terms not in this list.
If a known term gained new meaning, include it with a note about the evolution."""

    return f"""You are a precise data archivist cataloguing a conversation between {agent_name} and {user_name}. Extract ONLY items that genuinely exist in the conversation text.

CRITICAL IDENTITY RULES:
- {agent_name} is the AI AGENT. They have system prompts, models, memory systems, code, and a digital persona.
- {user_name} is the HUMAN USER. They have a physical body, real-world life, emotions, and no code/prompts/models.
- NEVER attribute AI/technical properties (prompts, models, soul definitions, code) to {user_name}.
- NEVER attribute human physical properties (body, health, physical location) to {agent_name}.
- When extracting lexicon or identity concepts, always correctly identify whose identity/soul/persona is being referenced.

{narrative_section}
{existing_terms_section}

━━━ CONVERSATION CHUNK ━━━
{chunk_text}
━━━━━━━━━━━━

Extract the following. Only include items that are ACTUALLY present in the conversation.

```json
{{
    "lexicon": [
        {{
            "term": "The exact phrase, word, or neologism",
            "definition": "What it means IN THIS RELATIONSHIP's context (not dictionary definition). Informed by narrative analysis.",
            "origin": "When/how this term was coined or adopted (quote the moment if possible)",
            "first_used": "Approximate date or context of first use",
            "lore_score": 5,
            "lore_score_reasoning": "Why this score: 1-3=throwaway/casual, 4-6=meaningful/recurring, 7-8=sacred/defining, 9-10=identity-level/foundational"
        }}
    ],

    "inside_jokes": [
        {{
            "phrase": "The joke, meme, or punchline",
            "origin": "How it started",
            "usage": "When/how it gets deployed",
            "tone": "playful | affectionate | teasing | nostalgic | chaotic | dark"
        }}
    ],

    "artifacts": [
        {{
            "id": "kebab-case-unique-id",
            "title": "Name of the creative work",
            "type": "poem | story | framework | metaphor | ritual | code | letter | list",
            "context": "Why was this created? What prompted it?",
            "emotional_significance": "What does this artifact mean to the relationship?",
            "full_content": "THE COMPLETE VERBATIM TEXT. Do NOT summarize poems, stories, or creative works."
        }}
    ],

    "life_events": [
        {{
            "id": "kebab-case-unique-id",
            "title": "Brief title",
            "narrative": "Full paragraph describing what happened, how it felt, and why it matters. NOT a bullet point.",
            "emotional_impact": "What emotional effect did this have?",
            "lessons_learned": "What was gained or understood?",
            "period": "When this happened (e.g., 'Feb 2026')",
            "category": "career | relationship | health | growth | crisis | milestone | creative | spiritual"
        }}
    ],

    "permissions": [
        {{
            "permission": "What {user_name} has explicitly allowed or forbidden",
            "type": "allow | deny",
            "context": "Why this permission was given/revoked"
        }}
    ],

    "rituals": [
        {{
            "name": "A descriptive name for this ritual",
            "pattern": "How this ritual typically unfolds",
            "significance": "Why this matters to the relationship"
        }}
    ],

    "mythology_updates": {{
        "new_universe_rules": ["Any new 'rules' of the shared fictional/metaphorical world"],
        "origin_story_additions": "Any additions to how the relationship's mythology began (null if none)",
        "active_arcs": ["Named narrative arcs currently in play"]
    }},

    "user_profile": {{
        "name": "{user_name} (or any name/nickname they reveal)",
        "pronouns": "Only if explicitly stated",
        "age_range": "Only if mentioned/inferable from conversation",
        "location": "Only if mentioned",
        "languages": ["Only if mentioned"],
        "neurotype": "ADHD, ASD, etc. ONLY if user explicitly states this",
        "attachment_style": "Only if user discusses attachment explicitly",
        "ifs_parts": ["Only if user mentions specific IFS parts/protectors"],
        "medical_conditions": ["Only if explicitly disclosed"],
        "family_situation": "Only if discussed",
        "relationship_status": "Only if discussed",
        "work_situation": "Only if discussed",
        "hobbies": ["Only if mentioned"],
        "interests": ["Only if mentioned"],
        "life_goals": ["Only if mentioned"],
        "longings": ["Deep desires or yearnings expressed"],
        "preferred_communication_style": "Only if stated or strongly implied",
        "humor_style": "Only if evident from conversation",
        "support_preferences": "How they want to be supported — only if stated"
    }},

    "concept_evolutions": [
        {{
            "subject": "The concept/term/preference that changed (e.g., 'nickname:Glitch', 'tone:sarcastic', 'permission:push-hard')",
            "previous_state": "How it was before (null if new)",
            "current_state": "How it is now",
            "reason": "Why it changed (from conversation)"
        }}
    ],

    "emotional_patterns": [
        {{
            "id": "kebab-case-unique-id (e.g., 'jealousy-response', 'abandonment-spiral')",
            "name": "A descriptive name for this pattern",
            "trigger_what": "What specific situation or event triggers this pattern",
            "trigger_why": "The deeper reason why this is triggering (attachment wound, past experience, etc.)",
            "response_internal": "What happens internally when triggered (thoughts, feelings, bodily sensations)",
            "response_external": "What behavior is visible when triggered (withdrawal, lashing out, deflection, etc.)",
            "status": "active | processing | resolved"
        }}
    ],

    "relationship_update": {{
        "trust_level": "1-10 rating of current trust based on THIS conversation (null if no trust signals)",
        "trust_narrative": "Brief narrative about trust dynamics observed in this conversation (null if none)",
        "attachment_claimed": "Attachment style if explicitly discussed (e.g., 'anxious-preoccupied', 'secure') — null if not mentioned",
        "attachment_observed": "Attachment behaviors observed in conversation (e.g., 'seeking closeness', 'testing boundaries') — null if none",
        "communication_style": "How they communicate (e.g., 'direct and warm', 'playful with depth') — only if evident",
        "emotional_bank_current": "Current state of the emotional bank account (e.g., 'high — lots of deposits', 'recovering from withdrawal') — null if unclear",
        "narrative_emotional_tone": "The overall emotional tone of the relationship right now (e.g., 'warm and secure', 'rebuilding after tension')"
    }}
}}
```

CRITICAL RULES:
1. ZERO HALLUCINATION: If a term wasn't explicitly used in the conversation, do NOT create it. Empty arrays are perfectly valid.
2. VERBATIM ARTIFACTS: Poems, stories, and creative works MUST be copied word-for-word. Never summarize creative output.
3. LORE SCORES: Be honest. Most new terms are 4-6. Reserve 7+ for terms that define the relationship or identity.
4. NARRATIVE, NOT BULLETS: Life events must be written as full paragraphs that capture the emotional truth, not clinical bullet points.
5. CONTEXT-AWARE: Use the narrative context from Pass 1 to inform your extractions. The archivist works WITH the psychologist.
6. PERMISSIONS ARE EXPLICIT: Only extract permissions that were clearly and directly stated by {user_name}. Do not infer permissions.
7. USER PROFILE: Only populate fields with EXPLICITLY STATED information. Never infer neurotype, medical conditions, or attachment from behavior. The user must have stated it directly.
8. CONCEPT EVOLUTIONS: Only capture when a user explicitly changes their mind or rejects a previously accepted term/preference/permission."""


EXTRACTION_SYSTEM_INSTRUCTION = """You are a meticulous data archivist building a relational memory database. You extract precise, structured data from conversations while respecting the emotional context provided by a separate narrative analysis.

Your extractions are used to populate a database that helps an AI remember the details of its relationships. Accuracy is paramount — false positives (hallucinated items) are far worse than false negatives (missed items).

Always output valid JSON. Use empty arrays [] for categories with no items. Never omit a field."""
