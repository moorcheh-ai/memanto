"""
Browser sign-in to Memanto Cloud (OAuth 2.0 device authorization grant shape).

The CLI asks for a code, the user approves it in the console, and the CLI
polls until it receives a device key. No key is ever typed or pasted.
"""

import platform
import time
import webbrowser
from collections.abc import Callable
from typing import Any

import httpx

__all__ = ["DeviceLoginError", "device_login"]

_TIMEOUT_SECONDS = 30.0


class DeviceLoginError(Exception):
    """Sign-in did not complete (denied, expired, limit reached, or server error)."""


def _post(http: httpx.Client, path: str, body: dict[str, Any]) -> httpx.Response:
    try:
        return http.post(path, json=body)
    except httpx.TransportError as e:
        raise DeviceLoginError(f"Could not reach Memanto Cloud: {e}") from e


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
    from memanto.app import __version__

    with httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=_TIMEOUT_SECONDS,
        transport=transport,
        headers={"User-Agent": f"memanto-cli/{__version__}"},
    ) as http:
        start = _post(
            http,
            "/cli/device-code",
            {
                "client_name": "memanto-cli",
                "hostname": platform.node() or "unknown",
                "cli_version": __version__,
            },
        )
        if not start.is_success:
            raise DeviceLoginError(
                f"Memanto Cloud could not start sign-in (HTTP {start.status_code})."
            )
        code = start.json()

        try:
            opened = bool(open_browser(code["verification_uri_complete"]))
        except Exception:
            opened = False
        on_code(code, opened)

        interval = float(code.get("interval", 5))
        deadline = time.monotonic() + float(code.get("expires_in", 600))
        while time.monotonic() < deadline:
            sleep(interval)
            response = _post(http, "/cli/token", {"device_code": code["device_code"]})
            if response.is_success:
                return dict(response.json())

            try:
                body = response.json()
            except ValueError:
                body = {}
            error = body.get("error") if isinstance(body, dict) else None
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error == "access_denied":
                raise DeviceLoginError("Sign-in was denied.")
            if error == "expired_token":
                raise DeviceLoginError(
                    "The sign-in code expired. Run 'memanto login' again."
                )
            description = (
                body.get("error_description") if isinstance(body, dict) else None
            )
            raise DeviceLoginError(
                description or f"Sign-in failed (HTTP {response.status_code})."
            )

    raise DeviceLoginError("The sign-in code expired. Run 'memanto login' again.")
