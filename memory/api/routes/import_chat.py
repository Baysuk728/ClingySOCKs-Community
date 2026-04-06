"""
Import Chat API route.

Endpoints for previewing and executing chat history imports from various formats.
Supports ChatGPT, Claude, generic JSON, Notebook LM, and plain text formats.
"""

import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from api.auth import require_api_key
from src.db.session import get_session
from src.db.models import Entity, Conversation, Message
from src.importers.universal_parser import parse_any_format

router = APIRouter(dependencies=[Depends(require_api_key)])

# Maximum upload size: 100 MB
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def _make_import_id(source_format: str, original_id: str) -> str:
    """Generate a deterministic conversation ID for imports to enable dedup."""
    if not original_id:
        return f"imp_{uuid.uuid4().hex[:12]}"
    # Hash the original ID to avoid collisions with organic UUIDs
    h = hashlib.md5(f"{source_format}:{original_id}".encode()).hexdigest()[:12]
    return f"imp_{h}"


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
):
    """
    Parse an uploaded chat file and return conversation metadata for selection.
    Does NOT write to the database.
    
    Accepts: multipart/form-data with a .json or .txt file.
    Returns: detected format + list of conversations with titles, dates, message counts.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    # Read file content
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    try:
        conversations, fmt = parse_any_format(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {str(e)}")
    
    if not conversations:
        raise HTTPException(status_code=422, detail="No conversations found in file. Check the format.")
    
    # Build preview metadata
    conv_previews = []
    total_messages = 0
    
    for conv in conversations:
        msg_count = len(conv.messages)
        total_messages += msg_count
        
        # Compute import ID for duplicate detection
        import_id = _make_import_id(conv.source_format, conv.original_id)
        
        conv_previews.append({
            "original_id": conv.original_id,
            "import_id": import_id,
            "title": conv.title,
            "message_count": msg_count,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "source_format": conv.source_format,
            "first_message_preview": conv.messages[0].content[:120] if conv.messages else None,
        })
    
    return {
        "format": fmt,
        "conversations": conv_previews,
        "total_conversations": len(conv_previews),
        "total_messages": total_messages,
    }


@router.post("/execute")
async def execute_import(
    file: UploadFile = File(...),
    entity_id: str = Form(...),
    user_id: str = Form(...),
    conversation_ids: str = Form("*"),  # JSON array of original_ids, or "*" for all
):
    """
    Parse and import selected conversations into the database.
    
    Accepts: multipart/form-data with:
      - file: the chat export file
      - entity_id: target agent/entity ID
      - user_id: owner user ID (Identity UID)
      - conversation_ids: JSON array of original_id strings, or "*" for all
    
    Creates Conversation + Message rows with harvest_status="pending".
    Returns import statistics.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    # Parse conversation_ids selection
    selected_ids = None  # None means all
    if conversation_ids != "*":
        try:
            selected_ids = set(json.loads(conversation_ids))
        except Exception:
            raise HTTPException(status_code=400, detail="conversation_ids must be a JSON array or '*'")
    
    # Parse file
    try:
        conversations, fmt = parse_any_format(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {str(e)}")
    
    if not conversations:
        raise HTTPException(status_code=422, detail="No conversations found in file")
    
    # Filter to selected conversations
    if selected_ids is not None:
        conversations = [c for c in conversations if c.original_id in selected_ids]
        if not conversations:
            raise HTTPException(status_code=400, detail="None of the selected conversations found in file")
    
    # Import into database
    stats = {
        "imported": 0,
        "skipped": 0,
        "total_messages": 0,
        "errors": [],
    }
    
    now = datetime.now(timezone.utc)
    
    with get_session() as session:
        # Ensure entity exists
        entity = session.get(Entity, entity_id)
        if not entity:
            # Auto-create entity for the import
            entity = Entity(
                id=entity_id,
                entity_type="agent",
                name=entity_id,
                owner_user_id=user_id,
            )
            session.add(entity)
            try:
                session.flush()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to create entity: {str(e)}")
        
        for conv in conversations:
            try:
                result = _import_single_conversation(
                    session, conv, entity_id, fmt, now
                )
                if result is None:
                    stats["skipped"] += 1
                else:
                    stats["imported"] += 1
                    stats["total_messages"] += result
                    session.commit()
            except Exception as e:
                error_msg = f"Error importing '{conv.title}': {str(e)}"
                stats["errors"].append(error_msg)
                session.rollback()
    
    return stats


def _import_single_conversation(
    session,
    conv,
    entity_id: str,
    source_format: str,
    imported_at: datetime,
) -> Optional[int]:
    """
    Import a single parsed conversation into the database.
    Returns message count, or None if skipped (duplicate).
    """
    # Generate deterministic import ID
    conv_id = _make_import_id(source_format, conv.original_id)
    
    # Check for duplicates
    existing = session.get(Conversation, conv_id)
    if existing:
        return None  # Skip — already imported
    
    if not conv.messages:
        return None
    
    # Determine timestamps
    first_ts = conv.messages[0].timestamp or imported_at
    last_ts = conv.messages[-1].timestamp or imported_at
    
    # Create conversation row
    conversation = Conversation(
        id=conv_id,
        entity_id=entity_id,
        title=conv.title,
        created_at=conv.created_at or first_ts,
        updated_at=last_ts,
        message_count=len(conv.messages),
        last_harvested_index=-1,
        harvest_status="pending",
        source=source_format,
        imported_at=imported_at,
    )
    session.add(conversation)
    
    # Create message rows
    msg_count = 0
    for idx, msg in enumerate(conv.messages):
        # Normalize sender: "user" stays "user", everything else → entity_id
        sender_id = "user" if msg.role == "user" else entity_id
        
        message = Message(
            id=f"{conv_id}-msg-{idx}",
            conversation_id=conv_id,
            sender_id=sender_id,
            content=msg.content,
            timestamp=msg.timestamp or imported_at,
            message_index=idx,
            is_harvested=False,
        )
        session.add(message)
        msg_count += 1
    
    session.flush()
    return msg_count


# Need json import for conversation_ids parsing
import json
