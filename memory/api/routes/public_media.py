"""
Public media endpoint — serves files from data/agent/ without authentication.

Used by external services that need to pull media via URL.
Only files placed in data/agent/ are accessible, with path-escape protection.
"""

import os
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

AGENT_DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", "./data/agent")).resolve()


@router.get("/{file_path:path}")
async def serve_public_media(file_path: str):
    """
    Serve a file from the agent data directory without authentication.
    External services can pull images from these URLs.

    Example: GET /media/assets/avatars/agent_avatar.png
    """
    clean = file_path.replace("\\", "/").strip("/")
    if not clean:
        raise HTTPException(status_code=400, detail="No file path provided")

    resolved = (AGENT_DATA_DIR / clean).resolve()

    # Prevent directory traversal attacks
    if not str(resolved).startswith(str(AGENT_DATA_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"

    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
