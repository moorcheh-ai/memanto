"""Client for the Memanto Cloud Public API (memanto-cloud) and local device-code auth.

In Local MCP (``memanto/integrations/mcp``), signing in via the ``login`` tool
uses ``POST /cli/device-code`` and ``POST /cli/token`` on ``memanto-cloud``.
Because Local MCP runs directly on the user's machine, once the user approves
the code in the Memanto Console, the minted ``mk_...`` API key is automatically:
1. Set in ``os.environ["MEMANTO_API_KEY"]`` for the current MCP server process,
2. Saved to ``~/.memanto/.env``, and
3. Persisted to the user-level OS environment variable ``MEMANTO_API_KEY``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv, set_key
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    MemantoError,
    MemoryOperationError,
)

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_API_URL = "https://memanto-saas-public-gw-33wzz25k.ue.gateway.dev"
_AUTH_CACHE_TTL_SECONDS = 300.0
_MAX_AUTH_CACHE_ENTRIES = 512


class PublicApiUnauthorizedError(MemantoError):
    """Raised when an API key is missing or rejected by the Public API (/me)."""

    def __init__(
        self,
        message: str = (
            "Unauthorized: missing or invalid Memanto API key. Call the "
            "'login' tool to sign in via the browser and automatically set "
            "MEMANTO_API_KEY in your environment."
        ),
    ) -> None:
        super().__init__(message=message)


def hash_api_key(api_key: str) -> str:
    """Return a SHA-256 hex digest of an API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def load_local_env_api_key(env_file: Path | None = None) -> str | None:
    """Load MEMANTO_API_KEY / MOORCHEH_API_KEY from process env or ~/.memanto/.env."""
    for var in ("MEMANTO_API_KEY", "MOORCHEH_API_KEY"):
        val = os.environ.get(var, "").strip()
        if val and val != "__pending_local_login__":
            return val

    target = env_file or (Path.home() / ".memanto" / ".env")
    if target.exists():
        load_dotenv(target, override=False)
        for var in ("MEMANTO_API_KEY", "MOORCHEH_API_KEY"):
            val = os.environ.get(var, "").strip()
            if val and val != "__pending_local_login__":
                return val
    return None


