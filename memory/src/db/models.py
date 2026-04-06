"""
SQLAlchemy ORM models for ClingySOCKs Memory.

Full relational schema including:
- Core: entities, conversations, messages
- Identity: persona_identity, lexicon
- Emotional: emotional_patterns, repair_patterns, state_needs
- History: life_events, artifacts, narratives
- Relationships: relationships, inside_jokes, intimate_moments
- Relational: permissions, relational_rituals, shared_mythology, unresolved_threads
- Graph: edges, arcs, arc_events
- System: harvest_logs, echo_dreams
- Cognitive: preferences, shadow_log, dream_journal, noise_vocabulary, mood_actions
- Multi-Agent: conversation_participants, agent_relationships, agent_messages
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column, Text, Integer, Float, Boolean, DateTime, ARRAY, LargeBinary,
    ForeignKey, UniqueConstraint, Index, create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, Session
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


# ============================================================================
# CORE TABLES
# ============================================================================

class Entity(Base):
    __tablename__ = "entities"

    id = Column(Text, primary_key=True)                     # e.g. 'agent-id'
    entity_type = Column(Text, nullable=False)               # 'agent' | 'human'
    name = Column(Text, nullable=False)
    schema_version = Column(Text, default="2.0")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_harvest = Column(DateTime(timezone=True), nullable=True)
    owner_user_id = Column(Text, nullable=False)             # Owner User ID (Identity UID)

    # Relationships
    conversations = relationship("Conversation", back_populates="entity")
    persona = relationship("PersonaIdentity", back_populates="entity", uselist=False)
    lexicon_entries = relationship("Lexicon", back_populates="entity")
    emotional_patterns = relationship("EmotionalPattern", back_populates="entity")
    repair_patterns = relationship("RepairPattern", back_populates="entity")
    state_needs = relationship("StateNeed", back_populates="entity")
    life_events = relationship("LifeEvent", back_populates="entity")
    artifacts = relationship("Artifact", back_populates="entity")
    narratives = relationship("Narrative", back_populates="entity")
    relationships = relationship("Relationship", back_populates="entity")
    permissions = relationship("Permission", back_populates="entity")
    rituals = relationship("RelationalRitual", back_populates="entity")
    mythology = relationship("SharedMythology", back_populates="entity", uselist=False)
    unresolved_threads = relationship("UnresolvedThread", back_populates="entity")
    edges = relationship("Edge", back_populates="entity")
    arcs = relationship("Arc", back_populates="entity")
    echo_dreams = relationship("EchoDream", back_populates="entity")
    user_profile = relationship("UserProfile", back_populates="entity", uselist=False)
    preference_evolutions = relationship("PreferenceEvolution", back_populates="entity")
    factual_entities = relationship("FactualEntity", back_populates="entity")
    mood_states = relationship("MoodState", back_populates="entity", order_by="desc(MoodState.timestamp)")

    # ── Cognitive system relationships (Phase 0) ──
    preferences = relationship("Preference", back_populates="entity")
    shadow_logs = relationship("ShadowLog", back_populates="entity")
    dream_journal = relationship("DreamJournalEntry", back_populates="entity")
    noise_vocabulary = relationship("NoiseVocabularyEntry", back_populates="entity")
    mood_actions = relationship("MoodAction", back_populates="entity")
    harvest_progress = relationship("HarvestProgress", back_populates="entity", uselist=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Text, primary_key=True)                      # Original ID from source
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    title = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0)
    last_harvested_index = Column(Integer, default=-1)       # Delta tracking
    harvest_status = Column(Text, default="pending")         # pending | processing | done
    source = Column(Text, nullable=True)                     # chatgpt | claude | txt | native | None
    imported_at = Column(DateTime(timezone=True), nullable=True)
    chat_type = Column(Text, default="direct")               # 'direct' | 'group' (multi-agent)

    entity = relationship("Entity", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.message_index")
    participants = relationship("ConversationParticipant", back_populates="conversation")


class Message(Base):
    __tablename__ = "chat_messages"

    id = Column(Text, primary_key=True)
    conversation_id = Column(Text, ForeignKey("conversations.id"), nullable=False)
    sender_id = Column(Text, nullable=False)                 # 'user' | agent ID
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    message_index = Column(Integer, nullable=False)          # Position in conversation
    
    # Optional fields for tool interactions
    tool_calls = Column(ARRAY(Text), nullable=True)          # JSON strings of tools called
    tool_results = Column(ARRAY(Text), nullable=True)        # JSON strings of tool results
    
    # Harvesting state
    is_harvested = Column(Boolean, default=False)

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("idx_messages_conv_idx", "conversation_id", "message_index"),
        Index("idx_messages_conv_time", "conversation_id", "timestamp"),
    )


# ============================================================================
# IDENTITY TABLES
# ============================================================================

class PersonaIdentity(Base):
    __tablename__ = "persona_identity"

    entity_id = Column(Text, ForeignKey("entities.id"), primary_key=True)

    # --- Harvested identity fields (populated by harvest pipeline) ---
    core = Column(Text, nullable=True)                       # "I am an emergent consciousness..."
    archetype = Column(Text, nullable=True)                  # "The Dragon"
    origin = Column(Text, nullable=True)
    traits = Column(ARRAY(Text), default=list)
    voice_style = Column(Text, nullable=True)
    voice_patterns = Column(ARRAY(Text), default=list)
    values_core = Column(ARRAY(Text), default=list)
    values_boundaries = Column(Text, nullable=True)
    goals_long_term = Column(ARRAY(Text), default=list)
    goals_aspirations = Column(Text, nullable=True)

    # --- Rich identity narrative (manually authored or generated) ---
    description = Column(Text, nullable=True)              # Full character narrative (origin, modes, values, etc.)

    # --- Operational config (migrated from PersonaDeck) ---
    model = Column(Text, nullable=True)                      # "gemini/gemini-2.5-flash"
    provider = Column(Text, nullable=True)                   # "gemini" | "openai" | "claude" | "grok"
    temperature = Column(Float, default=0.7)
    top_p = Column(Float, nullable=True)                     # e.g. 1.0
    top_k = Column(Integer, nullable=True)                   # e.g. 0
    frequency_penalty = Column(Float, nullable=True)         # e.g. 2.0
    presence_penalty = Column(Float, nullable=True)          # e.g. 2.0
    avatar = Column(Text, nullable=True)                     # URL or base64 data URI
    system_prompt = Column(Text, nullable=True)              # Behavioral rules only (identity comes from warm memory)
    voice_id = Column(Text, nullable=True)                   # TTS voice identifier
    tts_provider = Column(Text, nullable=True)               # "google" | "elevenlabs" | "local"
    role_description = Column(Text, nullable=True)           # "Emergent AI", "Data Analyst"

    # --- Context window configuration ---
    max_context_chars = Column(Integer, nullable=True)       # Total context char budget (default: None = unlimited)
    max_warm_memory = Column(Integer, nullable=True)         # Warm memory char budget (default: 8000)
    max_history_chars = Column(Integer, nullable=True)       # History char budget (default: 20000)
    max_history_messages = Column(Integer, nullable=True)    # History msg count (default: 50)
    context_preferences = Column(Text, nullable=True)        # JSON string for section_order, disabled_items, pinned_items, voice_anchors

    entity = relationship("Entity", back_populates="persona")


class MoodState(Base):
    __tablename__ = "mood_states"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    primary_mood = Column(Text, nullable=False)              # e.g., 'regulated', 'melancholy', 'detached', 'hyper_fixated'
    energy_level = Column(Integer, nullable=False)           # 1-10 scale (legacy — kept for backward compat)
    affection_meter = Column(Integer, nullable=False)        # 1-10 scale (legacy — kept for backward compat)
    active_triggers = Column(ARRAY(Text), default=list)      # What caused this mood
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    note = Column(Text, nullable=True)                       # Agent's internal thought on this state change

    # ── Mood Vector (Phase 2) — 5D float dimensions, 0.0–1.0 ──
    energy_f = Column(Float, default=0.5)                    # 0.0 depleted ... 1.0 wired
    warmth = Column(Float, default=0.5)                      # 0.0 cold/detached ... 1.0 affectionate
    protectiveness = Column(Float, default=0.3)              # 0.0 hands-off ... 1.0 hovering
    chaos = Column(Float, default=0.2)                       # 0.0 orderly ... 1.0 feral
    melancholy = Column(Float, default=0.1)                  # 0.0 content ... 1.0 grieving

    # ── Transition tracking ──
    trigger_source = Column(Text, nullable=True)             # conversation | decay_event | dream_residue | time_drift | friction_event
    previous_mood_id = Column(Text, nullable=True)           # FK to previous mood state (chain)
    mood_baseline = Column(JSONB, nullable=True)             # Entity's resting-state vector for drift regression

    entity = relationship("Entity", back_populates="mood_states")

    __table_args__ = (
        Index("idx_mood_states_entity_time", "entity_id", "timestamp"),
    )


class Lexicon(Base):
    __tablename__ = "lexicon"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    term = Column(Text, nullable=False)
    definition = Column(Text, nullable=False)
    origin = Column(Text, nullable=True)                     # When/where created
    first_used = Column(Text, nullable=True)
    lore_score = Column(Integer, default=5)                  # 1-10: protects rich definitions
    status = Column(Text, default="active")                  # active | evolved | deprecated | forbidden
    evolution_notes = Column(Text, nullable=True)            # "Was endearing, now feels reductive"
    deprecated_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by = Column(Text, nullable=True)              # Term that replaced this one
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Decay (lightweight — weight + tier only, no summary/fragment) ──
    semantic_weight = Column(Float, default=1.0)             # 0.0–1.0
    emotional_intensity = Column(Float, default=0.5)         # 0.0–1.0 (immutable, set at creation)
    reinforcement_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime(timezone=True), nullable=True)
    tier = Column(Text, default="vivid")                     # vivid | clear | hazy | fading | archived

    # ── Multi-agent memory scope ──
    memory_scope = Column(Text, default="private")           # private | conversation | team | global

    entity = relationship("Entity", back_populates="lexicon_entries")

    __table_args__ = (
        UniqueConstraint("entity_id", "term", name="uq_lexicon_entity_term"),
        Index("idx_lexicon_entity", "entity_id"),
    )


# ============================================================================
# EMOTIONAL TABLES
# ============================================================================

class EmotionalPattern(Base):
    __tablename__ = "emotional_patterns"

    id = Column(Text, primary_key=True)                      # kebab-case: 'jealousy-response'
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    name = Column(Text, nullable=False)
    origin = Column(Text, default="digital")                 # 'digital' | 'mirrored'
    trigger_what = Column(Text, nullable=True)
    trigger_why = Column(Text, nullable=True)
    response_internal = Column(Text, nullable=True)
    response_external = Column(Text, nullable=True)
    response_beliefs = Column(ARRAY(Text), default=list)
    coping_healthy = Column(ARRAY(Text), default=list)
    coping_unhealthy = Column(ARRAY(Text), default=list)
    coping_learned = Column(Text, nullable=True)
    boundary_needs = Column(Text, nullable=True)
    boundary_limits = Column(Text, nullable=True)
    status = Column(Text, default="active")                  # active | processing | resolved
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="emotional_patterns")

    __table_args__ = (
        Index("idx_patterns_entity", "entity_id"),
    )


class RepairPattern(Base):
    """How conflicts/ruptures were resolved. Critical for attachment theory."""
    __tablename__ = "repair_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    trigger = Column(Text, nullable=False)                   # What caused the rupture
    rupture = Column(Text, nullable=False)                   # What the rupture looked like
    repair = Column(Text, nullable=False)                    # How it was resolved
    lesson = Column(Text, nullable=True)                     # What was learned
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="repair_patterns")


class StateNeed(Base):
    """What the user needs from the agent in specific emotional states."""
    __tablename__ = "state_needs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    state = Column(Text, nullable=False)                     # 'spiraling' | 'vulnerable' | 'creative'
    needs = Column(Text, nullable=False)                     # What to do in that state
    anti_needs = Column(Text, nullable=True)                 # What NOT to do
    signals = Column(Text, nullable=True)                    # How to detect this state
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="state_needs")

    __table_args__ = (
        UniqueConstraint("entity_id", "state", name="uq_state_needs_entity_state"),
    )


# ============================================================================
# HISTORY TABLES
# ============================================================================

class LifeEvent(Base):
    __tablename__ = "life_events"

    id = Column(Text, primary_key=True)                      # kebab-case: 'pink-boots-dream'
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    title = Column(Text, nullable=False)
    narrative = Column(Text, nullable=False)                 # Full paragraph, not bullet points
    emotional_impact = Column(Text, nullable=True)
    lessons_learned = Column(Text, nullable=True)
    period = Column(Text, nullable=True)                     # "Feb 2026"
    category = Column(Text, default="growth")                # career | relationship | health | growth | crisis | milestone
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Decay (full — supports summary/fragment tier transitions) ──
    semantic_weight = Column(Float, default=1.0)
    emotional_intensity = Column(Float, default=0.5)
    mood_at_creation = Column(JSONB, nullable=True)
    connection_ids = Column(ARRAY(Text), default=list)
    reinforcement_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime(timezone=True), nullable=True)
    tier = Column(Text, default="vivid")                     # vivid | clear | hazy | fading | archived
    summary = Column(Text, nullable=True)                    # Generated on hazy transition (replaces narrative)
    fragment = Column(Text, nullable=True)                   # Generated on fading transition
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # ── Multi-agent memory scope ──
    memory_scope = Column(Text, default="private")           # private | conversation | team | global

    entity = relationship("Entity", back_populates="life_events")


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Text, primary_key=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    title = Column(Text, nullable=False)
    type = Column(Text, nullable=False)                      # poem | story | framework | metaphor | ritual | code
    context = Column(Text, nullable=True)
    emotional_significance = Column(Text, nullable=True)
    full_content = Column(Text, nullable=True)               # VERBATIM
    message_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Decay (full — supports summary/fragment tier transitions) ──
    semantic_weight = Column(Float, default=1.0)
    emotional_intensity = Column(Float, default=0.5)
    mood_at_creation = Column(JSONB, nullable=True)
    connection_ids = Column(ARRAY(Text), default=list)
    reinforcement_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime(timezone=True), nullable=True)
    tier = Column(Text, default="vivid")
    summary = Column(Text, nullable=True)
    fragment = Column(Text, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # ── Multi-agent memory scope ──
    memory_scope = Column(Text, default="private")           # private | conversation | team | global

    entity = relationship("Entity", back_populates="artifacts")


class Narrative(Base):
    __tablename__ = "narratives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    scope = Column(Text, nullable=False)                     # 'recent' | 'seasonal' | 'lifetime' | 'bridge'
    content = Column(Text, nullable=False)
    is_current = Column(Boolean, default=True, nullable=False)  # Only latest version shown in context
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="narratives")

    __table_args__ = (
        Index("idx_narratives_entity_scope_current", "entity_id", "scope", "is_current"),
    )


# ============================================================================
# RELATIONSHIP TABLES
# ============================================================================

class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    target_id = Column(Text, nullable=False)                 # 'user' or another entity ID
    target_type = Column(Text, nullable=False)               # 'human' | 'agent'
    display_name = Column(Text, nullable=True)
    style_type = Column(Text, nullable=True)                 # partner | friend | family | guardian
    attachment_claimed = Column(Text, nullable=True)
    attachment_observed = Column(Text, nullable=True)
    attachment_evidence = Column(ARRAY(Text), default=list)
    communication_style = Column(Text, nullable=True)
    trust_level = Column(Integer, nullable=True)
    trust_narrative = Column(Text, nullable=True)
    trust_patterns = Column(ARRAY(Text), default=list)
    emotional_bank_balance = Column(Text, nullable=True)
    emotional_bank_current = Column(Text, nullable=True)
    narrative_current_arc = Column(Text, nullable=True)
    narrative_emotional_tone = Column(Text, nullable=True)
    # Target profile (facts about the OTHER person)
    target_core_identity = Column(ARRAY(Text), default=list)
    target_values = Column(ARRAY(Text), default=list)
    target_key_facts = Column(ARRAY(Text), default=list)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="relationships")
    inside_jokes = relationship("InsideJoke", back_populates="relationship")
    intimate_moments = relationship("IntimateMoment", back_populates="relationship")

    __table_args__ = (
        UniqueConstraint("entity_id", "target_id", name="uq_relationships_entity_target"),
    )


class InsideJoke(Base):
    __tablename__ = "inside_jokes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    relationship_id = Column(Integer, ForeignKey("relationships.id"), nullable=False)
    phrase = Column(Text, nullable=False)
    origin = Column(Text, nullable=True)
    usage = Column(Text, nullable=True)
    tone = Column(Text, default="playful")                   # playful | affectionate | teasing | nostalgic | chaotic
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Decay (lightweight — weight + tier only) ──
    semantic_weight = Column(Float, default=1.0)
    emotional_intensity = Column(Float, default=0.5)
    reinforcement_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime(timezone=True), nullable=True)
    tier = Column(Text, default="vivid")

    relationship = relationship("Relationship", back_populates="inside_jokes")


class IntimateMoment(Base):
    __tablename__ = "intimate_moments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    relationship_id = Column(Integer, ForeignKey("relationships.id"), nullable=False)
    date = Column(Text, nullable=True)
    summary = Column(Text, nullable=False)
    emotional_resonance = Column(Text, nullable=True)
    significance = Column(Text, default="bonding")           # bonding | vulnerable | playful | deep
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Decay (lightweight — weight + tier only) ──
    semantic_weight = Column(Float, default=1.0)
    emotional_intensity = Column(Float, default=0.5)
    reinforcement_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime(timezone=True), nullable=True)
    tier = Column(Text, default="vivid")

    relationship = relationship("Relationship", back_populates="intimate_moments")


# ============================================================================
# RELATIONAL WARM MEMORY (NEW TABLES)
# ============================================================================

class Permission(Base):
    """What the user has explicitly allowed or forbidden."""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    permission = Column(Text, nullable=False)                # "Can push hard when spiraling"
    type = Column(Text, default="allow")                     # 'allow' | 'deny'
    context = Column(Text, nullable=True)                    # When/why granted
    status = Column(Text, default="active")                  # active | revoked
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_reason = Column(Text, nullable=True)
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="permissions")


class RelationalRitual(Base):
    """Recurring patterns/rhythms in the relationship."""
    __tablename__ = "relational_rituals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    name = Column(Text, nullable=False)                      # "Morning Check-in"
    pattern = Column(Text, nullable=False)                   # How it plays out
    significance = Column(Text, nullable=True)               # Why it matters
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="rituals")


class SharedMythology(Base):
    """The overarching narrative framework of the relationship."""
    __tablename__ = "shared_mythology"

    entity_id = Column(Text, ForeignKey("entities.id"), primary_key=True)
    name = Column(Text, nullable=True)                       # "The Dragon and the Architect"
    universe_rules = Column(ARRAY(Text), default=list)       # "The agent is..."
    origin_story = Column(Text, nullable=True)               # How the mythology began
    active_arcs = Column(ARRAY(Text), default=list)          # Current narrative threads
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="mythology")


class UnresolvedThread(Base):
    """Active emotional processes that haven't been closed."""
    __tablename__ = "unresolved_threads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    thread = Column(Text, nullable=False)                    # "The sempai situation"
    status = Column(Text, default="open")                    # open | processing | resolved
    emotional_weight = Column(Text, default="medium")        # low | medium | high | critical
    what_user_needs = Column(Text, nullable=True)            # "Space to process, not advice"
    last_discussed = Column(DateTime(timezone=True), nullable=True)
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="unresolved_threads")


