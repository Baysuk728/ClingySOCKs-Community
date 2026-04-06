"""
Universal Chat Format Parser

Detects and parses various chat export formats into a standardized structure
for import into ClingySOCKs PostgreSQL database.

Supported formats:
- ChatGPT export (.json)  — array of conversations with `mapping` tree
- Claude export (.json)   — single conversation with `chat_messages` / `messages`
- Generic JSON (.json)    — array of {role, content} objects
- Notebook LM (.txt)      — [YYYY-MM-DD HH:MM:SS] USER/ASSISTANT: message
- Plain text (.txt)       — lines prefixed with User:/Human:/Assistant:/AI:/Bot:

Ported from legacy TypeScript universal import (misc/legacy-functions/src/universalImport.ts)
plus ChatGPT mapping traversal from jsonProcessor.ts.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ParsedMessage:
    """A single parsed chat message in normalized form."""
    role: str           # "user" | "assistant"
    content: str
    timestamp: Optional[datetime] = None


@dataclass
class ParsedConversation:
    """A parsed conversation with its messages."""
    original_id: str
    title: str
    messages: list[ParsedMessage] = field(default_factory=list)
    created_at: Optional[datetime] = None
    source_format: str = "unknown"


# ============================================================================
# FORMAT DETECTION
# ============================================================================

FormatType = str  # "chatgpt" | "claude" | "generic_json" | "notebook_lm" | "plain_text" | "unknown"


def detect_format(content: bytes | str, filename: str) -> FormatType:
    """
    Auto-detect the chat export format from file content and extension.
    
    Args:
        content: Raw file content (bytes or string).
        filename: Original filename for extension-based detection.
    
    Returns:
        Detected format string.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    # Decode bytes if needed
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="replace")
    else:
        text = content

    if ext == "json":
        try:
            data = json.loads(text)
            
            # ChatGPT export: array of objects with 'mapping' key
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict) and "mapping" in first:
                    return "chatgpt"
            
            # Single ChatGPT conversation (not in array)
            if isinstance(data, dict) and "mapping" in data:
                return "chatgpt"
            
            # Claude format: has 'uuid' and 'chat_messages' or 'messages'
            if isinstance(data, dict) and "uuid" in data:
                if "chat_messages" in data or "messages" in data:
                    return "claude"
            
            # Claude export as array of conversations
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict) and "uuid" in first and ("chat_messages" in first or "messages" in first):
                    return "claude"
            
            # Generic JSON: array of {role, content}
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict) and ("role" in first and "content" in first):
                    return "generic_json"
            
            # Object with 'messages' key
            if isinstance(data, dict) and "messages" in data and isinstance(data["messages"], list):
                return "generic_json"
            
            # ClingySOCKs native export format
            if isinstance(data, dict) and "conversations" in data and isinstance(data["conversations"], list):
                return "generic_json"
                
        except (json.JSONDecodeError, ValueError):
            pass

    if ext == "txt" or ext == "":
        # Notebook LM format: [YYYY-MM-DD HH:MM:SS] USER/ASSISTANT:
        if re.search(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] (USER|ASSISTANT):", text[:2000]):
            return "notebook_lm"
        
        # Plain text — has User:/Human:/Assistant: markers
        if re.search(r"(?i)^(user|human|assistant|ai|bot):", text[:2000], re.MULTILINE):
            return "plain_text"
        
        # Default for .txt
        if ext == "txt":
            return "plain_text"

    return "unknown"


# ============================================================================
# PARSERS
# ============================================================================

