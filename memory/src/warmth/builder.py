"""
Warm Memory Builder.

Assembles runtime context from PostgreSQL for injection into agent prompts.
Configurable detail levels: concise, standard, detailed, full.
"""

from typing import Literal
from datetime import datetime, timezone

from src.db.models import (
    Entity, PersonaIdentity, Lexicon, Narrative, UnresolvedThread,
    EmotionalPattern, StateNeed, Permission, RelationalRitual,
    SharedMythology, Relationship, InsideJoke, IntimateMoment,
    LifeEvent, RepairPattern, Artifact, EchoDream, UserProfile, MemoryBlock,
    Preference
)
from src.db.session import get_session

WarmLevel = Literal["concise", "standard", "detailed", "full"]

# Character budgets per level (approximate targets for the formatter)
LEVEL_BUDGETS = {
    "concise": 4_000,
    "standard": 8_000,
    "detailed": 16_000,
    "full": 32_000,
}


def _filter_items(items: list, section_key: str, disabled_items: dict | None) -> list:
    """Filter out items whose IDs are in the disabled set for a given section."""
    if not disabled_items or section_key not in disabled_items:
        return items
    skip = {str(x) for x in disabled_items[section_key]}
    return [item for item in items if str(item.id) not in skip]


def _merge_pinned_items(session, items: list, section_key: str, model_class,
                        entity_id: str, pinned_items: dict | None,
                        id_field: str = "id") -> list:
    """Merge user-pinned items into a section's item list.
    
    If the user has pinned specific items (by ID) for a section,
    ensure those items are included even if they wouldn't normally
    be selected (e.g., below lore_score threshold or beyond limit).
    """
    if not pinned_items or section_key not in pinned_items:
        return items
    
    pinned_ids = {str(x) for x in pinned_items[section_key]}
    existing_ids = {str(getattr(item, id_field)) for item in items}
    missing_ids = pinned_ids - existing_ids
    
    if not missing_ids:
        return items
    
    # Bulk-fetch the missing pinned items from DB
    if id_field == "id":
        try:
            # Convert IDs to correct type (int if the PK is integer)
            import inspect
            pk_col = model_class.__table__.primary_key.columns.values()[0]
            cast = int if str(pk_col.type) in ("INTEGER", "BIGINT") else str
            typed_ids = []
            for pid in missing_ids:
                try:
                    typed_ids.append(cast(pid))
                except (ValueError, TypeError):
                    pass
            if typed_ids:
                objs = session.query(model_class).filter(
                    pk_col.in_(typed_ids),
                    model_class.entity_id == entity_id,
                ).all()
                items.extend(objs)
        except Exception:
            pass

    return items


