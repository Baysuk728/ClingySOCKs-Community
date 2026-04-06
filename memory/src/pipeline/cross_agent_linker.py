"""
Cross-Agent Entity Linker.

Post-harvest step that links FactualEntity records to actual agent entities
in the `entities` table. When Agent A's harvest captures "Agent B" as a
FactualEntity (type=person/companion), this linker:

1. Detects FactualEntities whose names match known agents
2. Sets `linked_entity_id` to the actual agent's entity_id
3. Optionally creates AgentRelationship records
4. Marks cross-agent edges with memory_scope='team'

This runs after factual extraction, once per harvest.
"""

from datetime import datetime, timezone

from src.db.session import get_session
from src.db.models import (
    Entity, FactualEntity, Edge, AgentRelationship,
)


def link_cross_agent_entities(
    entity_id: str,
    owner_user_id: str | None = None,
) -> dict:
    """
    Scan an agent's FactualEntities for references to other known agents
    and link them.

    Args:
        entity_id: The agent whose factual entities to scan
        owner_user_id: If provided, only match agents owned by this user

    Returns:
        Stats dict: entities_linked, relationships_created, edges_upgraded
    """
    stats = {
        "entities_linked": 0,
        "relationships_created": 0,
        "edges_upgraded": 0,
    }

    with get_session() as session:
        # Load all known agents (excluding the current entity)
        agent_query = session.query(Entity).filter(
            Entity.entity_type == "agent",
            Entity.id != entity_id,
        )
        if owner_user_id:
            agent_query = agent_query.filter(Entity.owner_user_id == owner_user_id)

        known_agents = agent_query.all()

        if not known_agents:
            return stats

        # Build lookup: lowercase name/alias → Entity
        agent_lookup: dict[str, Entity] = {}
        for agent in known_agents:
            agent_lookup[agent.name.lower().strip()] = agent
            # Also add the entity_id as a possible match
            agent_lookup[agent.id.lower().strip()] = agent

        # Load this entity's factual entities that might be agents
        # (type = person, companion, or concept — agents can be described as any)
        candidate_types = ["person", "companion", "concept", "group"]
        factual_entities = (
            session.query(FactualEntity)
            .filter_by(entity_id=entity_id)
            .filter(FactualEntity.type.in_(candidate_types))
            .filter(FactualEntity.linked_entity_id.is_(None))  # Not already linked
            .all()
        )

        for fe in factual_entities:
            # Try to match by name
            matched_agent = agent_lookup.get(fe.name.lower().strip())

            # Try aliases
            if not matched_agent and fe.aliases:
                for alias in fe.aliases:
                    matched_agent = agent_lookup.get(alias.lower().strip())
                    if matched_agent:
                        break

            if not matched_agent:
                continue

            # Link the factual entity to the actual agent
            fe.linked_entity_id = matched_agent.id
            fe.memory_scope = "team"  # Cross-agent facts are team-scoped
            stats["entities_linked"] += 1
            print(f"   🔗 Linked FactualEntity '{fe.name}' → Agent '{matched_agent.name}' ({matched_agent.id})")

            # Auto-create AgentRelationship if not exists
            existing_rel = (
                session.query(AgentRelationship)
                .filter_by(
                    source_entity_id=entity_id,
                    target_entity_id=matched_agent.id,
                )
                .first()
            )
            if not existing_rel:
                rel = AgentRelationship(
                    source_entity_id=entity_id,
                    target_entity_id=matched_agent.id,
                    relationship_type="peer",
                    trust_level=5,
                    context=f"Auto-detected: {fe.name} mentioned in conversations",
                )
                session.add(rel)
                stats["relationships_created"] += 1
                print(f"   🤝 Created AgentRelationship: {entity_id} → {matched_agent.id}")

            # Upgrade edges involving this factual entity to team scope
            edges = (
                session.query(Edge)
                .filter_by(entity_id=entity_id, status="active")
                .filter(
                    (Edge.from_id == fe.id) | (Edge.to_id == fe.id)
                )
                .all()
            )
            for edge in edges:
                if edge.memory_scope == "private":
                    edge.memory_scope = "team"
                    stats["edges_upgraded"] += 1

        session.commit()

    if any(v > 0 for v in stats.values()):
        print(f"   ✅ Cross-agent linking: {stats['entities_linked']} linked, "
              f"{stats['relationships_created']} relationships, "
              f"{stats['edges_upgraded']} edges upgraded to team scope")

    return stats