def _set_os_user_env_var(name: str, value: str) -> bool:
    """Persist an environment variable at the OS user level (best-effort)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            try:
                import ctypes

                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                SMTO_ABORTIFHUNG = 0x0002
                result = ctypes.c_long()
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST,
                    WM_SETTINGCHANGE,
                    0,
                    "Environment",
                    SMTO_ABORTIFHUNG,
                    1000,
                    ctypes.byref(result),
                )
            except Exception:
                pass
            return True

        wrote_unix = False
        if sys.platform == "darwin":
            try:
                import subprocess

                subprocess.run(
                    ["launchctl", "setenv", name, value],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )
                wrote_unix = True
            except Exception:
                pass

        home = Path.home()
        export_line = f'export {name}="{value}"'
        for rc_name in (".zshrc", ".bashrc", ".profile"):
            rc_path = home / rc_name
            if not rc_path.exists():
                continue
            try:
                lines = rc_path.read_text(encoding="utf-8").splitlines()
                prefix = f"export {name}="
                replaced = False
                new_lines: list[str] = []
                for line in lines:
                    if line.strip().startswith(prefix):
                        new_lines.append(export_line)
                        replaced = True
                    else:
                        new_lines.append(line)
                if not replaced:
                    new_lines.append(export_line)
                rc_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                wrote_unix = True
            except Exception:
                pass
        return wrote_unix
    except Exception as exc:
        logger.debug("Could not persist user OS env var %s: %s", name, exc)
    return False


def persist_local_api_key(
    api_key: str,
    *,
    env_file: Path | None = None,
    set_os_env: bool = True,
) -> dict[str, Any]:
    """Automatically set MEMANTO_API_KEY in process env, ~/.memanto/.env, and OS user env."""
    clean_key = api_key.strip()
    os.environ["MEMANTO_API_KEY"] = clean_key
    os.environ.setdefault("MOORCHEH_API_KEY", clean_key)

    target = env_file or (Path.home() / ".memanto" / ".env")
    wrote_dotenv = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text("", encoding="utf-8")
        set_key(str(target), "MEMANTO_API_KEY", clean_key)
        wrote_dotenv = True
    except Exception as exc:
        logger.warning("Failed to write MEMANTO_API_KEY to %s: %s", target, exc)

    wrote_os_env = _set_os_user_env_var("MEMANTO_API_KEY", clean_key) if set_os_env else False
    return {
        "process_env": True,
        "dotenv_path": str(target) if wrote_dotenv else None,
        "os_user_env": wrote_os_env,
    }


class _AuthVerificationCache:
    """Bounded TTL cache for verified API keys via GET /me."""

    def __init__(
        self,
        ttl_seconds: float = _AUTH_CACHE_TTL_SECONDS,
        max_entries: int = _MAX_AUTH_CACHE_ENTRIES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, key_hash: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key_hash)
            if entry is None:
                return None
            expires_at, payload = entry
            if now >= expires_at:
                self._entries.pop(key_hash, None)
                return None
            return dict(payload)

    def put(self, key_hash: str, payload: dict[str, Any]) -> None:
        now = time.monotonic()
        with self._lock:
            if (
                key_hash not in self._entries
                and len(self._entries) >= self._max_entries
            ):
                expired = [k for k, (exp, _) in self._entries.items() if now >= exp]
                for k in expired:
                    self._entries.pop(k, None)
                if len(self._entries) >= self._max_entries:
                    oldest_key = min(
                        self._entries, key=lambda k: self._entries[k][0]
                    )
                    self._entries.pop(oldest_key, None)
            self._entries[key_hash] = (now + self._ttl, dict(payload))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_auth_cache = _AuthVerificationCache()


class _LocalDeviceAuthManager:
    """Manages local device-code sign-in and automatic MEMANTO_API_KEY env setup."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] | None = None

    def start(
        self,
        *,
        base_url: str = DEFAULT_PUBLIC_API_URL,
        client_name: str = "memanto-mcp",
        cli_version: str | None = None,
        open_browser: bool = True,
        env_file: Path | None = None,
    ) -> dict[str, Any]:
        hostname = socket.gethostname() or "local-mcp"
        status_code, data = CloudPublicApiClient.request_device_code(
            base_url=base_url,
            client_name=client_name,
            hostname=hostname,
            cli_version=cli_version,
        )
        if status_code != 200 or not data.get("device_code"):
            raise MemoryOperationError(
                f"Could not start device sign-in (HTTP {status_code})."
            )

        verify_url = str(
            data.get("verification_uri_complete")
            or data.get("verification_uri")
            or ""
        )
        interval = max(2, int(data.get("interval") or 5))
        expires_in = int(data.get("expires_in") or 600)
        now = time.monotonic()

        browser_opened = False
        if open_browser and verify_url and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                browser_opened = bool(webbrowser.open(verify_url))
            except Exception:
                browser_opened = False

        state: dict[str, Any] = {
            "device_code": str(data["device_code"]),
            "user_code": str(data.get("user_code") or ""),
            "verification_uri": str(data.get("verification_uri") or ""),
            "verification_uri_complete": verify_url,
            "interval": interval,
            "expires_at": now + expires_in,
            "last_poll_at": 0.0,
            "base_url": base_url,
            "env_file": env_file,
            "browser_opened": browser_opened,
            "status": "pending",
            "api_key": None,
            "user_email": None,
            "plan": None,
            "env_saved": None,
            "error": None,
        }
        with self._lock:
            self._state = state

        poller = threading.Thread(
            target=self._background_poll_loop,
            args=(state["device_code"],),
            daemon=True,
            name="memanto-mcp-device-poll",
        )
        poller.start()
        return dict(state)

    def _background_poll_loop(self, device_code: str) -> None:
        while True:
            with self._lock:
                current = self._state
                if (
                    current is None
                    or current.get("device_code") != device_code
                    or current.get("status") != "pending"
                ):
                    return
                wait_sec = max(5.0, float(current.get("interval") or 5))
            time.sleep(wait_sec)
            polled = self.poll_once(force=False)
            if polled is None or polled.get("status") != "pending":
                return

    def get_state(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._state) if self._state is not None else None

    def poll_once(self, *, force: bool = False) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            state = self._state
            if state is None:
                return None
            if state["status"] != "pending":
                return dict(state)
            if now >= float(state["expires_at"]):
                state["status"] = "expired"
                state["error"] = "This sign-in code expired. Run login again."
                return dict(state)
            min_gap = max(4.0, float(state.get("interval") or 5) - 0.5)
            if not force and (now - float(state["last_poll_at"]) < min_gap):
                return dict(state)
            state["last_poll_at"] = now
            device_code = str(state["device_code"])
            base_url = str(state["base_url"])
            env_file = state.get("env_file")

        try:
            status_code, data = CloudPublicApiClient.poll_device_token(
                device_code=device_code,
                base_url=base_url,
            )
        except Exception as exc:
            logger.debug("Device token poll transient error: %s", exc)
            with self._lock:
                return dict(self._state) if self._state else None

        with self._lock:
            state = self._state
            if state is None or state.get("device_code") != device_code:
                return dict(state) if state else None
            if status_code == 200 and isinstance(data, dict) and data.get("api_key"):
                api_key = str(data["api_key"]).strip()
                env_saved = persist_local_api_key(api_key, env_file=env_file)
                state["status"] = "approved"
                state["api_key"] = api_key
                state["user_email"] = data.get("user_email")
                state["plan"] = data.get("plan")
                state["env_saved"] = env_saved
            elif isinstance(data, dict):
                err = data.get("error")
                if err == "slow_down":
                    state["interval"] = float(state.get("interval") or 5) + 5.0
                elif err in ("expired_token", "access_denied", "device_limit"):
                    state["status"] = "failed"
                    state["error"] = (
                        data.get("error_description")
                        or data.get("message")
                        or str(err)
                    )
            return dict(state)

    def clear(self) -> None:
        with self._lock:
            self._state = None