def build_warm_memory(
    entity_id: str,
    level: WarmLevel = "standard",
    user_entity_id: str | None = None,
    disabled_items: dict[str, list[str]] | None = None,
    pinned_items: dict[str, list[str]] | None = None,
) -> dict:
    """
    Build warm memory context from the database.

    Returns a dict of named sections, each a string ready for formatting.
    Sections included depend on the budget level.

    Args:
        entity_id: Agent entity ID
        level: Detail level (concise/standard/detailed/full)
        user_entity_id: Optional user entity ID for user profile lookup
        disabled_items: Optional dict mapping section_key -> list of item IDs to exclude
        pinned_items: Optional dict mapping section_key -> list of item IDs to force-include
    """
    sections = {}

    with get_session() as session:
        # ══════════════════════════════════════════════════════════
        # ALWAYS INCLUDED (all levels)
        # ══════════════════════════════════════════════════════════

        # Persona Identity
        persona = session.get(PersonaIdentity, entity_id)
        if persona:
            sections["persona"] = _build_persona(persona)

        # Recent Narrative (current version only)
        recent = (
            session.query(Narrative)
            .filter_by(entity_id=entity_id, scope="recent", is_current=True)
            .order_by(Narrative.updated_at.desc())
            .first()
        )
        if recent:
            sections["recent_narrative"] = recent.content

        # Active Threads
        threads = (
            session.query(UnresolvedThread)
            .filter_by(entity_id=entity_id, status="open")
            .order_by(UnresolvedThread.created_at.desc())
            .limit(10)
            .all()
        )
        threads = _filter_items(threads, "active_threads", disabled_items)
        if threads:
            sections["active_threads"] = _build_threads(threads)

        # Session Bridge (current version only)
        # Combined with recent narrative for richer context continuity
        bridge = (
            session.query(Narrative)
            .filter_by(entity_id=entity_id, scope="bridge", is_current=True)
            .order_by(Narrative.updated_at.desc())
            .first()
        )
        if bridge:
            bridge_text = bridge.content or ""
            recent_text = sections.get("recent_narrative", "")
            # Skip bridge if it's nearly identical to recent narrative
            if recent_text and bridge_text:
                overlap = sum(1 for w in bridge_text.split() if w in recent_text)
                total = len(bridge_text.split()) or 1
                if overlap / total < 0.6:
                    sections["session_bridge"] = bridge_text
            else:
                sections["session_bridge"] = bridge_text

        if level == "concise":
            return sections

        # ══════════════════════════════════════════════════════════
        # STANDARD level additions
        # ══════════════════════════════════════════════════════════

        # Sacred Lexicon (lore_score >= 6, top 10)
        lexicon = (
            session.query(Lexicon)
            .filter_by(entity_id=entity_id)
            .filter(Lexicon.lore_score >= 6)
            .filter(Lexicon.status.in_(["active", "evolved"]))
            .order_by(Lexicon.lore_score.desc())
            .limit(10)
            .all()
        )
        lexicon = _filter_items(lexicon, "lexicon", disabled_items)
        lexicon = _merge_pinned_items(
            session, lexicon, "lexicon", Lexicon, entity_id, pinned_items
        )
        if lexicon:
            sections["lexicon"] = _build_lexicon(lexicon)

        # Active Permissions (top 10 most recent)
        permissions = (
            session.query(Permission)
            .filter_by(entity_id=entity_id, status="active")
            .order_by(Permission.created_at.desc())
            .limit(10)
            .all()
        )
        permissions = _filter_items(permissions, "permissions", disabled_items)
        permissions = _merge_pinned_items(
            session, permissions, "permissions", Permission, entity_id, pinned_items
        )
        if permissions:
            sections["permissions"] = _build_permissions(permissions)

        # Primary Relationship
        primary_rel = (
            session.query(Relationship)
            .filter_by(entity_id=entity_id, target_id="user")
            .first()
        )
        if primary_rel:
            sections["relationship"] = _build_relationship(primary_rel)

        # User Profile (promoted above mythology/seasonal — more important at standard level)
        profile_id = user_entity_id or entity_id
        profile = session.get(UserProfile, profile_id)
        if profile:
            sections["user_profile"] = _build_user_profile(profile)

        # Memory Blocks (pinned ones at standard level, up to 10)
        pinned_blocks = (
            session.query(MemoryBlock)
            .filter_by(entity_id=entity_id, status="active", pinned=True)
            .order_by(MemoryBlock.updated_at.desc())
            .limit(10)
            .all()
        )
        pinned_blocks = _filter_items(pinned_blocks, "memory_blocks", disabled_items)
        if pinned_blocks:
            sections["memory_blocks"] = _build_memory_blocks(pinned_blocks)
            
        # Active Preferences (Autonomous Opinions) — gated: standard+
        from src.edition import has_feature, Feature as EditionFeature
        if has_feature(EditionFeature.PREFERENCE_ENGINE):
            from src.services.preference_engine import get_active_preferences
            active_prefs = get_active_preferences(session, entity_id, limit=5)
            if active_prefs:
                sections["active_preferences"] = _build_preferences(active_prefs)

        # Emotional Patterns (promoted from detailed) — gated: standard+
        if has_feature(EditionFeature.MOOD_ENGINE):
            patterns = (
                session.query(EmotionalPattern)
                .filter_by(entity_id=entity_id, status="active")
                .limit(5)
                .all()
            )
            patterns = _filter_items(patterns, "emotional_patterns", disabled_items)
            if patterns:
                sections["emotional_patterns"] = _build_patterns(patterns)

        # Most Recent Echo Dream (promoted from detailed) — gated: pro+
        if has_feature(EditionFeature.DREAM_ENGINE):
            dream = (
                session.query(EchoDream)
                .filter_by(entity_id=entity_id)
                .order_by(EchoDream.created_at.desc())
                .first()
            )
            if dream:
                sections["echo_dream"] = _build_dream(dream)

        # Recent Life Events (promoted from detailed)
        sections["recent_events"] = []
        events = (
            session.query(LifeEvent)
            .filter_by(entity_id=entity_id)
            .filter(LifeEvent.tier != "archived")
            .order_by(LifeEvent.semantic_weight.desc().nulls_last())
            .limit(10)
            .all()
        )

        for ev in events:
            # For hazy/fading tiers, use the summary/fragment instead of full narrative
            if ev.tier == "fading" and ev.fragment:
                content = ev.fragment
            elif ev.tier == "hazy" and ev.summary:
                content = ev.summary
            else:
                content = ev.narrative

            sections["recent_events"].append({
                "title": ev.title,
                "content": content,
                "tier": ev.tier,
                "weight": ev.semantic_weight,
            })

        # Inside Jokes (promoted from full)
        if primary_rel:
            jokes = (
                session.query(InsideJoke)
                .filter_by(relationship_id=primary_rel.id)
                .limit(5)
                .all()
            )
            jokes = _filter_items(jokes, "inside_jokes", disabled_items)
            if jokes:
                sections["inside_jokes"] = _build_jokes(jokes)

            # Intimate Moments (promoted from full)
            moments = (
                session.query(IntimateMoment)
                .filter_by(relationship_id=primary_rel.id)
                .order_by(IntimateMoment.created_at.desc())
                .limit(3)
                .all()
            )
            moments = _filter_items(moments, "intimate_moments", disabled_items)
            if moments:
                sections["intimate_moments"] = _build_moments(moments)

        # Rituals (promoted from full)
        rituals = (
            session.query(RelationalRitual)
            .filter_by(entity_id=entity_id)
            .limit(5)
            .all()
        )
        rituals = _filter_items(rituals, "rituals", disabled_items)
        if rituals:
            sections["rituals"] = _build_rituals(rituals)

        if level == "standard":
            return sections

        # ══════════════════════════════════════════════════════════
        # DETAILED level additions (budget > 8K)
        # ══════════════════════════════════════════════════════════

        # Shared Mythology (moved from standard — expensive section)
        mythology = (
            session.query(SharedMythology)
            .filter_by(entity_id=entity_id)
            .first()
        )
        if mythology:
            sections["mythology"] = _build_mythology(mythology)

        # Seasonal + Lifetime Narratives (current version only)
        for scope in ("seasonal", "lifetime"):
            narr = (
                session.query(Narrative)
                .filter_by(entity_id=entity_id, scope=scope, is_current=True)
                .order_by(Narrative.updated_at.desc())
                .first()
            )
            if narr:
                sections[f"{scope}_narrative"] = narr.content

        # State Needs
        state_needs = (
            session.query(StateNeed)
            .filter_by(entity_id=entity_id)
            .all()
        )
        state_needs = _filter_items(state_needs, "state_needs", disabled_items)
        if state_needs:
            sections["state_needs"] = _build_state_needs(state_needs)

        # Repair Patterns
        repairs = (
            session.query(RepairPattern)
            .filter_by(entity_id=entity_id)
            .order_by(RepairPattern.created_at.desc())
            .limit(5)
            .all()
        )
        repairs = _filter_items(repairs, "repair_patterns", disabled_items)
        if repairs:
            sections["repair_patterns"] = _build_repairs(repairs)

        # Emotional Patterns
        patterns = (
            session.query(EmotionalPattern)
            .filter_by(entity_id=entity_id, status="active")
            .limit(10)
            .all()
        )
        patterns = _filter_items(patterns, "emotional_patterns", disabled_items)
        if patterns:
            sections["emotional_patterns"] = _build_patterns(patterns)

        # Recent Life Events
        sections["recent_events"] = []
        events = (
            session.query(LifeEvent)
            .filter_by(entity_id=entity_id)
            .filter(LifeEvent.tier != "archived")
            .order_by(LifeEvent.semantic_weight.desc().nulls_last())
            .limit(10)
            .all()
        )

        for ev in events:
            # For hazy/fading tiers, use the summary/fragment instead of full narrative
            if ev.tier == "fading" and ev.fragment:
                content = ev.fragment
            elif ev.tier == "hazy" and ev.summary:
                content = ev.summary
            else:
                content = ev.narrative

            sections["recent_events"].append({
                "title": ev.title,
                "content": content,
                "tier": ev.tier,
                "weight": ev.semantic_weight,
            })

        if has_feature(EditionFeature.DREAM_ENGINE):
            dream = (
                session.query(EchoDream)
                .filter_by(entity_id=entity_id)
                .order_by(EchoDream.created_at.desc())
                .first()
            )
            if dream:
                sections["echo_dream"] = _build_dream(dream)

        # All Active Memory Blocks (added at detailed level)
        sections["memory_blocks"] = []
        blocks = (
            session.query(MemoryBlock)
            .filter_by(entity_id=entity_id, status="active")
            .filter(MemoryBlock.tier != "archived")
            .order_by(
                MemoryBlock.pinned.desc(),
                MemoryBlock.memory_weight.desc().nulls_last(),
                MemoryBlock.updated_at.desc()
            )
            .limit(10)
            .all()
        )

        for b in blocks:
            # Use degraded content if available based on tier
            if b.tier == "fading" and b.fragment:
                content = b.fragment
            elif b.tier == "hazy" and b.summary:
                content = b.summary
            else:
                content = b.content
                
            sections["memory_blocks"].append({
                "id": b.id,
                "title": b.title,
                "category": b.category or "uncategorized",
                "pinned": b.pinned,
                "content": content,
                "tier": b.tier,
                "weight": b.memory_weight,
            })

        if level == "detailed":
            return sections

        # ══════════════════════════════════════════════════════════
        # FULL level additions
        # ══════════════════════════════════════════════════════════

        # Inside Jokes
        if primary_rel:
            jokes = (
                session.query(InsideJoke)
                .filter_by(relationship_id=primary_rel.id)
                .limit(15)
                .all()
            )
            jokes = _filter_items(jokes, "inside_jokes", disabled_items)
            if jokes:
                sections["inside_jokes"] = _build_jokes(jokes)

            # Intimate Moments
            moments = (
                session.query(IntimateMoment)
                .filter_by(relationship_id=primary_rel.id)
                .order_by(IntimateMoment.created_at.desc())
                .limit(10)
                .all()
            )
            moments = _filter_items(moments, "intimate_moments", disabled_items)
            if moments:
                sections["intimate_moments"] = _build_moments(moments)

        # Rituals
        rituals = (
            session.query(RelationalRitual)
            .filter_by(entity_id=entity_id)
            .all()
        )
        rituals = _filter_items(rituals, "rituals", disabled_items)
        if rituals:
            sections["rituals"] = _build_rituals(rituals)

        # All Lexicon (not just high-score)
        all_lexicon = (
            session.query(Lexicon)
            .filter_by(entity_id=entity_id)
            .filter(Lexicon.status.in_(["active", "evolved"]))
            .order_by(Lexicon.lore_score.desc())
            .all()
        )
        all_lexicon = _filter_items(all_lexicon, "lexicon", disabled_items)
        if all_lexicon:
            sections["lexicon"] = _build_lexicon(all_lexicon)

        # All Artifacts (titles + context)
        artifacts = (
            session.query(Artifact)
            .filter_by(entity_id=entity_id)
            .order_by(Artifact.created_at.desc())
            .limit(20)
            .all()
        )
        artifacts = _filter_items(artifacts, "artifacts", disabled_items)
        if artifacts:
            sections["artifacts"] = _build_artifacts(artifacts)

    return sections


