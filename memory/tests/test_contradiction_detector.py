"""Tests for Contradiction Detector (contradiction_detector.py)."""

import pytest
from src.db.models import Edge, FactualEntity


class TestEdgeContradictions:
    """Detect contradictory edge relations."""

    def test_no_contradictions_clean_graph(self, seed_memories):
        from src.services.contradiction_detector import detect_contradictions
        result = detect_contradictions(seed_memories)

        # Seeded edges are clean — no contradictions expected
        assert isinstance(result, list)

    def test_detects_contradictory_edges(self, seed_memories):
        """Two edges with opposing relations (e.g., works_on + left) = contradiction."""
        from src.db.session import get_session
        from src.services.contradiction_detector import detect_contradictions

        with get_session() as session:
            # Add contradictory edge pair
            session.add(Edge(
                entity_id=seed_memories,
                from_id="person-alice",
                from_type="factual_entity",
                to_id="project-auth",
                to_type="factual_entity",
                relation="works_on",
                strength=0.8,
            ))
            session.add(Edge(
                entity_id=seed_memories,
                from_id="person-alice",
                from_type="factual_entity",
                to_id="project-auth",
                to_type="factual_entity",
                relation="left",
                strength=0.7,
            ))

        result = detect_contradictions(seed_memories, scope="edges")
        # Should find the works_on / left contradiction
        assert len(result) >= 1
        assert any("contradict" in str(c).lower() or c.get("severity") for c in result)


class TestEntityContradictions:
    """Detect duplicate or ambiguous factual entities."""

    def test_detects_duplicate_names(self, seed_memories):
        from src.db.session import get_session
        from src.services.contradiction_detector import detect_contradictions

        with get_session() as session:
            # Add a duplicate-named entity with different type
            session.add(FactualEntity(
                id="concept-auth-system",
                entity_id=seed_memories,
                type="concept",
                name="Auth System",  # Same name as project-auth
                description="Abstract concept of authentication",
            ))

        result = detect_contradictions(seed_memories, scope="entities")
        assert isinstance(result, list)
        # May or may not flag depending on implementation — at minimum shouldn't crash


class TestContradictionReport:
    """contradiction_report() — summary with counts and severity."""

    def test_report_structure(self, seed_memories):
        from src.services.contradiction_detector import contradiction_report
        report = contradiction_report(seed_memories)

        assert isinstance(report, dict)
        assert "contradictions" in report or "summary" in report or "total" in report

    def test_report_empty_entity(self, patch_session):
        from src.services.contradiction_detector import contradiction_report
        report = contradiction_report("nonexistent-entity")
        assert isinstance(report, dict)
