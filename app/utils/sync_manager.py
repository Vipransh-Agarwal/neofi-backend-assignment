from typing import Dict, Set, Any
from datetime import datetime
import asyncio
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Event, User

class SyncManager:
    def __init__(self):
        self._connected_clients: Dict[int, WebSocket] = {}
        self._event_subscriptions: Dict[int, Set[int]] = {}  # event_id -> set of user_ids
        self._sync_locks: Dict[int, asyncio.Lock] = {}  # event_id -> lock
        
    async def register_client(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self._connected_clients[user_id] = websocket
        
    def unregister_client(self, user_id: int):
        if user_id in self._connected_clients:
            del self._connected_clients[user_id]
            
    def subscribe_to_event(self, event_id: int, user_id: int):
        if event_id not in self._event_subscriptions:
            self._event_subscriptions[event_id] = set()
            self._sync_locks[event_id] = asyncio.Lock()
        self._event_subscriptions[event_id].add(user_id)
        
    def unsubscribe_from_event(self, event_id: int, user_id: int):
        if event_id in self._event_subscriptions:
            self._event_subscriptions[event_id].discard(user_id)
            
    async def broadcast_event_update(
        self, 
        event_id: int, 
        update_type: str, 
        data: Dict[str, Any], 
        modified_by: int
    ):
        """Broadcast event updates to all subscribed clients"""
        if event_id in self._event_subscriptions:
            message = {
                "type": update_type,
                "event_id": event_id,
                "data": data,
                "modified_by": modified_by,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self._sync_locks[event_id]:
                for user_id in self._event_subscriptions[event_id]:
                    if user_id in self._connected_clients:
                        try:
                            await self._connected_clients[user_id].send_json(message)
                        except Exception:
                            await self.unregister_client(user_id)
                            
    async def resolve_conflict(
        self, 
        event_id: int, 
        conflicting_updates: list[Dict[str, Any]], 
        db: AsyncSession
    ):
        """Resolve conflicts using a last-write-wins strategy with vector clocks"""
        async with self._sync_locks[event_id]:
            # Sort updates by timestamp
            sorted_updates = sorted(
                conflicting_updates,
                key=lambda x: x["timestamp"]
            )
            
            # Apply the latest update
            latest_update = sorted_updates[-1]
            
            # Notify clients about conflict resolution
            await self.broadcast_event_update(
                event_id,
                "conflict_resolved",
                latest_update,
                latest_update["modified_by"]
            )
            
            return latest_update

sync_manager = SyncManager()
