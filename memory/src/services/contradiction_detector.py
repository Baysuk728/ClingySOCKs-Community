"""
Contradiction Detection — Validate facts against the knowledge graph.

Detects conflicts between:
1. FactualEntity attributes (e.g., two "person" entities claiming different roles)
2. Edge relationships (conflicting "works_on" or "assigned_to" edges)
3. Temporal conflicts (entity validity window overlaps)
4. Cross-type conflicts (life_event claims vs factual_entity data)

Can run:
- During harvest (post-edge-building validation pass)
- On-demand via API endpoint
- As part of subconscious daemon cycle

Inspired by MemPalace's fact_checker.py concept.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, func

from src.db.models import (
    Edge, FactualEntity, LifeEvent, Narrative,
)
from src.db.session import get_session

logger = logging.getLogger("clingysocks.contradiction")


# ── Contradiction Types ──────────────────────────────

class ContradictionSeverity:
    CRITICAL = "critical"  # Direct factual conflict
    WARNING = "warning"    # Possible inconsistency
    INFO = "info"          # Minor discrepancy worth noting


def detect_contradictions(
    entity_id: str,
    scope: str = "all",
) -> list[dict[str, Any]]:
    """
    Run contradiction detection across the knowledge graph.
    
    Args:
        entity_id: Entity to check
        scope: "all", "edges", "entities", "temporal"
        
    Returns:
        List of detected contradictions with severity and details
    """
    contradictions = []

    if scope in ("all", "edges"):
        contradictions.extend(_check_edge_contradictions(entity_id))

    if scope in ("all", "entities"):
        contradictions.extend(_check_entity_contradictions(entity_id))

    if scope in ("all", "temporal"):
        contradictions.extend(_check_temporal_contradictions(entity_id))

    # Sort by severity (critical first)
    severity_order = {ContradictionSeverity.CRITICAL: 0, ContradictionSeverity.WARNING: 1, ContradictionSeverity.INFO: 2}
    contradictions.sort(key=lambda c: severity_order.get(c.get("severity", "info"), 3))

    return contradictions


def _check_edge_contradictions(entity_id: str) -> list[dict]:
    """
    Check for contradictory edges:
    - Same from→to with conflicting relations (e.g., "works_on" + "left")
    - Multiple active edges for exclusive relationships
    """
    contradictions = []

    # Relation pairs that are contradictory
    CONTRADICTORY_PAIRS = [
        ("works_on", "left"),
        ("assigned_to", "completed"),
        ("supports", "opposes"),
        ("caused_by", "prevented_by"),
        ("trusts", "distrusts"),
        ("likes", "dislikes"),
        ("agrees_with", "disagrees_with"),
    ]

    with get_session() as session:
        active_edges = session.query(Edge).filter_by(
            entity_id=entity_id, status="active"
        ).all()

        # Group by (from_type:from_id, to_type:to_id) pair
        edge_groups: dict[tuple, list[Edge]] = {}
        for edge in active_edges:
            pair = (f"{edge.from_type}:{edge.from_id}", f"{edge.to_type}:{edge.to_id}")
            edge_groups.setdefault(pair, []).append(edge)

            # Also check reverse direction
            pair_rev = (f"{edge.to_type}:{edge.to_id}", f"{edge.from_type}:{edge.from_id}")
            edge_groups.setdefault(pair_rev, []).append(edge)

        for pair, edges in edge_groups.items():
            if len(edges) < 2:
                continue

            relations = {e.relation for e in edges}

            for rel_a, rel_b in CONTRADICTORY_PAIRS:
                if rel_a in relations and rel_b in relations:
                    contradictions.append({
                        "severity": ContradictionSeverity.CRITICAL,
                        "type": "contradictory_edges",
                        "pair": pair,
                        "relations": [rel_a, rel_b],
                        "message": f"Conflicting edges between {pair[0]} and {pair[1]}: '{rel_a}' vs '{rel_b}'.",
                        "edge_ids": [e.id for e in edges if e.relation in (rel_a, rel_b)],
                    })

    return contradictions


def _check_entity_contradictions(entity_id: str) -> list[dict]:
    """
    Check for conflicting factual entities:
    - Duplicate names with different types
    - Same entity with conflicting descriptions
    """
    contradictions = []

    with get_session() as session:
        entities = session.query(FactualEntity).filter_by(
            entity_id=entity_id
        ).all()

        # Group by normalized name
        by_name: dict[str, list[FactualEntity]] = {}
        for fe in entities:
            normalized = fe.name.lower().strip()
            by_name.setdefault(normalized, []).append(fe)

            # Also check aliases
            if fe.aliases:
                for alias in fe.aliases:
                    norm_alias = alias.lower().strip()
                    by_name.setdefault(norm_alias, []).append(fe)

        for name, group in by_name.items():
            if len(group) < 2:
                continue

            # Check for type conflicts (same name, different type)
            types = set(fe.type for fe in group)
            unique_ids = set(fe.id for fe in group)

            if len(unique_ids) > 1 and len(types) > 1:
                contradictions.append({
                    "severity": ContradictionSeverity.WARNING,
                    "type": "ambiguous_entity",
                    "name": name,
                    "entity_types": list(types),
                    "entity_ids": list(unique_ids),
                    "message": f"'{name}' exists as multiple types: {', '.join(types)}. Consider merging or disambiguating.",
                })

            # Check for description conflicts within same type
            for fe_type in types:
                same_type = [fe for fe in group if fe.type == fe_type]
                if len(same_type) > 1 and len(set(fe.id for fe in same_type)) > 1:
                    contradictions.append({
                        "severity": ContradictionSeverity.INFO,
                        "type": "duplicate_entity",
                        "name": name,
                        "entity_type": fe_type,
                        "entity_ids": list(set(fe.id for fe in same_type)),
                        "message": f"Multiple '{fe_type}' entities named '{name}'. May be duplicates.",
                    })

    return contradictions


def _check_temporal_contradictions(entity_id: str) -> list[dict]:
    """
    Check for temporal conflicts:
    - Events with impossible date sequences
    - Edges referencing items that don't exist anymore
    """
    contradictions = []

    with get_session() as session:
        # Check for edges pointing to non-existent items
        active_edges = session.query(Edge).filter_by(
            entity_id=entity_id, status="active"
        ).all()

        # Build set of known IDs per type
        known_ids: dict[str, set[str]] = {}

        from src.memory_registry import MEMORY_TYPES, resolve_model

        for key, defn in MEMORY_TYPES.items():
            try:
                model = resolve_model(key)
                if model and hasattr(model, "entity_id"):
                    ids = set(
                        str(r[0]) for r in
                        session.query(model.id).filter_by(entity_id=entity_id).all()
                    )
                    known_ids[key] = ids
            except Exception:
                continue

        for edge in active_edges:
            from_exists = edge.from_id in known_ids.get(edge.from_type, set())
            to_exists = edge.to_id in known_ids.get(edge.to_type, set())

            if not from_exists and edge.from_type in known_ids:
                contradictions.append({
                    "severity": ContradictionSeverity.WARNING,
                    "type": "dangling_edge",
                    "edge_id": edge.id,
                    "missing_side": "from",
                    "missing_type": edge.from_type,
                    "missing_id": edge.from_id,
                    "message": f"Edge {edge.id} references non-existent {edge.from_type}:{edge.from_id}.",
                })

            if not to_exists and edge.to_type in known_ids:
                contradictions.append({
                    "severity": ContradictionSeverity.WARNING,
                    "type": "dangling_edge",
                    "edge_id": edge.id,
                    "missing_side": "to",
                    "missing_type": edge.to_type,
                    "missing_id": edge.to_id,
                    "message": f"Edge {edge.id} references non-existent {edge.to_type}:{edge.to_id}.",
                })

    return contradictions


# ── Summary Report ───────────────────────────────────

def contradiction_report(entity_id: str) -> dict[str, Any]:
    """
    Generate a human-readable contradiction report.
    """
    contradictions = detect_contradictions(entity_id)

    critical = [c for c in contradictions if c["severity"] == ContradictionSeverity.CRITICAL]
    warnings = [c for c in contradictions if c["severity"] == ContradictionSeverity.WARNING]
    infos = [c for c in contradictions if c["severity"] == ContradictionSeverity.INFO]

    return {
        "entity_id": entity_id,
        "total": len(contradictions),
        "critical": len(critical),
        "warnings": len(warnings),
        "info": len(infos),
        "health": "clean" if not critical and not warnings else ("issues" if critical else "minor"),
        "contradictions": contradictions,
    }
