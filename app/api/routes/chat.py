from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.models.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSession,
    ChatSessionCreate,
)
from app.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSession])
async def list_chat_sessions() -> list[ChatSession]:
    return chat_service.list_sessions()


@router.post("/sessions", response_model=ChatSession, status_code=status.HTTP_201_CREATED)
async def create_chat_session(payload: ChatSessionCreate) -> ChatSession:
    return chat_service.create_session(payload.case_id)


@router.get("/sessions/{session_id}", response_model=ChatSession)
async def get_chat_session(session_id: UUID) -> ChatSession:
    session = chat_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_chat_message(session_id: UUID, payload: ChatMessageRequest) -> ChatMessageResponse:
    try:
        message = await chat_service.send_message(session_id, payload.content)
    except KeyError:
        raise HTTPException(status_code=404, detail="Chat session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    session = chat_service.get_session(session_id)
    case_status = None
    if session and session.case_id:
        from app.services.case_service import case_service

        case = case_service.get_case(session.case_id)
        case_status = case.status.value if case else None

    return ChatMessageResponse(
        session_id=session_id,
        role=message.role,
        content=message.content,
        case_id=session.case_id if session else None,
        case_status=case_status,
    )
