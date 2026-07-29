from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.exceptions.handlers import register_exception_handlers

from app.api.v1.api import api_router
from app.core.lifespan import lifespan

app=FastAPI(
    title="Chat Service (RAG)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
register_exception_handlers(app)

app.include_router(api_router,prefix="/api/v1")