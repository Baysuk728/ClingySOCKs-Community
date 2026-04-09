"""
Shared test fixtures for ClingySOCKs enhanced features.

Uses SQLite in-memory database to avoid requiring PostgreSQL for tests.
Patches get_session() so all service modules use the test DB.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

# Set test env before any src imports
os.environ["EMBEDDINGS_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["VAULT_MODE"] = "prod"  # Prevents session.py from building a PG engine at import time

# Teach SQLite how to store Python lists and dicts (PG ARRAY/JSONB defaults)
sqlite3.register_adapter(list, lambda val: json.dumps(val))
sqlite3.register_adapter(dict, lambda val: json.dumps(val))

from src.db.models import (
    Base, Entity, PersonaIdentity, UserProfile, Relationship,
    MoodState, Narrative, MemoryBlock, Conversation, Message,
    Edge, FactualEntity, LifeEvent, UnresolvedThread, EchoDream,
    EmotionalPattern, Lexicon, Permission, Artifact,
)


# ── SQLite setup ─────────────────────────────────────

_types_replaced = False

def _replace_pg_types():
    """Replace PG-specific column types with Text (once)."""
    global _types_replaced
    if _types_replaced:
        return
    import sqlalchemy.sql.sqltypes as sqltypes
    from sqlalchemy import Text

    pg_types = [sqltypes.ARRAY]
    try:
        from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB
        pg_types.extend([PG_ARRAY, JSONB])
    except ImportError:
        pass
    try:
        from pgvector.sqlalchemy import Vector
        pg_types.append(Vector)
    except ImportError:
        pass

    pg_type_tuple = tuple(pg_types)
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, pg_type_tuple):
                col.type = Text()
    _types_replaced = True

# Do the type replacement once at module load
_replace_pg_types()

# Single shared engine for all tests (SQLite in-memory)
_shared_engine = create_engine("sqlite://", echo=False)
Base.metadata.create_all(_shared_engine)


@pytest.fixture
def db_engine():
    """Shared SQLite engine — tables already created."""
    return _shared_engine


@pytest.fixture(autouse=True)
def _clean_tables():
    """Delete all rows between tests for isolation."""
    yield
    # After each test, wipe all table data
    with _shared_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_session(db_engine):
    """SQLAlchemy session bound to test engine."""
    _SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = _SessionLocal()
    yield session
    session.close()


@pytest.fixture
def patch_session(db_engine, monkeypatch):
    """
    Patch src.db.session.get_session to use the test SQLite engine.
    All service modules that call get_session() will use the test DB.
    """
    _SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)

    @contextmanager
    def _test_get_session():
        session = _SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("src.db.session.get_session", _test_get_session)
    return _test_get_session


# ── Entity ID ────────────────────────────────────────

TEST_ENTITY_ID = "test-agent-001"


@pytest.fixture
def entity_id():
    return TEST_ENTITY_ID


# ── Seed Helpers ─────────────────────────────────────

def _now(**delta_kwargs):
    return datetime.now(timezone.utc) + timedelta(**delta_kwargs) if delta_kwargs else datetime.now(timezone.utc)


@pytest.fixture
def seed_entity(patch_session, entity_id):
    """Seed a basic entity with persona, user profile, and relationship."""
    from src.db.session import get_session

    with get_session() as session:
        entity = Entity(
            id=entity_id,
            entity_type="agent",
            name="TestAgent",
            owner_user_id="test-user",
        )
        session.add(entity)

        persona = PersonaIdentity(entity_id=entity_id)
        if hasattr(persona, "display_name"):
            persona.display_name = "TestAgent"
        session.add(persona)

        profile = UserProfile(entity_id=entity_id)
        if hasattr(profile, "name"):
            profile.name = "TestUser"
        session.add(profile)

        rel = Relationship(
            entity_id=entity_id,
            target_id="test-user",
            target_type="human",
        )
        if hasattr(rel, "style"):
            rel.style = "supportive"
        if hasattr(rel, "trust_level"):
            rel.trust_level = "high"
        session.add(rel)

    return entity_id


@pytest.fixture
def seed_memories(patch_session, seed_entity):
    """Seed entity with a variety of memory items for testing."""
    entity_id = seed_entity
    from src.db.session import get_session

    with get_session() as session:
        # Life event
        session.add(LifeEvent(
            id="evt-auth-migration",
            entity_id=entity_id,
            title="Auth migration started",
            narrative="We began migrating the authentication system to OAuth2.",
            category="technical",
            created_at=_now(days=-10),
        ))
        session.add(LifeEvent(
            id="evt-auth-complete",
            entity_id=entity_id,
            title="Auth migration completed",
            narrative="The auth migration to OAuth2 is now complete.",
            category="technical",
            created_at=_now(days=-3),
        ))

        # Factual entities
        session.add(FactualEntity(
            id="person-alice",
            entity_id=entity_id,
            type="person",
            name="Alice",
            description="Frontend developer working on auth",
            created_at=_now(days=-15),
        ))
        session.add(FactualEntity(
            id="project-auth",
            entity_id=entity_id,
            type="project",
            name="Auth System",
            description="OAuth2 authentication migration project",
            created_at=_now(days=-12),
        ))

        # Edges
        session.add(Edge(
            entity_id=entity_id,
            from_id="evt-auth-migration",
            from_type="life_event",
            to_id="person-alice",
            to_type="factual_entity",
            relation="involves",
            strength=0.8,
        ))
        session.add(Edge(
            entity_id=entity_id,
            from_id="evt-auth-migration",
            from_type="life_event",
            to_id="evt-auth-complete",
            to_type="life_event",
            relation="evolved_into",
            strength=0.9,
        ))

        # Unresolved thread
        session.add(UnresolvedThread(
            entity_id=entity_id,
            thread="Need to review auth test coverage",
            status="open",
            what_user_needs="Code review feedback",
            created_at=_now(days=-2),
        ))

        # Mood state
        mood = MoodState(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            primary_mood="focused",
            energy_level=7,
            affection_meter=5,
            timestamp=_now(),
        )
        if hasattr(mood, "energy_f"):
            mood.energy_f = 0.7
        if hasattr(mood, "warmth"):
            mood.warmth = 0.6
        if hasattr(mood, "chaos"):
            mood.chaos = 0.2
        if hasattr(mood, "melancholy"):
            mood.melancholy = 0.1
        session.add(mood)

        # Narrative (uses updated_at, not created_at)
        session.add(Narrative(
            entity_id=entity_id,
            scope="recent",
            content="Working on auth migration with Alice. Good progress.",
            is_current=True,
            updated_at=_now(days=-1),
        ))

        # Memory blocks (pinned)
        session.add(MemoryBlock(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            title="Auth migration notes",
            content="OAuth2 flow: code grant → token exchange → refresh",
            category="notes",
            pinned=True,
            status="active",
            created_at=_now(days=-5),
        ))

        # Lexicon
        session.add(Lexicon(
            entity_id=entity_id,
            term="PKCE",
            definition="Proof Key for Code Exchange - OAuth2 extension for auth security",
            status="active",
            created_at=_now(days=-8),
        ))

        # Conversation + messages
        conv_id = str(uuid.uuid4())
        session.add(Conversation(
            id=conv_id,
            entity_id=entity_id,
            title="Auth discussion",
            source="native",
            created_at=_now(days=-5),
        ))
        session.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            sender_id="user",
            content="Let's talk about the auth migration",
            timestamp=_now(days=-5),
            message_index=0,
        ))
        session.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            sender_id=entity_id,
            content="The OAuth2 migration is going well with PKCE support",
            timestamp=_now(days=-5, hours=1),
            message_index=1,
        ))

    return entity_id
