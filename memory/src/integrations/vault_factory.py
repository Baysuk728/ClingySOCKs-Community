"""
Vault factory — selects the correct vault implementation based on AUTH_PROVIDER.

Usage:
    from src.integrations.vault_factory import get_vault
    vault = get_vault()
    api_key = await vault.get_llm_key(user_id, model)

Both LocalKeyVault and KeyVault have the same public interface.
"""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_vault():
    """
    Get the singleton vault instance.
    Uses LocalKeyVault (PostgreSQL).
    """
    from src.integrations.local_vault import local_vault
    return local_vault
