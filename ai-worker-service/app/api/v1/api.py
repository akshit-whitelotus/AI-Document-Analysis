from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.search import router as search_router

api_router=APIRouter()

api_router.include_router(health_router,prefix="/health",tags=["Health"])
api_router.include_router(search_router,prefix="/internal/search",tags=["Internal"])