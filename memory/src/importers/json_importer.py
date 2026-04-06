"""
JSON Importer for ClingySOCKs Memory.

Imports conversation history from full_history.json into PostgreSQL.
Handles the specific JSON structure from the ClingySOCKs chat export.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import (
    track, Progress, SpinnerColumn, TextColumn, BarColumn, 
    TaskProgressColumn, TimeRemainingColumn
)

from src.db.models import Entity, Conversation, Message
from src.db.session import get_session

console = Console()


def import_json_history(
    json_path: str | Path,
    entity_id: str,
    entity_name: str,
    owner_user_id: str,
    entity_type: str = "agent",
) -> dict:
    """
    Import full_history.json into the database.

    Expected JSON structure:
    {
        "exportDate": "...",
        "userId": "...",
        "totalConversations": N,
        "conversations": [
            {
                "id": "...",
                "title": "...",
                "messages": [
                    {
                        "senderId": "user" | "<agent-uuid>",
                        "content": "...",
                        "id": "msg-...",
                        "timestamp": "2026-02-07T08:05:31.471Z"
                    }
                ]
            }
        ]
    }

    Returns stats dict.
    """
    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    console.print(f"📂 Loading [bold]{json_path.name}[/bold]...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data.get("conversations", [])
    source_user_id = data.get("userId", owner_user_id)

    console.print(f"   Found [bold]{len(conversations)}[/bold] conversations")

    stats = {
        "conversations_imported": 0,
        "messages_imported": 0,
        "conversations_skipped": 0,
        "errors": [],
    }

    with get_session() as session:
        # Ensure entity exists
        entity = session.get(Entity, entity_id)
        if not entity:
            entity = Entity(
                id=entity_id,
                entity_type=entity_type,
                name=entity_name,
                owner_user_id=owner_user_id,
            )
            session.add(entity)
            session.commit() # Commit entity creation
            console.print(f"   ✅ Created entity: [bold]{entity_name}[/bold] ({entity_id})")
        else:
            console.print(f"   ℹ️ Entity already exists: [bold]{entity.name}[/bold]")

        # Import conversations
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("[cyan]Importing...", total=len(conversations))

            for conv_data in conversations:
                try:
                    result = _import_conversation(session, conv_data, entity_id, source_user_id)
                    if result:
                        stats["conversations_imported"] += 1
                        stats["messages_imported"] += result
                        session.commit()  # Commit each successful conversation
                    else:
                        stats["conversations_skipped"] += 1
                        # The function _import_conversation now prints why it skipped
                        session.rollback() 
                except Exception as e:
                    error_msg = f"Error importing '{conv_data.get('title', 'unknown')}': {e}"
                    stats["errors"].append(error_msg)
                    console.print(f"   ❌ {error_msg}")
                    import traceback
                    traceback.print_exc()
                    session.rollback() # Rollback on error
                progress.advance(task)

    console.print(f"\n📊 Import Complete:")
    console.print(f"   Conversations: {stats['conversations_imported']} imported, {stats['conversations_skipped']} skipped")
    console.print(f"   Messages: {stats['messages_imported']} imported")
    if stats["errors"]:
        console.print(f"   Errors: {len(stats['errors'])}")

    return stats


def _import_conversation(
    session,
    conv_data: dict,
    entity_id: str,
    source_user_id: str,
) -> Optional[int]:
    """Import a single conversation. Returns message count or None if skipped."""
    conv_id = conv_data.get("id")
    if not conv_id:
        return None

    # Check if already imported
    existing = session.get(Conversation, conv_id)
    if existing:
        console.print(f"   ⚠️ Skipping '{conv_data.get('title')}' (ID: {conv_id}) - Already exists")
        return None  # Skip, already imported

    messages_data = conv_data.get("messages", [])
    if not messages_data:
        console.print(f"   ⚠️ Skipping '{conv_data.get('title')}' - No messages")
        return None

    # Parse timestamps
    first_ts = _parse_timestamp(messages_data[0].get("timestamp"))
    last_ts = _parse_timestamp(messages_data[-1].get("timestamp"))

    # Create conversation
    conversation = Conversation(
        id=conv_id,
        entity_id=entity_id,
        title=conv_data.get("title", "Untitled"),
        created_at=first_ts,
        updated_at=last_ts,
        message_count=len(messages_data),
        last_harvested_index=-1,
        harvest_status="pending",
    )
    session.add(conversation)

    # Import messages
    for idx, msg_data in enumerate(messages_data):
        try:
            sender = msg_data.get("senderId", "unknown")
            if sender != "user":
                sender = entity_id

            content = msg_data.get("content", "")
            if not content:
                continue

            # Debug excessively long content
            if len(content) > 10000:
                print(f"⚠️  Long message detected: {len(content)} chars (ID: {msg_data.get('id')})")

            message = Message(
                id=msg_data.get("id", f"{conv_id}-msg-{idx}"),
                conversation_id=conv_id,
                sender_id=sender,
                content=content,
                timestamp=_parse_timestamp(msg_data.get("timestamp")),
                message_index=idx,
            )
            session.add(message)
        except Exception as msg_error:
            print(f"❌ Error preparing message {idx}: {msg_error}")

    try:
        session.flush()
        return len(messages_data)
    except Exception as flush_error:
        print(f"❌ Error saving conversation '{conv_data.get('title')}': {flush_error}")
        session.rollback()
        return None


def _parse_timestamp(ts_str: Optional[str]) -> datetime:
    """Parse ISO timestamp string to datetime."""
    if not ts_str:
        return datetime.now(timezone.utc)

    try:
        # Handle ISO format: "2026-02-07T08:05:31.471Z"
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
