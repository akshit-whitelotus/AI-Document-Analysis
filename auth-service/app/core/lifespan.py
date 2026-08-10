from contextlib import asynccontextmanager
from fastapi import FastAPI
from shared.logger.logger import get_logger

logger=get_logger(__name__)

@asynccontextmanager
async def lifespan(app:FastAPI):
    logger.info("Starting with Auth-Service")

    yield

    logger.info("Stopping Auth-Service")
    