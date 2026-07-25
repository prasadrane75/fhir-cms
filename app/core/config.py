from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_OPENAI_KEYS = {"", "sk-your-key-here", "changeme"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FHIR Case Management System"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://cms:cms@localhost:5432/cms_audit"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    fhir_base_url: str = "http://localhost:8080/fhir"

    openai_api_key: str = ""
    llm_base_url: str | None = None
    llm_model: str = "mistral-nemo:latest"
    llm_api_key: str = "ollama"

    webhook_secret: str = ""
    webhook_clinical_query: str = (
        "Review the latest observation in context and recommend whether care management should proceed."
    )
    webhook_enabled: bool = True
    webhook_public_base_url: str = "http://api:8000"

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def normalize_llm_base_url(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_openai_api_key(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if normalized in _PLACEHOLDER_OPENAI_KEYS:
            return ""
        return normalized

    @property
    def uses_local_llm(self) -> bool:
        return self.llm_base_url is not None


settings = Settings()
