from __future__ import annotations

import re

_ENV_SECRET_RE = re.compile(
    r"""(?ix)
    (?:\bexport\s+)?
    \b(?P<name>[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASS|KEY)[A-Z0-9_]*)
    (?P<sep>\s*=\s*)
    (?P<quote>["']?)
    (?P<value>[^"'\s]+|[^"']+?)
    (?P=quote)
    (?=\s|$)
    """
)
_LOWER_PASSWORD_RE = re.compile(
    r"""(?ix)
    \b(?P<name>password|passwd|secret|token)
    (?P<sep>\s*=\s*)
    (?P<quote>["'])
    (?P<value>.*?)
    (?P=quote)
    """
)
_AUTH_BEARER_RE = re.compile(r"(?i)(Authorization:\s*Bearer\s+)[A-Za-z0-9._~+/=-]+")
_COMMON_TOKEN_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{16,}|sk-[A-Za-z0-9_-]{16,}|"
    r"mc_[A-Za-z0-9_-]{12,})\b"
)


def redact_secrets(text: str) -> str:
    """Redact common credential shapes before transcripts enter memory."""

    def replace_env(match: re.Match[str]) -> str:
        quote = match.group("quote")
        redacted = f"{quote}<redacted>{quote}" if quote else "<redacted>"
        return f"{match.group('name')}{match.group('sep')}{redacted}"

    def replace_lower(match: re.Match[str]) -> str:
        quote = match.group("quote")
        return f"{match.group('name')}{match.group('sep')}{quote}<redacted>{quote}"

    redacted = _ENV_SECRET_RE.sub(replace_env, text)
    redacted = _LOWER_PASSWORD_RE.sub(replace_lower, redacted)
    redacted = _AUTH_BEARER_RE.sub(r"\1<redacted>", redacted)
    return _COMMON_TOKEN_RE.sub("<redacted>", redacted)
