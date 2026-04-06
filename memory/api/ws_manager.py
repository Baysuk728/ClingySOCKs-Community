"""
WebSocket connection manager for real-time push messaging.

Manages per-entity connections so the agent can push messages
to connected React frontend clients.
"""

from typing import Dict, Set
from fastapi import WebSocket
import json


class ConnectionManager:
    """Manages WebSocket connections per entity_id."""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, entity_id: str, ws: WebSocket):
        await ws.accept()
        if entity_id not in self._connections:
            self._connections[entity_id] = set()
        self._connections[entity_id].add(ws)
        print(f"🔌 WebSocket connected for entity {entity_id} ({len(self._connections[entity_id])} clients)")

    def disconnect(self, entity_id: str, ws: WebSocket):
        if entity_id in self._connections:
            self._connections[entity_id].discard(ws)
            if not self._connections[entity_id]:
                del self._connections[entity_id]
        print(f"🔌 WebSocket disconnected for entity {entity_id}")

    async def push_message(self, entity_id: str, message: dict) -> int:
        """Push a message to all connected clients for an entity.
        
        Returns number of clients the message was delivered to.
        """
        if entity_id not in self._connections:
            return 0

        delivered = 0
        dead = []
        for ws in self._connections[entity_id]:
            try:
                await ws.send_json(message)
                delivered += 1
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            self._connections[entity_id].discard(ws)

        return delivered

    def get_connected_count(self, entity_id: str) -> int:
        return len(self._connections.get(entity_id, set()))


# Singleton instance
ws_manager = ConnectionManager()
