import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes import api_router
from app.core.config import settings
from app.services.audit import init_db

STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Healthcare Case Management System with FHIR, LangGraph, and Neo4j",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def test_ui():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/chat")
async def chat_ui():
    return FileResponse(STATIC_DIR / "chat.html")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.app_name}
