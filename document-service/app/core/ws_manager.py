from uuid import UUID
from fastapi import WebSocket


class DocumentStatusConnectionManager:
    """
    Tracks open WebSocket connections keyed by owner_id. A single user can
    have this open in multiple tabs, so each owner_id maps to a list, not
    a single connection.

    Deliberately has no async I/O of its own beyond calling
    websocket.send_json() - the Redis subscription and the actual
    accept/receive loop live in the route (documents_ws.py), so this class
    can be unit tested without a real WebSocket or Redis.
    """
    def __init__(self):
        self._connections: dict[UUID, list[WebSocket]] = {}

    def connect(self, owner_id: UUID, websocket: WebSocket) -> None:
        self._connections.setdefault(owner_id, []).append(websocket)

    def disconnect(self, owner_id: UUID, websocket: WebSocket) -> None:
        connections = self._connections.get(owner_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            del self._connections[owner_id]

    def connection_count(self, owner_id: UUID) -> int:
        return len(self._connections.get(owner_id, []))

    async def send_to_owner(self, owner_id: UUID, payload: dict) -> None:
        # Iterate a copy - a send failure below calls disconnect(), which
        # mutates the same list we'd otherwise be iterating over.
        for websocket in list(self._connections.get(owner_id, [])):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(owner_id, websocket)


manager = DocumentStatusConnectionManager()
