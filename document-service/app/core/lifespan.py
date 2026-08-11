from contextlib import asynccontextmanager
from fastapi import FastAPI
from shared.clients.service_client import ServiceClient
from shared.config.settings import settings
from shared.logger.logger import get_logger

logger= get_logger(__name__)
@asynccontextmanager
async def lifespan(app:FastAPI):
    logger.info("Starting Document Service...")
    app.state.worker_client=ServiceClient(base_url=settings.AI_WORKER_SERVICE_URL)
    yield
    await app.state.worker_client.aclose()
    logger.info("Stopping Document Service...")