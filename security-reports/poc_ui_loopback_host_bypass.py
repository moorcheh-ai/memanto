#!/usr/bin/env python3
"""PoC: the UI loopback gate accepts a request whose Host header is not loopback.

Two gates answer the same question -- "did this request come from the local UI?"

  require_management_access  requires: loopback peer AND loopback Host AND not cross-site
  _require_local             requires: loopback peer AND not cross-site

A DNS-rebinding request satisfies everything ``_require_local`` checks: the
browser opens the connection from the loopback interface, so the peer address is
127.0.0.1, while the Host header still carries the attacker's hostname and no
Origin/Sec-Fetch-Site is attached (the browser believes it is same-origin).

This script feeds both gates that exact request shape and compares the verdicts.

Usage
-----
    python3 poc_ui_loopback_host_bypass.py

Exit codes
----------
0  unpatched -- the UI gate granted loopback trust to a request with a foreign Host.
1  patched -- the UI gate refused it (and still accepts genuine local requests).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ``require_management_access`` resolves the server credential, so the PoC needs
# *some* value configured. Any placeholder works; it is never compared here.
os.environ.setdefault("MOORCHEH_API_KEY", "poc-placeholder-not-a-real-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

from memanto.app.routes.auth_deps import require_management_access  # noqa: E402
from memanto.app.ui.routes.ui_router import _require_local  # noqa: E402


def request(peer: str, host_header: str | None, **extra_headers: str) -> MagicMock:
    req = MagicMock()
    req.client.host = peer
    headers = {}
    if host_header is not None:
        headers["host"] = host_header
    headers.update(extra_headers)
    req.headers = headers
    return req


def verdict(gate, req: MagicMock, *, is_async: bool) -> str:
    try:
        if is_async:
            asyncio.run(gate(req))
        else:
            gate(req, authorization=None, x_api_key=None)
    except HTTPException as exc:
        return f"refused (HTTP {exc.status_code})"
    except Exception as exc:  # pragma: no cover - surfaced for diagnosis
        return f"error ({type(exc).__name__}: {exc})"
    return "GRANTED"


def main() -> int:
    print("UI gate        = _require_local           (ui_router.py)")
    print("mgmt gate      = require_management_access (auth_deps.py)")
    print()

    cases = [
        (
            "rebinding   peer=127.0.0.1, Host=attacker.example:8000, no Origin",
            request("127.0.0.1", "attacker.example:8000"),
        ),
        (
            "rebinding   peer=127.0.0.1, Host=attacker.example (no port)",
            request("127.0.0.1", "attacker.example"),
        ),
        (
            "no Host     peer=127.0.0.1, header absent",
            request("127.0.0.1", None),
        ),
        (
            "legitimate  peer=127.0.0.1, Host=127.0.0.1:8000",
            request("127.0.0.1", "127.0.0.1:8000"),
        ),
        (
            "legitimate  peer=::ffff:127.0.0.1, Host=localhost:8000",
            request("::ffff:127.0.0.1", "localhost:8000"),
        ),
        (
            "cross-site  peer=127.0.0.1, Host=127.0.0.1:8000, Origin=evil",
            request(
                "127.0.0.1",
                "127.0.0.1:8000",
                origin="https://evil.example",
            ),
        ),
        (
            "remote      peer=203.0.113.10, Host=127.0.0.1:8000",
            request("203.0.113.10", "127.0.0.1:8000"),
        ),
    ]

    ui_verdicts = {}
    for label, req in cases:
        ui = verdict(_require_local, req, is_async=True)
        mgmt = verdict(require_management_access, req, is_async=False)
        ui_verdicts[label] = ui
        marker = "  <-- gate disagreement" if (ui == "GRANTED") != (mgmt == "GRANTED") else ""
        print(f"  {label}")
        print(f"      UI gate: {ui:<20} mgmt gate: {mgmt}{marker}")

    print()

    rebinding_labels = [label for label in ui_verdicts if label.startswith("rebinding")
                        or label.startswith("no Host")]
    granted = [label for label in rebinding_labels if ui_verdicts[label] == "GRANTED"]

    if granted:
        print(f"UNPATCHED: the UI gate granted loopback trust to {len(granted)} "
              "request(s) whose Host did not name a loopback interface.")
        print("Those requests reach /api/ui/browse, /api/ui/config, /api/ui/shutdown, ...")
        return 0

    print("PATCHED: the UI gate requires a loopback Host, and every legitimate "
          "local request is still accepted.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
