"""
MEMANTO CLI Package

Command-line interface for MEMANTO V2 API
"""

import sys


def _ensure_utf8_streams() -> None:
    """Make redirected output UTF-8 so Rich glyphs cannot crash the CLI.

    Rich emits box-drawing characters, bullets, em-dashes and braille spinner
    frames. When stdout is redirected on Windows, Python encodes it with the
    locale code page (cp1252 on most installs), which cannot represent any of
    them, so the command dies mid-run with UnicodeEncodeError. That hits every
    caller which captures the CLI: shell pipelines, CI logs, `> file`, and agent
    harnesses such as Claude Code.

    The encoding is the only thing worth testing. `isatty()` is not a usable
    discriminator here: on Windows, `NUL` reports itself as a character device,
    so `command > NUL` is a tty by that measure while still encoding as cp1252.
    A console that already reports UTF-8 is left untouched.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            encoding = (stream.encoding or "").lower().replace("-", "").replace("_", "")
            if encoding == "utf8":
                continue
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # Stream setup must never stop the CLI from starting.
            pass


_ensure_utf8_streams()
