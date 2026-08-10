from contextlib import asynccontextmanager
from fastapi import FastAPI

from shared.logger.logger import get_logger

from app.services.rag_service import RAGService

logger=get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting chat-service")

    app.state.rag_service = RAGService()

    try:
        yield
    finally:
        await app.state.rag_service.aclose()
        logger.info("Stopping chat-service")