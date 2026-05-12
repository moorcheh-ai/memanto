"""
MEMANTO CLI Configuration Manager

Handles configuration persistence:
  - API key: stored in ~/.memanto/.env (sensitive, not committed)
  - Other config: stored in ~/.memanto/config.yaml (non-sensitive)
"""

import importlib
import os
from pathlib import Path

from dotenv import load_dotenv, set_key

yaml = importlib.import_module("yaml")


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

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

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
        # Ensure the file exists
        if not self.env_file.exists():
            self.env_file.write_text("# MEMANTO Environment\n")
        set_key(str(self.env_file), "MOORCHEH_API_KEY", api_key)
        os.environ["MOORCHEH_API_KEY"] = api_key

        # Secure permissions (owner-only)
        try:
            self.env_file.chmod(0o600)
        except OSError:
            pass  # Windows may not support chmod

    def is_configured(self) -> bool:
        """Check if CLI has an API key configured."""
        return self.get_api_key() is not None

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
        with open(self.config_file, "w") as f:
            yaml.dump({"memanto": data}, f, default_flow_style=False, sort_keys=False)
        try:
            self.config_file.chmod(0o600)
        except OSError:
            pass

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
        """Get MEMANTO server URL."""
        server = self.load_yaml().get("server", {})
        host = server.get("url", "localhost")
        port = server.get("port", 8000)
        return f"http://{host}:{port}"

    def get_server_config(self) -> dict:
        """Get server config dict with defaults."""
        defaults = {"url": "localhost", "port": 8000, "auto_start": False}
        defaults.update(self.load_yaml().get("server", {}))
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
        }
        defaults.update(self.load_yaml().get("session", {}))
        return defaults

    def get_cli_config(self) -> dict:
        """Get CLI behavior config dict with defaults."""
        defaults = {
            "interactive_mode": True,
            "smart_parse": True,
            "auto_title": True,
            "color_output": True,
        }
        defaults.update(self.load_yaml().get("cli", {}))
        return defaults

    def get_answer_config(self) -> dict:
        """Get Answer config dict with defaults."""
        data = self.load_yaml()
        answer = data.get("answer", {})

        defaults = {
            "model": "anthropic.claude-sonnet-4-6",
            "temperature": 0.7,
            "answer_limit": 15,
            "threshold": 0.01,
        }
        defaults.update(answer)
        return defaults

    def set_answer_config(
        self,
        model: str | None = None,
        temperature: float | None = None,
        answer_limit: int | None = None,
        threshold: float | None = None,
    ) -> None:
        """Set Answer config values."""
        data = self.load_yaml()
        answer = data.setdefault("answer", {})
        if model is not None:
            answer["model"] = model
        if temperature is not None:
            answer["temperature"] = temperature
        if answer_limit is not None:
            answer["answer_limit"] = answer_limit
        if threshold is not None:
            answer["threshold"] = threshold

        self.save_yaml(data)

    def get_recall_config(self) -> dict:
        """Get Recall/Top-N config dict with defaults."""
        data = self.load_yaml()
        recall = data.get("recall", {})

        defaults = {"limit": 10}
        defaults.update(recall)
        return defaults

    def set_recall_config(self, limit: int | None = None) -> None:
        """Set Recall config values."""
        data = self.load_yaml()
        recall = data.setdefault("recall", {})
        if limit is not None:
            recall["limit"] = limit
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
        self.set("schedule_time", time_str)

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
        data = self.load_yaml()
        if "server" not in data:
            data["server"] = {}
        data["server"]["url"] = url
        data["server"]["port"] = port
        self.save_yaml(data)

    def set_cli_config(self, interactive_mode: bool, smart_parse: bool) -> None:
        """Set fallback CLI configuration."""
        data = self.load_yaml()
        if "cli" not in data:
            data["cli"] = {}
        data["cli"]["interactive_mode"] = interactive_mode
        data["cli"]["smart_parse"] = smart_parse
        self.save_yaml(data)
