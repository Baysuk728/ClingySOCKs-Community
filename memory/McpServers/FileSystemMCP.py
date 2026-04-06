"""
FileSystem MCP Server — Sandboxed file system access for the agent.

Gives the agent ability to read, write, list, and manage files
on the VPS within a sandboxed data directory.

Registered in mcp_config.json as "FileSystemMCP".
"""

import os
import sys
import shutil
from pathlib import Path

import _env_bridge  # noqa: F401 — load env vars from parent process bridge file

from mcp.server.fastmcp import FastMCP

# Fix UTF-8 encoding for Windows
if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

mcp = FastMCP("FileSystemMCP")

# Sandbox root — all file operations are restricted to this directory
AGENT_DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", "./data/agent")).resolve()
AGENT_DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 1_000_000  # 1MB read limit
MAX_WRITE_SIZE = 500_000   # 500KB write limit


def _safe_path(relative_path: str) -> Path:
    """Resolve a relative path within the sandbox. Raises ValueError if escape attempt."""
    # Normalize and resolve
    clean = relative_path.replace("\\", "/").lstrip("/")
    resolved = (AGENT_DATA_DIR / clean).resolve()

    # Ensure it's within the sandbox
    if not str(resolved).startswith(str(AGENT_DATA_DIR)):
        raise ValueError(f"Path escape attempt blocked: {relative_path}")

    return resolved


@mcp.tool()
def read_file(path: str) -> dict:
    """
    Read the contents of a file.

    Args:
        path: Relative path within the agent data directory (e.g., "journal/2026-03-03.md")
    """
    try:
        resolved = _safe_path(path)
        if not resolved.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not resolved.is_file():
            return {"success": False, "error": f"Not a file: {path}"}
        if resolved.stat().st_size > MAX_FILE_SIZE:
            return {"success": False, "error": f"File too large (>{MAX_FILE_SIZE} bytes)"}

        content = resolved.read_text(encoding="utf-8")
        return {
            "success": True,
            "path": path,
            "content": content,
            "size": len(content),
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Read failed: {str(e)}"}


@mcp.tool()
def write_file(path: str, content: str) -> dict:
    """
    Write content to a file. Creates parent directories automatically.
    Overwrites existing files.

    Args:
        path: Relative path within the agent data directory (e.g., "blog/my-post.md")
        content: The text content to write
    """
    try:
        if len(content) > MAX_WRITE_SIZE:
            return {"success": False, "error": f"Content too large (>{MAX_WRITE_SIZE} bytes)"}

        resolved = _safe_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": path,
            "size": len(content),
            "message": f"Written {len(content)} chars to {path}",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Write failed: {str(e)}"}


@mcp.tool()
def append_file(path: str, content: str) -> dict:
    """
    Append content to the end of a file. Creates the file if it doesn't exist.

    Args:
        path: Relative path within the agent data directory
        content: The text content to append
    """
    try:
        resolved = _safe_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)

        with open(resolved, "a", encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "path": path,
            "appended": len(content),
            "message": f"Appended {len(content)} chars to {path}",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Append failed: {str(e)}"}


@mcp.tool()
def list_directory(path: str = "") -> dict:
    """
    List files and directories at the given path.

    Args:
        path: Relative path within the agent data directory (empty string = root)
    """
    try:
        resolved = _safe_path(path) if path else AGENT_DATA_DIR

        if not resolved.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        if not resolved.is_dir():
            return {"success": False, "error": f"Not a directory: {path}"}

        entries = []
        for item in sorted(resolved.iterdir()):
            rel_path = str(item.relative_to(AGENT_DATA_DIR)).replace("\\", "/")
            entry = {
                "name": item.name,
                "path": rel_path,
                "type": "directory" if item.is_dir() else "file",
            }
            if item.is_file():
                entry["size"] = item.stat().st_size
            entries.append(entry)

        return {
            "success": True,
            "path": path or "/",
            "entries": entries,
            "count": len(entries),
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"List failed: {str(e)}"}


@mcp.tool()
def create_directory(path: str) -> dict:
    """
    Create a directory (and any parent directories).

    Args:
        path: Relative path within the agent data directory
    """
    try:
        resolved = _safe_path(path)
        resolved.mkdir(parents=True, exist_ok=True)
        return {
            "success": True,
            "path": path,
            "message": f"Directory created: {path}",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Create failed: {str(e)}"}


@mcp.tool()
def delete_file(path: str) -> dict:
    """
    Delete a file.

    Args:
        path: Relative path within the agent data directory
    """
    try:
        resolved = _safe_path(path)
        if not resolved.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if resolved.is_dir():
            return {"success": False, "error": "Use delete_directory for directories"}

        resolved.unlink()
        return {
            "success": True,
            "path": path,
            "message": f"Deleted: {path}",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Delete failed: {str(e)}"}


@mcp.tool()
def move_file(source: str, destination: str) -> dict:
    """
    Move or rename a file or directory.

    Args:
        source: Current relative path
        destination: New relative path
    """
    try:
        src = _safe_path(source)
        dst = _safe_path(destination)

        if not src.exists():
            return {"success": False, "error": f"Source not found: {source}"}

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        return {
            "success": True,
            "source": source,
            "destination": destination,
            "message": f"Moved: {source} → {destination}",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Move failed: {str(e)}"}


@mcp.tool()
def file_info(path: str) -> dict:
    """
    Get metadata about a file (size, modified time, etc.).

    Args:
        path: Relative path within the agent data directory
    """
    try:
        resolved = _safe_path(path)
        if not resolved.exists():
            return {"success": False, "error": f"Not found: {path}"}

        stat = resolved.stat()
        from datetime import datetime, timezone
        return {
            "success": True,
            "path": path,
            "type": "directory" if resolved.is_dir() else "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Info failed: {str(e)}"}


if __name__ == "__main__":
    mcp.run()
