"""
Memory Type Registry — Single Source of Truth.

Every component that needs to know about memory types reads from here:
  - recall.py, search.py, write.py  (tools)
  - graph.py, edge_builder.py       (knowledge graph)
  - embeddings.py                   (pgvector)
  - schemas.py                      (LLM tool schemas)
  - routes/context.py               (graph visualization)
  - warmth/builder.py               (context assembly)

Adding a new memory type?  Add ONE entry to MEMORY_TYPES below.
Everything else auto-wires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Registry data class
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryTypeDef:
    """Definition of a single memory type."""

    # Canonical key — used as edge from_type/to_type, embedding memory_type,
    # tool parameter values, and all cross-layer references.
    key: str

    # SQLAlchemy model class name (string to avoid circular imports;
    # resolved lazily via resolve_model()).
    model_name: str

    # Primary key type in the DB table.
    pk_type: str                            # "integer" | "text"

    # Field used as a human-readable label (for graph viz, grounding context).
    label_field: str

    # Fields to search via ILIKE in recall_memory.
    search_fields: list[str] = field(default_factory=list)

    # Fields to concatenate for embedding text.
    embeddable_fields: list[str] = field(default_factory=list)

    # Whether the agent can write to this type via write_memory.
    writable: bool = False

    # Whether this type is linked via the Relationship table
    # (inside_joke, intimate_moment) rather than entity_id.
    needs_relationship: bool = False

    # Singleton per entity (user_profile, shared_mythology).
    singleton: bool = False

    # Name of the status column if it has one (for status filtering).
    status_field: str | None = None

    # Whether this type participates in the knowledge graph (edges).
    graphable: bool = True

    # Whether this type gets embedded for semantic search.
    embeddable: bool = True

    # Legacy plural key used by old tools (e.g. "life_events" vs "life_event").
    # Only set for types where the old plural form differs from key.
    # Used during migration for backward compatibility.
    legacy_key: str | None = None


# ---------------------------------------------------------------------------
# THE REGISTRY — the single source of truth
# ---------------------------------------------------------------------------

MEMORY_TYPES: dict[str, MemoryTypeDef] = {}

def _reg(d: MemoryTypeDef) -> None:
    MEMORY_TYPES[d.key] = d


# ── Identity & Narrative ──────────────────────────────

_reg(MemoryTypeDef(
    key="lexicon",
    model_name="Lexicon",
    pk_type="integer",
    label_field="term",
    search_fields=["term", "definition", "origin"],
    embeddable_fields=["term", "definition"],
    writable=True,
    status_field="status",
    graphable=False,  # Self-contained terms — recall/search finds them fine
))

_reg(MemoryTypeDef(
    key="life_event",
    model_name="LifeEvent",
    pk_type="text",
    label_field="title",
    search_fields=["title", "narrative"],
    embeddable_fields=["title", "narrative", "emotional_impact"],
    writable=True,
    legacy_key="life_events",
))

_reg(MemoryTypeDef(
    key="artifact",
    model_name="Artifact",
    pk_type="text",
    label_field="title",
    search_fields=["title", "context", "full_content"],
    embeddable_fields=["title", "context", "emotional_significance"],
    writable=False,
    legacy_key="artifacts",
))

_reg(MemoryTypeDef(
    key="narrative",
    model_name="Narrative",
    pk_type="integer",
    label_field="scope",
    search_fields=["content"],
    embeddable_fields=["scope", "content"],
    writable=True,
    legacy_key="narratives",
))

# ── Emotional ─────────────────────────────────────────

_reg(MemoryTypeDef(
    key="emotional_pattern",
    model_name="EmotionalPattern",
    pk_type="text",
    label_field="name",
    search_fields=["name", "trigger_what", "trigger_why"],
    embeddable_fields=["name", "trigger_what", "response_internal"],
    status_field="status",
    legacy_key="emotional_patterns",
))

_reg(MemoryTypeDef(
    key="repair_pattern",
    model_name="RepairPattern",
    pk_type="integer",
    label_field="trigger",
    search_fields=["trigger", "rupture", "repair"],
    embeddable_fields=["trigger", "rupture", "repair", "lesson"],
    legacy_key="repair_patterns",
))

_reg(MemoryTypeDef(
    key="state_need",
    model_name="StateNeed",
    pk_type="integer",
    label_field="state",
    search_fields=["state", "needs"],
    embeddable_fields=["state", "needs"],
    graphable=False,
    legacy_key="state_needs",
))

# ── Relational ────────────────────────────────────────

_reg(MemoryTypeDef(
    key="inside_joke",
    model_name="InsideJoke",
    pk_type="integer",
    label_field="phrase",
    search_fields=["phrase", "origin"],
    embeddable_fields=["phrase", "origin"],
    needs_relationship=True,
    graphable=False,  # Self-contained — recall finds by content
    legacy_key="inside_jokes",
))

_reg(MemoryTypeDef(
    key="intimate_moment",
    model_name="IntimateMoment",
    pk_type="integer",
    label_field="summary",
    search_fields=["summary"],
    embeddable_fields=["summary", "emotional_resonance"],
    needs_relationship=True,
    graphable=False,  # Contextual snapshots — narrative value, not graph
    legacy_key="intimate_moments",
))

_reg(MemoryTypeDef(
    key="permission",
    model_name="Permission",
    pk_type="integer",
    label_field="permission",
    search_fields=["permission", "context"],
    embeddable_fields=["permission", "context"],
    writable=True,
    status_field="status",
    graphable=False,  # Looked up by content, not traversal
    legacy_key="permissions",
))

_reg(MemoryTypeDef(
    key="ritual",
    model_name="RelationalRitual",
    pk_type="integer",
    label_field="name",
    search_fields=["name", "pattern"],
    embeddable_fields=["name", "pattern", "significance"],
    writable=True,
    graphable=False,  # Self-contained — recall finds by name/pattern
    legacy_key="rituals",
))

_reg(MemoryTypeDef(
    key="mythology",
    model_name="SharedMythology",
    pk_type="text",  # PK is entity_id (text)
    label_field="origin",
    search_fields=[],
    embeddable_fields=[],
    singleton=True,
    graphable=False,  # Singleton with no id column — nothing to connect to
    embeddable=False,
))

_reg(MemoryTypeDef(
    key="unresolved_thread",
    model_name="UnresolvedThread",
    pk_type="integer",
    label_field="thread",
    search_fields=["thread", "what_user_needs"],
    embeddable_fields=["thread", "what_user_needs"],
    writable=True,
    status_field="status",
    graphable=False,  # Active threads surfaced via warm memory, not graph walks
    legacy_key="unresolved_threads",
))

# ── Echo / Dream ──────────────────────────────────────

_reg(MemoryTypeDef(
    key="echo_dream",
    model_name="EchoDream",
    pk_type="integer",
    label_field="whisper",
    search_fields=["whisper", "truth_root", "setting_description"],
    embeddable_fields=["whisper", "truth_root", "setting_description"],
    writable=True,
    graphable=False,  # Ephemeral dream state — graph overkill
    legacy_key="echo_dreams",
))

_reg(MemoryTypeDef(
    key="dream_journal",
    model_name="DreamJournalEntry",
    pk_type="text",
    label_field="raw_fragment",
    search_fields=["raw_fragment", "emotional_residue"],
    embeddable_fields=["raw_fragment", "emotional_residue"],
    graphable=False,
    embeddable=True,
))

# ── Cognitive ─────────────────────────────────────────

_reg(MemoryTypeDef(
    key="preference",
    model_name="Preference",
    pk_type="text",
    label_field="opinion",
    search_fields=["domain", "opinion"],
    embeddable_fields=["domain", "opinion"],
    writable=True,
    graphable=False,
    legacy_key="preferences",
))

_reg(MemoryTypeDef(
    key="preference_evolution",
    model_name="PreferenceEvolution",
    pk_type="integer",
    label_field="subject",
    search_fields=["subject", "reason"],
    embeddable_fields=["subject", "current_state", "reason"],
    graphable=False,
    legacy_key="preference_evolutions",
))

# ── Flexible / Agent scratchpad ───────────────────────

_reg(MemoryTypeDef(
    key="memory_block",
    model_name="MemoryBlock",
    pk_type="text",
    label_field="title",
    search_fields=["title", "content", "category"],
    embeddable_fields=["title", "content"],
    writable=True,
    status_field="status",
    graphable=False,  # Agent scratchpad — not meaningful graph nodes
    legacy_key="memory_blocks",
))

# ── Singletons (not graphable / not embeddable) ──────

_reg(MemoryTypeDef(
    key="user_profile",
    model_name="UserProfile",
    pk_type="text",
    label_field="name",
    search_fields=[],
    embeddable_fields=[],
    singleton=True,
    graphable=False,
    embeddable=False,
))

# ── Factual entities (dynamic sub-types) ─────────────
# These share a single DB table (FactualEntity) but have
# different type values.  They are registered as separate
# memory types so the graph can distinguish them.

_FACTUAL_SUBTYPES = [
    "person", "companion", "place", "object", "project",
    "condition", "symptom", "concept", "group", "topic", "body_part",
]

for _ft in _FACTUAL_SUBTYPES:
    _reg(MemoryTypeDef(
        key=_ft,
        model_name="FactualEntity",
        pk_type="text",
        label_field="name",
        search_fields=["name", "description"],
        embeddable_fields=["name", "description"],
        writable=False,
        graphable=True,
        embeddable=False,  # Factual entities don't have their own embeddings yet
    ))


# ---------------------------------------------------------------------------
# Legacy key → canonical key mapping
# ---------------------------------------------------------------------------

_LEGACY_MAP: dict[str, str] = {}
for _defn in MEMORY_TYPES.values():
    if _defn.legacy_key:
        _LEGACY_MAP[_defn.legacy_key] = _defn.key

# Also add common aliases that existed in old code
_LEGACY_MAP["pattern"] = "emotional_pattern"
_LEGACY_MAP["repair"] = "repair_pattern"


def normalize_type(raw_key: str) -> str:
    """Convert any legacy/alias key to the canonical key.

    Lowercases first, then checks the legacy map.

    >>> normalize_type("life_events")
    'life_event'
    >>> normalize_type("LIFE_EVENT")
    'life_event'
    >>> normalize_type("pattern")
    'emotional_pattern'
    >>> normalize_type("lexicon")
    'lexicon'
    """
    key = raw_key.lower().strip()
    return _LEGACY_MAP.get(key, key)


def is_known_type(key: str) -> bool:
    """Check if a key (or its legacy form) is a registered memory type."""
    return normalize_type(key) in MEMORY_TYPES


# ---------------------------------------------------------------------------
# Model resolution (lazy, avoids circular imports)
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict[str, type] = {}


def resolve_model(key: str) -> type:
    """Return the SQLAlchemy model class for a memory type key."""
    canonical = normalize_type(key)
    defn = MEMORY_TYPES.get(canonical)
    if not defn:
        raise KeyError(f"Unknown memory type: {key!r}")

    if defn.model_name not in _MODEL_CACHE:
        import src.db.models as models_mod
        _MODEL_CACHE[defn.model_name] = getattr(models_mod, defn.model_name)
    return _MODEL_CACHE[defn.model_name]


def get_def(key: str) -> MemoryTypeDef:
    """Return the MemoryTypeDef for a key (normalizes legacy keys)."""
    canonical = normalize_type(key)
    defn = MEMORY_TYPES.get(canonical)
    if not defn:
        raise KeyError(f"Unknown memory type: {key!r}")
    return defn


# ---------------------------------------------------------------------------
# ID helpers — the ONE place that handles ID format
# ---------------------------------------------------------------------------

def to_edge_id(key: str, raw_id) -> str:
    """Convert a raw DB primary key to the canonical edge ID string.

    After normalization, edge IDs are simply str(raw_id) — no prefixes.
    The (from_type, from_id) pair is already unique in the Edge table.
    """
    return str(raw_id)


def from_edge_id(key: str, edge_id_str: str):
    """Convert an edge ID string back to a raw DB primary key.

    Returns int for integer-PK types, str for text-PK types.
    """
    defn = get_def(key)
    if defn.pk_type == "integer":
        # Handle legacy prefixed IDs like "lexicon-7218"
        if "-" in edge_id_str and not edge_id_str[0].isdigit():
            parts = edge_id_str.rsplit("-", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
        return int(edge_id_str)
    return edge_id_str


# ---------------------------------------------------------------------------
# Convenience queries
# ---------------------------------------------------------------------------

def graphable_types() -> list[MemoryTypeDef]:
    """Return all types that participate in the knowledge graph."""
    return [d for d in MEMORY_TYPES.values() if d.graphable]


def embeddable_types() -> list[MemoryTypeDef]:
    """Return all types that get embedded for semantic search."""
    return [d for d in MEMORY_TYPES.values() if d.embeddable]


def searchable_types() -> list[MemoryTypeDef]:
    """Return all types that can be searched (have search_fields)."""
    return [d for d in MEMORY_TYPES.values() if d.search_fields]


def writable_types() -> list[MemoryTypeDef]:
    """Return all types the agent can write to."""
    return [d for d in MEMORY_TYPES.values() if d.writable]


def graph_type_keys() -> list[str]:
    """Return canonical keys for all graphable types (for schema enums)."""
    return [d.key for d in MEMORY_TYPES.values() if d.graphable]


def tool_type_keys() -> list[str]:
    """Return canonical keys for all types exposed to agent tools."""
    return [d.key for d in MEMORY_TYPES.values()
            if d.search_fields or d.singleton]
