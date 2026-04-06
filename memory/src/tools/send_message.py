"""
Agent Tool — send_message

Lets the agent proactively send a message to the user.
The message is:
  1. Saved to PostgreSQL (chat_messages table)
  2. Pushed via WebSocket (real-time if frontend is open)
  3. Sent via Telegram Bot (push notification)

This is the *tool* wrapper — it calls into the existing
agent_push infrastructure so all delivery logic stays in one place.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func

from src.db.models import Message, Conversation
from src.db.session import get_session


async def send_message(
    entity_id: str,
    content: str,
    *,
    chat_id: str | None = None,
    send_telegram: bool = True,
    send_ws: bool = True,
    source: str = "agent",
) -> dict:
    """
    Send a message from the agent to the user.

    Parameters
    ----------
    entity_id : str
        The persona/entity that is sending the message.
    content : str
        The message text (Markdown allowed).
    chat_id : str, optional
        Target conversation. If omitted, uses the entity's most recent conversation.
    send_telegram : bool
        Push via Telegram Bot? Default True.
    send_ws : bool
        Push via WebSocket? Default True.
    source : str
        Tag for the message origin (e.g. "agent", "heartbeat", "scheduled").

    Returns
    -------
    dict  with keys: success, message_id, ws_delivered, telegram_sent
    """

    message_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    resolved_chat_id = chat_id

    # ── 1. Save to PostgreSQL ────────────────────────────────────────────
    try:
        with get_session() as session:
            if not resolved_chat_id:
                conv = (
                    session.query(Conversation)
                    .filter_by(entity_id=entity_id)
                    .order_by(Conversation.updated_at.desc())
                    .first()
                )
                resolved_chat_id = conv.id if conv else f"push-{entity_id}"

            max_idx = (
                session
                .query(func.max(Message.message_index))
                .filter_by(conversation_id=resolved_chat_id)
                .scalar()
            )
            next_idx = 0 if max_idx is None else max_idx + 1

            msg = Message(
                id=message_id,
                conversation_id=resolved_chat_id,
                sender_id=entity_id,
                content=content,
                timestamp=timestamp,
                message_index=next_idx,
            )
            session.add(msg)
            session.commit()
            print(f"💾 send_message tool: saved {message_id[:8]}… (conv {resolved_chat_id[:8]}…)")
    except Exception as e:
        print(f"⚠️ send_message tool: DB save failed: {e}")
        return {"success": False, "error": f"DB save failed: {e}"}

    # ── 2. WebSocket push ────────────────────────────────────────────────
    ws_delivered = 0
    if send_ws:
        try:
            from api.ws_manager import ws_manager

            ws_payload = {
                "type": "agent_push",
                "message_id": message_id,
                "content": content,
                "timestamp": timestamp.isoformat(),
                "source": source,
                "chat_id": resolved_chat_id,
            }
            ws_delivered = await ws_manager.push_message(entity_id, ws_payload)
            print(f"📡 send_message tool: WS delivered to {ws_delivered} client(s)")
        except Exception as e:
            print(f"⚠️ send_message tool: WS push failed: {e}")

    # ── 3. Telegram ──────────────────────────────────────────────────────
    telegram_sent = False
    if send_telegram:
        try:
            from api.routes.agent_invoke import _send_telegram_message

            telegram_sent = await _send_telegram_message(content)
            if telegram_sent:
                print("📱 send_message tool: Telegram sent")
        except Exception as e:
            print(f"⚠️ send_message tool: Telegram failed: {e}")

    return {
        "success": True,
        "message_id": message_id,
        "chat_id": resolved_chat_id,
        "ws_delivered": ws_delivered,
        "telegram_sent": telegram_sent,
    }
