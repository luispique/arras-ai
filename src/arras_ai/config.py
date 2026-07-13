"""Runtime configuration, loaded from the environment (and an optional .env file)."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_JUDGE_MODEL = "claude-sonnet-5"


class Settings(BaseSettings):
    """Application settings.

    `ANTHROPIC_API_KEY` follows the SDK's own env var name so the Anthropic client
    picks it up transparently. The model can be overridden with `ARRAS_MODEL`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
        populate_by_name=True,
    )

    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias="ANTHROPIC_API_KEY",
    )
    model: str = Field(
        default=DEFAULT_MODEL,
        validation_alias=AliasChoices("ARRAS_MODEL", "MODEL"),
    )
    embedding_provider: str = Field(default="local", validation_alias="ARRAS_EMBEDDING_PROVIDER")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    voyage_api_key: str | None = Field(default=None, validation_alias="VOYAGE_API_KEY")
    kb_index_dir: str = Field(default=".arras_kb_index", validation_alias="ARRAS_KB_INDEX_DIR")
    judge_model: str = Field(default=DEFAULT_JUDGE_MODEL, validation_alias="ARRAS_JUDGE_MODEL")


def load_settings() -> Settings:
    """Load settings from the environment / .env file."""
    return Settings()
