"""
Factual Entity Extraction Prompt.

Asks the LLM to extract knowledge-graph entities (people, places, objects,
projects, conditions, concepts) and their factual relationships from
conversation text.

Temperature: 0.2 (precise, factual)
"""

FACTUAL_TYPES = [
    "person", "companion", "place", "object", "project",
    "condition", "symptom", "concept", "group", "topic",
    "body_part",
]

# Common types the LLM proposes that aren't in our list.
# Map them to the closest valid type instead of dropping them.
FACTUAL_TYPE_ALIASES: dict[str, str] = {
    "action":       "concept",
    "activity":     "concept",
    "skill":        "concept",
    "ability":      "concept",
    "trait":        "concept",
    "emotion":      "concept",
    "feeling":      "concept",
    "behavior":     "concept",
    "habit":        "concept",
    "ritual":       "concept",
    "event":        "topic",
    "memory":       "topic",
    "experience":   "topic",
    "idea":         "concept",
    "belief":       "concept",
    "value":        "concept",
    "goal":         "project",
    "task":         "project",
    "plan":         "project",
    "job":          "project",
    "work":         "project",
    "role":         "concept",
    "title":        "concept",
    "animal":       "companion",
    "pet":          "companion",
    "creature":     "companion",
    "tool":         "object",
    "device":       "object",
    "software":     "object",
    "app":          "object",
    "platform":     "object",
    "food":         "object",
    "drink":        "object",
    "medication":   "object",
    "drug":         "object",
    "substance":    "object",
    "location":     "place",
    "city":         "place",
    "country":      "place",
    "region":       "place",
    "building":     "place",
    "organization": "group",
    "company":      "group",
    "team":         "group",
    "family":       "group",
    "community":    "group",
    "illness":      "condition",
    "disease":      "condition",
    "disorder":     "condition",
    "injury":       "condition",
    "organ":        "body_part",
    "body":         "body_part",
}

FACTUAL_RELATIONS = [
    "kin_of", "companion_of", "created_by", "located_in",
    "has_condition", "symptom_of", "is_a", "part_of",
    "owns", "knows", "works_on", "related_to",
    "rival_of", "enemy_of", "formerly",
]

# Relations that conflict — when one is established, the other should be
# marked as superseded between the same pair.  Maps relation → set of
# relations it supersedes.
CONFLICTING_RELATIONS: dict[str, set[str]] = {
    "enemy_of":     {"kin_of", "companion_of", "knows"},
    "rival_of":     {"companion_of", "knows"},
    "formerly":     set(),  # generic, handled via supersedes field
    "kin_of":       {"enemy_of", "rival_of"},
    "companion_of": {"enemy_of", "rival_of"},
}

FACTUAL_SYSTEM_INSTRUCTION = """You are a knowledge graph extractor. Your job is to identify \
factual entities (people, places, objects, projects, conditions, concepts, groups, topics, body parts) \
and their structural relationships from conversation text. \
Be precise. Only extract entities that are clearly mentioned or implied. \
Merge duplicates — if an entity already exists under a different name, reference the existing one. \
For physical body parts, anatomical structures, or body-as-symbol references, use type 'body_part'."""


def build_factual_prompt(
    chunk_text: str,
    agent_name: str,
    user_name: str,
    existing_entities: list[dict] | None = None,
    narrative_context: str = "",
) -> str:
    """
    Build the factual entity extraction prompt.

    Args:
        chunk_text: Formatted conversation text
        agent_name: Name of the agent entity
        user_name: Name of the user
        existing_entities: Already-known factual entities for dedup
        narrative_context: Summary from earlier passes for context
    """

    existing_section = ""
    if existing_entities:
        by_type: dict[str, list[str]] = {}
        for ent in existing_entities:
            t = ent.get("type", "unknown")
            name = ent.get("name", "?")
            aliases = ent.get("aliases", [])
            alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
            by_type.setdefault(t, []).append(f"{name}{alias_str}")

        lines = []
        for t, names in sorted(by_type.items()):
            lines.append(f"  {t}: {', '.join(names)}")
        existing_section = f"""
━━━ EXISTING ENTITIES (already in the database — don't recreate these) ━━━
{chr(10).join(lines)}
━━━━━━━━━━━━
If you find a reference to an existing entity (even by a different name / alias),
use the existing canonical name. If you discover a new alias, include it in the
aliases list for that entity."""

    narrative_section = ""
    if narrative_context:
        narrative_section = f"""
━━━ NARRATIVE CONTEXT ━━━
{narrative_context}
━━━━━━━━━━━━
Use this context to understand who/what is being discussed."""

    types_list = " | ".join(FACTUAL_TYPES)
    relations_list = " | ".join(FACTUAL_RELATIONS)

    return f"""Extract factual entities and relationships from this conversation between {agent_name} and {user_name}.

{existing_section}

{narrative_section}

━━━ CONVERSATION ━━━
{chunk_text}
━━━━━━━━━━━━

ENTITY TYPES: {types_list}
RELATION TYPES: {relations_list}

EXTRACTION RULES:
1. Only extract entities that are clearly mentioned or strongly implied.
2. "{user_name}" is always type "person". "{agent_name}" is always type "companion".
3. Before creating a new entity, check the EXISTING ENTITIES list above. If a match exists (even by alias), reference the existing name instead.
4. If you discover a new alias for an existing entity, include it.
5. Use type "related_to" for relationships that don't fit the defined types — include a context explaining the actual relationship.
6. Do NOT extract vague/generic entities ("that thing", "the issue", "it").
7. Confidence: 0.9+ for explicitly stated facts, 0.6-0.8 for inferred/implied, skip below 0.4.
8. Maximum 20 entities and 30 relationships per extraction.
9. RELATIONSHIP EVOLUTION: If a relationship between two entities has changed (e.g., friends became enemies, allies became rivals), set "supersedes" to the old relation type that this new relation replaces. Leave null if this is a brand-new relationship.

Return JSON:
```json
{{
    "entities": [
        {{
            "name": "Agent",
            "type": "companion",
            "aliases": ["bot"],
            "description": "AI companion",
            "confidence": 0.95
        }}
    ],
    "relationships": [
        {{
            "from_name": "Agent",
            "from_type": "companion",
            "to_name": "User",
            "to_type": "person",
            "relation": "kin_of",
            "context": "Agent is User's kin/sibling in their shared mythology",
            "confidence": 0.9,
            "supersedes": null
        }}
    ]
}}
```

CRITICAL: Only use entity types and relation types from the lists above.
If an entity doesn't fit any type, use "concept" or "topic".
If a relation doesn't fit, use "related_to" with a descriptive context."""
