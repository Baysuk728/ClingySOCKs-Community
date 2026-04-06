"""
Edge Builder: Grounded Graph Edge & Arc Creation.

Creates edges AFTER items are stored in the database,
using real IDs instead of LLM-hallucinated ones.

Uses the memory_registry as the single source of truth for type keys
and ID formats.  Edge IDs are raw DB primary keys (no prefixes).
"""

import json
import re
from typing import Optional

import litellm

from src.config import (
    EXTRACTION_MODEL, EXTRACTION_TEMPERATURE,
    GEMINI_API_KEY, OPENAI_API_KEY,
)
from src.db.models import (
    Edge, Arc, ArcEvent, Relationship, FactualEntity,
)
from src.db.session import get_session
from src.memory_registry import (
    MEMORY_TYPES, graphable_types, resolve_model, normalize_type,
)


# Types that are queried via Relationship rather than entity_id
_RELATIONSHIP_TYPES = {"inside_joke", "intimate_moment"}


async def build_grounded_edges(
    entity_id: str,
    session,
    synthesis_arcs: list[dict] | None = None,
) -> dict:
    """
    Build grounded edges using real stored IDs from the database.

    This runs AFTER items have been stored, so we can reference
    actual database IDs instead of LLM-generated ones.

    Returns stats dict.
    """
    print("\n🔗 Building grounded edges...")

    # Gather all stored items from graphable types via the registry
    items_by_type: dict[str, list] = {}

    # Pre-fetch relationship IDs for relationship-linked types
    rel_ids = [
        r.id for r in
        session.query(Relationship).filter_by(entity_id=entity_id).all()
    ]

    for defn in graphable_types():
        # Factual entity sub-types share one table — query once, split later
        if defn.model_name == "FactualEntity":
            continue  # handled below

        Model = resolve_model(defn.key)

        if defn.key in _RELATIONSHIP_TYPES:
            if not rel_ids:
                continue
            rows = (
                session.query(Model)
                .filter(Model.relationship_id.in_(rel_ids))
                .all()
            )
        elif defn.singleton:
            row = session.query(Model).filter_by(entity_id=entity_id).first()
            rows = [row] if row else []
        else:
            rows = session.query(Model).filter_by(entity_id=entity_id).all()

        if rows:
            items_by_type[defn.key] = rows

    # Factual entities — query once, split by sub-type
    factual_all = (
        session.query(FactualEntity)
        .filter_by(entity_id=entity_id)
        .all()
    )
    for fe in factual_all:
        items_by_type.setdefault(fe.type, []).append(fe)

    if not items_by_type:
        print("   ℹ️ No items to create edges for")
        return {"edges_created": 0, "edges_updated": 0, "arcs_created": 0}

    # Build grounding context and valid ID set from registry
    grounding = _build_grounding_context(items_by_type)
    valid_ids = _build_id_lookup(items_by_type)

    # Build type enum from registry
    all_types = " | ".join(
        f'"{k}"' for k in sorted(items_by_type.keys())
    )
    all_relations = (
        '"triggered_by" | "evolved_from" | "deepens" | "references" | '
        '"resolved_by" | "contains" | "contrasts" | '
        '"kin_of" | "companion_of" | "created_by" | "located_in" | '
        '"has_condition" | "symptom_of" | "is_a" | "part_of" | '
        '"owns" | "knows" | "works_on" | "related_to"'
    )

    # Ask LLM to identify connections between EXISTING items only
    prompt = f"""Given these stored memory items, identify meaningful connections.

{grounding}

Create edges using ONLY the IDs listed above. Do NOT invent new IDs.

For each connection, specify:
- from_id: The source item ID (must be from the lists above)
- from_type: {all_types}
- to_id: The target item ID (must be from the lists above)
- to_type: {all_types}
- relation: {all_relations}
- strength: 0.0 to 1.0 (how strong is this connection?)
- context: One sentence explaining WHY this connection exists

Return JSON:
```json
{{
    "edges": [
        {{
            "from_id": "...", "from_type": "...",
            "to_id": "...", "to_type": "...",
            "relation": "...", "strength": 0.7,
            "context": "..."
        }}
    ]
}}
```

RULES:
1. Only use IDs from the lists above. Any edge with an unknown ID will be rejected.
2. Don't create edges between an item and itself.
3. Focus on MEANINGFUL connections, not trivial temporal proximity.
4. Maximum 20 edges to keep the graph focused.
5. Use lowercase type keys exactly as shown (e.g. "life_event" not "LIFE_EVENT")."""

    stats = {"edges_created": 0, "edges_updated": 0, "arcs_created": 0, "edges_rejected": 0}

    try:
        response = await litellm.acompletion(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": "You create knowledge graph edges between stored memory items. Only use IDs that actually exist. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=EXTRACTION_TEMPERATURE,
            max_tokens=16384,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "length":
            print("   \u26a0\ufe0f Edge builder response truncated — salvaging complete edges")
        data = _parse_edge_json(raw, truncated=(finish_reason == "length"))
        proposed_edges = data.get("edges", [])

        for edge_data in proposed_edges:
            # Normalize type keys (handle legacy names from LLM)
            raw_from_type = edge_data.get("from_type", "")
            raw_to_type = edge_data.get("to_type", "")
            from_type = normalize_type(raw_from_type)
            to_type = normalize_type(raw_to_type)
            from_id = str(edge_data.get("from_id", ""))
            to_id = str(edge_data.get("to_id", ""))

            from_key = (from_id, from_type)
            to_key = (to_id, to_type)

            if from_key not in valid_ids or to_key not in valid_ids:
                stats["edges_rejected"] += 1
                continue

            if from_key == to_key:
                stats["edges_rejected"] += 1
                continue

            # Check if edge already exists (composite unique constraint)
            existing_edge = (
                session.query(Edge)
                .filter_by(
                    entity_id=entity_id,
                    from_id=from_id,
                    from_type=from_type,
                    to_id=to_id,
                    to_type=to_type,
                    relation=edge_data.get("relation", "references"),
                )
                .first()
            )

            if existing_edge:
                existing_edge.strength = edge_data.get("strength", 0.5)
                existing_edge.context = edge_data.get("context")
                stats["edges_updated"] += 1
                continue

            edge = Edge(
                entity_id=entity_id,
                from_id=from_id,
                from_type=from_type,
                to_id=to_id,
                to_type=to_type,
                relation=edge_data.get("relation", "references"),
                strength=edge_data.get("strength", 0.5),
                context=edge_data.get("context"),
            )
            session.add(edge)
            stats["edges_created"] += 1

        print(f"   ✅ Edges: {stats['edges_created']} created, {stats.get('edges_updated', 0)} updated, {stats['edges_rejected']} rejected (LLM referenced IDs not in grounding context)")

    except Exception as e:
        print(f"   ❌ Edge building failed: {e}")

    # Store arcs from synthesis
    if synthesis_arcs:
        for arc_data in synthesis_arcs:
            try:
                arc = Arc(
                    id=arc_data.get("id", f"arc-{len(synthesis_arcs)}"),
                    entity_id=entity_id,
                    title=arc_data.get("title", "Untitled Arc"),
                    narrative=arc_data.get("narrative"),
                    status=arc_data.get("status", "open"),
                )
                session.merge(arc)

                for stage in arc_data.get("stages", []):
                    event = ArcEvent(
                        arc_id=arc.id,
                        event_id=stage.get("related_event_id"),
                        event_type=stage.get("event_type", "trigger"),
                        sequence=stage.get("sequence", 0),
                        narrative=stage.get("narrative", ""),
                    )
                    session.add(event)

                stats["arcs_created"] += 1
            except Exception as e:
                print(f"   ⚠️ Arc creation error: {e}")

        print(f"   ✅ Arcs: {stats['arcs_created']} created")

    return stats


def _build_grounding_context(items_by_type: dict[str, list]) -> str:
    """Build a grounding context string for the LLM.

    Uses the registry to auto-format each type.  IDs are raw DB PKs
    (no prefixes) — the (type, id) pair is unique.
    """
    from src.memory_registry import MEMORY_TYPES, get_def

    sections = []
    for type_key, items in items_by_type.items():
        if not items:
            continue
        defn = MEMORY_TYPES.get(type_key)
        if not defn:
            continue

        label_attr = defn.label_field
        display_name = type_key.upper().replace("_", " ")
        entries = []
        for item in items[-50:]:
            item_id = str(getattr(item, 'id', None) or item.entity_id)
            label = str(getattr(item, label_attr, "") or "")[:80]
            entries.append(f"  \u2022 [{item_id}] {label}")

        sections.append(f"{display_name} (type: {type_key}):\n" + "\n".join(entries))

    return "\n\n".join(sections)


def _build_id_lookup(items_by_type: dict[str, list]) -> set:
    """Build a lookup set of valid (str(id), type_key) tuples.

    IDs are raw DB primary keys cast to str — no prefixes.
    """
    valid: set[tuple[str, str]] = set()
    for type_key, items in items_by_type.items():
        for item in items:
            item_id = str(getattr(item, 'id', None) or item.entity_id)
            valid.add((item_id, type_key))
    return valid


def _parse_json(raw: str) -> dict:
    """Parse JSON from LLM response, using shared utility."""
    from src.pipeline.json_utils import parse_json_response
    return parse_json_response(raw)


def _parse_edge_json(raw: str, truncated: bool = False) -> dict:
    """Parse edge JSON from LLM, salvaging complete edges if truncated."""

    # Try clean parse first
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try shared utility (handles code fences + bracket repair)
    result = _parse_json(raw or "")
    if result.get("edges"):
        return result

    if not truncated:
        return {"edges": []}

    # Salvage complete edge objects from truncated JSON via regex
    edge_pattern = re.compile(
        r'\{\s*'
        r'"from_id"\s*:\s*"([^"]+)"\s*,\s*'
        r'"from_type"\s*:\s*"([^"]+)"\s*,\s*'
        r'"to_id"\s*:\s*"([^"]+)"\s*,\s*'
        r'"to_type"\s*:\s*"([^"]+)"\s*,\s*'
        r'"relation"\s*:\s*"([^"]+)"\s*,\s*'
        r'"strength"\s*:\s*([\d.]+)\s*,\s*'
        r'"context"\s*:\s*"([^"]*)"'
        r'\s*\}',
        re.DOTALL
    )

    edges = []
    for m in edge_pattern.finditer(raw or ""):
        edges.append({
            "from_id": m.group(1),
            "from_type": m.group(2),
            "to_id": m.group(3),
            "to_type": m.group(4),
            "relation": m.group(5),
            "strength": float(m.group(6)),
            "context": m.group(7),
        })

    if edges:
        print(f"   🔧 Salvaged {len(edges)} complete edges from truncated JSON")
    return {"edges": edges}
