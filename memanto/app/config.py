

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

load_dotenv()
_memanto_env = Path.home() / ".memanto" / ".env"
if _memanto_env.exists():
    load_dotenv(_memanto_env, override=True)

_config_file = Path.home() / ".memanto" / "config.yaml"
if _config_file.exists():
    try:
        import yaml

        with open(_config_file) as f:
            _data = yaml.safe_load(f)
            _memanto = _data.get("memanto", {})

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

            _summary = _memanto.get("summary", {})
            _sum_model = _summary.get("model")
            if _sum_model:
                os.environ["SUMMARY_MODEL"] = _sum_model

            _cli = _memanto.get("cli", {})
            _smart_parse = _cli.get("smart_parse")
            if _smart_parse is not None:
                os.environ["AUTO_PARSE_ENABLED"] = str(_smart_parse)

            _session = _memanto.get("session", {})
            if isinstance(_session, dict):
                for _yaml_key, _env_key in (
                    ("auto_renew_enabled", "SESSION_AUTO_RENEW_ENABLED"),
                    ("auto_recreate_enabled", "SESSION_AUTO_RECREATE_ENABLED"),
                ):
                    _toggle = _session.get(_yaml_key)
                    if isinstance(_toggle, bool):
                        os.environ.setdefault(_env_key, str(_toggle))

            _backend = _memanto.get("backend")
            if _backend:
                os.environ["MEMANTO_BACKEND"] = str(_backend)
    except Exception as _exc:
        logger.warning("Failed to load ~/.memanto/config.yaml: %s", _exc)

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

class ServerConfig(BaseModel):
    

    url: str = "localhost"
    port: int = 8000
    auto_start: bool = False

class SessionConfig(BaseModel):
    

    default_duration_hours: int = 6
    auto_extend: bool = True
    extend_threshold_minutes: int = 30
    warn_before_expiry_minutes: int = 15
    auto_renew_enabled: bool = True
    auto_renew_interval_hours: int = 6
    auto_recreate_enabled: bool = True

class CLIConfig(BaseModel):
    

    interactive_mode: bool = True
    smart_parse: bool = True
    auto_title: bool = True
    color_output: bool = True

class Settings(BaseSettings):

    MOORCHEH_API_KEY: str = ""

    MEMANTO_BACKEND: str = "cloud"
    MOORCHEH_ONPREM_URL: str = "http://localhost:8080"
    MOORCHEH_ONPREM_EMBEDDING_PROVIDER: str = ""

    MOORCHEH_ONPREM_TIMEOUT: int = 300

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    ALLOWED_ORIGINS: list[str] = []

    CORS_ORIGIN_REGEX: str | None = r"^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$"

    CORS_ALLOW_CREDENTIALS: bool = False

    MEMANTO_SECRET_KEY: str = ""
    SESSION_DEFAULT_DURATION_HOURS: int = 6
    SESSION_AUTO_EXTEND: bool = True
    SESSION_EXTEND_THRESHOLD_MINUTES: int = 30
    SESSION_AUTO_RENEW_ENABLED: bool = True
    SESSION_AUTO_RENEW_INTERVAL_HOURS: int = 6

    SESSION_AUTO_RECREATE_ENABLED: bool = True

    DEFAULT_TTL_SECONDS: int = 3600  # 1 hour

    ANSWER_MODEL: str = "anthropic.claude-sonnet-4-6"
    ANSWER_TEMPERATURE: float = 0.7
    ANSWER_LIMIT: int = 15  # number of context memories to retrieve
    ANSWER_THRESHOLD: float = 0.01  # confidence threshold for memory relevance

    SUMMARY_MODEL: str = "anthropic.claude-sonnet-4-6"

    RECALL_LIMIT: int = 10  # default top-N results for recall/search

    MEMANTO_SCHEDULE_TIME: str = "23:55"

    AUTO_PARSE_ENABLED: bool = True

    MEMANTO_UI_MODE: bool = False

    MEMANTO_ENABLE_DOCS: bool = False

    MEMANTO_REQUIRE_SECURE: bool = False

    MEMANTO_PROXY_ALLOWED_IPS: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )

    @property
    def proxy_allowed_ips(self) -> list[str]:
        
        raw = (self.MEMANTO_PROXY_ALLOWED_IPS or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                values = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "MEMANTO_PROXY_ALLOWED_IPS must be a valid JSON array of IP "
                    "addresses or a comma-separated list"
                ) from exc
        else:
            values = raw.split(",")
        entries = [str(v).strip() for v in values if str(v).strip()]
        try:
            return [_canonical_ip_string(entry) for entry in entries]
        except ValueError as exc:
            raise ValueError(
                "MEMANTO_PROXY_ALLOWED_IPS must contain valid IP addresses "
                "(CIDR blocks and hostnames are not supported)"
            ) from exc

settings = Settings()

def _canonical_ip_string(value: str) -> str:
    
    addr = ipaddress.ip_address(value)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return str(addr.ipv4_mapped)
    return str(addr)

def is_loopback_host(host: str | None) -> bool:
    
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

    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped
        return mapped is not None and mapped.is_loopback
    return False

def plain_http_exposure_message(host: str) -> str | None:
    
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
    
    if is_loopback_host(host):
        return
    message = plain_http_exposure_message(host)
    if settings.MEMANTO_REQUIRE_SECURE:
        if not settings.proxy_allowed_ips:
            raise RuntimeError(f"MEMANTO_REQUIRE_SECURE is set. {message}")
        return
    if not settings.DEBUG:
        logger.warning("%s", message)

def get_data_dir() -> Path:
    
    base = Path.home() / ".memanto"
    if settings.MEMANTO_BACKEND.strip().lower() == "on-prem":
        d = base / "on-prem"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return base

def get_conflicts_dir() -> Path:
    
    d = get_data_dir() / "conflicts"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_conflict_report_path(agent_id: str, date: str) -> Path:
    
    import re

    if not re.match(r"^[\w\-]+$", agent_id):
        raise ValueError(f"Invalid agent_id format: {agent_id}")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"Invalid date format: {date}")
    return get_conflicts_dir() / f"{agent_id}_{date}_conflicts.json"
