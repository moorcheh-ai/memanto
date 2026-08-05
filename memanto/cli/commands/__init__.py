"""
MEMANTO CLI Commands Package

Importing this module registers all CLI commands with the shared Typer app.
"""

# Import all command modules so their decorators register with the app/sub-apps.
# The order doesn't matter — each module decorates the shared app or sub-app
# instances from _shared.py.

from memanto.cli.commands import (
    agent,  # noqa: F401  (create, list, activate, deactivate, bootstrap)
    config_cmd,  # noqa: F401  (show)
    connect,  # noqa: F401  (all connect subcommands)
    core,  # noqa: F401  (main_callback, status, serve, ui)
    memory,  # noqa: F401  (remember, recall, answer, daily_summary, detect_conflicts, conflicts)
    memory_mgmt,  # noqa: F401  (export, sync)
    migrate,  # noqa: F401  (mem0/letta/supermemory → Memanto)
    schedule,  # noqa: F401  (enable, disable, status)
    session,  # noqa: F401  (info, extend)
)
