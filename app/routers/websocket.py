from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from ..dependencies import get_current_user_ws
from ..utils.notifications import notification_manager
from typing import Dict

router = APIRouter(prefix="/api/ws", tags=["websocket"])

@router.websocket("/events/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    try:
        # Accept the connection
        await notification_manager.connect(websocket, user_id)
        
        # Listen for messages from the client
        while True:
            try:
                data = await websocket.receive_json()
                
                if data["type"] == "subscribe":
                    event_id = int(data["event_id"])
                    notification_manager.subscribe_to_event(event_id, user_id)
                    await websocket.send_json({
                        "type": "subscription_success",
                        "event_id": event_id
                    })
                    
                elif data["type"] == "unsubscribe":
                    event_id = int(data["event_id"])
                    notification_manager.unsubscribe_from_event(event_id, user_id)
                    await websocket.send_json({
                        "type": "unsubscription_success",
                        "event_id": event_id
                    })
                    
            except WebSocketDisconnect:
                notification_manager.disconnect(websocket, user_id)
                break
                
    except Exception as e:
        await websocket.close(code=1000)
        notification_manager.disconnect(websocket, user_id)
