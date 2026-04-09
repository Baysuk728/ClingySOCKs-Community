"""
Presence Hooks — User presence tracking and context injection.

Tracks user online/offline state and injects lightweight real-time
signals into every prompt:
- Time awareness (current time, day of week)
- Presence state (online, offline, time since last seen)
- Session context (messages this session, session duration)
- Recent emotional markers (from mood states)

Inspired by Resonant's hooks system.
Self-contained — stores state in memory, reads from existing DB models.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from src.db.models import MoodState, Message, Conversation
from src.db.session import get_session

logger = logging.getLogger("clingysocks.presence")


# ── In-Memory Presence State ─────────────────────────
# Simple dict-based tracking. For production, could be moved to Redis or DB.

_presence_state: dict[str, dict[str, Any]] = {}


def update_presence(entity_id: str, user_id: str, state: str = "online") -> dict[str, Any]:
    """
    Update user presence state.
    
    Called when:
    - User sends a message → online
    - WebSocket connects → online
    - WebSocket disconnects → offline
    - Idle timeout → away
    
    Args:
        entity_id: Entity ID (agent)
        user_id: User ID
        state: "online", "away", "offline"
    """
    now = datetime.now(timezone.utc)
    key = f"{entity_id}:{user_id}"

    prev = _presence_state.get(key, {})
    prev_state = prev.get("state", "offline")

    transition = None
    if prev_state != state:
        transition = f"{prev_state}→{state}"

    _presence_state[key] = {
        "entity_id": entity_id,
        "user_id": user_id,
        "state": state,
        "updated_at": now.isoformat(),
        "previous_state": prev_state,
        "transition": transition,
        "session_start": prev.get("session_start", now.isoformat()) if state == "online" else None,
        "last_seen": now.isoformat() if state == "online" else prev.get("last_seen", now.isoformat()),
        "messages_this_session": (prev.get("messages_this_session", 0) + 1) if state == "online" else 0,
    }

    if transition:
        logger.debug(f"Presence: {user_id}@{entity_id} {transition}")

    return _presence_state[key]


def get_presence(entity_id: str, user_id: str) -> dict[str, Any]:
    """Get current presence state for a user."""
    key = f"{entity_id}:{user_id}"
    return _presence_state.get(key, {
        "entity_id": entity_id,
        "user_id": user_id,
        "state": "unknown",
    })


def increment_message_count(entity_id: str, user_id: str):
    """Increment the session message counter."""
    key = f"{entity_id}:{user_id}"
    if key in _presence_state:
        _presence_state[key]["messages_this_session"] = (
            _presence_state[key].get("messages_this_session", 0) + 1
        )


# ── Context Injection Hooks ──────────────────────────

def build_presence_context(entity_id: str, user_id: str = "user") -> dict[str, Any]:
    """
    Build lightweight presence context for prompt injection.
    
    Returns a dict suitable for adding to the system prompt preamble.
    Designed to be ~50-100 tokens.
    """
    now = datetime.now(timezone.utc)
    presence = get_presence(entity_id, user_id)

    context = {
        "time": {
            "now": now.strftime("%Y-%m-%d %H:%M UTC"),
            "day_of_week": now.strftime("%A"),
            "time_of_day": _time_of_day(now.hour),
        },
        "presence": {
            "state": presence.get("state", "unknown"),
        },
    }

    # Time away calculation
    last_seen = presence.get("last_seen")
    if last_seen and presence.get("state") == "online":
        # Calculate session duration
        session_start = presence.get("session_start")
        if session_start:
            try:
                start = datetime.fromisoformat(session_start)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                duration_minutes = int((now - start).total_seconds() / 60)
                context["presence"]["session_minutes"] = duration_minutes
            except (ValueError, TypeError):
                pass

        context["presence"]["messages_this_session"] = presence.get("messages_this_session", 0)

    # Transition info
    transition = presence.get("transition")
    if transition:
        context["presence"]["transition"] = transition

        # If returning from offline, show how long they were away
        if transition.endswith("→online") and last_seen:
            try:
                last = datetime.fromisoformat(last_seen)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                away_minutes = int((now - last).total_seconds() / 60)
                if away_minutes > 60:
                    context["presence"]["away_duration"] = f"{away_minutes // 60} hours"
                elif away_minutes > 0:
                    context["presence"]["away_duration"] = f"{away_minutes} minutes"
            except (ValueError, TypeError):
                pass

    # Recent mood (if available)
    try:
        with get_session() as session:
            mood = session.query(MoodState).filter_by(
                entity_id=entity_id
            ).order_by(MoodState.timestamp.desc()).first()

            if mood:
                mood_descriptors = []
                if (mood.energy_f or 0) > 0.6:
                    mood_descriptors.append("energetic")
                elif (mood.energy_f or 0) < 0.3:
                    mood_descriptors.append("low-energy")
                if (mood.warmth or 0) > 0.6:
                    mood_descriptors.append("warm")
                if (mood.chaos or 0) > 0.5:
                    mood_descriptors.append("unsettled")
                if (mood.melancholy or 0) > 0.5:
                    mood_descriptors.append("melancholic")

                if mood_descriptors:
                    context["emotional_tone"] = ", ".join(mood_descriptors)
    except Exception:
        pass

    return context


def format_presence_context(entity_id: str, user_id: str = "user") -> str:
    """
    Format presence context as compact text for system prompt injection.
    Target: ~50-100 tokens.
    """
    ctx = build_presence_context(entity_id, user_id)
    parts = []

    # Time
    time_info = ctx.get("time", {})
    parts.append(f"[{time_info.get('now', 'unknown')}] {time_info.get('day_of_week', '')} {time_info.get('time_of_day', '')}")

    # Presence
    presence = ctx.get("presence", {})
    transition = presence.get("transition")
    if transition:
        parts.append(f"User {transition}")
        away = presence.get("away_duration")
        if away:
            parts.append(f"(away {away})")

    session_msgs = presence.get("messages_this_session", 0)
    if session_msgs > 0:
        parts.append(f"Session: {session_msgs} messages")

    # Emotional tone
    tone = ctx.get("emotional_tone")
    if tone:
        parts.append(f"Emotional tone: {tone}")

    return " | ".join(parts)


def _time_of_day(hour: int) -> str:
    """Get descriptive time of day."""
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"
