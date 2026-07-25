from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from app.ai.llm import build_llm
from app.ai.tools import get_reference_ranges, query_clinical_knowledge_graph
from app.core.models.case import Case


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    case_context: str
    human_approved: bool | None


SYSTEM_PROMPT = """You are a clinical case review assistant for a healthcare Case Management System.
Use the Neo4j clinical knowledge graph tools to ground your recommendations in established
clinical knowledge about diseases, observations, reference ranges, and interventions.

When reviewing a case:
1. Query the knowledge graph for conditions relevant to the patient's observations.
2. Check reference ranges when observation LOINC codes are available.
3. Provide a concise clinical summary and a recommendation (approve or reject) with rationale.

Always cite which graph findings informed your assessment."""


@dataclass
class CaseReviewResult:
    summary: str
    awaiting_approval: bool
    interrupt_payload: dict[str, Any] | None = None
    human_approved: bool | None = None


_checkpointer = MemorySaver()
_agent = None


def _build_agent():
    tools = [query_clinical_knowledge_graph, get_reference_ranges]
    llm = build_llm()
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def human_approval_node(state: AgentState) -> dict:
        last = state["messages"][-1]
        ai_recommendation = last.content if isinstance(last, AIMessage) else str(last)

        decision = interrupt(
            {
                "type": "human_approval",
                "ai_recommendation": ai_recommendation,
                "case_context": state["case_context"],
                "message": (
                    "Review the AI recommendation and approve or reject before the case is finalized."
                ),
            }
        )

        approved = bool(decision.get("approved", False))
        reason = decision.get("reason") or ""
        verdict = "approved" if approved else "rejected"
        summary = f"Human reviewer {verdict} the case."
        if reason:
            summary += f" Reason: {reason}"

        return {
            "human_approved": approved,
            "messages": [AIMessage(content=summary)],
        }

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "human_approval"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("human_approval", human_approval_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "human_approval": "human_approval"},
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("human_approval", END)
    return graph.compile(checkpointer=_checkpointer)


def get_agent():
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


def _thread_config(case_id: UUID) -> dict:
    return {"configurable": {"thread_id": str(case_id)}}


def _extract_ai_summary(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content and not message.tool_calls:
            return message.content
    final_message = messages[-1]
    return final_message.content if hasattr(final_message, "content") else str(final_message)


def _interrupt_payload(result: dict) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value


def build_case_context(case: Case) -> str:
    lines = [
        f"Case ID: {case.id}",
        f"Title: {case.title}",
        f"Description: {case.description or 'N/A'}",
        f"Patient ID: {case.patient_id}",
    ]
    if case.patient:
        lines.append(f"Patient: {case.patient.display_name}, gender={case.patient.gender}")
    if case.observations:
        lines.append("Observations:")
        for obs in case.observations:
            codes = [c.get("code", "") for c in obs.code.coding]
            lines.append(f"  - {obs.code_display}: {obs.display_value} (codes: {', '.join(codes)})")
    return "\n".join(lines)


async def run_case_review(case: Case, clinical_query: str) -> CaseReviewResult:
    agent = get_agent()
    context = build_case_context(case)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Review the following case and answer the clinical query.\n\n"
                f"CASE CONTEXT:\n{context}\n\n"
                f"CLINICAL QUERY:\n{clinical_query}"
            )
        ),
    ]
    result = await agent.ainvoke(
        {"messages": messages, "case_context": context, "human_approved": None},
        _thread_config(case.id),
    )
    if result.get("__interrupt__"):
        return CaseReviewResult(
            summary=_extract_ai_summary(result["messages"]),
            awaiting_approval=True,
            interrupt_payload=_interrupt_payload(result),
        )
    return CaseReviewResult(
        summary=_extract_ai_summary(result["messages"]),
        awaiting_approval=False,
        human_approved=result.get("human_approved"),
    )


async def resume_case_review(case_id: UUID, approved: bool, reason: str | None = None) -> CaseReviewResult:
    agent = get_agent()
    result = await agent.ainvoke(
        Command(resume={"approved": approved, "reason": reason}),
        _thread_config(case_id),
    )
    return CaseReviewResult(
        summary=_extract_ai_summary(result["messages"]),
        awaiting_approval=bool(result.get("__interrupt__")),
        interrupt_payload=_interrupt_payload(result),
        human_approved=result.get("human_approved"),
    )
