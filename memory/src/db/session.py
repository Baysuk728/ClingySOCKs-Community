"""
Database session management for ClingySOCKs Memory.

Centralised single source of truth for the PostgreSQL connection.
Supports runtime reconfiguration so the app can switch from the
bootstrap .env DATABASE_URL to a user-configured BYOD database
stored in the secure vault.

Resolution order (at startup):
  1. Active BYOD database from secure vault  (if configured + initialized)
  2. .env DATABASE_URL                           (dev mode fallback)
  3. No database available                       (prod mode without BYOD)
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from src.config import DATABASE_URL
from src.db.models import Base


_CONNECTION_ERROR_MARKERS = (
    "connection refused",
    "server closed the connection",
    "terminating connection",
    "could not connect to server",
    "connection not open",
    "ssl syscall error",
    "connection reset by peer",
    "connection timed out",
    "timeout expired",
)


def _build_engine(url: str):
    return create_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        pool_timeout=30,
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )


def _is_connection_error(exc: Exception) -> bool:
    if isinstance(exc, (OperationalError, InterfaceError)):
        return True
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True

    exc_text = str(exc).lower()
    return any(marker in exc_text for marker in _CONNECTION_ERROR_MARKERS)


def _dispose_engine_safely() -> None:
    if _engine is None:
        return
    try:
        _engine.dispose()
    except Exception:
        pass


# ── VAULT_MODE ────────────────────────────────────────
# Read directly from env to avoid circular imports with vault.py
_VAULT_MODE = os.getenv("VAULT_MODE", "dev").lower().strip()

# ── Mutable Engine State ──────────────────────────────
# These are module-level so every caller of get_session()
# automatically uses the currently-active engine.
#
# In prod mode we do NOT bootstrap from .env — the engine stays
# None until a vault database is loaded via try_load_vault_database()
# or reconfigure_engine().  This ensures the system is truly
# non-functional until the user configures a database.

if _VAULT_MODE == "prod":
    _current_url = None
    _engine = None
    _SessionLocal = None
    _db_source = "none"   # "none" | "env" | "vault"
else:
    _current_url = DATABASE_URL
    _engine = _build_engine(_current_url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    _db_source = "env"

# Backward-compatible aliases for scripts that do `from src.db.session import engine`
# Updated by reconfigure_engine() when the engine changes.
engine = _engine
SessionLocal = _SessionLocal


def reconfigure_engine(url: str, *, source: str = "vault") -> None:
    """
    Hot-swap the database engine to a new URL at runtime.

    Called when:
      - A BYOD database is activated from the vault
      - Startup resolves an active database from the vault

    All subsequent get_session() calls will use the new engine.
    """
    global _engine, _SessionLocal, _current_url, _db_source, engine, SessionLocal

    old_engine = _engine

    _current_url = url
    _engine = _build_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    _db_source = source

    # Update backward-compat aliases
    engine = _engine
    SessionLocal = _SessionLocal

    # Dispose old engine connections
    try:
        old_engine.dispose()
    except Exception:
        pass

    # Mask the URL for logging
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    db_name = parsed.path.lstrip("/") if parsed.path else "unknown"
    print(f"🔗 Database engine reconfigured → {host}/{db_name} (source: {source})")


def get_db_source() -> str:
    """Return the current database source: 'env' or 'vault'."""
    return _db_source


def get_db_host() -> str:
    """Return a masked version of the current database URL for display."""
    if not _current_url:
        return "not configured"
    from urllib.parse import urlparse
    parsed = urlparse(_current_url)
    host = parsed.hostname or "unknown"
    db_name = parsed.path.lstrip("/") if parsed.path else "unknown"
    return f"{host}/{db_name}"


def init_db():
    """Create all tables. Enables pgvector extension first."""
    if _engine is None:
        print("⚠️  No database engine available — skipping table creation")
        print("   Configure a database in Settings → Database to get started.")
        return
    try:
        with _engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        Base.metadata.create_all(_engine)
        print("✅ Database tables created successfully (pgvector enabled)")
    except Exception as exc:
        if _is_connection_error(exc):
            _dispose_engine_safely()
            print(f"⚠️  Database unavailable during init_db — startup will continue: {exc}")
            return
        raise


def drop_db():
    """Drop all tables. USE WITH CAUTION."""
    if _engine is None:
        print("❌ No database engine available")
        return
    Base.metadata.drop_all(_engine)
    print("⚠️ All database tables dropped")


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when a database operation is attempted without a configured database."""
    pass


