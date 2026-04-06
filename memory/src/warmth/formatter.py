"""
Warm Memory Formatter.

Takes the sections dict from builder.py and assembles
a formatted string for system prompt injection.
"""

from typing import Literal

from src.warmth.builder import WarmLevel, LEVEL_BUDGETS


# Section display order and labels
# ORDER MATTERS: formatter truncates from bottom when over budget.
# Critical sections (identity, user, narrative) go first to survive pressure.
SECTION_CONFIG = {
    "persona":             "🔮 IDENTITY",
    "active_preferences":  "🎭 MY OPINIONS",
    "user_profile":        "👤 ABOUT THE USER",
    "session_bridge":      "🌉 LAST SESSION",
    "memory_blocks":       "📝 AGENT NOTES",
    "recent_narrative":    "📖 RECENT STORY",
    "active_threads":      "🧵 OPEN THREADS",
    "inside_jokes":        "😂 INSIDE JOKES",
    "lexicon":             "📜 SACRED LEXICON",
    "permissions":         "🔐 PERMISSIONS",
    "relationship":        "💫 RELATIONSHIP",
    "recent_events":       "📅 RECENT EVENTS",
    "emotional_patterns":  "🌀 EMOTIONAL PATTERNS",
    "echo_dream":          "🌙 LAST DREAM",
    "intimate_moments":    "✨ KEY MOMENTS",
    "rituals":             "🕯️ RITUALS",
    "mythology":           "🐉 SHARED MYTHOLOGY",
    "seasonal_narrative":  "🌿 SEASONAL ARC",
    "lifetime_narrative":  "⏳ LIFETIME ARC",
    "state_needs":         "🫂 WHAT THEY NEED",
    "repair_patterns":     "🩹 REPAIR PATTERNS",
    "artifacts":           "🎨 ARTIFACTS",
}


def format_warm_memory(
    sections: dict,
    level: WarmLevel = "standard",
    budget_override: int | None = None,
    section_order: list[str] | None = None,
    disabled_sections: list[str] | None = None,
) -> str:
    """
    Format warm memory sections into a string for system prompt injection.

    Args:
        sections: Dict from build_warm_memory()
        level: Budget level (affects max output size)
        budget_override: Override budget in chars (None = use level default)
        section_order: Custom order of section keys (None = use SECTION_CONFIG order)
        disabled_sections: Section keys to exclude (None = include all)

    Returns:
        Formatted string ready to inject between system prompt blocks.
    """
    budget = budget_override or LEVEL_BUDGETS.get(level, 8_000)
    skip = set(disabled_sections) if disabled_sections else set()

    # Use custom order if provided, falling back to SECTION_CONFIG order
    if section_order:
        ordered_keys = []
        for k in section_order:
            if k in SECTION_CONFIG:
                ordered_keys.append(k)
        # Append any keys from SECTION_CONFIG not in section_order (safety net)
        for k in SECTION_CONFIG:
            if k not in ordered_keys:
                ordered_keys.append(k)
    else:
        ordered_keys = list(SECTION_CONFIG.keys())

    parts = []
    total_chars = 0

    for section_key in ordered_keys:
        if section_key in skip:
            continue
        label = SECTION_CONFIG.get(section_key)
        if not label:
            continue
        content = sections.get(section_key)
        if not content:
            continue

        block = f"━━━ {label} ━━━\n{content}"

        # Check budget
        block_len = len(block) + 2  # +2 for newlines
        if total_chars + block_len > budget:
            # Truncate the last section to fit
            remaining = budget - total_chars - len(f"\n━━━ {label} ━━━\n") - 20
            if remaining > 100:
                truncated = content[:remaining] + "…"
                parts.append(f"━━━ {label} ━━━\n{truncated}")
            break

        parts.append(block)
        total_chars += block_len

    if not parts:
        return ""

    header = "╔══════════════════════════════════╗\n║     WARM MEMORY CONTEXT          ║\n╚══════════════════════════════════╝"
    return header + "\n\n" + "\n\n".join(parts)


def format_for_system_prompt(
    entity_id: str,
    level: WarmLevel = "standard",
    user_entity_id: str | None = None,
    budget_override: int | None = None,
) -> str:
    """
    One-call convenience: build + format warm memory.

    Usage:
        warm_context = format_for_system_prompt("agent-id", level="standard")
        system_prompt = f"{persona_instructions}\\n\\n{warm_context}\\n\\n{tool_instructions}"
    """
    from src.warmth.builder import build_warm_memory
    sections = build_warm_memory(entity_id, level=level, user_entity_id=user_entity_id)
    return format_warm_memory(sections, level=level, budget_override=budget_override)
