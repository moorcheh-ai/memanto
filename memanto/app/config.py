"""
MEMANTO Configuration

Server-side settings (loaded from .env via pydantic-settings).
CLI config models have been moved to cli/config/manager.py.
"""

import os
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load project .env first, then ~/.memanto/.env for the API key
load_dotenv()
_memanto_env = Path.home() / ".memanto" / ".env"
if _memanto_env.exists():
    load_dotenv(_memanto_env, override=True)

# Load model override from ~/.memanto/config.yaml
_config_file = Path.home() / ".memanto" / "config.yaml"
if _config_file.exists():
    try:
        import yaml

        with open(_config_file) as f:
            _data = yaml.safe_load(f)
            _memanto = _data.get("memanto", {})

            # Answer configuration
            _answer = _memanto.get("answer", {})
            _ans_model = _answer.get("model")
            if _ans_model:
                os.environ["ANSWER_MODEL"] = _ans_model
            _ans_temp = _answer.get("temperature")
            if _ans_temp is not None:
                os.environ["ANSWER_TEMPERATURE"] = str(_ans_temp)
            _ans_limit = _answer.get("answer_limit")
            if _ans_limit is not None:
                os.environ["ANSWER_LIMIT"] = str(_ans_limit)

            # Summary configuration
            _summary = _memanto.get("summary", {})
            _sum_model = _summary.get("model")
            if _sum_model:
                os.environ["SUMMARY_MODEL"] = _sum_model

            # CLI configuration
            _cli = _memanto.get("cli", {})
            _smart_parse = _cli.get("smart_parse")
            if _smart_parse is not None:
                os.environ["AUTO_PARSE_ENABLED"] = str(_smart_parse)

            # Backend selection (cloud | on-prem)
            _backend = _memanto.get("backend")
            if _backend:
                os.environ["MEMANTO_BACKEND"] = str(_backend)
    except Exception:
        pass

    # On-prem URL lives in ~/.memanto/on-prem/state.json so on-prem onboarding
    # never has to touch the shared cloud yaml.
    try:
        import json as _json

        _state_path = Path.home() / ".memanto" / "on-prem" / "state.json"
        if _state_path.exists():
            _state = _json.loads(_state_path.read_text())
            _op_url = _state.get("url")
            if _op_url:
                os.environ["MOORCHEH_ONPREM_URL"] = str(_op_url)
            _op_embed = _state.get("embedding_provider")
            if _op_embed:
                os.environ["MOORCHEH_ONPREM_EMBEDDING_PROVIDER"] = str(_op_embed)
    except Exception:
        pass


# CLI & YAML Format Models (kept for backward compat with config.yaml structure)
class ServerConfig(BaseModel):
    """Server configuration"""

    url: str = "localhost"
    port: int = 8000
    auto_start: bool = False


class SessionConfig(BaseModel):
    """Session management configuration"""

    default_duration_hours: int = 6
    auto_extend: bool = True
    extend_threshold_minutes: int = 30
    warn_before_expiry_minutes: int = 15
    auto_renew_enabled: bool = True
    auto_renew_interval_hours: int = 6


class CLIConfig(BaseModel):
    """CLI behavior configuration"""

    interactive_mode: bool = True
    smart_parse: bool = True
    auto_title: bool = True
    color_output: bool = True


class Settings(BaseSettings):
    """Unified Settings: sourced from environment / .env files"""

    # Moorcheh Configuration
    MOORCHEH_API_KEY: str = ""

    # Backend selection: "cloud" (default) or "on-prem".
    MEMANTO_BACKEND: str = "cloud"
    MOORCHEH_ONPREM_URL: str = "http://localhost:8080"
    MOORCHEH_ONPREM_EMBEDDING_PROVIDER: str = ""
    # HTTP read timeout (seconds) for the on-prem MoorchehClient. Default 300
    # so first-call LLM cold-starts on Ollama don't hit the SDK's 30s default.
    MOORCHEH_ONPREM_TIMEOUT: int = 300

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # CORS Configuration
    ALLOWED_ORIGINS: list[str] = ["*"]
    # Setting allow_credentials=True with a wildcard origin causes Starlette to
    # reflect any request Origin back, allowing any site to make credentialed
    # cross-origin requests.  Default to False; set to True only when ALLOWED_ORIGINS
    # lists explicit trusted domains (never with "*").
    CORS_ALLOW_CREDENTIALS: bool = False

    # Session Configuration
    MEMANTO_SECRET_KEY: str = ""
    SESSION_DEFAULT_DURATION_HOURS: int = 6
    SESSION_AUTO_EXTEND: bool = True
    SESSION_EXTEND_THRESHOLD_MINUTES: int = 30
    SESSION_AUTO_RENEW_ENABLED: bool = True
    SESSION_AUTO_RENEW_INTERVAL_HOURS: int = 6

    # Memory Configuration
    DEFAULT_TTL_SECONDS: int = 3600  # 1 hour

    # Answer Configuration
    ANSWER_MODEL: str = "anthropic.claude-sonnet-4-6"
    ANSWER_TEMPERATURE: float = 0.7
    ANSWER_LIMIT: int = 15  # number of context memories to retrieve
    ANSWER_THRESHOLD: float = 0.01  # confidence threshold for memory relevance

    # Summary & Conflict Detection Configuration
    SUMMARY_MODEL: str = "anthropic.claude-sonnet-4-6"

    # Recall / Search Configuration
    RECALL_LIMIT: int = 10  # default top-N results for recall/search

    # Validation Configuration
    REQUIRE_VALIDATION_FOR: list[str] = ["fact", "preference"]
    PROVISIONAL_TTL_SECONDS: int = 3600  # 1 hour
    PROVISIONAL_MAX_CONFIDENCE: float = 0.5

    # Schedule Configuration
    MEMANTO_SCHEDULE_TIME: str = "23:55"

    # Auto Parsing Configuration
    AUTO_PARSE_ENABLED: bool = True

    # UI Mode
    MEMANTO_UI_MODE: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


# Global settings instance
settings = Settings()


def get_data_dir() -> Path:
    """Root data dir for the active backend.

    Cloud users keep ``~/.memanto/`` (no migration). On-prem data is
    isolated under ``~/.memanto/on-prem/``.
    """
    base = Path.home() / ".memanto"
    if settings.MEMANTO_BACKEND.strip().lower() == "on-prem":
        d = base / "on-prem"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return base
