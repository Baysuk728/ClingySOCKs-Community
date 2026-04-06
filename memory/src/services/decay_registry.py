"""
Decay Capability Registry.

Defines which memory types support full tier transitions (summary/fragment
generation on hazy/fading) vs. lightweight decay (weight + tier only, skip
straight to archived when below threshold).

The decay service MUST check this registry before attempting tier transitions.
Calling LLM summarization on a table that has no `summary` column would fail.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecayCapability:
    """Describes what decay operations a memory type supports."""

    # Table name for identification
    table_name: str

    # The ORM model class name (for dynamic lookup)
    model_name: str

    # Column that holds the weight (most use 'semantic_weight', memory_blocks uses 'memory_weight')
    weight_column: str

    # Does this table have summary/fragment columns for full tier transitions?
    supports_full_transitions: bool

    # Does this table have connection_ids for decay rate modification?
    has_connections: bool

    # Does this table have mood_at_creation for emotional context?
    has_mood_snapshot: bool

    # The text column that gets summarized on hazy transition (if supports_full_transitions)
    # None for lightweight tables
    content_column: str | None

    # Human-readable label for logging/debugging
    label: str


# ============================================================================
# Registry
# ============================================================================

DECAY_REGISTRY: dict[str, DecayCapability] = {

    # ── Full transition support (summary + fragment columns exist) ──

    "life_events": DecayCapability(
        table_name="life_events",
        model_name="LifeEvent",
        weight_column="semantic_weight",
        supports_full_transitions=True,
        has_connections=True,
        has_mood_snapshot=True,
        content_column="narrative",
        label="Life Events",
    ),

    "artifacts": DecayCapability(
        table_name="artifacts",
        model_name="Artifact",
        weight_column="semantic_weight",
        supports_full_transitions=True,
        has_connections=True,
        has_mood_snapshot=True,
        content_column="full_content",
        label="Artifacts",
    ),

    "memory_blocks": DecayCapability(
        table_name="memory_blocks",
        model_name="MemoryBlock",
        weight_column="memory_weight",      # Legacy name — already existed before decay system
        supports_full_transitions=True,
        has_connections=True,
        has_mood_snapshot=True,
        content_column="content",
        label="Memory Blocks",
    ),

    # ── Lightweight (weight + tier only, no summary/fragment) ──
    # When these hit "hazy" threshold, they skip straight to a weight-only
    # demotion. No LLM summarization. They go vivid → clear → archived.
    # The intermediate tiers (hazy, fading) are skipped.

    "lexicon": DecayCapability(
        table_name="lexicon",
        model_name="Lexicon",
        weight_column="semantic_weight",
        supports_full_transitions=False,
        has_connections=False,
        has_mood_snapshot=False,
        content_column=None,
        label="Lexicon",
    ),

    "inside_jokes": DecayCapability(
        table_name="inside_jokes",
        model_name="InsideJoke",
        weight_column="semantic_weight",
        supports_full_transitions=False,
        has_connections=False,
        has_mood_snapshot=False,
        content_column=None,
        label="Inside Jokes",
    ),

    "intimate_moments": DecayCapability(
        table_name="intimate_moments",
        model_name="IntimateMoment",
        weight_column="semantic_weight",
        supports_full_transitions=False,
        has_connections=False,
        has_mood_snapshot=False,
        content_column=None,
        label="Intimate Moments",
    ),

    "echo_dreams": DecayCapability(
        table_name="echo_dreams",
        model_name="EchoDream",
        weight_column="semantic_weight",
        supports_full_transitions=False,
        has_connections=False,
        has_mood_snapshot=False,
        content_column=None,
        label="Echo Dreams",
    ),
}


# ============================================================================
# Tier thresholds
# ============================================================================

TIER_THRESHOLDS = {
    "vivid":    (0.8, 1.0),
    "clear":    (0.5, 0.8),
    "hazy":     (0.25, 0.5),
    "fading":   (0.1, 0.25),
    "archived": (0.0, 0.1),
}


def get_tier_for_weight(weight: float) -> str:
    """Determine which tier a weight value falls into."""
    if weight >= 0.8:
        return "vivid"
    elif weight >= 0.5:
        return "clear"
    elif weight >= 0.25:
        return "hazy"
    elif weight >= 0.1:
        return "fading"
    else:
        return "archived"


def get_full_transition_types() -> list[str]:
    """Return memory types that support full tier transitions (summary/fragment)."""
    return [k for k, v in DECAY_REGISTRY.items() if v.supports_full_transitions]


def get_lightweight_types() -> list[str]:
    """Return memory types that only support weight+tier decay (no summary/fragment)."""
    return [k for k, v in DECAY_REGISTRY.items() if not v.supports_full_transitions]


# ============================================================================
# Lightweight tier mapping
# ============================================================================
# For lightweight types, the effective tier path is:
#   vivid (>=0.8) → clear (>=0.5) → archived (<0.5)
# They skip hazy and fading entirely because there's no summary/fragment
# column to write to. The decay function still uses the same rate math,
# but tier transitions only fire at the vivid→clear and clear→archived
# boundaries.

LIGHTWEIGHT_TIER_MAP = {
    "vivid":    (0.5, 1.0),    # >=0.5 is "active" (vivid or clear combined)
    "clear":    (0.5, 0.8),    # Between 0.5 and 0.8
    "archived": (0.0, 0.5),    # Below 0.5 goes straight to archived
}


def get_tier_for_weight_lightweight(weight: float) -> str:
    """Tier assignment for lightweight memory types (no hazy/fading)."""
    if weight >= 0.8:
        return "vivid"
    elif weight >= 0.5:
        return "clear"
    else:
        return "archived"