# ============================================================================
# Section Formatters (internal)
# ============================================================================

def _build_persona(p: PersonaIdentity) -> str:
    parts = []
    # Rich character narrative (if set — this is the primary identity block)
    if p.description:
        parts.append(p.description)
    # Brief trait keywords (supplement the narrative)
    meta = []
    if p.core and not p.description:
        meta.append(f"Core: {p.core}")
    if p.archetype:
        meta.append(f"Archetype: {p.archetype}")
    if p.voice_style:
        meta.append(f"Voice: {p.voice_style}")
    if p.traits:
        meta.append(f"Traits: {', '.join(p.traits)}")
    if p.values_core:
        meta.append(f"Values: {', '.join(p.values_core)}")
    if p.goals_long_term:
        meta.append(f"Goals: {', '.join(p.goals_long_term)}")
    if meta:
        parts.append("\n".join(meta))
    return "\n\n".join(parts)


def _build_threads(threads: list) -> str:
    items = []
    for t in threads:
        weight = f" [{t.emotional_weight}]" if t.emotional_weight else ""
        items.append(f"• {t.thread}{weight}")
        if t.what_user_needs:
            items.append(f"  → Needs: {t.what_user_needs}")
    return "\n".join(items)


def _build_lexicon(entries: list) -> str:
    items = []
    for lex in entries:
        score = f" ({'★' * min(lex.lore_score or 0, 10)})" if lex.lore_score else ""
        items.append(f"• {lex.term}{score}: {lex.definition}")
    return "\n".join(items)


