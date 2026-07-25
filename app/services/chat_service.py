from datetime import datetime
from uuid import UUID

from langchain_core.messages import HumanMessage

from app.ai.agent import build_case_context
from app.ai.chat_agent import (
    bootstrap_messages,
    extract_assistant_reply,
    get_chat_agent,
    thread_config,
)
from app.core.models.case import CaseStatus
from app.core.models.chat import ChatMessage, ChatSession
from app.services.case_service import case_service


class ChatService:
    def __init__(self) -> None:
        self._sessions: dict[UUID, ChatSession] = {}

    def list_sessions(self) -> list[ChatSession]:
        return sorted(self._sessions.values(), key=lambda s: s.created_at, reverse=True)

    def get_session(self, session_id: UUID) -> ChatSession | None:
        return self._sessions.get(session_id)

    def create_session(self, case_id: UUID | None = None) -> ChatSession:
        session = ChatSession(case_id=case_id)
        greeting = "Clinical review chat ready. Ask about the case, labs, or reference ranges."
        if case_id:
            case = case_service.get_case(case_id)
            if case:
                greeting = (
                    f"Chat linked to case '{case.title}' ({case.status.value}). "
                    "Ask clinical questions or use /help for workflow commands."
                )
            else:
                greeting = f"Case {case_id} was not found. Chat started without case context."
        session.messages.append(ChatMessage(role="assistant", content=greeting))
        self._sessions[session.id] = session
        return session

    def _case_context(self, case_id: UUID | None) -> str | None:
        if not case_id:
            return None
        case = case_service.get_case(case_id)
        return build_case_context(case) if case else None

    async def _handle_command(self, session: ChatSession, content: str) -> str:
        case = case_service.get_case(session.case_id) if session.case_id else None
        parts = content.strip().split(maxsplit=1)
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""

        if command in {"/help", "help"}:
            return (
                "Workflow commands:\n"
                "/status — show linked case status\n"
                "/start-review — move case Pending → AI_Review\n"
                "/formal-review [query] — run full LangGraph review to Pending_Approval\n"
                "/approve [reason] — approve at Pending_Approval\n"
                "/reject [reason] — reject at Pending_Approval"
            )

        if not session.case_id or not case:
            return "Link this chat to a case first (create session with case_id)."

        if command == "/status":
            return (
                f"Case {case.id}\n"
                f"Status: {case.status.value}\n"
                f"Title: {case.title}\n"
                f"Patient: {case.patient_id}"
            )

        if command == "/start-review":
            if case.status != CaseStatus.PENDING:
                return f"Cannot start review from status {case.status.value}."
            case_service.transition(case.id, CaseStatus.AI_REVIEW)
            return "Case moved to AI_Review. Ask clinical questions or run /formal-review."

        if command == "/formal-review":
            if case.status != CaseStatus.AI_REVIEW:
                return f"Formal review requires AI_Review. Current status: {case.status.value}."
            query = argument or "Summarize this case and recommend approve or reject with rationale."
            updated = await case_service.run_ai_review(case.id, query)
            return (
                f"Formal review complete. Status: {updated.status.value}\n\n"
                f"{updated.ai_summary or 'No summary generated.'}"
            )

        if command == "/approve":
            if case.status != CaseStatus.PENDING_APPROVAL:
                return f"Approve requires Pending_Approval. Current status: {case.status.value}."
            updated = await case_service.resume_human_approval(case.id, True, argument or None)
            return f"Case approved. Final status: {updated.status.value}"

        if command == "/reject":
            if case.status != CaseStatus.PENDING_APPROVAL:
                return f"Reject requires Pending_Approval. Current status: {case.status.value}."
            updated = await case_service.resume_human_approval(case.id, False, argument or None)
            return f"Case rejected. Final status: {updated.status.value}"

        return f"Unknown command: {command}. Type /help for available commands."

    async def send_message(self, session_id: UUID, content: str) -> ChatMessage:
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Chat session {session_id} not found")

        session.messages.append(ChatMessage(role="user", content=content))

        if content.strip().startswith("/"):
            reply = await self._handle_command(session, content.strip())
        else:
            reply = await self._chat_with_agent(session, content)

        assistant_message = ChatMessage(role="assistant", content=reply)
        session.messages.append(assistant_message)
        return assistant_message

    async def _chat_with_agent(self, session: ChatSession, content: str) -> str:
        agent = get_chat_agent()
        case_context = self._case_context(session.case_id)
        config = thread_config(str(session.id))

        state = await agent.aget_state(config)
        if not state.values.get("messages"):
            await agent.ainvoke(
                {"messages": bootstrap_messages(case_context), "case_context": case_context},
                config,
            )

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=content)], "case_context": case_context},
            config,
        )
        return extract_assistant_reply(result["messages"])


chat_service = ChatService()