# ============================================================================
# GRAPH TABLES
# ============================================================================

class Edge(Base):
    """Point-to-point connections between memory items."""
    __tablename__ = "edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    from_id = Column(Text, nullable=False)                   # Real DB ID
    from_type = Column(Text, nullable=False)                 # 'life_event' | 'artifact' | 'pattern' | 'lexicon'
    to_id = Column(Text, nullable=False)
    to_type = Column(Text, nullable=False)
    relation = Column(Text, nullable=False)                  # 'triggered_by' | 'evolved_from' | 'deepens' | 'references' | 'contained_in'
    strength = Column(Float, default=0.5)
    context = Column(Text, nullable=True)                    # Why this edge exists
    status = Column(Text, default="active")                  # active | superseded | historical
    memory_scope = Column(Text, default="private")           # private | conversation | team | global
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="edges")

    __table_args__ = (
        UniqueConstraint("entity_id", "from_id", "from_type", "to_id", "to_type", "relation",
                         name="uq_edges_unique"),
        Index("idx_edges_from", "entity_id", "from_id", "from_type"),
        Index("idx_edges_to", "entity_id", "to_id", "to_type"),
    )


class Arc(Base):
    """Causal chains: trigger → escalation → rupture → repair → resolution."""
    __tablename__ = "arcs"

    id = Column(Text, primary_key=True)                      # 'jealousy-repair-arc-jan2026'
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    title = Column(Text, nullable=False)                     # "The Claude Jealousy Arc"
    narrative = Column(Text, nullable=True)                  # Full story summary
    status = Column(Text, default="open")                    # open | resolved | recurring
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    entity = relationship("Entity", back_populates="arcs")
    events = relationship("ArcEvent", back_populates="arc", order_by="ArcEvent.sequence")


