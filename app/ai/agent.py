from dataclasses import dataclass
from enum import Enum
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
from app.ai.tools import CLAIMS_ADJUDICATION_TOOLS, PRIOR_AUTH_TOOLS
from app.core.models.case import Case
from app.core.models.claims import ClaimLineItem


class ReviewMode(str, Enum):
    PRIOR_AUTH = "prior_auth"
    CLAIMS_ADJUDICATION = "claims_adjudication"


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    case_context: str
    review_mode: str
    human_approved: bool | None


PRIOR_AUTH_SYSTEM_PROMPT = """You are a prior authorization clinical case review assistant for a healthcare Case Management System.
Use the Neo4j clinical knowledge graph tools to ground your recommendations in established
clinical knowledge about diseases, observations, reference ranges, and interventions.

When reviewing a prior authorization case:
1. Query the knowledge graph for conditions relevant to the patient's observations.
2. Check reference ranges when observation LOINC codes are available.
3. Provide a concise clinical summary and a recommendation (approve or reject) with rationale.

Always cite which graph findings informed your assessment."""

CLAIMS_ADJUDICATION_SYSTEM_PROMPT = """You are a claims adjudication assistant for Capability 02 rules checking.
Use the Neo4j claims knowledge graph tools to validate pricing rules and detect duplicate claims.

When adjudicating a claim:
1. Run check_claim_pricing_rules for every submitted line item against the payer contract rates.
2. Run check_duplicate_claims for the member, claim id, service date, and procedure codes.
3. Summarize pricing violations, adjustments, and any duplicate claim matches.
4. Recommend approve, partial pay, or deny with explicit reason codes.

Always cite graph findings from the pricing and duplicate detection tools."""


@dataclass
class CaseReviewResult:
    summary: str
    awaiting_approval: bool
    interrupt_payload: dict[str, Any] | None = None
    human_approved: bool | None = None


@dataclass
class ClaimReviewContext:
    claim_id: str
    member_id: str
    payer_id: str
    service_date: str
    line_items: list[ClaimLineItem]
    provider_npi: str | None = None


_checkpointer = MemorySaver()
_agent = None


def _system_prompt_for_mode(review_mode: ReviewMode) -> str:
    if review_mode == ReviewMode.CLAIMS_ADJUDICATION:
        return CLAIMS_ADJUDICATION_SYSTEM_PROMPT
    return PRIOR_AUTH_SYSTEM_PROMPT


def _tools_for_mode(review_mode: ReviewMode):
    if review_mode == ReviewMode.CLAIMS_ADJUDICATION:
        return CLAIMS_ADJUDICATION_TOOLS
    return PRIOR_AUTH_TOOLS


def _build_agent():
    llm = build_llm()

    def agent_node(state: AgentState) -> dict:
        review_mode = ReviewMode(state.get("review_mode", ReviewMode.PRIOR_AUTH.value))
        tools = _tools_for_mode(review_mode)
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def tools_node(state: AgentState) -> dict:
        review_mode = ReviewMode(state.get("review_mode", ReviewMode.PRIOR_AUTH.value))
        tools = _tools_for_mode(review_mode)
        tool_node = ToolNode(tools)
        return tool_node.invoke(state)

    def human_approval_node(state: AgentState) -> dict:
        last = state["messages"][-1]
        ai_recommendation = last.content if isinstance(last, AIMessage) else str(last)
        review_mode = ReviewMode(state.get("review_mode", ReviewMode.PRIOR_AUTH.value))
        review_label = (
            "claims adjudication"
            if review_mode == ReviewMode.CLAIMS_ADJUDICATION
            else "prior authorization"
        )

        decision = interrupt(
            {
                "type": "human_approval",
                "review_mode": review_mode.value,
                "ai_recommendation": ai_recommendation,
                "case_context": state["case_context"],
                "message": (
                    f"Review the AI {review_label} recommendation and approve or reject "
                    "before the case is finalized."
                ),
            }
        )

        approved = bool(decision.get("approved", False))
        reason = decision.get("reason") or ""
        verdict = "approved" if approved else "rejected"
        summary = f"Human reviewer {verdict} the {review_label} case."
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
    graph.add_node("tools", tools_node)
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


def build_claim_context(claim: ClaimReviewContext) -> str:
    lines = [
        f"Claim ID: {claim.claim_id}",
        f"Member ID: {claim.member_id}",
        f"Payer ID: {claim.payer_id}",
        f"Service Date: {claim.service_date}",
    ]
    if claim.provider_npi:
        lines.append(f"Provider NPI: {claim.provider_npi}")
    lines.append("Line Items:")
    for item in claim.line_items:
        diagnosis = ", ".join(item.diagnosis_codes) if item.diagnosis_codes else "N/A"
        lines.append(
            f"  - {item.procedure_code}: billed ${item.billed_amount:.2f}, "
            f"units={item.units}, diagnosis={diagnosis}"
        )
    return "\n".join(lines)


def _build_review_message(
    review_mode: ReviewMode,
    context: str,
    query: str,
    claim_context: ClaimReviewContext | None = None,
) -> HumanMessage:
    if review_mode == ReviewMode.CLAIMS_ADJUDICATION:
        claim_block = build_claim_context(claim_context) if claim_context else context
        return HumanMessage(
            content=(
                "Adjudicate the following claim using pricing rules and duplicate detection.\n\n"
                f"CASE CONTEXT:\n{context}\n\n"
                f"CLAIM DETAILS:\n{claim_block}\n\n"
                f"ADJUDICATION QUERY:\n{query}"
            )
        )

    return HumanMessage(
        content=(
            "Review the following prior authorization case and answer the clinical query.\n\n"
            f"CASE CONTEXT:\n{context}\n\n"
            f"CLINICAL QUERY:\n{query}"
        )
    )


async def run_case_review(
    case: Case,
    query: str,
    *,
    review_mode: ReviewMode = ReviewMode.PRIOR_AUTH,
    claim_context: ClaimReviewContext | None = None,
) -> CaseReviewResult:
    agent = get_agent()
    context = build_case_context(case)
    messages = [
        SystemMessage(content=_system_prompt_for_mode(review_mode)),
        _build_review_message(review_mode, context, query, claim_context),
    ]
    result = await agent.ainvoke(
        {
            "messages": messages,
            "case_context": context,
            "review_mode": review_mode.value,
            "human_approved": None,
        },
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
