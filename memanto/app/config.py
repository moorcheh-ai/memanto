"""
MEMANTO Configuration

Server-side settings (loaded from .env via pydantic-settings).
CLI config models have been moved to cli/config/manager.py.
"""

import ipaddress
import json
import logging
import os
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

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

            # Session toggles. The Web UI and ``memanto config`` persist these
            # to config.yaml, but SessionService reads them off ``settings``,
            # so without this they would be inert for the server and only
            # half-honoured by the CLI. Use setdefault so an explicitly
            # exported SESSION_AUTO_* (containerised deployments) still wins.
            _session = _memanto.get("session", {})
            if isinstance(_session, dict):
                for _yaml_key, _env_key in (
                    ("auto_renew_enabled", "SESSION_AUTO_RENEW_ENABLED"),
                    ("auto_recreate_enabled", "SESSION_AUTO_RECREATE_ENABLED"),
                ):
                    _toggle = _session.get(_yaml_key)
                    if isinstance(_toggle, bool):
                        os.environ.setdefault(_env_key, str(_toggle))

            # Backend selection (cloud | on-prem)
            _backend = _memanto.get("backend")
            if _backend:
                os.environ["MEMANTO_BACKEND"] = str(_backend)
    except Exception as _exc:
        logger.warning("Failed to load ~/.memanto/config.yaml: %s", _exc)

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
    except Exception as _exc:
        logger.warning("Failed to load ~/.memanto/on-prem/state.json: %s", _exc)


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
    auto_recreate_enabled: bool = True


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
    # Transparently issue a fresh session (new token) when a request presents
    # an expired-but-not-terminated token. Gated behind management access.
    SESSION_AUTO_RECREATE_ENABLED: bool = True

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

    # Schedule Configuration
    MEMANTO_SCHEDULE_TIME: str = "23:55"

    # Auto Parsing Configuration
    AUTO_PARSE_ENABLED: bool = True

    # UI Mode
    MEMANTO_UI_MODE: bool = False

    # Security: expose the interactive API docs (/docs, /redoc, /openapi.json).
    # Off by default because the server binds 0.0.0.0 by default and the schema
    # would otherwise be enumerable by any network peer. Enable explicitly only
    # on a trusted network or behind an access-control layer - HTTPS protects
    # transport, not access to the schema.
    MEMANTO_ENABLE_DOCS: bool = False
    # Security: refuse to start when MEMANTO would be served over plain HTTP on
    # a non-loopback interface (the default 0.0.0.0 bind) so the session cookie
    # and API traffic cannot be sniffed on the network.
    MEMANTO_REQUIRE_SECURE: bool = False
    # Security: when TLS terminates at a reverse proxy, the browser-facing
    # scheme arrives as X-Forwarded-Proto. Only trust that header from peers in
    # this explicit allowlist (empty = never trust forwarded headers, so the
    # session cookie is only marked Secure when the request really arrived over
    # HTTPS). The proxy must overwrite any client-supplied forwarding headers.
    # Parsed via ``proxy_allowed_ips`` (a JSON array or comma-separated list).
    MEMANTO_PROXY_ALLOWED_IPS: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )

    @property
    def proxy_allowed_ips(self) -> list[str]:
        """Trusted reverse-proxy peers allowed to set ``X-Forwarded-Proto``.

        Reads ``MEMANTO_PROXY_ALLOWED_IPS`` as a JSON array (``["1.2.3.4"]``)
        or a comma-separated list. Empty or unset means the forwarded header is
        never trusted, so the session cookie is only marked ``Secure`` when the
        browser connection really arrived over HTTPS.
        """
        raw = (self.MEMANTO_PROXY_ALLOWED_IPS or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                values = json.loads(raw)
            except json.JSONDecodeError:
                return []
            return [str(ip).strip() for ip in values if str(ip).strip()]
        return [ip.strip() for ip in raw.split(",") if ip.strip()]


# Global settings instance
settings = Settings()


def is_loopback_host(host: str | None) -> bool:
    """True when a uvicorn ``host`` binds only to loopback interfaces."""
    raw = (host or "").strip().lower().strip("[]")
    if raw == "localhost":
        return True
    if not raw:
        return False
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    # IPv4-mapped IPv6 (e.g. ``::ffff:127.0.0.1``) is not flagged by
    # ``is_loopback`` alone, so unwrap the embedded IPv4 address.
    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped
        return mapped is not None and mapped.is_loopback
    return False


def plain_http_exposure_message(host: str) -> str | None:
    """Describe the exposure when ``host`` serves plain HTTP on the network.

    Returns a human-readable warning for any non-loopback bind (the app ships
    with no built-in TLS and defaults to binding ``0.0.0.0``), else ``None``.
    Suppressing the *warning* under ``DEBUG`` is a caller-side decision; it must
    never disable the ``MEMANTO_REQUIRE_SECURE`` enforcement.
    """
    if is_loopback_host(host):
        return None
    return (
        f"Memanto is serving over plain HTTP on {host!r} (no built-in TLS). Any "
        "network peer that can reach this port can sniff the session cookie "
        "(full memory read/write for an active agent) and enumerate every API "
        "route. Bind to a loopback address (127.0.0.1) or terminate TLS in "
        "front of Memanto."
    )


def check_secure_deployment(host: str) -> None:
    """Warn (or hard-fail) when Memanto would serve plain HTTP on the network."""
    if is_loopback_host(host):
        return
    message = plain_http_exposure_message(host)
    if settings.MEMANTO_REQUIRE_SECURE:
        raise RuntimeError(f"MEMANTO_REQUIRE_SECURE is set. {message}")
    if not settings.DEBUG:
        logger.warning("%s", message)


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


def get_conflicts_dir() -> Path:
    """Return the shared directory for conflict reports."""
    d = get_data_dir() / "conflicts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_conflict_report_path(agent_id: str, date: str) -> Path:
    """Return a safely constructed path for a conflict report, validating components against traversal."""
    import re

    if not re.match(r"^[\w\-]+$", agent_id):
        raise ValueError(f"Invalid agent_id format: {agent_id}")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"Invalid date format: {date}")
    return get_conflicts_dir() / f"{agent_id}_{date}_conflicts.json"
