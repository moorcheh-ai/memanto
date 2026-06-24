"""
MEMANTO CLI - Welcome Banner Display

Beautiful startup display with Moorcheh blue-violet branding,
memory type taxonomy, and quick-start commands.
"""

import platform
import time

from rich.console import Console
from rich.live import Live
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from memanto.app.clients.backend import Backend
from memanto.cli.config.manager import ConfigManager
from memanto.cli.ui.theme import (
    BOLD_BRIGHT,
    BOLD_PRIMARY,
    PRIMARY,
)

MEMANTO_VERSION = "0.1.0"

# ASCII art logo — clean block Memanto
LOGO = r"""
          ███╗   ███╗ ███████╗ ███╗   ███╗  █████╗  ███╗   ██╗ ████████╗  ██████╗
 ▐▛██▜▌   ████╗ ████║ ██╔════╝ ████╗ ████║ ██╔══██╗ ████╗  ██║ ╚══██╔══╝ ██╔═══██╗
 ▌ ◈◈ ▐   ██╔████╔██║ █████╗   ██╔████╔██║ ███████║ ██╔██╗ ██║    ██║    ██║   ██║
 ▝▜██▛▘   ██║╚██╔╝██║ ██╔══╝   ██║╚██╔╝██║ ██╔══██║ ██║╚██╗██║    ██║    ██║   ██║
 ▌▌▘▝▐▐   ██║ ╚═╝ ██║ ███████╗ ██║ ╚═╝ ██║ ██║  ██║ ██║ ╚████║    ██║    ╚██████╔╝
 ▘    ▝   ╚═╝     ╚═╝ ╚══════╝ ╚═╝     ╚═╝ ╚═╝  ╚═╝ ╚═╝  ╚═══╝    ╚═╝     ╚═════╝
                            remember · recall · answer
""".strip("\n")

# Animation frames
ANT_WALK_1 = " ▌▌▘▝▐▐ "
ANT_WALK_2 = " ▘▌▌▐▐▝ "
EYES_NORMAL = "◈◈"
EYES_WINK = "-◈"

# All 13 MEMANTO memory types
MEMORY_TYPES = [
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "context",
    "observation",
    "commitment",
    "relationship",
    "error",
]


def print_logo() -> None:
    """Print the MEMANTO ASCII logo and tagline."""
    console = Console()
    console.print()

    # ── Logo ────────────────────────────────────────────────────────
    lines = LOGO.split("\n")

    with Live(console=console, refresh_per_second=10, transient=False) as live:
        # Quick 1-second animation (10 frames)
        for i in range(20):
            # Walking legs (alternates every frame)
            current_legs = ANT_WALK_2 if i % 2 == 0 else ANT_WALK_1
            # Winking eyes (winks on frame 5 and 6)
            current_eyes = EYES_WINK if i in [5, 6.15, 16] else EYES_NORMAL

            # Rebuild the logo lines
            anim_lines = list(lines)
            anim_lines[2] = anim_lines[2].replace(EYES_NORMAL, current_eyes)
            anim_lines[4] = anim_lines[4].replace(ANT_WALK_1, current_legs)

            logo_text = Text("\n".join(anim_lines), style=BOLD_PRIMARY)
            live.update(logo_text)
            time.sleep(0.1)

    # Tagline
    tagline = Text()
    tagline.append("  Your agents focus. Memanto remembers.\n", style="bold white")
    tagline.append("  powered by ", style="dim")
    tagline.append("moorcheh.ai", style=BOLD_PRIMARY)
    console.print(tagline)
    console.print()


def show_welcome_banner(config_manager: ConfigManager) -> None:
    """Render the full MEMANTO welcome banner to the console."""
    console = Console()

    # ── System ──────────────────────────────────────────────────────
    console.print(Rule("System", style=PRIMARY))
    py_ver = platform.python_version()
    os_name = platform.system()
    sys_line = Text()
    sys_line.append(f"  v{MEMANTO_VERSION}", style=BOLD_BRIGHT)
    sys_line.append("  ·  ", style="dim")
    sys_line.append(f"Python {py_ver}", style="white")
    sys_line.append("  ·  ", style="dim")
    sys_line.append(os_name, style="white")
    console.print(sys_line)
    console.print()

    # ── Status ──────────────────────────────────────────────────────
    console.print(Rule("Status", style=PRIMARY))

    has_key = config_manager.is_configured()
    config_manager.get_api_key()
    backend = config_manager.get_backend()

    status_table = Table(show_header=False, box=None, padding=(0, 2), show_edge=False)
    status_table.add_column("Label", style="dim", min_width=14)
    status_table.add_column("Value")

    # Backend
    status_table.add_row("  Backend", backend.value)
    if backend == Backend.ON_PREM:
        op = config_manager.get_onprem_config()
        status_table.add_row("  On-Prem URL", op.get("url", ""))
        status_table.add_row(
            "  Embedding", op.get("embedding_provider") or "[dim]—[/dim]"
        )
    elif has_key:
        status_table.add_row("  API Key", "[green]●[/green] configured")
    else:
        status_table.add_row("  API Key", "[red]●[/red] not configured")

    # Active Agent
    active_agent, _ = config_manager.get_active_session()
    if active_agent:
        status_table.add_row("  Agent", f"[green]●[/green] {active_agent} (active)")
    else:
        status_table.add_row("  Agent", "[dim]○[/dim] none")

    console.print(status_table)
    console.print()

    # ── Memory Types ────────────────────────────────────────────────
    console.print(Rule("Memory Types", style=PRIMARY))

    # Build 4-column rows of memory types
    cols = 4
    rows_text = []
    for i in range(0, len(MEMORY_TYPES), cols):
        chunk = MEMORY_TYPES[i : i + cols]
        row = Text("  ")
        for _j, mt in enumerate(chunk):
            row.append("◆ ", style=BOLD_PRIMARY)
            row.append(f"{mt:<14}", style="white")
        rows_text.append(row)

    for row in rows_text:
        console.print(row)
    console.print()

    # ── Quick Start ─────────────────────────────────────────────────
    console.print(Rule("Quick Start", style=PRIMARY))

    commands = [
        ("memanto agent create <agent_name_or_id>", "Create a new memanto agent"),
        ('memanto remember "..."', "Store a memory"),
        ('memanto recall "..."', "Search memories"),
        ('memanto answer "..."', "Ask a question (RAG)"),
        ("memanto connect list", "See agent integrations"),
        ("memanto connect <agent>", "Connect to an AI agent"),
        ("memanto ui", "Open the web dashboard UI"),
        ("memanto status", "Full dashboard"),
        ("memanto serve", "Start local REST API server"),
    ]

    cmd_table = Table(show_header=False, box=None, padding=(0, 1), show_edge=False)
    cmd_table.add_column("Cmd", style=BOLD_BRIGHT, min_width=28)
    cmd_table.add_column("Desc", style="dim")

    for cmd, desc in commands:
        cmd_table.add_row(f"  {cmd}", desc)

    console.print(cmd_table)
    console.print()

    # Note about server
    console.print("  [dim]Server is only needed for REST API endpoints.[/dim]")
    console.print(
        "  [dim]All CLI commands work directly without a running server.[/dim]"
    )
    console.print()

    # Footer
    console.print(
        f"  Run [{BOLD_PRIMARY}]memanto --help[/{BOLD_PRIMARY}] for all commands\n",
        style="dim",
    )
