from contextlib import asynccontextmanager

from fastapi import FastAPI
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings
from shared.logger.logger import get_logger

logger=get_logger(__name__)

@asynccontextmanager
async def lifespan(app:FastAPI):
    logger.info("Starting gateway-service")
    app.state.auth_client=ServiceClient(base_url=settings.AUTH_SERVICE_URL)
    app.state.document_client=ServiceClient(base_url=settings.DOCUMENT_SERVICE_URL)
    app.state.chat_client=ServiceClient(base_url=settings.CHAT_SERVICE_URL)
    yield
    await app.state.auth_client.aclose()
    await app.state.document_client.aclose()
    await app.state.chat_client.aclose()
    logger.info("Stopping gateway-service")