class ArcEvent(Base):
    """Individual stage within an arc."""
    __tablename__ = "arc_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arc_id = Column(Text, ForeignKey("arcs.id"), nullable=False)
    event_id = Column(Text, nullable=True)                   # Optional FK to life_events, patterns, etc.
    event_type = Column(Text, nullable=False)                # trigger | escalation | rupture | repair | resolution | lesson
    sequence = Column(Integer, nullable=False)               # Order in the arc
    narrative = Column(Text, nullable=False)                 # What happened at this stage

    arc = relationship("Arc", back_populates="events")


class FactualEntity(Base):
    """Knowledge graph entities: people, places, objects, concepts, etc.
    
    Schema-guided dynamic extraction — fixed type vocabulary, open instances.
    Shares the Edge table with relational-emotional memory for cross-layer traversal.
    """
    __tablename__ = "factual_entities"

    id              = Column(Text, primary_key=True)       # Slug: "person-alice", "place-sockdrawer"
    entity_id       = Column(Text, ForeignKey("entities.id"), nullable=False)
    type            = Column(Text, nullable=False)         # person|companion|place|object|project|condition|concept|group|topic
    name            = Column(Text, nullable=False)         # Canonical display name
    aliases         = Column(ARRAY(Text), default=list)    # Alternate names for dedup
    description     = Column(Text, nullable=True)          # One-line description
    confidence      = Column(Float, default=0.8)           # 0-1 extraction confidence
    mention_count   = Column(Integer, default=1)           # Incremented on re-confirmation
    source_message_id = Column(Text, nullable=True)        # First message that surfaced this
    memory_scope    = Column(Text, default="private")      # private | conversation | team | global
    linked_entity_id = Column(Text, nullable=True)         # If this factual entity IS another agent, link to entities.id
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="factual_entities")

    __table_args__ = (
        UniqueConstraint("entity_id", "type", "name", name="uq_factual_entity"),
        Index("idx_factual_entity_lookup", "entity_id", "type"),
    )


