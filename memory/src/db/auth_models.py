"""
Authentication models for self-hosted (local) deployments.

These tables provide the authentication and vault system for self-hosters.
All data lives in the same PostgreSQL database as the rest of ClingySOCKs.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, Index
from src.db.models import Base


class AppUser(Base):
    """
    In SaaS mode, this table may be bypassed by the central auth provider.
    """
    __tablename__ = "app_users"

    id = Column(Text, primary_key=True)                          # UUID
    email = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)                 # bcrypt hash
    display_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_app_users_email", "email"),
    )


class ApiKeyEntry(Base):
    """
    Encrypted API key storage (replaces the centralized vault for self-hosted).

    Stores BYOK keys (LLM providers, TTS, search) in PostgreSQL.
    Uses the same AES-256-GCM encryption as the Firestore vault.
    """
    __tablename__ = "api_keys"

    id = Column(Text, primary_key=True)                          # UUID
    user_id = Column(Text, nullable=False)                     # References app_users.id (no FK for dev-mode flexibility)
    provider = Column(Text, nullable=False)                      # 'gemini', 'openai', etc.
    encrypted_key = Column(Text, nullable=False)                 # JSON string of {iv, encryptedData, authTag}
    masked_key = Column(Text, nullable=True)                     # Display mask: "sk-m••••key"
    search_provider = Column(Text, nullable=True)                # For search keys: 'exa', 'tavily', etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_api_keys_user_provider", "user_id", "provider", unique=True),
    )
