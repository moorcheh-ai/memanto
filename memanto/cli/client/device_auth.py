"""
Browser sign-in to Memanto Cloud (OAuth 2.0 device authorization grant shape).

The CLI asks for a code, the user approves it in the console, and the CLI
polls until it receives a device key. No key is ever typed or pasted.
``DeviceLogin`` exposes the start and poll steps separately so the local web
UI can run the same flow without blocking a request.
"""

import platform
import time
import webbrowser
from collections.abc import Callable
from typing import Any

import httpx

__all__ = ["DeviceLogin", "DeviceLoginError", "device_login"]

_TIMEOUT_SECONDS = 30.0
_EXPIRED = "The sign-in code expired. Run 'memanto login' again."


class DeviceLoginError(Exception):
    """Sign-in did not complete (denied, expired, limit reached, or server error)."""


class DeviceLogin:
    """One browser sign-in: ``start()`` once, then ``poll()`` until it returns a result."""

    def __init__(
        self, base_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        from memanto.app import __version__

        self._version = __version__
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
            headers={"User-Agent": f"memanto-cli/{__version__}"},
        )
        self.code: dict[str, Any] = {}
        self.interval = 5.0
        self.deadline = 0.0

    def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        try:
            return self._http.post(path, json=body)
        except httpx.TransportError as e:
            raise DeviceLoginError(f"Could not reach Memanto Cloud: {e}") from e

    def start(self) -> dict[str, Any]:
        """Ask for a sign-in code; returns the device-code response."""
        response = self._post(
            "/cli/device-code",
            {
                "client_name": "memanto-cli",
                "hostname": platform.node() or "unknown",
                "cli_version": self._version,
            },
        )
        if not response.is_success:
            raise DeviceLoginError(
                f"Memanto Cloud could not start sign-in (HTTP {response.status_code})."
            )
        self.code = response.json()
        self.interval = float(self.code.get("interval", 5))
        self.deadline = time.monotonic() + float(self.code.get("expires_in", 600))
        return self.code

    def poll(self) -> dict[str, Any] | None:
        """Check once; ``{api_key, user_email, plan}`` when approved, None while pending.

        Raises:
            DeviceLoginError: Denied, expired, or failed.
        """
        if time.monotonic() >= self.deadline:
            raise DeviceLoginError(_EXPIRED)
        response = self._post("/cli/token", {"device_code": self.code["device_code"]})
        if response.is_success:
            return dict(response.json())

        try:
            body = response.json()
        except ValueError:
            body = {}
        error = body.get("error") if isinstance(body, dict) else None
        if error == "authorization_pending":
            return None
        if error == "slow_down":
            self.interval += 5
            return None
        if error == "access_denied":
            raise DeviceLoginError("Sign-in was denied.")
        if error == "expired_token":
            raise DeviceLoginError(_EXPIRED)
        description = body.get("error_description") if isinstance(body, dict) else None
        raise DeviceLoginError(
            description or f"Sign-in failed (HTTP {response.status_code})."
        )

    def close(self) -> None:
        self._http.close()


def device_login(
    base_url: str,
    on_code: Callable[[dict[str, Any], bool], None],
    open_browser: Callable[[str], bool] = webbrowser.open,
    sleep: Callable[[float], None] = time.sleep,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Run browser sign-in and return ``{api_key, user_email, plan}``.

    Args:
        base_url: Memanto Cloud public API URL.
        on_code: Called once with the device-code response and whether a
            browser was opened, so the caller can print the code and URL.
        open_browser: Opens the approval page; returns False when no browser
            is available (e.g. over SSH).
        sleep: Wait between polls (injected for tests).
        transport: Optional httpx transport (tests inject a mock here).

    Raises:
        DeviceLoginError: Sign-in was denied, expired, or failed.
    """
    login = DeviceLogin(base_url, transport=transport)
    try:
        code = login.start()
        try:
            opened = bool(open_browser(code["verification_uri_complete"]))
        except Exception:
            opened = False
        on_code(code, opened)

        while True:
            sleep(login.interval)
            result = login.poll()
            if result is not None:
                return result
    finally:
        login.close()