class DatabaseUnavailableError(RuntimeError):
    """Raised when the configured database is temporarily unavailable."""
    pass


@contextmanager
def get_session() -> Session:
    """Context manager for database sessions with auto-commit/rollback."""
    if _SessionLocal is None:
        raise DatabaseNotConfiguredError(
            "No database configured. "
            "In VAULT_MODE=prod, configure a database in Settings → Database."
        )
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass

        if _is_connection_error(exc):
            _dispose_engine_safely()
            raise DatabaseUnavailableError(
                "Database is temporarily unavailable. Retry in a moment."
            ) from exc
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass


def check_connection() -> bool:
    """Test database connectivity. Tries to create DB if missing."""
    if _engine is None:
        return False
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        # If database doesn't exist, try to create it
        if "does not exist" in str(e) or '3D000' in str(e):
            print(f"⚠️  Database does not exist. Attempting to create...")
            try:
                from urllib.parse import urlparse

                url = urlparse(_current_url)
                # Construct URL for default postgres db
                netloc = f"{url.username}:{url.password}@{url.hostname}:{url.port}" if url.port else f"{url.username}:{url.password}@{url.hostname}"
                if not url.password:
                    netloc = f"{url.username}@{url.hostname}:{url.port}" if url.port else f"{url.username}@{url.hostname}"

                default_db_url = f"postgresql://{netloc}/postgres"

                default_engine = create_engine(default_db_url, isolation_level="AUTOCOMMIT")
                with default_engine.connect() as conn:
                    db_name = url.path[1:]
                    conn.execute(text(f"CREATE DATABASE {db_name}"))
                print(f"✅ Created database '{db_name}'")
                return True
            except Exception as create_error:
                print(f"❌ Failed to create database: {create_error}")
                return False

        if _is_connection_error(e):
            _dispose_engine_safely()
        print(f"❌ Database connection failed: {e}")
        return False


def try_load_vault_database() -> bool:
    """
    Try to load an active BYOD database from the vault and reconfigure the engine.

    Checks the vault for a pointer to the user whose
    BYOD database should be used as the app's primary database.

    Skipped entirely when AUTH_PROVIDER=local (self-hosted mode).

    Returns True if the engine was reconfigured, False otherwise.
    """
    # Skip vault BYOD lookup in self-hosted mode
    auth_provider = os.getenv("AUTH_PROVIDER", "local").lower().strip()
    if auth_provider == "local":
        return False

    try:
        from src.integrations.vault import VaultConnector
        from src.integrations.crypto import decrypt

        vc = VaultConnector()
        db = fs.get_db()
        if not db:
            return False

        # Check system-level active database pointer
        doc = db.collection("system").document("active_database").get()
        if not doc.exists:
            return False

        data = doc.to_dict()
        user_id = data.get("user_id")
        if not user_id or not data.get("active"):
            return False

        # Load the user's encrypted database URL
        vault_doc = (
            db.collection("users")
            .document(user_id)
            .collection("vault")
            .document("database")
            .get()
        )
        if not vault_doc.exists:
            print(f"⚠️ Active database pointer references user {user_id} but no vault/database doc found")
            return False

        vault_data = vault_doc.to_dict()
        if not vault_data.get("initialized"):
            print(f"⚠️ Active database for user {user_id} exists but is not initialized")
            return False

        encrypted_cs = vault_data.get("encryptedConnectionString")
        if not encrypted_cs:
            return False

        db_url = decrypt(encrypted_cs)
        reconfigure_engine(db_url, source="vault")
        return True

    except Exception as e:
        print(f"⚠️ Failed to load vault database on startup: {e}")
        return False
