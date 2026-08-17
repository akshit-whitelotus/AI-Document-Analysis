from fastapi import APIRouter
from app.api.v1.admin import router as admin_router
from app.api.v1.documents import router as documents_router
from app.api.v1.documents_ws import router as documents_ws_router
from app.api.v1.health import router as health_router

api_router=APIRouter()

api_router.include_router(health_router,prefix="/health",tags=["Health"])
api_router.include_router(documents_router,prefix="/documents",tags=["Documents"])
api_router.include_router(documents_ws_router,prefix="/documents",tags=["Documents"])
# Registered at /documents/admin/... (not a seperate top-level /admin) so it
# rides through the gateway's existing "/documents/{path:path}" proxy route
# (see gateway-service/app/api/v1/proxy.py) with no gateway changes needed -
# the gateway already forwards everything under /documents/* to this service.
api_router.include_router(admin_router,prefix="/documents/admin",tags=["Admin"])
