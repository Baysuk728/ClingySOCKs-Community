"""
Agent Memory Tool — Graph Traverse.

Walk the knowledge graph from a starting node to discover
related memories, causal chains, and connections.

Uses the memory_registry as the single source of truth for type keys.
Edge IDs are raw DB primary keys (no prefixes).
"""

from typing import Any
from collections import deque

from sqlalchemy import or_, and_, func

from src.db.models import Edge, Arc, ArcEvent
from src.db.session import get_session
from src.memory_registry import normalize_type, MEMORY_TYPES, graph_type_keys


def graph_traverse(
    entity_id: str,
    start_node_type: str,
    start_node_id: str,
    max_depth: int = 2,
    edge_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Traverse the knowledge graph from a starting node.

    Uses BFS to walk edges up to max_depth hops.

    Args:
        entity_id: Entity ID (for scoping)
        start_node_type: Type of starting node (canonical key)
        start_node_id: ID of starting node (raw DB primary key)
        max_depth: Maximum hops (1-3 recommended)
        edge_types: Optional filter for edge relationship types

    Returns:
        Dict with nodes, edges, and arcs found
    """
    # Normalise inputs
    start_node_id = str(start_node_id)
    start_node_type = normalize_type(start_node_type)
    max_depth = min(max_depth, 5)  # Safety cap

    # Validate: reject non-graphable types with an actionable message
    defn = MEMORY_TYPES.get(start_node_type)
    if defn and not defn.graphable:
        valid_types = graph_type_keys()
        return {
            "error": (
                f"'{start_node_type}' is not a graphable memory type — "
                f"no edges are ever created for it. "
                f"Use recall_memory or search_memories to find a graphable item, "
                f"then pass its '_type' and 'id' here."
            ),
            "valid_graph_types": valid_types,
            "hint": (
                f"You recalled a '{start_node_type}' item (id={start_node_id}). "
                f"To explore graph connections, search for a related graphable item "
                f"(e.g. life_event, person, topic) and use that as the starting node."
            ),
        }
    if not defn and start_node_type not in {e for t in MEMORY_TYPES for e in (t,)}:
        valid_types = graph_type_keys()
        return {
            "error": (
                f"'{start_node_type}' is not a recognized memory type. "
                f"Use one of the valid graphable types."
            ),
            "valid_graph_types": valid_types,
        }

    with get_session() as session:
        # Debug: count total edges for this entity to verify edges exist
        total_edges = (
            session.query(func.count(Edge.id))
            .filter_by(entity_id=entity_id)
            .scalar() or 0
        )

        visited_nodes = set()
        visited_edges = set()
        result_nodes = []
        result_edges = []

        # BFS queue: (node_type, node_id, current_depth)
        queue = deque([(start_node_type, start_node_id, 0)])
        visited_nodes.add((start_node_type, start_node_id))

        while queue:
            node_type, node_id, depth = queue.popleft()

            if depth >= max_depth:
                continue

            # Find edges where this node appears on either side.
            # With normalized IDs (no prefixes), a simple equality match
            # on (type, id) is sufficient.
            edge_query = (
                session.query(Edge)
                .filter_by(entity_id=entity_id)
                .filter(
                    or_(
                        and_(
                            Edge.from_type == node_type,
                            Edge.from_id == node_id,
                        ),
                        and_(
                            Edge.to_type == node_type,
                            Edge.to_id == node_id,
                        ),
                    )
                )
            )

            # Filter by edge types if specified
            if edge_types:
                edge_query = edge_query.filter(Edge.relation.in_(edge_types))

            edges = edge_query.all()

            for edge in edges:
                if edge.id in visited_edges:
                    continue
                visited_edges.add(edge.id)

                result_edges.append({
                    "id": edge.id,
                    "from_type": edge.from_type,
                    "from_id": edge.from_id,
                    "to_type": edge.to_type,
                    "to_id": edge.to_id,
                    "relation": edge.relation,
                    "strength": edge.strength,
                    "context": edge.context,
                })

                # Determine the "other" node
                if edge.from_type == node_type and edge.from_id == node_id:
                    next_type = edge.to_type
                    next_id = edge.to_id
                else:
                    next_type = edge.from_type
                    next_id = edge.from_id

                node_key = (next_type, next_id)
                if node_key not in visited_nodes:
                    visited_nodes.add(node_key)
                    result_nodes.append({
                        "type": next_type,
                        "id": next_id,
                        "depth": depth + 1,
                    })
                    queue.append((next_type, next_id, depth + 1))

        # Also find any Arcs that include the start node
        arcs = _find_related_arcs(session, entity_id, start_node_type, start_node_id)

        # Debug info when no results found but edges exist
        debug = {"total_edges_for_entity": total_edges}
        if total_edges > 0 and not result_edges:
            # Show generic samples so the agent can pick a valid starting node
            samples = (
                session.query(Edge.from_type, Edge.from_id, Edge.to_type, Edge.to_id)
                .filter_by(entity_id=entity_id)
                .limit(5)
                .all()
            )
            debug["sample_edges"] = [
                {"from": f"{s.from_type}::{s.from_id}", "to": f"{s.to_type}::{s.to_id}"}
                for s in samples
            ]
            debug["queried_as"] = {"type": start_node_type, "id": start_node_id}
            debug["hint"] = (
                "No edges match this (type, id) pair. "
                "Make sure start_node_type matches the '_type' field and "
                "start_node_id matches the 'id' field from recall/search results. "
                "Try using one of the sample_edges above as a starting point."
            )

            # Search for this node_id anywhere in edges (fuzzy — catches prefix leftovers)
            partial_matches = (
                session.query(Edge.from_type, Edge.from_id, Edge.to_type, Edge.to_id)
                .filter_by(entity_id=entity_id)
                .filter(or_(
                    Edge.from_id.contains(start_node_id),
                    Edge.to_id.contains(start_node_id),
                ))
                .limit(5)
                .all()
            )
            debug["partial_id_matches"] = [
                {"from": f"{s.from_type}::{s.from_id}", "to": f"{s.to_type}::{s.to_id}"}
                for s in partial_matches
            ]

            # Count how many edges reference this type at all
            type_count = (
                session.query(func.count(Edge.id))
                .filter_by(entity_id=entity_id)
                .filter(or_(
                    Edge.from_type == start_node_type,
                    Edge.to_type == start_node_type,
                ))
                .scalar() or 0
            )
            debug["edges_with_type"] = {start_node_type: type_count}

        return {
            "start": {"type": start_node_type, "id": start_node_id},
            "nodes_found": len(result_nodes),
            "edges_found": len(result_edges),
            "nodes": result_nodes,
            "edges": result_edges,
            "arcs": arcs,
            "debug": debug,
        }


def _find_related_arcs(session, entity_id: str, node_type: str, node_id: str) -> list[dict]:
    """Find any narrative arcs that reference this node."""
    arcs = (
        session.query(Arc)
        .filter_by(entity_id=entity_id)
        .all()
    )

    related = []
    for arc in arcs:
        events = (
            session.query(ArcEvent)
            .filter_by(arc_id=arc.id)
            .all()
        )

        event_list = []
        arc_related = False
        for ev in events:
            event_dict = {
                "event_type": ev.event_type,
                "narrative": ev.narrative,
                "event_id": ev.event_id,
                "sequence": ev.sequence,
            }
            event_list.append(event_dict)
            # Check if this arc event references our node
            if ev.event_id and ev.event_id == node_id:
                arc_related = True

        if arc_related:
            related.append({
                "id": arc.id,
                "title": arc.title,
                "status": arc.status,
                "events": event_list,
            })

    return related
