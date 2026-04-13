import json
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages active WebSocket connections per user_id."""

    def __init__(self):
        # user_id → list of active websockets (supports multiple tabs)
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        logger.info(f"WS connected: user={user_id} total_connections={len(self._connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        if user_id in self._connections:
            try:
                self._connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info(f"WS disconnected: user={user_id}")

    async def send_to_user(self, user_id: str, event_type: str, data: dict) -> None:
        """Send a typed event to all connections for a user."""
        if user_id not in self._connections:
            return
        message = json.dumps({"type": event_type, "data": data, "ts": __import__("time").time()})
        dead = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, user_id)

    async def broadcast(self, event_type: str, data: dict) -> None:
        """Broadcast an event to all connected users."""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, event_type, data)

    @property
    def connected_user_ids(self) -> List[str]:
        return list(self._connections.keys())


# Singleton
ws_manager = WebSocketManager()
