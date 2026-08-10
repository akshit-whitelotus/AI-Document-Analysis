import asyncio

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.config.settings import settings
from shared.logger.logger import get_logger

logger=get_logger(__name__)
ws_router=APIRouter()


def _upstream_ws_url(token:str) -> str:
    base=settings.DOCUMENT_SERVICE_URL.replace("https://","wss://").replace("http://","ws://")
    return f"{base}/api/v1/documents/ws?token={token}"


@ws_router.websocket("/documents/ws")
async def proxy_documents_ws(websocket: WebSocket):
    """
    Relays a WebSocket connection through to document-service's own
    /documents/ws route. This is a genuinely different code path from
    proxy.py's HTTP request/response proxying (see proxy_chat_query_stream
    for the SSE case) - there's no equivalent of a single buffered
    request/response for a WebSocket, so this opens its own outbound
    connection to the upstream service and pumps messages both ways until
    either side disconnects.
    """
    token=websocket.query_params.get("token","")
    await websocket.accept()

    try:
        async with websockets.connect(_upstream_ws_url(token)) as upstream:
            async def browser_to_upstream():
                while True:
                    message=await websocket.receive_text()
                    await upstream.send(message)

            async def upstream_to_browser():
                async for message in upstream:
                    await websocket.send_text(message)

            browser_task=asyncio.create_task(browser_to_upstream())
            upstream_task=asyncio.create_task(upstream_to_browser())
            done,pending=await asyncio.wait(
                {browser_task,upstream_task},return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending,return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except (websockets.exceptions.ConnectionClosed,websockets.exceptions.InvalidStatus) as exc:
        # document-service rejected the connection (e.g. bad/missing
        # token) or closed it - propagate that as a close on the browser
        # side rather than leaving the connection hanging open.
        logger.info("proxy_documents_ws: upstream rejected or closed the connection",error=str(exc))
    except Exception as exc:
        logger.error("proxy_documents_ws: error",error=str(exc))
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
