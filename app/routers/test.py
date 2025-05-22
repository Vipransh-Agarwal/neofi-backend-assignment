from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter(tags=["test"])  # Remove prefix to make /test work

@router.get("/test")  # This will match /test
async def get_websocket_test():
    html_content = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>WebSocket Test</title>
            <style>
                body { padding: 20px; font-family: Arial, sans-serif; }
                .container { max-width: 800px; margin: 0 auto; }
                .form-group { margin-bottom: 15px; }
                input { padding: 5px; margin-right: 10px; }
                button { padding: 5px 10px; }
                #messages { 
                    margin-top: 20px;
                    padding: 10px;
                    border: 1px solid #ccc;
                    height: 400px;
                    overflow-y: auto;
                }
                .message { margin: 5px 0; padding: 5px; border-bottom: 1px solid #eee; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>WebSocket Test</h2>
                <div class="form-group">
                    <input type="text" id="userId" placeholder="User ID">
                    <input type="text" id="token" placeholder="Bearer Token">
                    <button onclick="connect()">Connect</button>
                </div>
                <div class="form-group">
                    <input type="text" id="eventId" placeholder="Event ID">
                    <button onclick="subscribe()">Subscribe</button>
                    <button onclick="unsubscribe()">Unsubscribe</button>
                </div>
                <div id="messages"></div>
            </div>

            <script>
                let ws;
                let userId;
                
                function connect() {
                    userId = document.getElementById('userId').value;
                    const token = document.getElementById('token').value;
                    ws = new WebSocket(`ws://localhost:8000/api/ws/events/${userId}`);
                    
                    ws.onopen = function() {
                        appendMessage('Connected to WebSocket');
                    };
                    
                    ws.onmessage = function(event) {
                        appendMessage('Received: ' + event.data);
                    };
                    
                    ws.onclose = function() {
                        appendMessage('Disconnected from WebSocket');
                    };

                    ws.onerror = function(error) {
                        appendMessage('Error: ' + error);
                    };
                }
                
                function subscribe() {
                    const eventId = document.getElementById('eventId').value;
                    ws.send(JSON.stringify({
                        type: 'subscribe',
                        event_id: parseInt(eventId)
                    }));
                }
                
                function unsubscribe() {
                    const eventId = document.getElementById('eventId').value;
                    ws.send(JSON.stringify({
                        type: 'unsubscribe',
                        event_id: parseInt(eventId)
                    }));
                }
                
                function appendMessage(message) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message';
                    messageDiv.textContent = new Date().toISOString() + ': ' + message;
                    document.getElementById('messages').appendChild(messageDiv);
                }
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)