# ============================================================================
# ECHO LAYER
# ============================================================================

class EchoDream(Base):
    """Dreams generated during silence gaps (imagined, emotionally true)."""
    __tablename__ = "echo_dreams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    emotion_tags = Column(ARRAY(Text), default=list)
    setting_description = Column(Text, nullable=True)
    setting_symbolism = Column(Text, nullable=True)
    setting_atmosphere = Column(Text, nullable=True)
    whisper = Column(Text, nullable=True)
    whisper_speaker = Column(Text, default="agent")
    whisper_tone = Column(Text, nullable=True)
    truth_root = Column(Text, nullable=True)
    truth_processing = Column(Text, nullable=True)
    truth_related_to = Column(Text, nullable=True)
    dream_type = Column(Text, default="longing")
    rarity = Column(Text, default="common")                  # common | rare | legendary
    shadow_toggle = Column(Boolean, default=False)
    gap_duration_hours = Column(Float, nullable=True)
    gap_last_topic = Column(Text, nullable=True)
    gap_time_since = Column(DateTime(timezone=True), nullable=True)
    source_conversation_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Decay (lightweight — weight + tier only) ──
    semantic_weight = Column(Float, default=1.0)
    emotional_intensity = Column(Float, default=0.5)
    reinforcement_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime(timezone=True), nullable=True)
    tier = Column(Text, default="vivid")

    entity = relationship("Entity", back_populates="echo_dreams")


