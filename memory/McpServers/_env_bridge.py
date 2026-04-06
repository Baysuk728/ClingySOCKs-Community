"""
Shared env-bridge loader for MCP subprocess servers.

In Docker/Coolify setups, StdioServerParameters(env=...) doesn't always
propagate environment variables to child processes. As a workaround,
the parent process (mcp_client.py) writes os.environ to a .env.mcp file
before spawning MCP servers. Each server imports this module to load it.

Usage (at the top of each MCP server, before reading any env vars):
    import _env_bridge  # noqa: F401 — loads .env.mcp + .env into os.environ
"""

from pathlib import Path
from dotenv import load_dotenv

_project_root = Path(__file__).parent.parent

# Primary: env bridge file written by parent process at MCP boot time
_bridge = _project_root / ".env.mcp"
if _bridge.exists():
    load_dotenv(_bridge, override=False)

# Fallback: regular .env file (for local dev setups without Docker)
load_dotenv(_project_root / ".env", override=False)