def parse_chatgpt(content: str) -> list[ParsedConversation]:
    """
    Parse ChatGPT export format.
    
    ChatGPT exports are JSON arrays of conversation objects.
    Each conversation has a `mapping` dict where keys are node IDs
    and values contain `message` objects with `content.parts` arrays.
    Messages must be sorted by `create_time`.
    """
    data = json.loads(content)
    
    # Normalize to list
    if isinstance(data, dict):
        data = [data]
    
    conversations = []
    
    for conv_obj in data:
        if not isinstance(conv_obj, dict):
            continue
            
        mapping = conv_obj.get("mapping", {})
        if not mapping:
            continue
        
        title = conv_obj.get("title", "Untitled")
        original_id = conv_obj.get("id", "")
        conv_create_time = conv_obj.get("create_time")
        
        # Collect all messages from the mapping tree
        raw_messages = []
        
        for node_id, node in mapping.items():
            message = node.get("message") if isinstance(node, dict) else None
            if not message:
                continue
            
            content_obj = message.get("content", {})
            if not content_obj:
                continue
                
            parts = content_obj.get("parts", [])
            if not parts or not isinstance(parts, list):
                continue
            
            # Filter to string parts only (skip dicts like tool outputs, images, etc.)
            string_parts = [str(p) for p in parts if p is not None and isinstance(p, str)]
            if not string_parts:
                continue
            
            text = "\n".join(string_parts).strip()
            if not text:
                continue
            
            role = message.get("author", {}).get("role", "user")
            create_time = message.get("create_time", 0)
            
            # Skip system messages
            if role == "system":
                continue
            
            raw_messages.append({
                "role": role,
                "content": text,
                "timestamp": create_time,
            })
        
        # Sort by timestamp
        raw_messages.sort(key=lambda m: m["timestamp"])
        
        # Convert to ParsedMessage objects
        messages = []
        for msg in raw_messages:
            ts = None
            if msg["timestamp"]:
                try:
                    ts = datetime.fromtimestamp(msg["timestamp"], tz=timezone.utc)
                except (ValueError, OSError, OverflowError):
                    ts = None
            
            normalized_role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append(ParsedMessage(
                role=normalized_role,
                content=msg["content"],
                timestamp=ts,
            ))
        
        if not messages:
            continue
        
        created_at = None
        if conv_create_time:
            try:
                created_at = datetime.fromtimestamp(conv_create_time, tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                created_at = messages[0].timestamp if messages else None
        
        conversations.append(ParsedConversation(
            original_id=original_id,
            title=title,
            messages=messages,
            created_at=created_at or (messages[0].timestamp if messages else None),
            source_format="chatgpt",
        ))
    
    return conversations


def parse_claude(content: str) -> list[ParsedConversation]:
    """
    Parse Claude export format.
    
    Claude exports have `uuid`, and messages in `chat_messages` or `messages` array.
    Each message has `sender`/`role` and `text`/`content` fields.
    """
    data = json.loads(content)
    
    # Normalize to list
    if isinstance(data, dict):
        data = [data]
    
    conversations = []
    
    for conv_obj in data:
        if not isinstance(conv_obj, dict):
            continue
        
        original_id = conv_obj.get("uuid", conv_obj.get("id", ""))
        title = conv_obj.get("name", conv_obj.get("title", "Untitled"))
        
        msg_array = conv_obj.get("chat_messages") or conv_obj.get("messages") or []
        
        messages = []
        for msg in msg_array:
            if not isinstance(msg, dict):
                continue
            
            role_raw = msg.get("sender") or msg.get("role") or "user"
            text = msg.get("text") or msg.get("content") or ""
            ts_str = msg.get("created_at") or msg.get("timestamp")
            
            if not text.strip():
                continue
            
            # Normalize role
            normalized_role = "assistant" if role_raw in ("assistant", "claude") else "user"
            
            # Parse timestamp
            ts = _parse_flexible_timestamp(ts_str)
            
            messages.append(ParsedMessage(
                role=normalized_role,
                content=text.strip(),
                timestamp=ts,
            ))
        
        if not messages:
            continue
        
        created_at = _parse_flexible_timestamp(conv_obj.get("created_at"))
        
        conversations.append(ParsedConversation(
            original_id=original_id,
            title=title,
            messages=messages,
            created_at=created_at or (messages[0].timestamp if messages else None),
            source_format="claude",
        ))
    
    return conversations


def parse_generic_json(content: str) -> list[ParsedConversation]:
    """
    Parse generic JSON chat format.
    
    Supports:
    - Array of {role, content} message objects (single conversation)
    - Object with `messages` array key
    - ClingySOCKs native format with `conversations` array
    """
    data = json.loads(content)
    
    conversations = []
    
    # ClingySOCKs native format: { conversations: [{ id, title, messages: [...] }] }
    if isinstance(data, dict) and "conversations" in data:
        for idx, conv_obj in enumerate(data["conversations"]):
            if not isinstance(conv_obj, dict):
                continue
            
            msg_array = conv_obj.get("messages", [])
            messages = _parse_generic_messages(msg_array)
            
            if not messages:
                continue
            
            conversations.append(ParsedConversation(
                original_id=conv_obj.get("id", f"conv_{idx}"),
                title=conv_obj.get("title", f"Conversation {idx + 1}"),
                messages=messages,
                created_at=messages[0].timestamp if messages else None,
                source_format="generic_json",
            ))
        return conversations
    
    # Object with `messages` key
    if isinstance(data, dict) and "messages" in data:
        messages = _parse_generic_messages(data["messages"])
        if messages:
            conversations.append(ParsedConversation(
                original_id="conv_0",
                title=data.get("title", "Imported Conversation"),
                messages=messages,
                created_at=messages[0].timestamp if messages else None,
                source_format="generic_json",
            ))
        return conversations
    
    # Plain array of message objects
    if isinstance(data, list):
        messages = _parse_generic_messages(data)
        if messages:
            conversations.append(ParsedConversation(
                original_id="conv_0",
                title="Imported Conversation",
                messages=messages,
                created_at=messages[0].timestamp if messages else None,
                source_format="generic_json",
            ))
    
    return conversations


def _parse_generic_messages(msg_array: list) -> list[ParsedMessage]:
    """Parse a flat array of message dicts."""
    messages = []
    base_time = datetime.now(timezone.utc)
    
    for i, msg in enumerate(msg_array):
        if not isinstance(msg, dict):
            continue
        
        role_raw = msg.get("role") or msg.get("sender") or msg.get("senderId") or "user"
        text = msg.get("content") or msg.get("text") or msg.get("message") or ""
        ts_str = msg.get("timestamp") or msg.get("created_at")
        
        if not text.strip():
            continue
        
        # Normalize role
        normalized_role = "assistant" if role_raw in ("assistant", "system", "ai", "bot", "claude") else "user"
        # If senderId is not "user", it's an agent
        if "senderId" in msg and msg["senderId"] != "user":
            normalized_role = "assistant"
        
        ts = _parse_flexible_timestamp(ts_str)
        if not ts:
            ts = base_time + timedelta(seconds=i)
        
        messages.append(ParsedMessage(
            role=normalized_role,
            content=text.strip(),
            timestamp=ts,
        ))
    
    return messages


def parse_notebook_lm(content: str) -> list[ParsedConversation]:
    """
    Parse Notebook LM chunk format.
    
    Format: [YYYY-MM-DD HH:MM:SS] USER/ASSISTANT: message (can be multi-line)
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    
    pattern = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (USER|ASSISTANT): ")
    
    # Find all message start positions
    matches = []
    for m in pattern.finditer(content):
        matches.append({
            "timestamp_str": m.group(1),
            "role": m.group(2),
            "content_start": m.end(),
            "match_start": m.start(),
        })
    
    messages = []
    for i, match_info in enumerate(matches):
        # Content runs from this match's end to the next match's start (or EOF)
        if i + 1 < len(matches):
            msg_content = content[match_info["content_start"]:matches[i + 1]["match_start"]].strip()
        else:
            msg_content = content[match_info["content_start"]:].strip()
        
        if not msg_content:
            continue
        
        try:
            ts = datetime.strptime(match_info["timestamp_str"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            ts = None
        
        role = "user" if match_info["role"] == "USER" else "assistant"
        
        messages.append(ParsedMessage(
            role=role,
            content=msg_content,
            timestamp=ts,
        ))
    
    if not messages:
        return []
    
    return [ParsedConversation(
        original_id="notebook_lm_0",
        title="Imported Notebook LM Chat",
        messages=messages,
        created_at=messages[0].timestamp,
        source_format="notebook_lm",
    )]


def parse_plain_text(content: str) -> list[ParsedConversation]:
    """
    Parse plain text chat format.
    
    Detects role markers: User:/Human:/Assistant:/AI:/Bot:
    Multi-line messages accumulate until the next role marker.
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    
    lines = content.split("\n")
    
    messages = []
    current_role = "user"
    current_content = ""
    base_time = datetime.now(timezone.utc)
    msg_index = 0
    
    role_pattern = re.compile(r"^(user|human|assistant|ai|bot):\s*", re.IGNORECASE)
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_content:
                current_content += "\n"
            continue
        
        match = role_pattern.match(stripped)
        if match:
            # Flush current message
            if current_content.strip():
                messages.append(ParsedMessage(
                    role=current_role,
                    content=current_content.strip(),
                    timestamp=base_time + timedelta(seconds=msg_index * 60),
                ))
                msg_index += 1
            
            # Determine new role
            role_word = match.group(1).lower()
            current_role = "assistant" if role_word in ("assistant", "ai", "bot") else "user"
            current_content = stripped[match.end():].strip()
        else:
            # Continue current message
            if current_content:
                current_content += "\n" + stripped
            else:
                current_content = stripped
    
    # Flush final message
    if current_content.strip():
        messages.append(ParsedMessage(
            role=current_role,
            content=current_content.strip(),
            timestamp=base_time + timedelta(seconds=msg_index * 60),
        ))
    
    if not messages:
        return []
    
    return [ParsedConversation(
        original_id="plaintext_0",
        title="Imported Text Chat",
        messages=messages,
        created_at=messages[0].timestamp,
        source_format="plain_text",
    )]


# ============================================================================
# UNIFIED PARSER
# ============================================================================

def parse_any_format(content: bytes | str, filename: str) -> tuple[list[ParsedConversation], str]:
    """
    Detect format and parse file content into standardized conversations.
    
    Args:
        content: Raw file content (bytes or string).
        filename: Original filename.
    
    Returns:
        Tuple of (list of parsed conversations, detected format string).
    """
    fmt = detect_format(content, filename)
    
    # Ensure string for all parsers
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="replace")
    else:
        text = content
    
    conversations: list[ParsedConversation] = []
    
    if fmt == "chatgpt":
        conversations = parse_chatgpt(text)
    elif fmt == "claude":
        conversations = parse_claude(text)
    elif fmt == "generic_json":
        conversations = parse_generic_json(text)
    elif fmt == "notebook_lm":
        conversations = parse_notebook_lm(text)
    elif fmt == "plain_text":
        conversations = parse_plain_text(text)
    else:
        # Try JSON first, then plain text as fallback
        try:
            conversations = parse_generic_json(text)
        except (json.JSONDecodeError, ValueError):
            pass
        
        if not conversations:
            conversations = parse_plain_text(text)
            fmt = "plain_text"
    
    return conversations, fmt


# ============================================================================
# HELPERS
# ============================================================================

def _parse_flexible_timestamp(ts_val) -> Optional[datetime]:
    """Parse various timestamp formats to datetime."""
    if ts_val is None:
        return None
    
    # Unix timestamp (seconds) — float or int
    if isinstance(ts_val, (int, float)):
        try:
            # Heuristic: if > 1e12 it's milliseconds
            if ts_val > 1e12:
                ts_val = ts_val / 1000
            return datetime.fromtimestamp(ts_val, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    
    if not isinstance(ts_val, str):
        return None
    
    # ISO format: "2026-02-07T08:05:31.471Z"
    ts_str = ts_val
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        pass
    
    # Try common date formats
    for fmt_str in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
    ]:
        try:
            return datetime.strptime(ts_str, fmt_str).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    
    return None
