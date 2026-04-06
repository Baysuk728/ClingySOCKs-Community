"""
Context Builder routes — preview, section management, and graph visualization.

Endpoints for the Context Builder UI:
- GET  /context/{entity_id}/preview   — Full context window preview with per-section details
- GET  /context/{entity_id}/sections  — List all sections with toggle state and char counts
- PUT  /context/{entity_id}/sections  — Update section ordering and enable/disable
- GET  /context/{entity_id}/graph     — Graph edges and nodes for visualization
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from typing import Any, Optional
from pydantic import BaseModel
import traceback

from api.auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


# ── Schemas ──────────────────────────────────────────────

class SectionItem(BaseModel):
    id: str
    label: str
    char_count: int

class SectionInfo(BaseModel):
    key: str
    label: str
    icon: str
    content: str
    char_count: int
    enabled: bool
    order: int
    items: list[SectionItem] | None = None

class MemoryBlockInfo(BaseModel):
    id: str
    title: str
    category: str | None
    pinned: bool
    char_count: int

class BudgetLimits(BaseModel):
    max_context_chars: Optional[int] = None  # Total context budget (None = unlimited)
    max_warm_memory: int
    max_history_chars: int
    max_history_messages: int

class ComponentSummary(BaseModel):
    system_instruction: int
    warm_memory_enabled: int
    dynamic_preamble: int
    tools: int
    history_estimate: int
    total: int

class ContextPreview(BaseModel):
    entity_id: str
    system_instruction: str
    system_instruction_chars: int
    sections: list[SectionInfo]
    dynamic_preamble: str
    dynamic_preamble_chars: int
    total_warm_chars: int
    budget: int
    budget_used_pct: float
    # Section ordering / preferences
    section_order: list[str]
    disabled_sections: list[str]
    disabled_items: dict[str, list[str]]
    pinned_items: dict[str, list[str]]
    voice_anchors: list[dict] | None = None
    # Full transparency fields
    active_model: str
    tools: list[str]
    tools_chars: int
    memory_blocks: list[MemoryBlockInfo]
    history_estimate_chars: int
    history_message_count: int
    budget_limits: BudgetLimits
    component_summary: ComponentSummary

class SectionConfigUpdate(BaseModel):
    section_order: list[str] | None = None
    disabled_sections: list[str] | None = None
    disabled_items: dict[str, list[str]] | None = None
    pinned_items: dict[str, list[str]] | None = None
    voice_anchors: list[dict] | None = None


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    group: str  # For coloring by type

class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    strength: float
    context: str | None = None
    status: str = "active"  # active | superseded | historical

class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    arcs: list[dict]
    stats: dict


# ── Section metadata (mirrors formatter.py SECTION_CONFIG) ──

SECTION_META = {
    "persona":             {"label": "Identity", "icon": "🔮"},
    "user_profile":        {"label": "About the User", "icon": "👤"},
    "session_bridge":      {"label": "Last Session", "icon": "🌉"},
    "recent_narrative":    {"label": "Recent Story", "icon": "📖"},
    "active_threads":      {"label": "Open Threads", "icon": "🧵"},
    "lexicon":             {"label": "Sacred Lexicon", "icon": "📜"},
    "permissions":         {"label": "Permissions", "icon": "🔐"},
    "memory_blocks":       {"label": "Agent Notes", "icon": "📝"},
    "relationship":        {"label": "Relationship", "icon": "💫"},
    "mythology":           {"label": "Shared Mythology", "icon": "🐉"},
    "seasonal_narrative":  {"label": "Seasonal Arc", "icon": "🌿"},
    "lifetime_narrative":  {"label": "Lifetime Arc", "icon": "⏳"},
    "state_needs":         {"label": "What They Need", "icon": "🫂"},
    "repair_patterns":     {"label": "Repair Patterns", "icon": "🩹"},
    "emotional_patterns":  {"label": "Emotional Patterns", "icon": "🌀"},
    "recent_events":       {"label": "Recent Events", "icon": "📅"},
    "echo_dream":          {"label": "Last Dream", "icon": "🌙"},
    "inside_jokes":        {"label": "Inside Jokes", "icon": "😂"},
    "intimate_moments":    {"label": "Key Moments", "icon": "✨"},
    "rituals":             {"label": "Rituals", "icon": "🕯️"},
    "artifacts":           {"label": "Artifacts", "icon": "🎨"},
}

DEFAULT_SECTION_ORDER = list(SECTION_META.keys())


def _load_context_preferences(entity_id: str) -> dict:
    """Load context preferences from persona_identity.context_preferences JSON column."""
    from src.db.session import get_session
    from src.db.models import PersonaIdentity
    import json

    with get_session() as session:
        persona = session.get(PersonaIdentity, entity_id)
        if persona and hasattr(persona, 'context_preferences') and persona.context_preferences:
            try:
                return json.loads(persona.context_preferences)
            except (json.JSONDecodeError, TypeError):
                pass
    return {}


def _save_context_preferences(entity_id: str, prefs: dict) -> None:
    """Save context preferences to persona_identity.context_preferences."""
    from src.db.session import get_session
    from src.db.models import PersonaIdentity
    import json

    with get_session() as session:
        persona = session.get(PersonaIdentity, entity_id)
        if persona:
            persona.context_preferences = json.dumps(prefs)
            session.commit()


# ── Routes ───────────────────────────────────────────────

@router.get("/{entity_id}/preview")
async def get_context_preview(
    entity_id: str,
    budget: int = Query(8000, description="Warm memory character budget"),
):
    """
    Get full context preview with per-section breakdown.
    Returns all sections with their content, char counts, and enabled state.
    """
    try:
        from src.warmth.builder import build_warm_memory
        from src.persona_config import load_persona_config
        from src.db.session import get_session
        from src.db.models import (
            PersonaIdentity, MemoryBlock, Conversation, Message,
            Permission, Lexicon, UnresolvedThread, EmotionalPattern,
            LifeEvent, InsideJoke, IntimateMoment, RelationalRitual,
            RepairPattern, StateNeed, Artifact, Relationship,
        )
        from src.tools.schemas import ALL_TOOL_SCHEMAS
        from datetime import datetime, timezone
        import json as _json

        # Load preferences
        prefs = _load_context_preferences(entity_id)
        section_order = prefs.get("section_order", DEFAULT_SECTION_ORDER)
        disabled_sections = prefs.get("disabled_sections", [])
        disabled_items = prefs.get("disabled_items", {})
        pinned_items = prefs.get("pinned_items", {})
        voice_anchors = prefs.get("voice_anchors", None)

        # Build raw warm memory data (all sections, unformatted)
        # Pass disabled_items so the builder filters out hidden items
        raw_sections = build_warm_memory(entity_id, level="full", disabled_items=disabled_items)

        # Load persona config (model, budgets, system prompt)
        try:
            persona_config = load_persona_config(entity_id)
            system_prompt = persona_config.system_prompt or ""
        except Exception:
            persona_config = None
            system_prompt = ""

        active_model = persona_config.model if persona_config else "unknown"
        max_context = persona_config.max_context_chars if persona_config else None
        max_warm = persona_config.max_warm_memory if persona_config else 8000
        max_hist_chars = persona_config.max_history_chars if persona_config else 20000
        max_hist_msgs = persona_config.max_history_messages if persona_config else 50

        # Use persona budget as default if not overridden by query param
        if budget == 8000 and max_warm != 8000:
            budget = max_warm

        system_instruction = ""
        if system_prompt:
            system_instruction = f"# CORE IDENTITY\n{system_prompt}\n\n"
        system_instruction += "# AVAILABLE TOOLS\n"
        system_instruction += "You have access to memory tools (recall, search, write, graph_traverse). Use them to retrieve facts or discover deep connections between memories.\n"

        # ── Tools ──
        builtin_tool_names = [
            t["function"]["name"] for t in ALL_TOOL_SCHEMAS
            if "function" in t and "name" in t["function"]
        ]
        # MCP tool names from config file
        all_tool_names = builtin_tool_names
        tools_text = _json.dumps(all_tool_names)
        tools_chars = len(tools_text)

        # ── Memory Blocks (individual) ──
        memory_block_infos = []
        with get_session() as session:
            blocks = (
                session.query(MemoryBlock)
                .filter_by(entity_id=entity_id, status="active")
                .order_by(MemoryBlock.pinned.desc(), MemoryBlock.updated_at.desc())
                .limit(20)
                .all()
            )
            for b in blocks:
                memory_block_infos.append(MemoryBlockInfo(
                    id=b.id,
                    title=b.title,
                    category=b.category,
                    pinned=b.pinned if b.pinned else False,
                    char_count=len(b.content) if b.content else 0,
                ))

            # ── History Estimate ──
            # Get the most recent conversation for this entity
            latest_conv = (
                session.query(Conversation)
                .filter_by(entity_id=entity_id)
                .order_by(Conversation.updated_at.desc())
                .first()
            )
            history_estimate_chars = 0
            history_message_count = 0
            if latest_conv:
                from sqlalchemy import func
                stats = (
                    session.query(
                        func.count(Message.id),
                        func.coalesce(func.sum(func.length(Message.content)), 0),
                    )
                    .filter(Message.conversation_id == latest_conv.id)
                    .first()
                )
                if stats:
                    history_message_count = stats[0] or 0
                    history_estimate_chars = stats[1] or 0

            # ── Per-item data for multi-item sections ──
            # Query ALL items (including disabled) so the UI can show toggles
            section_items: dict[str, list[SectionItem]] = {}
            disabled_set = {k: {str(x) for x in v} for k, v in disabled_items.items()} if disabled_items else {}

            # Permissions
            all_perms = session.query(Permission).filter_by(entity_id=entity_id, status="active").all()
            if all_perms:
                section_items["permissions"] = [
                    SectionItem(
                        id=str(p.id),
                        label=p.permission[:100],
                        char_count=len(f"  {'✓' if p.type == 'allow' else '✗'} {p.permission}"),
                    ) for p in all_perms
                ]

            # Lexicon
            all_lex = (
                session.query(Lexicon)
                .filter_by(entity_id=entity_id)
                .filter(Lexicon.status.in_(["active", "evolved"]))
                .order_by(Lexicon.lore_score.desc())
                .all()
            )
            if all_lex:
                section_items["lexicon"] = [
                    SectionItem(
                        id=str(l.id),
                        label=l.term,
                        char_count=len(f"• {l.term} ({'★' * min(l.lore_score or 0, 10)}): {l.definition}"),
                    ) for l in all_lex
                ]

            # Active Threads
            all_threads = (
                session.query(UnresolvedThread)
                .filter_by(entity_id=entity_id, status="open")
                .order_by(UnresolvedThread.created_at.desc())
                .limit(10).all()
            )
            if all_threads:
                def _thread_chars(t):
                    c = len(f"• {t.thread}" + (f" [{t.emotional_weight}]" if t.emotional_weight else ""))
                    if t.what_user_needs:
                        c += len(f"\n  → Needs: {t.what_user_needs}")
                    return c
                section_items["active_threads"] = [
                    SectionItem(id=str(t.id), label=t.thread[:80], char_count=_thread_chars(t))
                    for t in all_threads
                ]

            # Emotional Patterns
            all_patterns = (
                session.query(EmotionalPattern)
                .filter_by(entity_id=entity_id, status="active")
                .limit(10).all()
            )
            if all_patterns:
                section_items["emotional_patterns"] = [
                    SectionItem(id=str(p.id), label=p.name, char_count=len(p.name or "") + len(p.trigger_what or "") + len(p.response_external or "") + 20)
                    for p in all_patterns
                ]

            # Recent Events
            all_events = (
                session.query(LifeEvent)
                .filter_by(entity_id=entity_id)
                .order_by(LifeEvent.created_at.desc())
                .limit(5).all()
            )
            if all_events:
                section_items["recent_events"] = [
                    SectionItem(id=str(e.id), label=e.title, char_count=len(f"• {e.title} ({e.period or ''}): {(e.narrative or '')[:200]}"))
                    for e in all_events
                ]

            # Relationship-dependent items
            rel = session.query(Relationship).filter_by(entity_id=entity_id, target_id="user").first()
            if rel:
                all_jokes = session.query(InsideJoke).filter_by(relationship_id=rel.id).limit(15).all()
                if all_jokes:
                    section_items["inside_jokes"] = [
                        SectionItem(id=str(j.id), label=j.phrase[:60], char_count=len(f'• "{j.phrase}" — {j.origin or "?"} [{j.tone}]'))
                        for j in all_jokes
                    ]
                all_moments = (
                    session.query(IntimateMoment)
                    .filter_by(relationship_id=rel.id)
                    .order_by(IntimateMoment.created_at.desc())
                    .limit(10).all()
                )
                if all_moments:
                    section_items["intimate_moments"] = [
                        SectionItem(id=str(m.id), label=m.summary[:60], char_count=len(f"• {(m.summary or '')[:150]}" + (f" [{m.significance}]" if m.significance else "")))
                        for m in all_moments
                    ]

            # Rituals
            all_rituals = session.query(RelationalRitual).filter_by(entity_id=entity_id).all()
            if all_rituals:
                section_items["rituals"] = [
                    SectionItem(id=str(r.id), label=r.name, char_count=len(f"• {r.name}: {r.pattern or ''}"))
                    for r in all_rituals
                ]

            # State Needs
            all_needs = session.query(StateNeed).filter_by(entity_id=entity_id).all()
            if all_needs:
                section_items["state_needs"] = [
                    SectionItem(id=str(s.id), label=f"When {s.state}", char_count=len(f"• When {s.state}: {s.needs}") + (len(f"\n  ✗ Avoid: {s.anti_needs}") if s.anti_needs else 0))
                    for s in all_needs
                ]

            # Repair Patterns
            all_repairs = (
                session.query(RepairPattern)
                .filter_by(entity_id=entity_id)
                .order_by(RepairPattern.created_at.desc())
                .limit(5).all()
            )
            if all_repairs:
                section_items["repair_patterns"] = [
                    SectionItem(id=str(r.id), label=(r.trigger or "")[:60], char_count=len(r.trigger or "") + len(r.rupture or "") + len(r.repair or "") + len(r.lesson or "") + 30)
                    for r in all_repairs
                ]

            # Artifacts
            all_artifacts = (
                session.query(Artifact)
                .filter_by(entity_id=entity_id)
                .order_by(Artifact.created_at.desc())
                .limit(20).all()
            )
            if all_artifacts:
                section_items["artifacts"] = [
                    SectionItem(id=str(a.id), label=a.title, char_count=len(f"• [{a.type}] {a.title}: {a.context or 'no context'}"))
                    for a in all_artifacts
                ]

        # ── Dynamic Preamble ──
        utc_now = datetime.now(timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            amsterdam = ZoneInfo("Europe/Amsterdam")
            local_dt = utc_now.astimezone(amsterdam)
            local_time_str = local_dt.strftime("%A, %B %d, %Y, %H:%M")
        except Exception:
            local_time_str = utc_now.strftime("%A, %B %d, %Y, %H:%M") + " (UTC)"

        dynamic_preamble = f"[SYSTEM METADATA]\nCurrent Time (UTC): {utc_now.isoformat()}\nLocal Time (Amsterdam): {local_time_str}\nSILENCE GAP: (live)\n------------------\n"
        dynamic_preamble += f"\nActive Model: {active_model}\n"

        # ── Assemble section info with ordering ──
        sections = []
        all_keys = set(SECTION_META.keys())
        ordered_keys = [k for k in section_order if k in all_keys]
        for k in DEFAULT_SECTION_ORDER:
            if k not in ordered_keys:
                ordered_keys.append(k)

        total_warm_chars = 0
        for i, key in enumerate(ordered_keys):
            meta = SECTION_META.get(key, {"label": key, "icon": "📦"})
            raw_content = raw_sections.get(key, "")
           # Some sections return structured data (list/dict) — coerce to string for display
            if isinstance(raw_content, str):
                content = raw_content
            elif raw_content is None:
                content = ""
            else:
                import json as _json
                # Preview endpoint expects textual section content. Use default=str for dates/UUIDs
                content = _json.dumps(raw_content, default=str, ensure_ascii=False, indent=2)
            char_count = len(content)
            enabled = key not in disabled_sections

            if enabled and content:
                total_warm_chars += char_count

            sections.append(SectionInfo(
                key=key,
                label=meta["label"],
                icon=meta["icon"],
                content=content,
                char_count=char_count,
                enabled=enabled,
                order=i,
                items=section_items.get(key),
            ))

        budget_used_pct = (total_warm_chars / budget * 100) if budget > 0 else 0

        # ── Component summary ──
        sys_chars = len(system_instruction)
        preamble_chars = len(dynamic_preamble)
        # History estimate is clamped to the actual budget
        hist_budget_chars = min(history_estimate_chars, max_hist_chars)
        total_context_chars = sys_chars + total_warm_chars + preamble_chars + tools_chars + hist_budget_chars

        return ContextPreview(
            entity_id=entity_id,
            system_instruction=system_instruction,
            system_instruction_chars=sys_chars,
            sections=sections,
            dynamic_preamble=dynamic_preamble,
            dynamic_preamble_chars=preamble_chars,
            total_warm_chars=total_warm_chars,
            budget=budget,
            budget_used_pct=min(budget_used_pct, 100),
            section_order=ordered_keys,
            disabled_sections=disabled_sections,
            disabled_items=disabled_items,
            pinned_items=pinned_items,
            voice_anchors=voice_anchors,
            active_model=active_model,
            tools=all_tool_names,
            tools_chars=tools_chars,
            memory_blocks=memory_block_infos,
            history_estimate_chars=history_estimate_chars,
            history_message_count=history_message_count,
            budget_limits=BudgetLimits(
                max_context_chars=max_context,
                max_warm_memory=max_warm,
                max_history_chars=max_hist_chars,
                max_history_messages=max_hist_msgs,
            ),
            component_summary=ComponentSummary(
                system_instruction=sys_chars,
                warm_memory_enabled=total_warm_chars,
                dynamic_preamble=preamble_chars,
                tools=tools_chars,
                history_estimate=hist_budget_chars,
                total=total_context_chars,
            ),
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.put("/{entity_id}/sections")
async def update_section_config(entity_id: str, update: SectionConfigUpdate):
    """Update section ordering and enable/disable preferences."""
    prefs = _load_context_preferences(entity_id)

    if update.section_order is not None:
        prefs["section_order"] = update.section_order
    if update.disabled_sections is not None:
        prefs["disabled_sections"] = update.disabled_sections
    if update.disabled_items is not None:
        # Clean up empty lists
        prefs["disabled_items"] = {k: v for k, v in update.disabled_items.items() if v}
    if update.pinned_items is not None:
        prefs["pinned_items"] = {k: v for k, v in update.pinned_items.items() if v}
    if update.voice_anchors is not None:
        prefs["voice_anchors"] = update.voice_anchors

    _save_context_preferences(entity_id, prefs)

    return {"status": "ok", "preferences": prefs}


class BudgetUpdateRequest(BaseModel):
    max_context_chars: Optional[int] = None
    max_warm_memory: Optional[int] = None
    max_history_chars: Optional[int] = None
    max_history_messages: Optional[int] = None


@router.put("/{entity_id}/budgets")
async def update_budget_config(entity_id: str, update: BudgetUpdateRequest):
    """Update context budget configuration for a persona."""
    from src.db.session import get_session
    from src.db.models import PersonaIdentity

    with get_session() as session:
        persona = session.get(PersonaIdentity, entity_id)
        if not persona:
            return JSONResponse(status_code=404, content={"error": "Persona not found"})

        if update.max_context_chars is not None:
            # Allow 0 to mean "clear/unlimited"
            persona.max_context_chars = update.max_context_chars if update.max_context_chars > 0 else None
        if update.max_warm_memory is not None:
            persona.max_warm_memory = update.max_warm_memory
        if update.max_history_chars is not None:
            persona.max_history_chars = update.max_history_chars
        if update.max_history_messages is not None:
            persona.max_history_messages = update.max_history_messages

        session.commit()

    return {
        "status": "ok",
        "budgets": {
            "max_context_chars": persona.max_context_chars,
            "max_warm_memory": persona.max_warm_memory,
            "max_history_chars": persona.max_history_chars,
            "max_history_messages": persona.max_history_messages,
        }
    }


@router.get("/{entity_id}/graph")
async def get_graph_data(
    entity_id: str,
    limit: int = Query(200, description="Max edges to return"),
):
    """
    Get knowledge graph data for visualization.
    Returns nodes, edges, and arcs with labels resolved from DB.
    """
    try:
        from src.db.session import get_session
        from src.db.models import Edge, Arc, ArcEvent
        from sqlalchemy import func

        with get_session() as session:
            # Load all edges for this entity
            edges_raw = (
                session.query(Edge)
                .filter_by(entity_id=entity_id)
                .limit(limit)
                .all()
            )

            # Collect unique node IDs
            node_set = set()
            graph_edges = []

            for e in edges_raw:
                src_key = f"{e.from_type}::{e.from_id}"
                tgt_key = f"{e.to_type}::{e.to_id}"
                node_set.add((e.from_type, e.from_id))
                node_set.add((e.to_type, e.to_id))

                graph_edges.append(GraphEdge(
                    source=src_key,
                    target=tgt_key,
                    relation=e.relation or "related",
                    strength=e.strength or 0.5,
                    context=e.context,
                    status=e.status or "active",
                ))

            # Resolve node labels from their respective tables
            # Normalize type keys to handle legacy names in existing edges
            type_groups: dict[str, list[str]] = {}
            for ntype, nid in node_set:
                type_groups.setdefault(ntype, []).append(nid)

            # Build label resolvers and PK type info from the registry
            from src.memory_registry import (
                MEMORY_TYPES as _REG, resolve_model, normalize_type,
                is_known_type,
            )

            label_resolvers = {}
            INT_PK_TYPES = set()
            for _key, _defn in _REG.items():
                try:
                    _Model = resolve_model(_key)
                    label_resolvers[_key] = (_Model, _defn.label_field)
                    if _defn.pk_type == "integer":
                        INT_PK_TYPES.add(_key)
                except Exception:
                    pass

            labels = {}
            for ntype, ids in type_groups.items():
                canonical = normalize_type(ntype)
                resolver = label_resolvers.get(canonical)
                if not resolver:
                    continue
                Model, attr = resolver

                if canonical in INT_PK_TYPES:
                    # Composite IDs like "lexicon-141" → extract numeric part
                    id_map: dict[int, str] = {}  # numeric_id → original composite ID
                    for nid in ids:
                        parts = nid.rsplit("-", 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            id_map[int(parts[1])] = nid
                        elif nid.isdigit():
                            id_map[int(nid)] = nid
                    if id_map:
                        items = session.query(Model).filter(
                            Model.id.in_(list(id_map.keys()))
                        ).all()
                        for item in items:
                            original_id = id_map.get(item.id, str(item.id))
                            key = f"{ntype}::{original_id}"
                            labels[key] = getattr(item, attr, str(item.id)) or str(item.id)
                else:
                    # Text PK — use IDs directly
                    items = session.query(Model).filter(Model.id.in_(ids)).all()
                    for item in items:
                        key = f"{ntype}::{item.id}"
                        labels[key] = getattr(item, attr, str(item.id)) or str(item.id)

            graph_nodes = []
            for ntype, nid in node_set:
                key = f"{ntype}::{nid}"
                graph_nodes.append(GraphNode(
                    id=key,
                    type=ntype,
                    label=labels.get(key, str(nid)[:40]),
                    group=ntype,
                ))

            # Load arcs
            arcs_raw = session.query(Arc).filter_by(entity_id=entity_id).all()
            arcs_data = []
            for arc in arcs_raw:
                events = (
                    session.query(ArcEvent)
                    .filter_by(arc_id=arc.id)
                    .order_by(ArcEvent.sequence)
                    .all()
                )
                arcs_data.append({
                    "id": arc.id,
                    "title": arc.title,
                    "status": arc.status,
                    "narrative": arc.narrative,
                    "events": [
                        {
                            "event_type": ev.event_type,
                            "narrative": ev.narrative,
                            "sequence": ev.sequence,
                        }
                        for ev in events
                    ],
                })

            # Stats
            edge_count = session.query(func.count(Edge.id)).filter_by(entity_id=entity_id).scalar() or 0
            relation_types = (
                session.query(Edge.relation)
                .filter_by(entity_id=entity_id)
                .distinct()
                .all()
            )
            node_types = list(type_groups.keys())

        return GraphData(
            nodes=graph_nodes,
            edges=graph_edges,
            arcs=arcs_data,
            stats={
                "total_edges": edge_count,
                "total_nodes": len(graph_nodes),
                "relation_types": [r[0] for r in relation_types if r[0]],
                "node_types": node_types,
                "total_arcs": len(arcs_data),
            },
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