def _build_permissions(perms: list) -> str:
    allows = [p for p in perms if p.type == "allow"]
    denies = [p for p in perms if p.type == "deny"]
    parts = []
    if allows:
        parts.append("Allowed:")
        for p in allows:
            parts.append(f"  ✓ {p.permission}")
    if denies:
        parts.append("Forbidden:")
        for p in denies:
            parts.append(f"  ✗ {p.permission}")
    return "\n".join(parts)


def _build_relationship(rel: Relationship) -> str:
    parts = []
    if rel.trust_level:
        parts.append(f"Trust: {rel.trust_level}/10")
    if rel.trust_narrative:
        parts.append(f"Trust Dynamics: {rel.trust_narrative}")
    if rel.attachment_claimed:
        parts.append(f"Attachment: {rel.attachment_claimed}")
    if rel.attachment_observed:
        parts.append(f"Observed Attachment: {rel.attachment_observed}")
    if rel.communication_style:
        parts.append(f"Communication: {rel.communication_style}")
    if rel.emotional_bank_current:
        parts.append(f"Emotional Bank: {rel.emotional_bank_current}")
    if rel.narrative_emotional_tone:
        parts.append(f"Tone: {rel.narrative_emotional_tone}")
    if rel.narrative_current_arc:
        parts.append(f"Current Arc: {rel.narrative_current_arc}")
    return "\n".join(parts) if parts else "Primary relationship established"


