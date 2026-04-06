"""
Factual Entity Extraction Pass.

Extracts knowledge-graph entities (people, places, objects, projects,
conditions, concepts, groups, topics) and their structural relationships
from conversation text.

Runs after items are stored in the database, alongside edge building.
Uses entity resolution to prevent duplicates.
"""

import re
import litellm

from src.config import (
    EXTRACTION_MODEL, EXTRACTION_TEMPERATURE, MAX_OUTPUT_TOKENS,
)
from src.db.models import FactualEntity, Edge
from src.prompts.factual import (
    build_factual_prompt, FACTUAL_SYSTEM_INSTRUCTION,
    FACTUAL_TYPES, FACTUAL_TYPE_ALIASES, FACTUAL_RELATIONS,
    CONFLICTING_RELATIONS,
)
from src.pipeline.json_utils import parse_json_response


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def _resolve_entity(
    name: str,
    etype: str,
    existing: list[FactualEntity],
) -> FactualEntity | None:
    """Try to match a name/type against existing entities (by name or alias)."""
    name_lower = name.lower().strip()

    for ent in existing:
        if ent.type != etype:
            continue
        # Match by canonical name
        if ent.name.lower().strip() == name_lower:
            return ent
        # Match by alias
        if ent.aliases:
            for alias in ent.aliases:
                if alias.lower().strip() == name_lower:
                    return ent

    return None


