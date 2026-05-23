"""Typed environment settings via pydantic-settings.

Loaded once at import time; consumers `from app.core.settings import settings`.
Defaults are safe for local dev and tests — production must override the
secret values via the deployment environment.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Existing knobs (commit-1 / Dev 2 layer)
    use_llm: bool = False
    anthropic_api_key: str = ""
    litellm_model: str = "anthropic/claude-sonnet-4-5-20250929"
    db_path: str = "/data/ops.db"

    # Dev 3 additions
    webhook_secret: str = "dev-only-not-secret"
    admin_secret: str = "dev-only-not-secret"
    elevenlabs_api_key: str = ""
    elevenlabs_agent_id_outbound: str = ""
    fake_orchestrator: bool = False


settings = Settings()
