import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from utils.websocket_manager import ws_manager
from utils.jwt_handler import get_user_id_from_token

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, token: str = Query(...)):
    """
    WebSocket endpoint. Client must pass JWT token as query param:
    ws://localhost:8000/ws/{user_id}?token=<access_token>
    """
    # Validate token
    token_user_id = get_user_id_from_token(token)
    if not token_user_id or token_user_id != user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(websocket, user_id)
    try:
        # Send welcome ping
        await ws_manager.send_to_user(user_id, "connected", {"message": "Agent Arena live feed connected"})

        # Keep connection alive, listening for client pings
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id)
        logger.info(f"WS client disconnected: user={user_id}")
    except Exception as e:
        logger.error(f"WS error for user={user_id}: {e}")
        ws_manager.disconnect(websocket, user_id)
