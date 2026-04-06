"""
File browser routes — list and download files from the agent's sandbox.

Exposes the data/agent/ directory (FileSystemMCP sandbox) so the user
can browse & download files the agent has written on the VPS.
"""

import os
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from api.auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])

# Same sandbox the FileSystemMCP uses
AGENT_DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", "./data/agent")).resolve()


def _safe_path(relative_path: str) -> Path:
    """Resolve a relative path within the sandbox. Raises 403 on escape."""
    clean = relative_path.replace("\\", "/").strip("/")
    if not clean:
        return AGENT_DATA_DIR
    resolved = (AGENT_DATA_DIR / clean).resolve()
    if not str(resolved).startswith(str(AGENT_DATA_DIR)):
        raise HTTPException(status_code=403, detail="Path escape blocked")
    return resolved


def _relative_to_agent_data(path: Path) -> str:
    """Return a stable sandbox-relative path with forward slashes."""
    return path.relative_to(AGENT_DATA_DIR).as_posix()


@router.get("/list")
async def list_files(path: str = ""):
    """
    List files and directories at the given relative path inside data/agent/.
    Returns { items: [...] } where each item has name, type, size, modified.
    """
    target = _safe_path(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path or '/'}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    items = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size if entry.is_file() else None,
                "modified": stat.st_mtime,
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "path": path or "/",
        "items": items,
    }


@router.get("/read")
async def read_file(path: str):
    """
    Read a text file and return its contents.
    Limited to 2MB to avoid memory issues.
    """
    target = _safe_path(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    MAX_SIZE = 2_000_000
    if target.stat().st_size > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large ({target.stat().st_size} bytes). Max: {MAX_SIZE}")

    # Try reading as text, fall back to binary info
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {
            "path": path,
            "binary": True,
            "size": target.stat().st_size,
            "content": None,
        }

    return {
        "path": path,
        "binary": False,
        "size": len(content),
        "content": content,
    }


@router.get("/download")
async def download_file(path: str):
    """
    Download a file from the agent sandbox.
    """
    target = _safe_path(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"

    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type=media_type,
    )


@router.delete("/delete")
async def delete_file(path: str):
    """
    Delete a file from the agent sandbox.
    """
    target = _safe_path(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {path}")

    if target == AGENT_DATA_DIR:
        raise HTTPException(status_code=403, detail="Cannot delete sandbox root")

    if target.is_file():
        target.unlink()
        return {"deleted": path, "type": "file"}
    elif target.is_dir():
        import shutil
        shutil.rmtree(target)
        return {"deleted": path, "type": "directory"}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    path: str = Form(""),
    overwrite: bool = Form(False),
):
    """
    Upload a file into data/agent/ or one of its subdirectories.

    - path: Optional target directory path relative to sandbox root.
    - overwrite: Whether an existing file with the same name may be replaced.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    target_dir = _safe_path(path)
    if target_dir.exists() and not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Upload path must be a directory")

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = (target_dir / Path(file.filename).name).resolve()

    if not str(target_file).startswith(str(AGENT_DATA_DIR)):
        raise HTTPException(status_code=403, detail="Path escape blocked")

    if target_file.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="File already exists. Enable overwrite to replace it.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    target_file.write_bytes(data)

    return {
        "success": True,
        "filename": target_file.name,
        "path": _relative_to_agent_data(target_file),
        "size": target_file.stat().st_size,
    }
