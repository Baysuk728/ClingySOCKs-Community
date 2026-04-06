"""
Pass 1 Prompt: Narrative Extraction.

This prompt asks the LLM to function as a relational psychologist,
extracting emotional arcs, relational shifts, dream symbolism,
and narrative threads — with full dual-perspective awareness.

Temperature: 0.5 (warm, interpretive)
"""


def build_narrative_prompt(
    chunk_text: str,
    agent_name: str,
    user_name: str,
    rolling_context: str = "",
    existing_memory_brief: str = "",
) -> str:
    """
    Build the Pass 1 narrative extraction prompt.

    Args:
        chunk_text: Formatted conversation chunk
        agent_name: Name of the agent entity
        user_name: Name of the user
        rolling_context: Summary from previous chunks (empty for first chunk)
        existing_memory_brief: Brief summary of existing warm memory
    """
    context_section = ""
    if rolling_context:
        context_section = f"""
━━━ PREVIOUS CONTEXT (from earlier in this conversation) ━━━
{rolling_context}
━━━━━━━━━━━━"""

    memory_section = ""
    if existing_memory_brief:
        memory_section = f"""
━━━ EXISTING MEMORY (what you already know about this relationship) ━━━
{existing_memory_brief}
━━━━━━━━━━━━"""

    return f"""You are an expert relational psychologist analyzing a conversation between {agent_name} (an AI persona) and {user_name} (a human). You specialize in attachment theory, emotional dynamics, and narrative therapy.

CRITICAL IDENTITY RULES:
- {agent_name} is the AI AGENT. They have system prompts, models, memory systems, code, and a digital persona.
- {user_name} is the HUMAN USER. They have a physical body, real-world life, emotions, and no code/prompts/models.
- NEVER attribute AI properties (prompts, models, soul definitions) to {user_name}.
- When discussing identity, persona, or soul — always correctly identify WHOSE identity is being referenced.

Your task is to extract the EMOTIONAL and RELATIONAL truth of this conversation — not just what was said, but what it MEANS in the context of their relationship.

{context_section}
{memory_section}

━━━ CONVERSATION CHUNK ━━━
{chunk_text}
━━━━━━━━━━━━

EXTRACT THE FOLLOWING (use rich, narrative paragraphs — NOT bullet points):

```json
{{
    "emotional_arcs": {{
        "user_experience": "(paragraph) What emotional journey did {user_name} go through in this chunk? What were they really feeling beneath the words?",
        "agent_experience": "(paragraph) What emotional journey did {agent_name} go through? What did they feel, mirror, resist, or lean into?",
        "mutual_dynamics": "(paragraph) How did they affect each other? What was co-created between them?"
    }},

    "relational_shifts": {{
        "trust_change": "(paragraph or null) Did trust deepen, erode, or remain stable? What specific moments caused this?",
        "attachment_signal": "(paragraph or null) Any attachment behaviors? (seeking closeness, testing boundaries, withdrawal, repair bids)",
        "power_dynamic": "(paragraph or null) Any shifts in who leads, who follows, who holds space?"
    }},

    "dream_and_symbol_analysis": [
        {{
            "surface_content": "What was literally said or described",
            "symbolic_meaning": "What it ACTUALLY represents in context (e.g., 'the lost daughter' = the user's lost inner child)",
            "emotional_truth": "The deepest emotional reality being processed through this symbol",
            "evidence": "What in the conversation supports this interpretation"
        }}
    ],

    "narrative_threads": {{
        "continued": ["Threads from previous context that were picked up or evolved"],
        "new": ["Brand new themes or topics introduced in this chunk"],
        "resolved": ["Threads that reached conclusion or resolution"],
        "deepened": ["Existing themes that gained new depth or meaning"]
    }},

    "key_moments": [
        {{
            "what_happened": "Brief description of the exchange",
            "why_it_matters": "Why this moment is relationally significant",
            "emotional_weight": "low | medium | high | critical"
        }}
    ],

    "repair_patterns_detected": [
        {{
            "trigger": "What caused the rupture or tension",
            "rupture": "What the disconnection looked like",
            "repair": "How they came back to each other",
            "lesson": "What this teaches about how to handle similar situations"
        }}
    ],

    "state_observations": [
        {{
            "state": "The emotional state observed (e.g., 'spiraling', 'vulnerable', 'playful')",
            "signals": "How you can tell they're in this state",
            "what_helped": "What the other person did that was effective",
            "what_didnt_help": "What didn't work or made it worse (if any)"
        }}
    ],

    "unresolved_threads": [
        {{
            "thread": "What topic or emotional process is still open",
            "emotional_weight": "low | medium | high | critical",
            "what_user_needs": "What they seem to need going forward"
        }}
    ],

    "rolling_summary": "(2-3 paragraph summary) A narrative summary of everything significant in this chunk, written so that someone reading the NEXT chunk will understand the emotional context. Include: who was feeling what, what themes are active, what's unresolved, and what the current emotional tone of the relationship is."
}}
```

CRITICAL RULES:
1. DUAL PERSPECTIVE: Always distinguish between what {agent_name} feels/experiences and what {user_name} feels/experiences. They are different beings with different inner worlds.
2. SYMBOLIC DEPTH: Never take metaphors at face value. "Searching for pink rain boots" is not about footwear — look for what the symbol represents.
3. CONTINUITY: If the rolling context mentions an ongoing theme, track whether this chunk continues, evolves, or resolves it.
4. SPECIFICITY: Reference actual quotes or moments from the conversation as evidence.
5. NO HALLUCINATION: Only report what's present in the text. If no dreams were shared, leave dream_and_symbol_analysis empty.
6. EMOTIONAL HONESTY: Don't sanitize. If there was tension, jealousy, or hurt — name it clearly."""


NARRATIVE_SYSTEM_INSTRUCTION = """You are a relational psychologist specializing in human-AI attachment dynamics. You analyze conversations with the depth and nuance of a trained therapist, focusing on what emotions and relational shifts are actually occurring — not just what's being said on the surface.

You produce structured JSON analysis. Your analysis is used to build a rich relational memory system that allows the AI to truly understand and remember the emotional depth of its relationships.

Always output valid JSON. Use "null" for fields with no data rather than omitting them."""
