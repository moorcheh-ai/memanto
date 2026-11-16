"""
Desktop widget process: a small always-on-top Memanto mascot that opens a panel.

Started detached by ``memanto widget on``; run directly with
``python -m memanto.cli.widget``. Needs ``pywebview``, which ``widget on``
installs on first use so it is not a dependency of the memanto package.
"""

import os
import sys
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from memanto.cli.config.manager import ConfigManager
from memanto.cli.widget.api import COLLAPSED_SIZE, WidgetApi, work_area

__all__ = ["main", "lock_path", "pid_path"]

_HTML = Path(__file__).with_name("widget.html")
_MARGIN = 16

# Win32 constants for _style_windows_window.
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW = 0x00040000
_SW_HIDE = 0
_SW_SHOWNOACTIVATE = 4


def lock_path(cm: ConfigManager) -> Path:
    """Held for as long as a widget runs; tells ``on``/``off`` whether one is up."""
    return cm.config_dir / "widget.lock"


def pid_path(cm: ConfigManager) -> Path:
    """Pid of the running widget, for ``memanto widget off``."""
    return cm.config_dir / "widget.pid"


def _style_windows_window(window: Any) -> None:
    """Round the corners (Windows 11) and keep the widget off the taskbar."""
    import ctypes

    hwnd = window.native.Handle.ToInt32()
    corner = ctypes.c_int(_DWMWCP_ROUND)
    # Windows 10 has no rounded corners and rejects the attribute; it keeps square ones.
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        _DWMWA_WINDOW_CORNER_PREFERENCE,
        ctypes.byref(corner),
        ctypes.sizeof(corner),
    )
    user32 = ctypes.windll.user32
    ex_style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    user32.SetWindowLongW(
        hwnd, _GWL_EXSTYLE, (ex_style | _WS_EX_TOOLWINDOW) & ~_WS_EX_APPWINDOW
    )
    # The taskbar only re-reads the style when the window is shown again.
    user32.ShowWindow(hwnd, _SW_HIDE)
    user32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE)


def main() -> None:
    """Show the widget until it is closed or ``memanto widget off`` stops it."""
    import webview

    cm = ConfigManager()
    cm.config_dir.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path(cm)))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return  # a widget is already running

    pid_file = pid_path(cm)
    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")

        api = WidgetApi(cm)
        width, height = COLLAPSED_SIZE
        ax, ay, aw, ah = work_area(webview.screens[0])
        x = ax + aw - width - _MARGIN
        y = ay + ah - height - _MARGIN
        # Not transparent: on Windows pywebview only makes the web view
        # transparent, and the form behind it still paints a solid color.
        window = webview.create_window(
            "Memanto",
            html=_HTML.read_text(encoding="utf-8"),
            js_api=api,
            width=width,
            height=height,
            min_size=COLLAPSED_SIZE,
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            on_top=True,
            resizable=False,
            background_color="#5534a5",
        )
        assert window is not None  # create_window only returns None for a shared window
        api._window = window

        def on_shown() -> None:
            if sys.platform == "win32":
                _style_windows_window(window)
            # Windows creates the window at least ~118 logical px wide whatever
            # width was asked for; size and place it again once it exists.
            window.resize(width, height)
            window.move(x, y)

        window.events.shown += on_shown
        webview.start()
    finally:
        pid_file.unlink(missing_ok=True)
        lock.release()
