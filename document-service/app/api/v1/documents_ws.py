import asyncio
from fastapi import APIRouter,WebSocket,WebSocketDisconnect
from shared.cache.redis_client import subscribe_document_status
from shared.exceptions.exceptions import UnauthorizedException
from shared.logger.logger import get_logger
from shared.security.oauth import resolve_user_from_token
from app.core.ws_manager import manager

logger=get_logger(__name__)
router=APIRouter()

@router.websocket("/ws")
async def document_status_ws(websocket: WebSocket, token:str | None=None):
    """
    wss://.../api/v1/documents/ws?token=<jwt access token>

    Authenticated via a query param rather than CurrentUserDep/HTTPBearer,
    because the browser's native WebSocket API cannot set an Authorization
    header. Rejects the connection (closes without ever accepting) before
    any data is exchanged if the token is missing or invalid, the same way
    HTTP requests get a 401 before touching any route logic.

    Pushes one JSON message per document status change belonging to this
    user - see ai-worker-service/app/tasks.py's publish_document_status()
    calls - so the frontend doesn't need to poll GET /documents/ repeatedly
    to notice when a newly uploaded document finishes processing.
    """
    if not token:
        await websocket.close(code=1008)
        return
    try:
        user=resolve_user_from_token(token)
    except UnauthorizedException:
        await websocket.close(code=1008)
        return
    await  websocket.accept()
    manager.connect(user.id,websocket)

    async def forward_status_updates():
        async for message in subscribe_document_status(str(user.id)):
            await websocket.send_json(message)
    async def watch_for_disconnect():
        while True:
            await websocket.receive_text()
    forward_task=asyncio.create_task(forward_status_updates())
    disconnect_task=asyncio.create_task(watch_for_disconnect())
    try:
        done,pending=await asyncio.wait(
            {forward_task,disconnect_task},return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("document_status_ws: error",owner_id=str(user.id),error=str(exc))
    finally:
        manager.disconnect(user.id,websocket)