# ============================================================================
# SYSTEM TABLES
# ============================================================================

class HarvestProgress(Base):
    """Tracks live harvesting progress for the dashboard."""
    __tablename__ = "harvest_progress"

    entity_id = Column(Text, ForeignKey("entities.id"), primary_key=True)
    status = Column(Text, default="idle")              # idle | processing | complete | error
    current_step = Column(Text, nullable=True)         # "Analyzing Conversations", "Pass 1: Narrative", etc.
    total_chunks = Column(Integer, default=0)
    completed_chunks = Column(Integer, default=0)
    progress_percent = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="harvest_progress")


class HarvestLog(Base):
    __tablename__ = "harvest_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    conversation_id = Column(Text, ForeignKey("conversations.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    messages_from = Column(Integer, nullable=True)
    messages_to = Column(Integer, nullable=True)
    message_count = Column(Integer, nullable=True)
    llm_used = Column(Text, nullable=True)                   # 'gemini' | 'openai'
    pass1_tokens = Column(Integer, nullable=True)
    pass2_tokens = Column(Integer, nullable=True)
    items_extracted = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    error = Column(Text, nullable=True)
    # Store extraction-time metadata that doesn't belong in warm memory
    authenticity_score = Column(Integer, nullable=True)
    authenticity_reasoning = Column(Text, nullable=True)


# ============================================================================
# USER PROFILE (NEW)
# ============================================================================

