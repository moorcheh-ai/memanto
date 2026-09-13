"""
MEMANTO CLI Configuration Manager

Handles configuration persistence:
  - API key: stored in ~/.memanto/.env (sensitive, not committed)
  - Other config: stored in ~/.memanto/config.yaml (non-sensitive)
  - Connections registry: stored in ~/.memanto/connections.json
"""

import importlib
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv, set_key
from filelock import FileLock

from memanto.app.clients.backend import Backend, parse_backend
from memanto.app.utils.atomic_write import atomic_write_text
from memanto.app.utils.validation import validate_recall_limit
from memanto.cli.schedule_time import normalize_schedule_time

yaml = importlib.import_module("yaml")


def _normalize_duplicated_api_key(key: str) -> str:
    """Fix pasted keys accidentally doubled (same half repeated twice)."""
    key = key.strip()
    if len(key) % 2 == 0:
        half = len(key) // 2
        if key[:half] == key[half:]:
            return key[:half]
    return key


def _validate_server_port(port) -> int:
    """Return a valid TCP port or raise ValueError."""
    if isinstance(port, bool):
        raise ValueError("server port must be an integer between 1 and 65535")
    try:
        validated = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("server port must be an integer between 1 and 65535") from exc
    if isinstance(port, float) and not port.is_integer():
        raise ValueError("server port must be an integer between 1 and 65535")
    if validated < 1 or validated > 65535:
        raise ValueError("server port must be an integer between 1 and 65535")
    return validated


_SESSION_CONFIG_LIMITS = {
    "default_duration_hours": (1, 168),
    "extend_threshold_minutes": (1, 1440),
    "warn_before_expiry_minutes": (1, 1440),
    "auto_renew_interval_hours": (1, 168),
}
_SESSION_CONFIG_BOOLEANS = {
    "auto_extend",
    "auto_renew_enabled",
    "auto_recreate_enabled",
}


def _validate_positive_int_config(name: str, value, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    try:
        validated = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be an integer between {minimum} and {maximum}"
        ) from exc
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    if validated < minimum or validated > maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return validated


def _validate_int_range(name: str, value, minimum: int, maximum: int) -> int:
    return _validate_positive_int_config(name, value, minimum, maximum)


