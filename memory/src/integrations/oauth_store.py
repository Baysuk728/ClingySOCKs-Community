"""
OAuth Token Store — Persist and load platform tokens from PostgreSQL.

Used by:
  - main.py (load into os.environ at startup before MCP boot)
  - SocialMCP (refresh expired tokens automatically)
"""

import os
from datetime import datetime, timezone

from src.db.session import get_session
from src.db.models import OAuthToken


# Maps platform/config names → environment variable names
_PLATFORM_ENV_MAP = {
    "instagram": "INSTAGRAM_ACCESS_TOKEN",
    "youtube": "YOUTUBE_REFRESH_TOKEN",
    "linkedin": "LINKEDIN_ACCESS_TOKEN",
    "patreon": "PATREON_ACCESS_TOKEN",
    # Server-level config (stored as pseudo-platform entries)
    "public_base_url": "PUBLIC_BASE_URL",
}


def save_token(
    platform: str,
    access_token: str,
    scopes: str = "",
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    """Upsert an OAuth token for a platform into the database."""
    with get_session() as session:
        existing = session.query(OAuthToken).filter_by(platform=platform).first()
        if existing:
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.scopes = scopes
            existing.expires_at = expires_at
            existing.updated_at = datetime.now(timezone.utc)
        else:
            token = OAuthToken(
                platform=platform,
                access_token=access_token,
                refresh_token=refresh_token,
                scopes=scopes,
                expires_at=expires_at,
            )
            session.add(token)

    # Also hot-load into current process env
    env_key = _PLATFORM_ENV_MAP.get(platform)
    if env_key:
        os.environ[env_key] = access_token


def save_config(key: str, value: str) -> None:
    """Save a server-level config value (e.g. public_base_url) to the DB.

    Reuses the oauth_tokens table: platform=key, access_token=value.
    Loaded into os.environ at startup via load_all_tokens_to_env().
    """
    if key not in _PLATFORM_ENV_MAP:
        raise ValueError(f"Unknown config key: {key}. Valid: {list(_PLATFORM_ENV_MAP)}")
    save_token(platform=key, access_token=value)


def get_refresh_token(platform: str) -> str | None:
    """Get the stored refresh token for a platform."""
    try:
        with get_session() as session:
            tok = session.query(OAuthToken).filter_by(platform=platform).first()
            return tok.refresh_token if tok else None
    except Exception:
        return None





def load_all_tokens_to_env() -> int:
    """Load all stored OAuth tokens into os.environ.

    Called at startup before MCP processes are spawned so child
    processes inherit the tokens via the environment.

    Returns the number of tokens loaded.
    """
    # Maps platform → env var name for refresh tokens
    _REFRESH_ENV_MAP = {}
    count = 0
    try:
        with get_session() as session:
            tokens = session.query(OAuthToken).all()
            for tok in tokens:
                env_key = _PLATFORM_ENV_MAP.get(tok.platform)
                if env_key and tok.access_token:
                    os.environ[env_key] = tok.access_token
                    print(f"  🔑 Loaded OAuth token for: {tok.platform}")
                    count += 1
                # Also export refresh tokens so MCP subprocesses can refresh
                refresh_key = _REFRESH_ENV_MAP.get(tok.platform)
                if refresh_key and tok.refresh_token:
                    os.environ[refresh_key] = tok.refresh_token
    except Exception as e:
        print(f"  ⚠️  Could not load OAuth tokens from DB: {e}")
    return count
