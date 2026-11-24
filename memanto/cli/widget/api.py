"""
Desktop widget backend, exposed to the widget page as ``window.pywebview.api``.

Uses the same client and session files as the CLI: ``build_client`` picks
``SdkClient`` (Memanto local) or ``HostedClient`` (Memanto Cloud), and the
active agent is the ``~/.memanto/sessions/active`` marker. Switching agents
here switches them for the CLI and every other in-process client too.
"""

import functools
import logging
import sys
from collections.abc import Callable
from typing import Any

from memanto.app.clients.backend import BACKEND_LABELS, Backend
from memanto.app.services.session_service import get_session_service
from memanto.cli.client.factory import build_client
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.config.manager import ConfigManager

__all__ = [
    "WidgetApi",
    "COLLAPSED_SIZE",
    "EXPANDED_SIZE",
    "panel_position",
    "tile_position",
    "work_area",
]

logger = logging.getLogger(__name__)

COLLAPSED_SIZE = (56, 56)
EXPANDED_SIZE = (340, 480)


Rect = tuple[int, int, int, int]  # x, y, width, height in logical pixels
Anchor = tuple[bool, bool]  # (right, bottom): which tile edges the panel keeps


def _reported(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Return ``{"error": message}`` instead of raising, so the page can show it."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # shown to the user in the widget
            return {"error": getattr(e, "message", None) or str(e) or type(e).__name__}

    return wrapper


def _live_memory_count(client: SdkClient, namespace: str | None) -> int | None:
    """The agent's memory count from Moorcheh, or None when it can't be read.

    Local agent metadata keeps ``memory_count`` at 0 forever (see the
    ``/agents`` routes), so it is read live, like the local UI does.
    """
    if not namespace:
        return None
    try:
        # The Moorcheh SDK has no single-namespace read, only list().
        listed = client._get_moorcheh().namespaces.list().get("namespaces", [])
        for ns in listed:
            if ns.get("namespace_name") == namespace:
                return int(ns["item_count"])
        return None
    except Exception as e:
        # The count is one stat among several; show "—" rather than fail the panel.
        logger.warning("Could not read memory count for %s: %s", namespace, e)
        return None


class WidgetApi:
    """Methods the widget page calls. Every call re-reads config and sessions."""

    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        client_factory: Callable[[ConfigManager], SdkClient] = build_client,
    ) -> None:
        self._cm = config_manager or ConfigManager()
        self._client_factory = client_factory
        self._window: Any = None
        self._anchor: Anchor = (True, True)

    def _client(self) -> SdkClient:
        """A client joined to the active session, like the CLI's ``get_client``."""
        client = self._client_factory(self._cm)
        session = get_session_service().get_active_session()
        if session is not None:
            client.agent_id = session.agent_id
            client.session_token = session.session_token
        return client

    # Reads

    @_reported
    def state(self) -> dict[str, Any]:
        """Backend, active agent with its stats, session time left, Cloud usage."""
        return self._state()

    def _state(self) -> dict[str, Any]:
        backend = self._cm.get_backend()
        client = self._client()
        session = get_session_service().get_active_session()

        agent = None
        session_info = None
        if session is not None:
            info = client.get_agent(session.agent_id)
            memory_count = info.get("memory_count")
            if backend != Backend.MEMANTO_CLOUD:
                memory_count = _live_memory_count(client, info.get("namespace"))
            agent = {
                "id": session.agent_id,
                "description": info.get("description") or "",
                "memory_count": memory_count,
                "session_count": info.get("session_count"),
                "last_session": info.get("last_session"),
            }
            session_info = {
                "expires_at": session.expires_at.isoformat(),
                "duration_seconds": int(
                    (session.expires_at - session.started_at).total_seconds()
                ),
                "remaining_seconds": max(
                    0, int(session.time_remaining().total_seconds())
                ),
            }

        account = None
        if backend == Backend.MEMANTO_CLOUD:
            account = client.get_account()  # type: ignore[attr-defined]

        return {
            "backend": backend.value,
            "backend_label": BACKEND_LABELS[backend],
            "agent": agent,
            "session": session_info,
            "account": account,
        }

    @_reported
    def agents(self) -> dict[str, Any]:
        """All agents, for the switcher."""
        listed = self._client().list_agents().get("agents", [])
        return {
            "agents": [
                {"id": a["agent_id"], "description": a.get("description") or ""}
                for a in listed
            ]
        }

    # Session

    @_reported
    def switch(self, agent_id: str) -> dict[str, Any]:
        """Make *agent_id* the active agent everywhere.

        Joins the agent's live session when it has one, so tools already using
        it stay signed in; otherwise activates it.
        """
        if get_session_service().join_session(agent_id) is None:
            self._client().activate_agent(agent_id)
        return self._state()

    @_reported
    def reset(self) -> dict[str, Any]:
        """Replace the active agent's session with a fresh one.

        In-process clients (CLI, hooks, MCP) read the new session on their next
        call; anything still holding the old token must activate again.
        """
        session = get_session_service().get_active_session()
        if session is None:
            raise ValueError("No active agent to reset.")
        self._client().activate_agent(session.agent_id)
        return self._state()

    # Chat

    @_reported
    def ask(self, question: str) -> dict[str, Any]:
        """Answer *question* from the active agent's memories."""
        session = get_session_service().get_active_session()
        if session is None:
            raise ValueError("Pick an agent first.")
        result = self._client().answer(session.agent_id, question)
        return {"answer": result.get("answer", "")}

    # Window

    def expand(self) -> None:
        """Grow from the mascot into the panel, opening toward the screen's
        free side so the panel never lands off-screen."""
        if self._window is None:
            return
        tile = (self._window.x, self._window.y, *COLLAPSED_SIZE)
        x, y, self._anchor = panel_position(
            tile, work_area(_screen_at(tile)), EXPANDED_SIZE
        )
        self._window.move(x, y)
        self._window.resize(*EXPANDED_SIZE)

    def collapse(self) -> None:
        """Shrink back to the mascot, at the panel corner it opened from."""
        if self._window is None:
            return
        panel = (self._window.x, self._window.y, *EXPANDED_SIZE)
        x, y = tile_position(panel, self._anchor, COLLAPSED_SIZE)
        self._window.resize(*COLLAPSED_SIZE)
        self._window.move(x, y)

    def quit(self) -> None:
        """Close the widget (same as ``memanto widget off``)."""
        if self._window is not None:
            self._window.destroy()