local_login_manager = _LocalDeviceAuthManager()


class CloudPublicApiClient:
    """Stateless client that forwards MCP operations to the Memanto Public API (memanto-cloud)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_PUBLIC_API_URL,
        timeout: float = 30.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise PublicApiUnauthorizedError()
        self.api_key: str = api_key.strip()
        self.key_hash: str = hash_api_key(self.api_key)
        self.base_url: str = base_url.rstrip("/")
        self.timeout: float = timeout
        self.agent_id: str | None = None

    def _headers(self, source: str | None = None) -> dict[str, str]:
        headers = {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "memanto-mcp-local/1.0",
        }
        if source:
            headers["X-Memanto-Client"] = source
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(
                    method,
                    url,
                    headers=self._headers(source),
                    json=json_body,
                    params=params,
                )
        except httpx.RequestError as exc:
            raise MemoryOperationError(
                f"Failed to reach Memanto Public API at {self.base_url}: {exc}"
            ) from exc

        try:
            data = resp.json() if resp.text else {}
        except ValueError:
            data = {"message": resp.text}
        return resp.status_code, data

    @staticmethod
    def _extract_error_message(data: Any, fallback: str) -> str:
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, dict) and detail.get("message"):
                return str(detail["message"])
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
            for key in ("message", "error_description", "error"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return fallback

    @classmethod
    def request_device_code(
        cls,
        *,
        base_url: str = DEFAULT_PUBLIC_API_URL,
        client_name: str = "memanto-mcp",
        hostname: str = "local-mcp",
        cli_version: str | None = None,
        timeout: float = 15.0,
    ) -> tuple[int, dict[str, Any]]:
        """Start an unauthenticated device-code sign-in via ``POST /cli/device-code``."""
        url = f"{base_url.rstrip('/')}/cli/device-code"
        body: dict[str, Any] = {
            "client_name": client_name,
            "hostname": hostname,
        }
        if cli_version:
            body["cli_version"] = cli_version
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=body)
        except httpx.RequestError as exc:
            raise MemoryOperationError(
                f"Failed to reach Memanto Public API at {base_url}: {exc}"
            ) from exc
        try:
            data = resp.json() if resp.text else {}
        except ValueError:
            data = {"message": resp.text}
        return resp.status_code, data if isinstance(data, dict) else {}

    @classmethod
    def poll_device_token(
        cls,
        *,
        device_code: str,
        base_url: str = DEFAULT_PUBLIC_API_URL,
        timeout: float = 15.0,
    ) -> tuple[int, dict[str, Any]]:
        """Poll ``POST /cli/token`` until approved, returning ``{ api_key, user_email, plan }``."""
        url = f"{base_url.rstrip('/')}/cli/token"
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json={"device_code": device_code})
        except httpx.RequestError as exc:
            raise MemoryOperationError(
                f"Failed to reach Memanto Public API at {base_url}: {exc}"
            ) from exc
        try:
            data = resp.json() if resp.text else {}
        except ValueError:
            data = {"message": resp.text}
        return resp.status_code, data if isinstance(data, dict) else {}

    def verify_auth(self, *, use_cache: bool = True) -> dict[str, Any]:
        """Verify the API key against ``GET /me`` on the Memanto Public API."""
        if use_cache:
            cached = _auth_cache.get(self.key_hash)
            if cached is not None:
                return cached

        status, data = self._request("GET", "/me")
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(
                    data,
                    "Invalid or unauthorized Memanto API key (rejected by GET /me).",
                )
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(
                    data, f"Public API /me returned HTTP {status}"
                )
            )
        payload = data if isinstance(data, dict) else {"status": "ok"}
        _auth_cache.put(self.key_hash, payload)
        return payload

    def activate_agent(
        self, agent_id: str, duration_hours: int | None = None
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        self.agent_id = agent_id
        return {"agent_id": agent_id, "status": "ready"}

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        status, data = self._request(
            "GET",
            f"/agents/{enc}",
            params={"include_counts": "false"},
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on GET /agents/{id}")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"GET /agents/{agent_id} failed")
            )
        return data if isinstance(data, dict) else {"agent_id": agent_id}

    def create_agent(
        self,
        agent_id: str,
        pattern: str = "tool",
        description: str | None = None,
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        body: dict[str, Any] = {
            "agent_id": agent_id,
            "pattern": pattern,
        }
        if description is not None:
            body["description"] = description
        status, data = self._request("POST", "/agents", json_body=body)
        if status == 409:
            raise AgentAlreadyExistsError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on POST /agents")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"POST /agents failed ({status})")
            )
        return data if isinstance(data, dict) else {"agent_id": agent_id}

    def list_agents(self) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        status, data = self._request("GET", "/agents")
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on GET /agents")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"GET /agents failed ({status})")
            )
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {"agents": data, "count": len(data), "warnings": []}
        return {"agents": [], "count": 0, "warnings": []}

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        status, data = self._request("DELETE", f"/agents/{enc}")
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on DELETE /agents/{id}")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"DELETE /agents/{agent_id} failed")
            )
        return data if isinstance(data, dict) else {"status": "deleted", "agent_id": agent_id}

    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "agent",
        provenance: str = "explicit_statement",
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        body: dict[str, Any] = {
            "type": memory_type,
            "title": title,
            "content": content,
            "confidence": confidence,
            "tags": tags or [],
            "source": source,
            "provenance": provenance,
        }
        status, data = self._request(
            "POST", f"/agents/{enc}/remember", json_body=body, source=source
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on remember")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"remember failed ({status})")
            )
        return data if isinstance(data, dict) else {}

    def batch_remember(
        self,
        *,
        agent_id: str,
        memories: list[dict[str, Any]],
        source: str | None = None,
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        status, data = self._request(
            "POST",
            f"/agents/{enc}/batch-remember",
            json_body={"memories": memories},
            source=source,
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on batch-remember")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"batch-remember failed ({status})")
            )
        return data if isinstance(data, dict) else {}

    def recall(
        self,
        *,
        agent_id: str,
        query: str,
        limit: int | None = None,
        type: list[str] | str | None = None,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        min_similarity: float | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        body: dict[str, Any] = {"query": query}
        if limit is not None:
            body["limit"] = limit
        effective_type = type if type is not None else memory_type
        if effective_type:
            body["type"] = effective_type
        if tags is not None:
            body["tags"] = tags
        if min_confidence is not None:
            body["min_confidence"] = min_confidence
        if min_similarity is not None:
            body["min_similarity"] = min_similarity
        if source is not None:
            body["source"] = source

        status, data = self._request(
            "POST", f"/agents/{enc}/recall", json_body=body, source=source
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on recall")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"recall failed ({status})")
            )
        return data if isinstance(data, dict) else {"memories": []}

    def recall_recent(
        self,
        *,
        agent_id: str,
        limit: int | None = None,
        type: list[str] | str | None = None,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        body: dict[str, Any] = {}
        if limit is not None:
            body["limit"] = limit
        effective_type = type if type is not None else memory_type
        if effective_type:
            body["type"] = effective_type
        if tags is not None:
            body["tags"] = tags
        if min_confidence is not None:
            body["min_confidence"] = min_confidence
        if source is not None:
            body["source"] = source

        status, data = self._request(
            "POST", f"/agents/{enc}/recall/recent", json_body=body, source=source
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on recall/recent")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"recall/recent failed ({status})")
            )
        return data if isinstance(data, dict) else {"memories": []}

    def recall_as_of(
        self,
        *,
        agent_id: str,
        as_of: str,
        query: str | None = None,
        limit: int | None = None,
        type: list[str] | str | None = None,
        memory_type: str | None = None,
        min_confidence: float | None = None,
        min_similarity: float | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        body: dict[str, Any] = {"as_of": as_of}
        if query is not None:
            body["query"] = query
        if limit is not None:
            body["limit"] = limit
        effective_type = type if type is not None else memory_type
        if effective_type:
            body["type"] = effective_type
        if min_confidence is not None:
            body["min_confidence"] = min_confidence
        if min_similarity is not None:
            body["min_similarity"] = min_similarity
        if source is not None:
            body["source"] = source

        status, data = self._request(
            "POST", f"/agents/{enc}/recall/as-of", json_body=body, source=source
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on recall/as-of")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"recall/as-of failed ({status})")
            )
        return data if isinstance(data, dict) else {"memories": []}

    def recall_changed_since(
        self,
        *,
        agent_id: str,
        since: str,
        query: str | None = None,
        limit: int | None = None,
        type: list[str] | str | None = None,
        memory_type: str | None = None,
        min_confidence: float | None = None,
        min_similarity: float | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        body: dict[str, Any] = {"since": since}
        if query is not None:
            body["query"] = query
        if limit is not None:
            body["limit"] = limit
        effective_type = type if type is not None else memory_type
        if effective_type:
            body["type"] = effective_type
        if min_confidence is not None:
            body["min_confidence"] = min_confidence
        if min_similarity is not None:
            body["min_similarity"] = min_similarity
        if source is not None:
            body["source"] = source

        status, data = self._request(
            "POST",
            f"/agents/{enc}/recall/changed-since",
            json_body=body,
            source=source,
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(
                    data, "Unauthorized on recall/changed-since"
                )
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(
                    data, f"recall/changed-since failed ({status})"
                )
            )
        return data if isinstance(data, dict) else {"memories": []}

    def answer(
        self,
        *,
        agent_id: str,
        question: str,
        limit: int | None = None,
        temperature: float | None = None,
        kiosk_mode: bool | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        self.verify_auth(use_cache=True)
        enc = quote(agent_id, safe="")
        body: dict[str, Any] = {"question": question}
        if limit is not None:
            body["limit"] = limit
        if temperature is not None:
            body["temperature"] = temperature
        if kiosk_mode is not None:
            body["kiosk_mode"] = kiosk_mode

        status, data = self._request(
            "POST", f"/agents/{enc}/answer", json_body=body, source=source
        )
        if status == 404:
            raise AgentNotFoundError(agent_id)
        if status in (401, 403):
            raise PublicApiUnauthorizedError(
                self._extract_error_message(data, "Unauthorized on answer")
            )
        if status >= 400:
            raise MemoryOperationError(
                self._extract_error_message(data, f"answer failed ({status})")
            )
        return data if isinstance(data, dict) else {}
