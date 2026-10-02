"""Identify the AI coding tool behind a MEMANTO call.

Every memory operation reaches MEMANTO from *some* tool - Claude Code, Cursor,
Codex, an MCP client, or a bare shell. Sessions themselves come from
``SessionService``; this module answers only the other half of the question:
*which tool* is driving the session right now.

Identity arrives three ways, best first:

* ``MEMANTO_CLIENT`` in the environment, or an ``X-Memanto-Client`` header, set
  by something that knows exactly who it is.
* The MCP ``initialize`` handshake's ``clientInfo``, bound for the duration of
  a tool call.
* Environment markers a tool happens to leave behind (``CLAUDECODE``,
  ``CURSOR_TRACE_ID``, ...).

Detection is deliberately conservative: a marker has to be specific to one tool
before it earns a mapping here. Attributing a memory to the wrong tool is worse
than attributing it to nobody, because the Connections UI reads these labels
back as fact.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass, replace

# Environment markers that identify exactly one tool, checked in order. Each
# entry is (env var names, tool slug, display name); the slug matches the
# `agent_registry` name so the Connections UI can join on it directly.
_ENV_SIGNATURES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("CURSOR_TRACE_ID", "CURSOR_AGENT"), "cursor", "Cursor"),
    (("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"), "claude-code", "Claude Code"),
    (("CODEX_SANDBOX", "CODEX_HOME"), "codex", "Codex CLI"),
    (("WINDSURF_HOME", "WINDSURF_SESSION_ID"), "windsurf", "Windsurf"),
    (("GEMINI_CLI", "GEMINI_SANDBOX"), "gemini-cli", "Gemini CLI"),
    (("GOOSE_PROVIDER", "GOOSE_CONTEXT_STRATEGY"), "goose", "Goose"),
    (("OPENCODE", "OPENCODE_BIN_PATH"), "opencode", "OpenCode"),
    (("CLINE_SESSION_ID", "CLINE_HOME"), "cline", "Cline"),
    (("CONTINUE_GLOBAL_DIR",), "continue", "Continue"),
    (("PI_AGENT", "PI_SESSION_ID"), "pi", "Pi (coding agent)"),
    (("ANTIGRAVITY_HOME",), "antigravity", "Antigravity (Google)"),
)

# MCP clients name themselves freely in the initialize handshake. Fold the
# common spellings onto registry slugs so a Cursor MCP write and a Cursor CLI
# write land on the same connection instead of two lookalike rows.
_TOOL_ALIASES: dict[str, str] = {
    "claude-ai": "claude-code",
    "claude-code": "claude-code",
    "claude-desktop": "claude-desktop",
    "cursor": "cursor",
    "cursor-vscode": "cursor",
    "codex": "codex",
    "codex-cli": "codex",
    "windsurf": "windsurf",
    "visual-studio-code": "github-copilot",
    "vscode": "github-copilot",
    "gemini-cli": "gemini-cli",
    "goose": "goose",
    "opencode": "opencode",
    "cline": "cline",
    "continue": "continue",
    "roo": "roo",
    "roo-code": "roo",
    "augment": "augment",
}

UNKNOWN_TOOL = "unknown"


@dataclass(frozen=True)
class ClientIdentity:
    """Which tool called MEMANTO, and from where."""

    tool: str
    display: str
    project_dir: str | None = None

    @property
    def is_known(self) -> bool:
        return self.tool != UNKNOWN_TOOL


UNKNOWN_CLIENT = ClientIdentity(tool=UNKNOWN_TOOL, display="Unknown client")

# Set by the HTTP middleware and the MCP tool wrapper, which know the caller
# better than this process's own environment does. A ContextVar (not a module
# global) so concurrent requests in the API server cannot read each other's
# identity.
_current: ContextVar[ClientIdentity | None] = ContextVar(
    "memanto_client_identity", default=None
)

# The MEMANTO session an operation belongs to. Bound by the clients and routes,
# which have already validated the session token; the memory services below
# them only receive an agent_id and would otherwise have to re-read the session
# file on every write.
_current_session: ContextVar[str | None] = ContextVar(
    "memanto_session_id", default=None
)


def set_client(identity: ClientIdentity | None):
    """Bind *identity* to the current context; returns the reset token."""
    return _current.set(identity)


def reset_client(token) -> None:
    """Undo a previous :func:`set_client`."""
    _current.reset(token)


def set_memanto_session(session_id: str | None) -> None:
    """Record which MEMANTO session subsequent operations belong to.

    Deliberately fire-and-forget rather than a paired set/reset: a CLI process
    handles exactly one session, and in the API server each request runs in its
    own context copy, so there is nothing to leak into.
    """
    _current_session.set(session_id)


def get_memanto_session() -> str | None:
    """The MEMANTO session bound to this context, if any."""
    return _current_session.get()


def normalize_tool(raw: str | None) -> str:
    """Fold a free-text client name onto a registry slug."""
    if not raw:
        return UNKNOWN_TOOL
    token = "".join(
        ch if ch.isalnum() else "-" for ch in str(raw).strip().lower()
    ).strip("-")
    while "--" in token:
        token = token.replace("--", "-")
    if not token:
        return UNKNOWN_TOOL
    return _TOOL_ALIASES.get(token, token)


def display_for(tool: str) -> str:
    """Human label for a slug, preferring the agent registry's own wording."""
    try:
        from memanto.cli.connect.agent_registry import get_agent

        agent = get_agent(tool)
        if agent is not None:
            return agent.display_name
    except Exception:
        # The registry lives in the CLI package; the API server can run
        # without it importable. A title-cased slug is a fine fallback.
        pass
    return tool.replace("-", " ").title()


def client_from_tool(name: str) -> ClientIdentity:
    """Build an identity for a tool that named itself.

    An agent knows exactly what it is; environment sniffing only guesses. This
    is the path a ``--tool`` flag or an ``X-Memanto-Client`` header takes, and
    it is the only way tools that leave no distinctive environment marker can
    be attributed at all.
    """
    slug = normalize_tool(name)
    try:
        project_dir = os.getcwd()
    except OSError:
        project_dir = None
    return ClientIdentity(tool=slug, display=display_for(slug), project_dir=project_dir)


def detect_client() -> ClientIdentity:
    """Identify the tool behind this call.

    Never raises: an unidentified caller is a normal outcome, not an error.
    """
    bound = _current.get()
    if bound is not None:
        return bound

    try:
        project_dir = os.getcwd()
    except OSError:
        project_dir = None

    explicit = os.environ.get("MEMANTO_CLIENT", "").strip()
    if explicit:
        tool = normalize_tool(explicit)
        return ClientIdentity(
            tool=tool, display=display_for(tool), project_dir=project_dir
        )

    for env_names, tool, display in _ENV_SIGNATURES:
        if any(name in os.environ for name in env_names):
            return ClientIdentity(tool=tool, display=display, project_dir=project_dir)

    return replace(UNKNOWN_CLIENT, project_dir=project_dir)
