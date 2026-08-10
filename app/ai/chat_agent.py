from typing import Annotated

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app.ai.llm import build_llm
from app.ai.tools import ALL_REVIEW_TOOLS

CHAT_SYSTEM_PROMPT = """You are a clinical and claims review assistant in a live chat session.

Use the Neo4j knowledge graph tools to ground answers in established data:
- Prior authorization: diseases, observations, reference ranges, interventions.
- Claims adjudication (Capability 02): pricing rules and duplicate claim detection.

Guidelines:
- Answer conversationally and cite graph findings when you use them.
- Use the provided case context when a case is linked to this session.
- Ask clarifying questions when clinical or claim data is missing.
- Do not invent lab values, diagnoses, or claim amounts not supported by context or tools.
- For formal workflow actions, users can type slash commands such as:
  /status, /start-review, /formal-review, /approve, /reject
"""


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    case_context: str | None


_chat_checkpointer = MemorySaver()
_chat_agent = None


def _build_chat_agent():
    tools = ALL_REVIEW_TOOLS
    llm = build_llm().bind_tools(tools)

    def agent_node(state: ChatState) -> dict:
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: ChatState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(ChatState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=_chat_checkpointer)


def get_chat_agent():
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = _build_chat_agent()
    return _chat_agent


def thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": f"chat-{session_id}"}}


def bootstrap_messages(case_context: str | None) -> list[BaseMessage]:
    system_content = CHAT_SYSTEM_PROMPT
    if case_context:
        system_content += f"\n\nCASE CONTEXT:\n{case_context}"
    return [SystemMessage(content=system_content)]


def extract_assistant_reply(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content and not message.tool_calls:
            return str(message.content)
    return "I could not generate a response."