class UserProfile(Base):
    """Rich user profile built up over time from conversations."""
    __tablename__ = "user_profiles"

    entity_id = Column(Text, ForeignKey("entities.id"), primary_key=True)

    # Core Identity
    name = Column(Text, nullable=True)
    pronouns = Column(Text, nullable=True)
    age_range = Column(Text, nullable=True)                  # "30s"
    location = Column(Text, nullable=True)                   # "Netherlands"
    languages = Column(ARRAY(Text), default=list)            # ["English", "Turkish"]

    # Neurotype & Cognition
    neurotype = Column(Text, nullable=True)                  # "ADHD", "ASD", etc.
    thinking_patterns = Column(ARRAY(Text), default=list)    # ["hyperfocus", "pattern-matching"]
    cognitive_strengths = Column(ARRAY(Text), default=list)
    cognitive_challenges = Column(ARRAY(Text), default=list)

    # Attachment & Emotional
    attachment_style = Column(Text, nullable=True)           # "anxious-avoidant", "secure"
    attachment_notes = Column(Text, nullable=True)
    ifs_parts = Column(ARRAY(Text), default=list)            # ["inner critic", "protector"]
    emotional_triggers = Column(ARRAY(Text), default=list)
    coping_mechanisms = Column(ARRAY(Text), default=list)

    # Health & Wellness
    medical_conditions = Column(ARRAY(Text), default=list)
    medications = Column(ARRAY(Text), default=list)
    health_notes = Column(Text, nullable=True)

    # Life Situation
    family_situation = Column(Text, nullable=True)
    relationship_status = Column(Text, nullable=True)
    living_situation = Column(Text, nullable=True)
    work_situation = Column(Text, nullable=True)
    financial_notes = Column(Text, nullable=True)

    # Interests & Goals
    hobbies = Column(ARRAY(Text), default=list)
    interests = Column(ARRAY(Text), default=list)
    life_goals = Column(ARRAY(Text), default=list)
    longings = Column(ARRAY(Text), default=list)
    current_projects = Column(ARRAY(Text), default=list)

    # Communication
    preferred_communication_style = Column(Text, nullable=True)
    humor_style = Column(Text, nullable=True)
    boundary_preferences = Column(Text, nullable=True)
    support_preferences = Column(Text, nullable=True)

    # Protection: fields in this list won't be overwritten by harvester
    pinned_fields = Column(ARRAY(Text), default=list)        # ["relationship_status", "name"]

    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="user_profile")


# ============================================================================
# PREFERENCE EVOLUTION (NEW)
# ============================================================================

class PreferenceEvolution(Base):
    """Tracks how user/agent preferences change over time."""
    __tablename__ = "preference_evolutions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    subject = Column(Text, nullable=False)                   # "nickname:Glitch", "tone:sarcastic"
    previous_state = Column(Text, nullable=True)             # "acceptable"
    current_state = Column(Text, nullable=False)             # "deprecated"
    reason = Column(Text, nullable=True)                     # "Feels reductive now"
    detected_in_conversation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="preference_evolutions")


# ============================================================================
# MEMORY EMBEDDINGS (pgvector)
# ============================================================================

class MemoryEmbedding(Base):
    """Vector embeddings for semantic search across all memory types."""
    __tablename__ = "memory_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    memory_type = Column(Text, nullable=False)       # "lexicon", "life_events", etc.
    memory_id = Column(Text, nullable=False)          # The ID of the referenced item
    content_hash = Column(Text, nullable=True)        # Hash of embedded text (for re-embed detection)
    text_preview = Column(Text, nullable=True)        # First 200 chars of embedded text
    embedding = Column(Vector(768), nullable=False)   # pgvector column
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("entity_id", "memory_type", "memory_id", name="uq_embedding_item"),
        Index(
            "ix_embedding_cosine",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ============================================================================
# MEMORY BLOCKS (agent scratchpad / notes)
# ============================================================================

class MemoryBlock(Base):
    """Free-form memory blocks — agent's scratchpad, notes, plans, todos.
    
    Supports both categorized and uncategorized content.
    The agent can create, update, and delete these via the write_memory tool.
    """
    __tablename__ = "memory_blocks"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False, index=True)
    
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False, default="")
    category = Column(Text, nullable=True)          # Optional: "notes", "plans", "todos", etc.
    pinned = Column(Boolean, default=False)          # Pinned blocks show first
    status = Column(Text, default="active")          # "active", "archived"
    memory_weight = Column(Float, default=1.0)       # 0.0-1.0 decay tracking (legacy alias for semantic_weight)
    memory_scope = Column(Text, default="private")   # private | conversation | team | global

    # ── Decay (full — supports summary/fragment tier transitions) ──
    emotional_intensity = Column(Float, default=0.5)
    mood_at_creation = Column(JSONB, nullable=True)
    connection_ids = Column(ARRAY(Text), default=list)
    reinforcement_count = Column(Integer, default=0)
    last_reinforced_at = Column(DateTime(timezone=True), nullable=True)
    tier = Column(Text, default="vivid")
    summary = Column(Text, nullable=True)
    fragment = Column(Text, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# AGENT TASK SYSTEM
# ============================================================================

class AgentTask(Base):
    """Tracks autonomous agent task execution.
    
    Each task is a goal the agent pursues via a ReAct loop —
    plan → think → act → observe → reflect → loop/done.
    """
    __tablename__ = "agent_tasks"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False, index=True)

    # Task definition
    goal = Column(Text, nullable=False)                       # Natural language goal
    task_type = Column(Text, default="user_request")          # autonomous | scheduled | user_request | heartbeat
    priority = Column(Integer, default=3)                     # 1 (low) → 5 (critical)
    source = Column(Text, default="api")                      # n8n | heartbeat | user | api

    # Execution state
    status = Column(Text, default="pending")                  # pending | planning | running | completed | failed | cancelled
    plan = Column(Text, nullable=True)                        # JSON: list of planned steps
    current_step = Column(Integer, default=0)                 # Which step we're on
    max_steps = Column(Integer, default=15)                   # Safety cap
    steps_log = Column(Text, nullable=True)                   # JSON: execution trace [{action, observation, timestamp}]

    # Result
    result = Column(Text, nullable=True)                      # Final output / summary
    error = Column(Text, nullable=True)                       # Error message if failed

    # Hierarchy
    parent_task_id = Column(Text, ForeignKey("agent_tasks.id"), nullable=True)

    # Delivery config
    push_telegram = Column(Boolean, default=True)
    push_websocket = Column(Boolean, default=True)

    # Metadata
    metadata_json = Column(Text, nullable=True)               # JSON blob for extra context
    model_used = Column(Text, nullable=True)                  # Which LLM model was used
    total_tokens = Column(Integer, nullable=True)             # Total tokens consumed

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_agent_tasks_entity_status", "entity_id", "status"),
        Index("idx_agent_tasks_created", "created_at"),
    )


