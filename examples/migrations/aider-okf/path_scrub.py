"""Bounded redaction of local user-home paths in publishable demo output."""

from __future__ import annotations

import re

_HOME_ROOT = r"(?:[A-Za-z]:\\Users\\[^\\\s\"']+|/(?:home|Users)/[^/\s\"']+)"
_QUOTED_HOME = re.compile(
    rf"(?P<quote>[\"'])(?P<path>{_HOME_ROOT}[^\"'\r\n]*)(?P=quote)"
)
_LINE_VALUE_HOME = re.compile(
    rf"(?m)(?P<prefix>^(?:\s*)|[=:][ \t]*)(?P<path>{_HOME_ROOT}[^\r\n]*?)"
    r"(?P<suffix>[ \t]*$)"
)
_HOME_TOKEN = re.compile(rf"{_HOME_ROOT}(?:(?:\\[ \t])|[^\s\"'<>|])*")


def scrub_home_paths(text: str) -> str:
    """Redact quoted, line-valued, ordinary, and escaped-space home paths.

    A literal-space path has no universal delimiter when embedded in prose. The
    line-value rule therefore consumes it only when it is the whole value after
    ``=``/``:`` or begins the line. Quoted paths and shell-style escaped spaces
    are safe to recognize anywhere.
    """

    text = _QUOTED_HOME.sub("<USER_HOME>", text)
    text = _LINE_VALUE_HOME.sub(
        lambda match: f"{match.group('prefix')}<USER_HOME>{match.group('suffix')}",
        text,
    )
    return _HOME_TOKEN.sub("<USER_HOME>", text)
