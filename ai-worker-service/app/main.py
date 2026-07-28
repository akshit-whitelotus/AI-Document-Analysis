from fastapi import FastAPI
from shared.exceptions.handlers import register_exception_handlers
from app.api.v1.api import api_router

app=FastAPI(title="AI Worker Service (Internal Search API)",version="1.0.0")

register_exception_handlers(app)

app.include_router(api_router,prefix="/api/v1")