def _build_mythology(myth: SharedMythology) -> str:
    parts = []
    if myth.origin_story:
        parts.append(f"Origin: {myth.origin_story[:300]}")
    if myth.universe_rules:
        parts.append("Rules: " + "; ".join(myth.universe_rules[:5]))
    if myth.active_arcs:
        parts.append("Active Arcs: " + ", ".join(myth.active_arcs[:5]))
    return "\n".join(parts)


def _build_state_needs(needs: list) -> str:
    items = []
    for s in needs:
        items.append(f"• When {s.state}: {s.needs}")
        if s.anti_needs:
            items.append(f"  ✗ Avoid: {s.anti_needs}")
    return "\n".join(items)


def _build_repairs(repairs: list) -> str:
    items = []
    for r in repairs:
        items.append(f"• Trigger: {r.trigger}")
        items.append(f"  Rupture: {r.rupture}")
        items.append(f"  Repair: {r.repair}")
        if r.lesson:
            items.append(f"  Lesson: {r.lesson}")
    return "\n".join(items)


def _build_patterns(patterns: list) -> str:
    items = []
    for p in patterns:
        items.append(f"• {p.name}")
        if p.trigger_what:
            items.append(f"  Trigger: {p.trigger_what}")
        if p.response_external:
            items.append(f"  Response: {p.response_external}")
    return "\n".join(items)

def _build_preferences(prefs: list) -> str:
    items = []
    # Convert numerical strength to a readable intensity tag
    for p in prefs:
        if p.strength >= 0.8: tag = "core identity"
        elif p.strength >= 0.6: tag = "strong"
        elif p.strength >= 0.3: tag = "moderate"
        else: tag = "tentative"
        
        items.append(f"• [{p.domain} | {tag}] \"{p.opinion}\" ({p.strength:.2f})")
    
    return "\n".join(items)


def _build_events(events: list) -> str:
    items = []
    for e in events:
        period = f" ({e.period})" if e.period else ""
        items.append(f"• {e.title}{period}: {e.narrative[:200]}")
    return "\n".join(items)


def _build_dream(dream: EchoDream) -> str:
    parts = []
    if dream.setting_description:
        parts.append(f"Setting: {dream.setting_description}")
    if dream.whisper:
        speaker = dream.whisper_speaker or "unknown"
        parts.append(f'Whisper ({speaker}): "{dream.whisper}"')
    if dream.truth_root:
        parts.append(f"Truth: {dream.truth_root}")
    if dream.emotion_tags:
        parts.append(f"Emotions: {', '.join(dream.emotion_tags)}")
    return "\n".join(parts)


def _build_jokes(jokes: list) -> str:
    items = []
    for j in jokes:
        items.append(f'• "{j.phrase}" — {j.origin or "origin unknown"} [{j.tone}]')
    return "\n".join(items)