async def run_factual_extraction(
    entity_id: str,
    session,
    chunk_text: str,
    agent_name: str,
    user_name: str,
    narrative_context: str = "",
    source_message_id: str | None = None,
) -> dict:
    """
    Extract factual entities and relationships from conversation text.

    Args:
        entity_id: The memory entity (agent) ID
        session: SQLAlchemy session
        chunk_text: Formatted conversation chunk
        agent_name: Agent display name
        user_name: User display name
        narrative_context: Rolling summary from earlier passes
        source_message_id: ID of the first message in this chunk

    Returns:
        Stats dict: entities_created, entities_updated, edges_created, edges_rejected
    """
    print("\n🔍 Running factual entity extraction...")

    stats = {
        "entities_created": 0,
        "entities_updated": 0,
        "edges_created": 0,
        "edges_rejected": 0,
    }

    # Load existing factual entities for this entity (for dedup)
    existing = (
        session.query(FactualEntity)
        .filter_by(entity_id=entity_id)
        .all()
    )
    existing_dicts = [
        {"type": e.type, "name": e.name, "aliases": e.aliases or []}
        for e in existing
    ]

    prompt = build_factual_prompt(
        chunk_text=chunk_text,
        agent_name=agent_name,
        user_name=user_name,
        existing_entities=existing_dicts if existing_dicts else None,
        narrative_context=narrative_context,
    )

    try:
        response = await litellm.acompletion(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": FACTUAL_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            temperature=EXTRACTION_TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        data = parse_json_response(raw)

    except Exception as e:
        print(f"   ❌ Factual extraction LLM call failed: {e}")
        return stats

    # ── Process entities ──
    extracted_entities = data.get("entities", [])
    # Map from (type, name_lower) → FactualEntity for relationship resolution
    entity_lookup: dict[tuple[str, str], FactualEntity] = {}
    for ent in existing:
        entity_lookup[(ent.type, ent.name.lower().strip())] = ent
        for alias in (ent.aliases or []):
            entity_lookup[(ent.type, alias.lower().strip())] = ent

    for raw_ent in extracted_entities:
        etype = raw_ent.get("type", "").lower().strip()
        name = raw_ent.get("name", "").strip()
        if not name or not etype:
            continue
        if etype not in FACTUAL_TYPES:
            mapped = FACTUAL_TYPE_ALIASES.get(etype)
            if mapped:
                print(f"   🔄 Mapped entity type '{etype}' → '{mapped}' for '{name}'")
                etype = mapped
            else:
                print(f"   ⚠️ Unknown entity type '{etype}' for '{name}', storing as 'concept'")
                etype = "concept"

        confidence = raw_ent.get("confidence", 0.8)
        if confidence < 0.4:
            continue  # Too uncertain

        # Entity resolution
        resolved = _resolve_entity(name, etype, existing)

        if resolved:
            # Update existing entity
            resolved.mention_count = (resolved.mention_count or 1) + 1
            resolved.confidence = max(resolved.confidence or 0, confidence)
            if raw_ent.get("description") and not resolved.description:
                resolved.description = raw_ent["description"]

            # Merge new aliases
            new_aliases = set(a.lower().strip() for a in (raw_ent.get("aliases") or []))
            current_aliases = set(a.lower().strip() for a in (resolved.aliases or []))
            added = new_aliases - current_aliases - {resolved.name.lower().strip()}
            if added:
                resolved.aliases = list(set(resolved.aliases or []) | added)

            stats["entities_updated"] += 1
            entity_lookup[(etype, name.lower().strip())] = resolved
        else:
            # Create new entity
            slug = f"{etype}-{_slugify(name)}"
            # Ensure uniqueness in case of slug collision
            counter = 2
            base_slug = slug
            while session.query(FactualEntity).filter_by(id=slug).first():
                slug = f"{base_slug}-{counter}"
                counter += 1

            new_ent = FactualEntity(
                id=slug,
                entity_id=entity_id,
                type=etype,
                name=name,
                aliases=[a.lower().strip() for a in (raw_ent.get("aliases") or [])],
                description=raw_ent.get("description"),
                confidence=confidence,
                mention_count=1,
                source_message_id=source_message_id,
            )
            session.add(new_ent)
            session.flush()  # Get ID populated
            existing.append(new_ent)
            entity_lookup[(etype, name.lower().strip())] = new_ent
            for alias in (new_ent.aliases or []):
                entity_lookup[(etype, alias)] = new_ent
            stats["entities_created"] += 1

    print(f"   ✅ Entities: {stats['entities_created']} created, {stats['entities_updated']} updated")

    # ── Process relationships ──
    extracted_rels = data.get("relationships", [])
    stats["edges_superseded"] = 0

    for raw_rel in extracted_rels:
        from_name = raw_rel.get("from_name", "").strip()
        from_type = raw_rel.get("from_type", "").lower().strip()
        to_name = raw_rel.get("to_name", "").strip()
        to_type = raw_rel.get("to_type", "").lower().strip()
        relation = raw_rel.get("relation", "related_to").lower().strip()
        confidence = raw_rel.get("confidence", 0.7)
        supersedes_rel = raw_rel.get("supersedes")  # Explicit LLM-flagged supersession

        if not from_name or not to_name or not from_type or not to_type:
            stats["edges_rejected"] += 1
            continue

        if confidence < 0.4:
            stats["edges_rejected"] += 1
            continue

        if relation not in FACTUAL_RELATIONS:
            relation = "related_to"  # Fallback

        # Resolve both endpoints
        from_ent = entity_lookup.get((from_type, from_name.lower().strip()))
        to_ent = entity_lookup.get((to_type, to_name.lower().strip()))

        if not from_ent or not to_ent:
            stats["edges_rejected"] += 1
            continue

        from_id = from_ent.id
        to_id = to_ent.id

        if from_id == to_id:
            stats["edges_rejected"] += 1
            continue

        # ── Supersession: mark conflicting old edges ──
        # Collect relations to supersede:
        #   1) Explicit LLM flag (supersedes_rel)
        #   2) CONFLICTING_RELATIONS map
        rels_to_supersede: set[str] = set()
        if supersedes_rel and isinstance(supersedes_rel, str):
            rels_to_supersede.add(supersedes_rel.lower().strip())
        rels_to_supersede |= CONFLICTING_RELATIONS.get(relation, set())

        if rels_to_supersede:
            # Find active edges between same pair (either direction) with conflicting relations
            old_edges = (
                session.query(Edge)
                .filter(
                    Edge.entity_id == entity_id,
                    Edge.status == "active",
                    Edge.relation.in_(rels_to_supersede),
                )
                .filter(
                    # Match either direction between the same pair
                    ((Edge.from_id == from_id) & (Edge.to_id == to_id)) |
                    ((Edge.from_id == to_id) & (Edge.to_id == from_id))
                )
                .all()
            )
            for old in old_edges:
                old.status = "superseded"
                old.context = (old.context or "") + f" [superseded by {relation}]"
                stats["edges_superseded"] += 1

        # Upsert the new/current edge
        existing_edge = (
            session.query(Edge)
            .filter_by(
                entity_id=entity_id,
                from_id=from_id,
                from_type=from_type,
                to_id=to_id,
                to_type=to_type,
                relation=relation,
            )
            .first()
        )

        if existing_edge:
            existing_edge.strength = max(existing_edge.strength or 0.5, confidence)
            existing_edge.status = "active"  # Re-confirm active
            if raw_rel.get("context"):
                existing_edge.context = raw_rel["context"]
        else:
            edge = Edge(
                entity_id=entity_id,
                from_id=from_id,
                from_type=from_type,
                to_id=to_id,
                to_type=to_type,
                relation=relation,
                strength=confidence,
                context=raw_rel.get("context"),
                status="active",
            )
            session.add(edge)

        stats["edges_created"] += 1

    superseded_msg = f", {stats['edges_superseded']} superseded" if stats["edges_superseded"] else ""
    print(f"   ✅ Factual edges: {stats['edges_created']} created, {stats['edges_rejected']} rejected{superseded_msg}")

    return stats
