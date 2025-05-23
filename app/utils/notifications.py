from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
from ..models import User, Event

class NotificationManager:
    def __init__(self):
        self._active_connections: Dict[int, List[WebSocket]] = {}
        self._event_subscribers: Dict[int, Set[int]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        """Connect a user's websocket."""
        await websocket.accept()
        if user_id not in self._active_connections:
            self._active_connections[user_id] = []
        self._active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        """Disconnect a user's websocket."""
        if user_id in self._active_connections:
            self._active_connections[user_id].remove(websocket)
            if not self._active_connections[user_id]:
                del self._active_connections[user_id]

    def subscribe_to_event(self, event_id: int, user_id: int):
        """Subscribe a user to event notifications."""
        if event_id not in self._event_subscribers:
            self._event_subscribers[event_id] = set()
        self._event_subscribers[event_id].add(user_id)

    def unsubscribe_from_event(self, event_id: int, user_id: int):
        """Unsubscribe a user from event notifications."""
        if event_id in self._event_subscribers:
            self._event_subscribers[event_id].discard(user_id)
            if not self._event_subscribers[event_id]:
                del self._event_subscribers[event_id]

    async def notify_event_change(self, event: Event, change_type: str, changed_by: User):
        """Notify all subscribers about an event change."""
        if event.id not in self._event_subscribers:
            return

        message = {
            "type": "event_change",
            "event_id": event.id,
            "change_type": change_type,
            "title": event.title,
            "changed_by": {
                "id": changed_by.id,
                "username": changed_by.username
            },
            "timestamp": str(event.updated_at)
        }

        for user_id in self._event_subscribers[event.id]:
            if user_id in self._active_connections:
                for websocket in self._active_connections[user_id]:
                    try:
                        await websocket.send_json(message)
                    except WebSocketDisconnect:
                        await self.disconnect(websocket, user_id)

notification_manager = NotificationManager()
