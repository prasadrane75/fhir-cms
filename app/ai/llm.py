from langchain_openai import ChatOpenAI

from app.core.config import settings


def build_llm() -> ChatOpenAI:
    if settings.uses_local_llm:
        return ChatOpenAI(
            model=settings.llm_model,
            temperature=0,
            api_key=settings.llm_api_key or "ollama",
            base_url=settings.llm_base_url,
        )
    if not settings.openai_api_key:
        raise ValueError(
            "No LLM configured. Set LLM_BASE_URL for local inference "
            "(e.g. http://greyflow-ai:11434/v1) or OPENAI_API_KEY."
        )
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=0,
        api_key=settings.openai_api_key,
    )
