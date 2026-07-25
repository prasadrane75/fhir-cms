from fastapi import APIRouter

from app.api.routes import audit, cases, chat, patients, webhooks

api_router = APIRouter()
api_router.include_router(cases.router)
api_router.include_router(patients.router)
api_router.include_router(audit.router)
api_router.include_router(webhooks.router)
api_router.include_router(chat.router)
