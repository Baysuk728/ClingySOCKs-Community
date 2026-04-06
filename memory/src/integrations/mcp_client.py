import json
import os
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

# Path for the env bridge file — written by the parent process before
# spawning MCP subprocesses so they can load env vars reliably even
# when StdioServerParameters doesn't propagate them (Docker/Coolify).
_MCP_ENV_BRIDGE = Path(__file__).parent.parent.parent / ".env.mcp"

class MCPClientManager:
    def __init__(self, config_path: str = "mcp_config.json"):
        self.config_path = config_path
        self.servers: Dict[str, dict] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stacks: Dict[str, AsyncExitStack] = {}
        self._reconnect_lock = asyncio.Lock()
        
        # Load config
        self._load_config()
        
    def _load_config(self):
        """Load the mcp_config.json file if it exists."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.servers = config.get("mcpServers", {})
            except Exception as e:
                print(f"❌ Failed to load MCP config {self.config_path}: {e}")
        else:
            print(f"⚠️ MCP config not found at {self.config_path}")

    @staticmethod
    def _write_env_bridge():
        """Write current os.environ to a .env file that MCP subprocesses can load.

        This is a workaround for Docker/Coolify setups where
        StdioServerParameters(env=...) doesn't propagate env vars
        to child processes reliably.
        """
        try:
            lines = []
            for key, val in os.environ.items():
                # Skip internal/noisy vars, only bridge vars MCP servers need
                if any(key.startswith(p) for p in ("_", "PYTHON", "PATH", "HOME", "LANG", "LC_", "TERM", "SHELL", "SHLVL", "PWD", "OLDPWD", "HOSTNAME")):
                    continue
                # Escape newlines and quotes for .env format
                escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                lines.append(f'{key}="{escaped}"')
            _MCP_ENV_BRIDGE.write_text("\n".join(lines), encoding="utf-8")
            print(f"  📝 Wrote {len(lines)} env vars to {_MCP_ENV_BRIDGE}")
        except Exception as e:
            print(f"  ⚠️  Failed to write MCP env bridge: {e}")

    async def connect_all(self):
        """Connect to all configured MCP servers."""
        self._write_env_bridge()
        for server_name, server_config in self.servers.items():
            await self.connect_server(server_name, server_config)
            
    async def connect_server(self, name: str, config: dict):
        """Connect to a specific MCP server using stdio or SSE transport."""
        print(f"🔌 Connecting to MCP server: {name}")
        try:
            # Clean up existing connection if any
            if name in self._exit_stacks:
                try:
                    await self._exit_stacks[name].aclose()
                except Exception:
                    pass
                self.sessions.pop(name, None)
                self._exit_stacks.pop(name, None)

            transport = config.get("transport", "stdio")

            if transport == "sse":
                # Remote SSE-based MCP server (e.g., Canva)
                await self._connect_sse(name, config)
                return

            command = config.get("command")
            args = config.get("args", [])
            env_overrides = config.get("env", {})

            # Explicitly merge with parent environment so VPS system variables
            # are reliably inherited.
            merged_env = os.environ.copy()

            if env_overrides:
                merged_env.update(env_overrides)

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=merged_env
            )
            
            exit_stack = AsyncExitStack()
            self._exit_stacks[name] = exit_stack
            
            stdio_transport = await exit_stack.enter_async_context(stdio_client(server_params))
            read_stream, write_stream = stdio_transport
            
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            
            await session.initialize()
            
            self.sessions[name] = session
            print(f"✅ Connected to MCP server: {name}")
            
        except Exception as e:
            print(f"❌ Failed to connect to MCP server {name}: {e}")

    async def _connect_sse(self, name: str, config: dict):
        """Connect to a remote MCP server via SSE (Server-Sent Events) transport."""
        try:
            from mcp.client.sse import sse_client

            url = config.get("url")
            if not url:
                print(f"❌ SSE server {name} missing 'url' in config")
                return

            headers = config.get("headers", {})

            exit_stack = AsyncExitStack()
            self._exit_stacks[name] = exit_stack

            sse_transport = await exit_stack.enter_async_context(
                sse_client(url=url, headers=headers)
            )
            read_stream, write_stream = sse_transport

            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()

            self.sessions[name] = session
            print(f"✅ Connected to SSE MCP server: {name}")

        except ImportError:
            print(f"⚠️ SSE client not available. Install 'mcp[sse]' or 'httpx-sse' for SSE support.")
        except Exception as e:
            print(f"❌ Failed to connect to SSE MCP server {name}: {e}")

    async def _ensure_connected(self, server_name: str) -> Optional[ClientSession]:
        """Check if a server session is alive; reconnect if needed."""
        session = self.sessions.get(server_name)
        if session:
            return session
        
        # Session is missing — try to reconnect
        async with self._reconnect_lock:
            # Double-check after acquiring lock
            session = self.sessions.get(server_name)
            if session:
                return session
                
            config = self.servers.get(server_name)
            if not config:
                print(f"❌ No config found for MCP server: {server_name}")
                return None
                
            print(f"🔄 Reconnecting to MCP server: {server_name}")
            await self.connect_server(server_name, config)
            return self.sessions.get(server_name)

    async def disconnect_all(self):
        """Disconnect from all MCP servers."""
        for name, stack in self._exit_stacks.items():
            try:
                await stack.aclose()
                print(f"🔌 Disconnected from MCP server: {name}")
            except Exception as e:
                print(f"❌ Error disconnecting from {name}: {e}")
                
        self.sessions.clear()
        self._exit_stacks.clear()

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Get all tools from all connected MCP servers and format them 
        for LiteLLM (OpenAI function calling schema).
        """
        all_tools = []
        for server_name in list(self.servers.keys()):
            try:
                session = await self._ensure_connected(server_name)
                if not session:
                    continue
                result = await session.list_tools()
                for tool in result.tools:
                    # Convert MCP tool schema to OpenAI format
                    openai_tool = {
                        "type": "function",
                        "function": {
                            "name": f"{server_name}__{tool.name}",  # Prefix with server name
                            "description": tool.description or "",
                            "parameters": tool.inputSchema
                        }
                    }
                    all_tools.append(openai_tool)
            except Exception as e:
                print(f"❌ Error listing tools for {server_name}: {e}")
                # Mark session as dead so next call will reconnect
                self.sessions.pop(server_name, None)
                
        return all_tools

    async def call_tool(self, tool_name_with_prefix: str, arguments: dict) -> Any:
        """
        Call a tool on the appropriate MCP server.
        Expects tool_name to be prefixed like 'ServerName__ToolName'.
        Auto-reconnects if the session is dead.
        """
        if "__" not in tool_name_with_prefix:
            raise ValueError(f"Invalid MCP tool name: {tool_name_with_prefix}. Must be prefixed with server name.")
            
        server_name, tool_name = tool_name_with_prefix.split("__", 1)
        
        # Try with auto-reconnect (up to 2 attempts)
        for attempt in range(2):
            session = await self._ensure_connected(server_name)
            if not session:
                raise ValueError(f"MCP server not connected and reconnect failed: {server_name}")
                
            try:
                print(f"🛠️ Calling MCP tool {tool_name} on {server_name} with: {arguments}")
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments=arguments),
                    timeout=30.0  # 30 second timeout to prevent hangs
                )
                
                # Extract content from result
                if getattr(result, "content", None):
                    # Typically content is a list of TextContent objects
                    texts = [c.text for c in result.content if hasattr(c, 'text')]
                    if len(texts) == 1:
                        return texts[0]
                    elif len(texts) > 1:
                        return "\n".join(texts)
                
                # Fallback
                return str(result)
            except asyncio.TimeoutError:
                print(f"⏱️ MCP tool {tool_name} timed out after 30s")
                # Kill the session and try reconnecting on next attempt
                self.sessions.pop(server_name, None)
                if attempt == 0:
                    print(f"🔄 Retrying after timeout...")
                    continue
                return json.dumps({"error": f"Tool {tool_name} timed out after 30s"})
            except Exception as e:
                print(f"❌ Error calling MCP tool {tool_name} (attempt {attempt+1}): {e}")
                # Mark session as dead for reconnect
                self.sessions.pop(server_name, None)
                if attempt == 0:
                    print(f"🔄 Retrying after error...")
                    continue
                return json.dumps({"error": str(e)})

# Global instance
mcp_manager = MCPClientManager()