def panel_position(
    tile: Rect, area: Rect, size: tuple[int, int]
) -> tuple[int, int, Anchor]:
    """Where the panel goes when the tile at *tile* opens inside *area*.

    The panel grows away from the nearest screen edges: a tile in the right
    half keeps its right edge, one in the bottom half keeps its bottom edge.
    The result is then clamped so the whole panel stays inside *area*.
    """
    tx, ty, tw, th = tile
    ax, ay, aw, ah = area
    w, h = size
    right = tx + tw / 2 > ax + aw / 2
    bottom = ty + th / 2 > ay + ah / 2
    x = tx + tw - w if right else tx
    y = ty + th - h if bottom else ty
    x = max(ax, min(x, ax + aw - w))
    y = max(ay, min(y, ay + ah - h))
    return x, y, (right, bottom)


def tile_position(
    panel: Rect, anchor: Anchor, size: tuple[int, int]
) -> tuple[int, int]:
    """Where the tile goes when the panel collapses: the corner it grew from."""
    px, py, pw, ph = panel
    right, bottom = anchor
    w, h = size
    return (px + pw - w if right else px, py + ph - h if bottom else py)


def work_area(screen: Any) -> Rect:
    """The usable part of a pywebview *screen* (minus the taskbar on Windows)."""
    frame = screen.frame
    if sys.platform == "win32" and frame is not None:
        # WinForms Screen.WorkingArea, in the same logical pixels as the bounds.
        return frame.X, frame.Y, frame.Width, frame.Height
    return screen.x, screen.y, screen.width, screen.height


def _screen_at(tile: Rect) -> Any:
    """The screen holding the centre of *tile* (the first screen if none does)."""
    import webview

    cx, cy = tile[0] + tile[2] / 2, tile[1] + tile[3] / 2
    screens = webview.screens
    for s in screens:
        if s.x <= cx < s.x + s.width and s.y <= cy < s.y + s.height:
            return s
    return screens[0]