def _validate_float_range(name: str, value, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    try:
        validated = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be between {minimum} and {maximum}") from exc
    if not math.isfinite(validated) or validated < minimum or validated > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return validated


def _validate_session_config(updates: dict) -> dict:
    """Validate user-editable session config updates."""
    if not isinstance(updates, dict):
        raise ValueError("session config must be an object")

    allowed = set(_SESSION_CONFIG_LIMITS) | _SESSION_CONFIG_BOOLEANS
    rejected = set(updates) - allowed
    if rejected:
        raise ValueError(f"unknown session config keys: {', '.join(sorted(rejected))}")

    validated = {}
    for key, value in updates.items():
        if key in _SESSION_CONFIG_LIMITS:
            minimum, maximum = _SESSION_CONFIG_LIMITS[key]
            validated[key] = _validate_positive_int_config(key, value, minimum, maximum)
        elif key in _SESSION_CONFIG_BOOLEANS:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
            validated[key] = value
    return validated


class ConfigManager:
    """Manages MEMANTO CLI configuration.

    API key lives in ``~/.memanto/.env`` (plain-text, owner-only permissions).
    Everything else (server, session, CLI prefs, active session) lives in
    ``~/.memanto/config.yaml``.
    """

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.home() / ".memanto"
        self.config_file = self.config_dir / "config.yaml"
        self.env_file = self.config_dir / ".env"
        self.connections_file = self.config_dir / "connections.json"

        # Load env vars from the memanto .env file
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)

    # API Key (env-based)

    def get_api_key(self) -> str | None:
        """Get Moorcheh API key from ~/.memanto/.env."""
        # Re-read from file each time to pick up changes
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)
        key = os.environ.get("MOORCHEH_API_KEY", "").strip()
        return key if key else None

    def set_api_key(self, api_key: str) -> None:
        """Save Moorcheh API key to ~/.memanto/.env."""
        self._set_env_var("MOORCHEH_API_KEY", api_key)

    def get_supermemory_api_key(self) -> str | None:
        """Get Supermemory API key from ~/.memanto/.env."""
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)
        key = (
            os.environ.get("SUPERMEMORY_API_KEY")
            or os.environ.get("supermemory_api_key")
            or ""
        ).strip()
        if not key:
            return None
        return _normalize_duplicated_api_key(key)

    def set_supermemory_api_key(self, api_key: str) -> None:
        """Save Supermemory API key to ~/.memanto/.env."""
        self._set_env_var("SUPERMEMORY_API_KEY", _normalize_duplicated_api_key(api_key))

    def get_mem0_api_key(self) -> str | None:
        """Get Mem0 API key from ~/.memanto/.env."""
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)
        key = (
            os.environ.get("MEM0_API_KEY") or os.environ.get("mem0_api_key") or ""
        ).strip()
        if not key:
            return None
        return _normalize_duplicated_api_key(key)

    def set_mem0_api_key(self, api_key: str) -> None:
        """Save Mem0 API key to ~/.memanto/.env."""
        self._set_env_var("MEM0_API_KEY", _normalize_duplicated_api_key(api_key))

    def get_letta_api_key(self) -> str | None:
        """Get Letta API key from ~/.memanto/.env."""
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)
        key = (
            os.environ.get("LETTA_API_KEY") or os.environ.get("letta_api_key") or ""
        ).strip()
        if not key:
            return None
        return _normalize_duplicated_api_key(key)

    def set_letta_api_key(self, api_key: str) -> None:
        """Save Letta API key to ~/.memanto/.env."""
        self._set_env_var("LETTA_API_KEY", _normalize_duplicated_api_key(api_key))

    def get_langfuse_api_key(self) -> str | None:
        """Get the Langfuse credential from ~/.memanto/.env.

        Langfuse authenticates with a key *pair*, so the credential is stored
        as ``"<public_key>:<secret_key>"``. The vendor-native
        ``LANGFUSE_PUBLIC_KEY``/``LANGFUSE_SECRET_KEY`` pair is also accepted
        and joined, since anyone already using Langfuse has those set.
        """
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)

        combined = (os.environ.get("LANGFUSE_API_KEY") or "").strip()
        if combined:
            return combined

        public_key = (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
        secret_key = (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
        if public_key and secret_key:
            return f"{public_key}:{secret_key}"
        return None

    def set_langfuse_api_key(self, api_key: str) -> None:
        """Save the combined Langfuse credential to ~/.memanto/.env."""
        self._set_env_var("LANGFUSE_API_KEY", api_key.strip())

    def get_langfuse_host(self) -> str | None:
        """Get the Langfuse base URL (cloud EU/US or self-hosted)."""
        if self.env_file.exists():
            load_dotenv(self.env_file, override=True)
        host = (os.environ.get("LANGFUSE_HOST") or "").strip()
        return host or None

    def set_langfuse_host(self, host: str) -> None:
        """Save the Langfuse base URL to ~/.memanto/.env."""
        self._set_env_var("LANGFUSE_HOST", host.strip().rstrip("/"))

    def _set_env_var(self, name: str, value: str) -> None:
        """Write a single variable to ~/.memanto/.env and update os.environ."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.env_file.exists():
            self.env_file.write_text("# MEMANTO Environment\n")
        set_key(str(self.env_file), name, value)
        os.environ[name] = value
        try:
            self.env_file.chmod(0o600)
        except OSError:
            pass  # Windows may not support chmod

    def get_analyze_dir(self, provider: str) -> Path:
        """Base directory for a provider's analyze artifacts (e.g. 'supermemory')."""
        path = self.config_dir / "analyze" / provider
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_migrate_dir(self, provider: str) -> Path:
        """Base directory for a provider's migrate artifacts (export + report)."""
        path = self.config_dir / "migrate" / provider
        path.mkdir(parents=True, exist_ok=True)
        return path

    def is_configured(self) -> bool:
        """Check if the active backend is configured.

        Cloud: requires an API key.
        On-prem: requires ``backend: on-prem`` persisted in config.yaml
        (server reachability is verified at runtime, not here).
        """
        if self.get_backend() == Backend.ON_PREM:
            return True
        return self.get_api_key() is not None

    # Backend selection

    def get_backend(self) -> Backend:
        """Get the active backend (cloud or on-prem)."""
        return parse_backend(self.load_yaml().get("backend"))

    def set_backend(self, backend: Backend) -> None:
        """Persist the active backend choice."""
        self.set("backend", backend.value)

    # On-prem config — strictly isolated under ~/.memanto/on-prem/state.json.
    # On-prem onboarding/runtime must NOT write into the shared yaml; that file
    # is the cloud's namespace.

    def _onprem_state_path(self) -> Path:
        return self.config_dir / "on-prem" / "state.json"

    def get_onprem_state(self) -> dict:
        """Read the on-prem state.json. Returns ``{}`` if missing/unreadable."""
        p = self._onprem_state_path()
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text())
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def set_onprem_state(self, **updates) -> None:
        """Merge ``updates`` into the on-prem state.json (creates dir if needed)."""
        p = self._onprem_state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(p) + ".lock")
        with lock:
            data = self.get_onprem_state()
            data.update({k: v for k, v in updates.items() if v is not None})
            atomic_write_text(p, json.dumps(data, indent=2))

    def get_onprem_config(self) -> dict:
        """Get on-prem config dict (url, embedding_provider, llm_model, ...).

        Sourced exclusively from ``~/.memanto/on-prem/state.json``; defaults
        apply only when keys are missing from state.
        """
        defaults = {
            "url": "http://localhost:8080",
            "embedding_provider": "",
            "embedding_model": "",
            "llm_provider": "",
            "llm_model": "",
        }
        defaults.update(self.get_onprem_state())
        return defaults

    def set_onprem_config(
        self,
        embedding_provider: str | None = None,
        url: str | None = None,
        embedding_model: str | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        """Persist on-prem config values into ``~/.memanto/on-prem/state.json``."""
        self.set_onprem_state(
            embedding_provider=embedding_provider,
            url=url,
            embedding_model=embedding_model,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )

    # Per-backend data directory

    def get_data_dir(self) -> Path:
        """Root data dir for the active backend.

        Cloud users keep ``~/.memanto/`` (no migration). On-prem data is
        isolated under ``~/.memanto/on-prem/`` so switching backends does
        not mix agents/sessions across them.
        """
        if self.get_backend() == Backend.ON_PREM:
            d = self.config_dir / "on-prem"
            d.mkdir(parents=True, exist_ok=True)
            return d
        return self.config_dir

    # YAML Config (non-sensitive settings)

    def load_yaml(self) -> dict:
        """Load config.yaml as a plain dict."""
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file) as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                return {}

            memanto_data = data.get("memanto", {})
            if not isinstance(memanto_data, dict):
                return {}

            return memanto_data
        except Exception:
            return {}

    def save_yaml(self, data: dict) -> None:
        """Save dict to config.yaml under the 'memanto' key."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            yaml.dump({"memanto": data}, f, default_flow_style=False, sort_keys=False)
        try:
            self.config_file.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _dict_section(data: dict, key: str, *, repair: bool = False) -> dict:
        """Return a dict section.

        When repair is true, malformed or missing sections are replaced in
        ``data`` so callers can populate them before saving.
        """
        section = data.get(key)
        if isinstance(section, dict):
            return section
        if repair:
            new_section: dict = {}
            data[key] = new_section
            return new_section
        return {}

    def get(self, key: str, default=None):
        """Get a top-level YAML config value."""
        return self.load_yaml().get(key, default)

    def set(self, key: str, value) -> None:
        """Set a top-level YAML config value."""
        data = self.load_yaml()
        data[key] = value
        self.save_yaml(data)

    # Convenience accessors

    def get_server_url(self) -> str:
        """Return the normalized local REST API URL from the server config."""
        server = self._dict_section(self.load_yaml(), "server")
        host = server.get("url", "localhost")
        port = server.get("port", 8000)

        host = str(host).strip() or "localhost"
        if host.startswith(("http://", "https://")):
            parsed = urlsplit(host)
            netloc = parsed.netloc
            try:
                explicit_port = parsed.port
            except ValueError:
                explicit_port = None
                netloc = parsed.hostname or "localhost"
            if explicit_port is None:
                netloc = f"{netloc}:{port}"
            return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))

        return f"http://{host}:{port}"

    def get_server_config(self) -> dict:
        """Get server config dict with defaults."""
        defaults = {"url": "localhost", "port": 8000, "auto_start": False}
        defaults.update(self._dict_section(self.load_yaml(), "server"))
        return defaults

    def get_session_config(self) -> dict:
        """Get session config dict with defaults."""
        defaults = {
            "default_duration_hours": 6,
            "auto_extend": True,
            "extend_threshold_minutes": 30,
            "warn_before_expiry_minutes": 15,
            "auto_renew_enabled": True,
            "auto_renew_interval_hours": 6,
            "auto_recreate_enabled": True,
        }
        defaults.update(self._dict_section(self.load_yaml(), "session"))
        return defaults

    def get_cli_config(self) -> dict:
        """Get CLI behavior config dict with defaults."""
        defaults = {
            "interactive_mode": True,
            "smart_parse": True,
            "auto_title": True,
            "color_output": True,
        }
        defaults.update(self._dict_section(self.load_yaml(), "cli"))
        return defaults

    def get_answer_config(self) -> dict:
        """Get Answer config dict with defaults.

        The ``model`` field is backend-specific: cloud uses the shared yaml
        (default Bedrock Claude); on-prem uses ``llm_model`` from
        ``~/.memanto/on-prem/state.json`` (set during onboarding). All other
        knobs (temperature/threshold/answer_limit/kiosk_mode) are shared
        because they describe how to query, not which provider to hit.
        """
        data = self.load_yaml()
        answer = self._dict_section(data, "answer")

        defaults = {
            "model": "anthropic.claude-sonnet-4-6",
            "temperature": 0.7,
            "answer_limit": 15,
            "threshold": 0.15,
            "kiosk_mode": False,
        }
        defaults.update(answer)
        if self.get_backend() == Backend.ON_PREM:
            # On-prem: override model with the onboarding-selected LLM. Do NOT
            # fall back to the cloud default — pass through None so callers
            # can omit ``ai_model`` and let the on-prem server use its
            # ``~/.moorcheh/config.json`` LLM.
            defaults["model"] = self.get_onprem_state().get("llm_model") or None
        return defaults

    def set_answer_config(
        self,
        model: str | None = None,
        temperature: float | None = None,
        answer_limit: int | None = None,
        threshold: float | None = None,
        kiosk_mode: bool | None = None,
    ) -> None:
        """Set Answer config values."""
        data = self.load_yaml()
        answer = self._dict_section(data, "answer", repair=True)
        if model is not None:
            answer["model"] = model
        if temperature is not None:
            answer["temperature"] = _validate_float_range(
                "temperature", temperature, 0.0, 2.0
            )
        if answer_limit is not None:
            answer["answer_limit"] = _validate_int_range(
                "answer_limit", answer_limit, 1, 50
            )
        if threshold is not None:
            answer["threshold"] = _validate_float_range(
                "threshold", threshold, 0.0, 1.0
            )
        if kiosk_mode is not None:
            if not isinstance(kiosk_mode, bool):
                raise ValueError("kiosk_mode must be a boolean")
            answer["kiosk_mode"] = bool(kiosk_mode)

        self.save_yaml(data)

    def set_session_config(self, updates: dict) -> None:
        """Set validated session config values."""
        data = self.load_yaml()
        session = data.setdefault("session", {})
        if not isinstance(session, dict):
            raise ValueError("stored session config must be an object")
        session.update(_validate_session_config(updates))
        self.save_yaml(data)

    def get_recall_config(self) -> dict:
        """Get Recall/Top-N config dict with defaults."""
        data = self.load_yaml()
        recall = self._dict_section(data, "recall")

        defaults = {"limit": 10, "min_similarity": 0.0}
        defaults.update(recall)
        return defaults

    def set_recall_config(
        self, limit: int | None = None, min_similarity: float | None = None
    ) -> None:
        """Set Recall config values."""
        data = self.load_yaml()
        recall = self._dict_section(data, "recall", repair=True)
        if limit is not None:
            validate_recall_limit(limit)
            recall["limit"] = limit
        if min_similarity is not None:
            if (
                not isinstance(min_similarity, (int, float))
                or not 0.0 <= float(min_similarity) <= 1.0
            ):
                raise ValueError("min_similarity must be between 0.0 and 1.0")
            recall["min_similarity"] = min_similarity
        self.save_yaml(data)

    # Schedule timing

    def get_schedule_time(self) -> str:
        """Get daily summary + conflict time (HH:MM format)."""
        value = self.load_yaml().get("schedule_time")
        if isinstance(value, str) and value:
            return value
        return "23:55"

    def set_schedule_time(self, time_str: str) -> None:
        """Set daily summary + conflict time."""
        self.set("schedule_time", normalize_schedule_time(time_str))

    # Active session tracking — sourced from SessionService (~/.memanto/sessions/).
    # CLI and API server both go through here so they always agree.

    def get_active_session(self) -> tuple[str | None, str | None]:
        """Return (agent_id, session_token) for the active session, or (None, None)."""
        from memanto.app.services.session_service import get_session_service

        session = get_session_service().get_active_session()
        if session is None:
            return None, None
        return session.agent_id, session.session_token

    def clear_active_session(self) -> None:
        """Clear the active-session marker."""
        from memanto.app.services.session_service import get_session_service

        get_session_service().clear_active_session()

    def set_server_config(self, url: str, port: int) -> None:
        """Set fallback server configuration."""
        validated_port = _validate_server_port(port)
        data = self.load_yaml()
        server = self._dict_section(data, "server", repair=True)
        server["url"] = url
        server["port"] = validated_port
        self.save_yaml(data)

    def set_cli_config(self, interactive_mode: bool, smart_parse: bool) -> None:
        """Set fallback CLI configuration."""
        data = self.load_yaml()
        cli = self._dict_section(data, "cli", repair=True)
        cli["interactive_mode"] = interactive_mode
        cli["smart_parse"] = smart_parse
        self.save_yaml(data)

    # Connections registry — tracks which agents have memanto installed where.
    # Forward-only: only updated by future install/remove calls, not backfilled.

    def load_connections(self) -> dict:
        """Load the connections registry from ~/.memanto/connections.json."""
        if not self.connections_file.exists():
            return {}
        try:
            with open(self.connections_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_connections(self, data: dict) -> None:
        """Atomically write the connections registry."""
        atomic_write_text(
            self.connections_file,
            json.dumps(data, indent=2, sort_keys=True),
        )

    def add_connection(
        self, agent_name: str, project_dir: str | None, is_global: bool
    ) -> None:
        """Record that ``agent_name`` was installed at ``project_dir`` (or globally)."""
        self.connections_file.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self.connections_file) + ".lock")
        with lock:
            data = self.load_connections()
            entry = data.setdefault(
                agent_name, {"projects": [], "installed_global": False}
            )
            if is_global:
                entry["installed_global"] = True
            elif project_dir:
                abs_path = str(Path(project_dir).resolve())
                if abs_path not in entry["projects"]:
                    entry["projects"].append(abs_path)
            self._save_connections(data)

    def remove_connection(
        self, agent_name: str, project_dir: str | None, is_global: bool
    ) -> None:
        """Inverse of ``add_connection``."""
        self.connections_file.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self.connections_file) + ".lock")
        with lock:
            data = self.load_connections()
            if agent_name not in data:
                return
            entry = data[agent_name]
            if is_global:
                entry["installed_global"] = False
            elif project_dir:
                abs_path = str(Path(project_dir).resolve())
                entry["projects"] = [
                    p for p in entry.get("projects", []) if p != abs_path
                ]
            if not entry.get("projects") and not entry.get("installed_global"):
                del data[agent_name]
            self._save_connections(data)