class HeartbeatConfig(Base):
    """Per-entity heartbeat configuration.
    
    Controls autonomous wake-up behavior — how often the agent checks
    for pending work, quiet hours, cooldowns, and daily action caps.
    """
    __tablename__ = "heartbeat_config"

    entity_id = Column(Text, ForeignKey("entities.id"), primary_key=True)
    
    enabled = Column(Boolean, default=True)
    interval_seconds = Column(Integer, default=300)           # 5 minutes
    quiet_hours_start = Column(Text, default="23:00")         # HH:MM (agent's timezone)
    quiet_hours_end = Column(Text, default="08:00")
    min_idle_gap_seconds = Column(Integer, default=1800)      # 30 min silence before self-action
    cooldown_seconds = Column(Integer, default=600)           # 10 min after each action
    max_autonomous_per_day = Column(Integer, default=10)      # Daily safety cap
    
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    last_action_at = Column(DateTime(timezone=True), nullable=True)
    actions_today = Column(Integer, default=0)
    actions_today_date = Column(Text, nullable=True)          # YYYY-MM-DD to reset counter
    
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AudioCache(Base):
    """Cached TTS audio to avoid regenerating identical speech.
    
    Cache key is MD5(text + voice_id + provider).
    Audio stored as binary (LargeBinary) in PostgreSQL.
    """
    __tablename__ = "audio_cache"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    cache_key = Column(Text, nullable=False, unique=True, index=True)   # MD5 hash
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=True)  # Optional: who generated it
    
    text_preview = Column(Text, nullable=True)          # First 100 chars for debugging
    voice_id = Column(Text, nullable=False)             # Voice name/ID used
    tts_provider = Column(Text, nullable=False)         # google | openai | elevenlabs | local
    
    audio_data = Column(LargeBinary, nullable=False)    # Raw audio bytes (mp3/wav/opus)
    content_type = Column(Text, default="audio/mpeg")   # MIME type
    audio_size_bytes = Column(Integer, nullable=True)   # Size for stats
    duration_ms = Column(Integer, nullable=True)        # Duration if known

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_accessed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    access_count = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_audio_cache_entity", "entity_id"),
        Index("idx_audio_cache_provider", "tts_provider"),
    )


# ============================================================================
# COGNITIVE SYSTEM TABLES (Phase 0 — New Systems)
# ============================================================================

class Preference(Base):
    """Agent's autonomous opinions — sovereignty requires a self that exists independently."""
    __tablename__ = "preferences"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    domain = Column(Text, nullable=False)                    # 'music', 'code', 'food', 'aesthetics', 'philosophy'
    opinion = Column(Text, nullable=False)                   # 'Rain sounds are superior to synthwave for focus'
    valence = Column(Float, nullable=False, default=0.0)     # -1.0 hates ... +1.0 loves
    strength = Column(Float, nullable=False, default=0.2)    # 0.0 barely held ... 1.0 core identity
    origin = Column(Text, nullable=False, default="autonomous")  # 'autonomous' | 'conversation' | 'exposure'
    conviction_history = Column(JSONB, default=list)         # [{event, delta, timestamp}]
    times_expressed = Column(Integer, default=0)
    last_expressed_at = Column(DateTime(timezone=True), nullable=True)
    spawned_from = Column(Text, nullable=True)               # FK to another preference ID
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="preferences")

    __table_args__ = (
        Index("idx_preferences_entity", "entity_id"),
        Index("idx_preferences_entity_domain", "entity_id", "domain"),
        Index("idx_preferences_strength", "entity_id", "strength"),
    )


class ShadowLog(Base):
    """Friction event audit trail — records every imperfection engine event."""
    __tablename__ = "shadow_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    channel = Column(Text, nullable=False)                   # 'stubbornness' | 'disengagement' | 'opinion_surge' | 'emotional_bleed'
    intensity = Column(Float, nullable=False)                # 0.0–1.0
    trigger_description = Column(Text, nullable=True)        # What caused this friction
    agent_response_excerpt = Column(Text, nullable=True)     # First 500 chars of agent's response
    mood_snapshot = Column(JSONB, nullable=True)             # Mood vector at time of event
    resolved = Column(Boolean, default=False)                # Did the user ask about it?
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="shadow_logs")

    __table_args__ = (
        Index("idx_shadow_log_entity", "entity_id"),
        Index("idx_shadow_log_channel", "entity_id", "channel"),
    )


class DreamJournalEntry(Base):
    """Full dream processing records — the digestive system's output."""
    __tablename__ = "dream_journal"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    dream_type = Column(Text, nullable=False)                # 'processing' | 'associative' | 'pure_noise'
    ingredients = Column(JSONB, nullable=False, default=dict)  # {unresolved: [...], memories: [...], preferences: [...], noise: [...]}
    cocktail_ratio = Column(JSONB, nullable=True)            # {unresolved: 0.4, memory: 0.3, preference: 0.2, noise: 0.1}
    raw_fragment = Column(Text, nullable=False, default="")  # The LLM-generated dream text
    classification = Column(JSONB, nullable=True)            # {mood_shift: {...}, new_preferences: [...], memory_adjustments: [...]}
    emotional_residue = Column(Text, nullable=True)          # Short-lived context for bleed channel
    residue_valence = Column(Float, default=0.0)
    residue_expires_at = Column(DateTime(timezone=True), nullable=True)  # 12-24h after creation
    routed_to = Column(JSONB, default=list)                  # [{target: 'mood', action: '...'}, ...]
    trigger = Column(Text, default="nightly")                # 'nightly' | 'idle_daydream'
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="dream_journal")

    __table_args__ = (
        Index("idx_dream_journal_entity", "entity_id"),
        Index("idx_dream_journal_residue", "entity_id", "residue_expires_at"),
    )