def _build_moments(moments: list) -> str:
    items = []
    for m in moments:
        sig = f" [{m.significance}]" if m.significance else ""
        items.append(f"• {m.summary[:150]}{sig}")
    return "\n".join(items)


def _build_rituals(rituals: list) -> str:
    items = []
    for r in rituals:
        items.append(f"• {r.name}: {r.pattern}")
    return "\n".join(items)


def _build_artifacts(artifacts: list) -> str:
    items = []
    for a in artifacts:
        items.append(f"• [{a.type}] {a.title}: {a.context or 'no context'}")
    return "\n".join(items)


def _build_user_profile(profile: UserProfile) -> str:
    parts = []
    # Core Identity
    if profile.name:
        parts.append(f"Name: {profile.name}")
    if profile.pronouns:
        parts.append(f"Pronouns: {profile.pronouns}")
    if profile.age_range:
        parts.append(f"Age: {profile.age_range}")
    if profile.location:
        parts.append(f"Location: {profile.location}")
    if profile.languages:
        parts.append(f"Languages: {', '.join(profile.languages)}")
    # Neurotype & Cognition
    if profile.neurotype:
        parts.append(f"Neurotype: {profile.neurotype}")
    if profile.thinking_patterns:
        parts.append(f"Thinking: {', '.join(profile.thinking_patterns)}")
    if profile.cognitive_strengths:
        parts.append(f"Strengths: {', '.join(profile.cognitive_strengths)}")
    if profile.cognitive_challenges:
        parts.append(f"Challenges: {', '.join(profile.cognitive_challenges)}")
    # Attachment & Emotional
    if profile.attachment_style:
        parts.append(f"Attachment: {profile.attachment_style}")
    if profile.attachment_notes:
        parts.append(f"Attachment notes: {profile.attachment_notes}")
    if profile.ifs_parts:
        parts.append(f"IFS parts: {', '.join(profile.ifs_parts)}")
    if profile.emotional_triggers:
        parts.append(f"Triggers: {', '.join(profile.emotional_triggers)}")
    if profile.coping_mechanisms:
        parts.append(f"Coping: {', '.join(profile.coping_mechanisms)}")
    # Health
    if profile.medical_conditions:
        parts.append(f"Health: {', '.join(profile.medical_conditions)}")
    if profile.medications:
        parts.append(f"Medications: {', '.join(profile.medications)}")
    if profile.health_notes:
        parts.append(f"Health notes: {profile.health_notes}")
    # Life Situation
    if profile.relationship_status:
        parts.append(f"Relationship: {profile.relationship_status}")
    if profile.family_situation:
        parts.append(f"Family: {profile.family_situation}")
    if profile.living_situation:
        parts.append(f"Living: {profile.living_situation}")
    if profile.work_situation:
        parts.append(f"Work: {profile.work_situation}")
    if profile.financial_notes:
        parts.append(f"Finances: {profile.financial_notes}")
    # Interests & Goals
    if profile.hobbies:
        parts.append(f"Hobbies: {', '.join(profile.hobbies)}")
    if profile.interests:
        parts.append(f"Interests: {', '.join(profile.interests)}")
    if profile.life_goals:
        parts.append(f"Goals: {', '.join(profile.life_goals)}")
    if profile.longings:
        parts.append(f"Longings: {', '.join(profile.longings)}")
    if profile.current_projects:
        parts.append(f"Projects: {', '.join(profile.current_projects)}")
    # Communication
    if profile.preferred_communication_style:
        parts.append(f"Communication: {profile.preferred_communication_style}")
    if profile.humor_style:
        parts.append(f"Humor: {profile.humor_style}")
    if profile.boundary_preferences:
        parts.append(f"Boundaries: {profile.boundary_preferences}")
    if profile.support_preferences:
        parts.append(f"Support: {profile.support_preferences}")
    return "\n".join(parts)


def _build_memory_blocks(blocks):
    """Format memory blocks for warm memory display."""
    lines = []
    for b in blocks:
        tag = f" [{b.category}]" if b.category else ""
        pin = " 📌" if b.pinned else ""
        lines.append(f"• [ID: {b.id}] {b.title}{tag}{pin}")
        if b.content:
            preview = b.content[:10000] + "…" if len(b.content) > 10000 else b.content
            lines.append(f"  {preview}")
    return "\n".join(lines)