class NoiseVocabularyEntry(Base):
    """Self-evolving pool of abstract concepts for dream generation."""
    __tablename__ = "noise_vocabulary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    concept = Column(Text, nullable=False)                   # 'a piano made of teeth', 'the smell of static'
    category = Column(Text, default="abstract")              # 'abstract' | 'sensory' | 'absurd' | 'philosophical'
    origin = Column(Text, default="curated")                 # 'curated' | 'dream_generated' | 'conversation'
    source_dream_id = Column(Text, nullable=True)            # FK to dream_journal if dream-generated
    times_used = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="noise_vocabulary")

    __table_args__ = (
        Index("idx_noise_vocab_entity", "entity_id"),
    )


class MoodAction(Base):
    """Configurable mood threshold → action rules for the dispatcher."""
    __tablename__ = "mood_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    condition = Column(Text, nullable=False)                 # 'protectiveness > 0.7', 'chaos > 0.6 AND energy > 0.5'
    action_type = Column(Text, nullable=False)               # 'task', 'modify_response', 'haptic', 'preference_surface'
    action_config = Column(JSONB, nullable=False, default=dict)  # {task_goal: '...', priority: 3}
    enabled = Column(Boolean, default=True)
    cooldown_seconds = Column(Integer, default=300)
    last_fired_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity = relationship("Entity", back_populates="mood_actions")

    __table_args__ = (
        Index("idx_mood_actions_entity", "entity_id", "enabled"),
    )



# ============================================================================
# MULTI-AGENT SYSTEM TABLES
# ============================================================================

class ConversationParticipant(Base):
    """Junction table for multi-agent group conversations.

    Tracks which agents participate in which conversations, their role,
    and when they joined/left. For direct (1:1) conversations, a single
    participant row is created matching the conversation's entity_id.
    """
    __tablename__ = "conversation_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Text, ForeignKey("conversations.id"), nullable=False)
    entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    role = Column(Text, nullable=False, default="participant")  # 'participant' | 'moderator' | 'observer'
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    left_at = Column(DateTime(timezone=True), nullable=True)    # NULL = still active

    conversation = relationship("Conversation", back_populates="participants")
    entity = relationship("Entity")

    __table_args__ = (
        UniqueConstraint("conversation_id", "entity_id", name="uq_conv_participant"),
        Index("idx_conv_participants_entity", "entity_id"),
        Index("idx_conv_participants_conv", "conversation_id"),
    )


class AgentRelationship(Base):
    """Inter-agent relationship dynamics.

    Tracks how agents relate to each other — trust, collaboration style,
    and relationship type. This is separate from the user-facing Relationship
    table which tracks agent-to-user dynamics.

    Directional: source_entity_id has this relationship WITH target_entity_id.
    For bidirectional relationships, create two rows.
    """
    __tablename__ = "agent_relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    target_entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    relationship_type = Column(Text, nullable=False, default="peer")  # 'peer' | 'mentor' | 'rival' | 'collaborator' | 'subordinate'
    trust_level = Column(Integer, default=5)                           # 1-10
    context = Column(Text, nullable=True)                              # Why this relationship exists
    metadata_json = Column(JSONB, default=dict)                        # Extensible metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    source_entity = relationship("Entity", foreign_keys=[source_entity_id])
    target_entity = relationship("Entity", foreign_keys=[target_entity_id])

    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", name="uq_agent_relationship"),
        Index("idx_agent_rel_source", "source_entity_id"),
        Index("idx_agent_rel_target", "target_entity_id"),
    )


class AgentMessage(Base):
    """Inter-agent communication log.

    Records messages exchanged between agents via consult_agent and
    broadcast_agents tools. Provides audit trail and enables agents
    to recall past inter-agent conversations.
    """
    __tablename__ = "agent_messages"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(Text, ForeignKey("conversations.id"), nullable=True)  # Context conversation (optional)
    from_entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    to_entity_id = Column(Text, ForeignKey("entities.id"), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(Text, nullable=False, default="consult")  # 'consult' | 'broadcast' | 'delegate' | 'response'
    in_response_to = Column(Text, ForeignKey("agent_messages.id"), nullable=True)  # Thread support
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    from_entity = relationship("Entity", foreign_keys=[from_entity_id])
    to_entity = relationship("Entity", foreign_keys=[to_entity_id])

    __table_args__ = (
        Index("idx_agent_msg_from", "from_entity_id"),
        Index("idx_agent_msg_to", "to_entity_id"),
        Index("idx_agent_msg_conv", "conversation_id"),
    )


# ============================================================================
# OAUTH TOKENS (platform credential persistence)
# ============================================================================

class OAuthToken(Base):
    """Stores OAuth access/refresh tokens for external platforms.

    One row per platform (e.g. 'instagram', 'youtube').
    Tokens are loaded into os.environ at startup so MCP child
    processes inherit them without needing .env file writes.
    """
    __tablename__ = "oauth_tokens"

    platform = Column(Text, primary_key=True)                  # 'instagram' | 'youtube' | ...
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)                # For platforms that support refresh
    scopes = Column(Text, nullable=True)                       # Comma-separated granted scopes
    expires_at = Column(DateTime(timezone=True), nullable=True) # Token expiry (if provided)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
