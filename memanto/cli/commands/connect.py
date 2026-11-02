"""
MEMANTO CLI - Connect commands (agent integrations).
"""

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from memanto.app.clients.backend import Backend
from memanto.cli.commands._shared import (
    AGENT_REGISTRY,
    BOLD_PRIMARY,
    BRIGHT,
    PRIMARY,
    SUCCESS,
    _error,
    _warn,
    config_manager,
    connect_app,
    console,
    detect_agents_in_project,
    detect_memanto_installed,
    detect_memanto_installed_global,
    get_client,
    install_agent,
    list_agents,
    remove_agent,
)
from memanto.cli.config.manager import MEMANTO_CONSOLE_URL

DEFAULT_AGENT_ID = "my-agent"


def _ensure_signed_in() -> None:
    """With no backend configured yet, sign in to Memanto Cloud before connecting."""
    if config_manager.is_configured():
        return
    from memanto.cli.commands.auth import sign_in

    console.print("Not signed in yet. Signing in to Memanto Cloud first.\n")
    sign_in()
    console.print()


def _activate_for_hooks(agent_id: str, replace_active: bool) -> None:
    """Make *agent_id* the active agent, which the session-start hook syncs from.

    Leaves an existing active agent alone unless *replace_active* is set.
    """
    active_agent_id, _ = config_manager.get_active_session()
    if active_agent_id == agent_id or (active_agent_id and not replace_active):
        return
    try:
        get_client().activate_agent(agent_id)
        console.print(f"[dim]Active agent: {agent_id}[/dim]")
    except Exception as e:
        _warn(f"Could not activate agent '{agent_id}': {e}")


def _print_install_result(result: dict, scope_label: str) -> None:
    """Pretty-print the result of an install_agent call."""
    steps = result["steps"]
    errors = result["errors"]

    if errors:
        for err in errors:
            console.print(f"  [red]✗[/red] {err}")
    if steps:
        for step in steps:
            console.print(f"  [green]✓[/green] {step}")
    if not errors and not steps:
        console.print("  [dim]Nothing to do[/dim]")


def _run_connect_for_agent(
    agent_name: str, project_dir: str, is_global: bool, mcp_agent_id: str | None = None
) -> None:
    """Run connect for a single agent with full UI output."""
    agent = AGENT_REGISTRY.get(agent_name)
    if not agent:
        _error(
            f"Unknown agent: {agent_name}",
            hint="Run 'memanto connect list' to see available agents.",
        )
    _ensure_signed_in()

    if is_global:
        scope_label = f"Global (~/{agent.config_global_dir or ''})"
    else:
        path_obj = Path(project_dir).resolve()
        # Prevent treating the user's home directory as a local project
        if path_obj == Path.home().resolve():
            _error(
                "Cannot install as a local project in your home directory.",
                hint="Use the --global / -g flag instead to install globally.",
            )
        scope_label = str(path_obj)

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]Connect to {agent.display_name}[/{BOLD_PRIMARY}]\n"
            f"{'Scope' if is_global else 'Project'}: [bold]{scope_label}[/bold]",
            border_style=PRIMARY,
        )
    )

    result = install_agent(
        agent_name, project_dir, is_global, mcp_agent_id=mcp_agent_id
    )
    _print_install_result(result, scope_label)

    # Summary
    scope_info = "globally (all projects)" if is_global else f"in {scope_label}"
    steps = result["steps"]
    errors = result["errors"]

    if not errors:
        console.print()
        # Build summary lines
        summary_parts = [
            f"[bold green]{agent.display_name} integration complete![/bold green]\n"
        ]
        summary_parts.append(f"[dim]Scope:[/dim] {scope_info}")
        for step in steps:
            summary_parts.append(f"[dim]•[/dim] {step}")

        if not agent.supports_hooks:
            summary_parts.append(
                "\n[dim]Tip: Run 'memanto memory sync --project-dir .' before\n"
                "starting a session to pre-populate MEMORY.md.[/dim]"
            )

        summary_parts.append(
            f"\nOpen a new {agent.display_name} session to start using Memanto."
        )

        console.print(
            Panel(
                "\n".join(summary_parts), title="Setup Complete", border_style=SUCCESS
            )
        )
        if mcp_agent_id:
            _activate_for_hooks(mcp_agent_id, replace_active=False)
    else:
        console.print(f"\n[yellow]Completed with {len(errors)} error(s)[/yellow]")


# Individual agent connect commands


@connect_app.command("update")
def update_templates(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
):
    """Update all active Memanto agent instructions (both local and global) to the latest version."""
    from memanto.cli.connect.updater import update_all_agents

    messages = update_all_agents(project_dir, update_global=True, update_local=True)

    # Filter out empty state messages if we successfully updated at least one thing
    has_success = any("Successfully updated" in m for m in messages)
    if has_success:
        messages = [
            m for m in messages if "No active Memanto integrations found" not in m
        ]

    # Deduplicate messages while preserving order
    seen = set()
    deduped = []
    for m in messages:
        if m not in seen:
            seen.add(m)
            deduped.append(m)

    for msg in deduped:
        console.print(msg)


@connect_app.command("claude-code")
def connect_claude_code(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.claude/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Claude Code.

    Examples:
        memanto connect claude-code
        memanto connect claude-code --project-dir ./my-project
        memanto connect claude-code --global
        memanto connect claude-code --agent-id my-project-assistant
    """
    _run_connect_for_agent("claude-code", project_dir, is_global, mcp_agent_id)


@connect_app.command("codex")
def connect_codex(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.codex/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to OpenAI Codex CLI.

    Examples:
        memanto connect codex
        memanto connect codex --project-dir ./my-project
        memanto connect codex --global
    """
    _run_connect_for_agent("codex", project_dir, is_global, mcp_agent_id)


@connect_app.command("pi")
def connect_pi(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.pi/agent/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Pi (coding agent).

    Adds MEMANTO instructions to AGENTS.md, deploys the skill, and installs a
    Pi extension that auto-syncs MEMORY.md on each fresh session start.

    Examples:
        memanto connect pi
        memanto connect pi --project-dir ./my-project
        memanto connect pi --global
    """
    _run_connect_for_agent("pi", project_dir, is_global, mcp_agent_id)


@connect_app.command("cursor")
def connect_cursor(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.cursor/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Cursor IDE.

    Creates a .cursor/rules/memanto.mdc rule file and deploys the skill.

    Examples:
        memanto connect cursor
        memanto connect cursor --global
        memanto connect cursor --agent-id cursor-workspace
    """
    _run_connect_for_agent("cursor", project_dir, is_global, mcp_agent_id)


@connect_app.command("windsurf")
def connect_windsurf(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Windsurf IDE.

    Appends MEMANTO instructions to .windsurfrules and deploys the skill.

    Examples:
        memanto connect windsurf
        memanto connect windsurf --global
        memanto connect windsurf --agent-id windsurf-workspace
    """
    _run_connect_for_agent("windsurf", project_dir, is_global, mcp_agent_id)


@connect_app.command("antigravity")
def connect_antigravity(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Google Antigravity.

    Deploys the memanto-memory skill to .agent/skills/.

    Examples:
        memanto connect antigravity
        memanto connect antigravity --global
    """
    _run_connect_for_agent("antigravity", project_dir, is_global, mcp_agent_id)


@connect_app.command("gemini-cli")
def connect_gemini_cli(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.gemini/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Google Gemini CLI.

    Adds MEMANTO instructions to GEMINI.md and deploys the skill.

    Examples:
        memanto connect gemini-cli
        memanto connect gemini-cli --global
    """
    _run_connect_for_agent("gemini-cli", project_dir, is_global, mcp_agent_id)


@connect_app.command("cline")
def connect_cline(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Cline VS Code extension.

    Creates a .clinerules/memanto.md instruction file and deploys the skill.

    Examples:
        memanto connect cline
        memanto connect cline --global
        memanto connect cline --agent-id cline-workspace
    """
    _run_connect_for_agent("cline", project_dir, is_global, mcp_agent_id)


@connect_app.command("continue")
def connect_continue(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.continue/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Continue.dev.

    Creates a .continue/rules/memanto.md instruction file and deploys the skill.

    Examples:
        memanto connect continue
        memanto connect continue --global
        memanto connect continue --agent-id continue-workspace
    """
    _run_connect_for_agent("continue", project_dir, is_global, mcp_agent_id)


@connect_app.command("opencode")
def connect_opencode(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to OpenCode CLI.

    Adds MEMANTO instructions to AGENTS.md and deploys the skill.

    Examples:
        memanto connect opencode
        memanto connect opencode --global
    """
    _run_connect_for_agent("opencode", project_dir, is_global, mcp_agent_id)


@connect_app.command("goose")
def connect_goose(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Goose AI agent.

    Deploys the memanto-memory skill to .goose/skills/.

    Examples:
        memanto connect goose
        memanto connect goose --global
    """
    _run_connect_for_agent("goose", project_dir, is_global, mcp_agent_id)


@connect_app.command("roo")
def connect_roo(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.roo/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Roo Code.

    Creates a .roo/rules/memanto.md instruction file and deploys the skill.

    Examples:
        memanto connect roo
        memanto connect roo --global
        memanto connect roo --agent-id roo-workspace
    """
    _run_connect_for_agent("roo", project_dir, is_global, mcp_agent_id)


@connect_app.command("github-copilot")
def connect_github_copilot(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to GitHub Copilot.

    Adds MEMANTO instructions to .github/copilot-instructions.md and deploys the skill.

    Examples:
        memanto connect github-copilot
        memanto connect github-copilot --global
    """
    _run_connect_for_agent("github-copilot", project_dir, is_global, mcp_agent_id)


@connect_app.command("augment")
def connect_augment(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Install globally to ~/.augment/"
    ),
    mcp_agent_id: str | None = typer.Option(
        None, "--agent-id", "-a", help="Default Memanto agent ID to use for MCP"
    ),
):
    """Connect MEMANTO to Augment Code.

    Creates an .augment/rules/memanto.md instruction file and deploys the skill.

    Examples:
        memanto connect augment
        memanto connect augment --global
    """
    _run_connect_for_agent("augment", project_dir, is_global, mcp_agent_id)


# Connect List


@connect_app.command("list")
def connect_list(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Project directory to check"
    ),
):
    """List all supported agents and their MEMANTO installation status.

    Shows which agents are available, detected in the project, and which
    have MEMANTO installed (locally and globally).

    Examples:
        memanto connect list
        memanto connect list --project-dir ./my-project
    """
    project_path = Path(project_dir).resolve()

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]MEMANTO Agent Integrations[/{BOLD_PRIMARY}]\n"
            f"Project: [bold]{project_path}[/bold]",
            border_style=PRIMARY,
        )
    )
    console.print()

    detected = {a.name for a in detect_agents_in_project(project_path)}
    installed_local = {a.name for a in detect_memanto_installed(project_path)}
    installed_global = {a.name for a in detect_memanto_installed_global()}

    table = Table(show_header=True, header_style=BOLD_PRIMARY)
    table.add_column("Agent Name", style=PRIMARY)
    table.add_column("Detected", justify="center", width=10)
    table.add_column("Local", justify="center", width=10)
    table.add_column("Global", justify="center", width=10)
    table.add_column("Instruction File", style="dim")

    for agent in list_agents():
        is_detected = agent.name in detected
        is_local = agent.name in installed_local
        is_global = agent.name in installed_global

        det_icon = "[green]●[/green]" if is_detected else "[dim]○[/dim]"
        local_icon = "[green]●[/green]" if is_local else "[dim]○[/dim]"
        global_icon = "[green]●[/green]" if is_global else "[dim]○[/dim]"

        table.add_row(
            agent.name,
            det_icon,
            local_icon,
            global_icon,
            agent.instruction_local_file
            or agent.instruction_global_file
            or "[dim]skills only[/dim]",
        )

    console.print(table)
    console.print()

    total_local = len(installed_local)
    total_global = len(installed_global)
    console.print(
        f"[dim]Local installs: {total_local} | Global installs: {total_global}[/dim]"
    )
    console.print("[dim]Connect an agent: memanto connect <agent-name>[/dim]")
    console.print("[dim]Interactive mode: memanto connect multi[/dim]")


# Connect Remove


@connect_app.command("remove")
def connect_remove(
    agent_name: str | None = typer.Argument(
        None, help="Agent to disconnect (e.g. claude-code, cursor)"
    ),
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Project directory"
    ),
    is_global: bool = typer.Option(
        False, "--global", "-g", help="Remove from global scope"
    ),
    all_agents: bool = typer.Option(
        False, "--all", help="Remove MEMANTO from all agents"
    ),
):
    """Remove MEMANTO integration from an agent.

    Examples:
        memanto connect remove claude-code
        memanto connect remove cursor --global
        memanto connect remove --all
    """
    if all_agents:
        "globally" if is_global else f"in {Path(project_dir).resolve()}"
        agents_to_remove = [a.name for a in list_agents()]
    elif agent_name:
        if agent_name not in AGENT_REGISTRY:
            _error(
                f"Unknown agent: {agent_name}",
                hint="Run 'memanto connect list' for available agents.",
            )
        agents_to_remove = [agent_name]
    else:
        _error(
            "Specify an agent name or use --all.",
            hint="Run 'memanto connect remove <agent>' or 'memanto connect remove --all'.",
        )

    removed_count = 0
    for name in agents_to_remove:
        result = remove_agent(name, project_dir, is_global)
        steps = result["steps"]
        errors = result["errors"]
        if steps:
            display_name = AGENT_REGISTRY[name].display_name
            console.print(f"[green]✓[/green] {display_name}")
            for step in steps:
                console.print(f"  [dim]{step}[/dim]")
            removed_count += 1
        for err in errors:
            console.print(f"[red]✗[/red] {err}")

    if removed_count == 0:
        console.print("[dim]No MEMANTO installations found to remove.[/dim]")
    else:
        console.print(f"\n[green]Removed MEMANTO from {removed_count} agent(s)[/green]")


# Interactive Connect Setup


@connect_app.command("multi")
def connect_multi(
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
):
    """Interactive setup — select multiple agents to connect.

    Auto-detects which agents are present in your project and lets you
    choose which ones to connect MEMANTO to.

    Examples:
        memanto connect setup
        memanto connect setup --global
        memanto connect setup --project-dir ./my-project
    """
    project_path = Path(project_dir).resolve()

    console.print(
        Panel.fit(
            f"[{BOLD_PRIMARY}]MEMANTO Connect — Interactive Setup[/{BOLD_PRIMARY}]\n"
            f"{'Scope: Global' if is_global else f'Project: {project_path}'}",
            border_style=PRIMARY,
        )
    )
    console.print()

    all_agents = list_agents()
    detected = {a.name for a in detect_agents_in_project(project_path)}

    if is_global:
        installed = {a.name for a in detect_memanto_installed_global()}
    else:
        installed = {a.name for a in detect_memanto_installed(project_path)}

    # Show menu
    console.print(f"[{BOLD_PRIMARY}]Available Agents:[/{BOLD_PRIMARY}]")
    console.print()

    for i, agent in enumerate(all_agents, 1):
        status_parts = []
        if agent.name in detected:
            status_parts.append("[green]detected[/green]")
        if agent.name in installed:
            status_parts.append("[cyan]installed[/cyan]")
        status = f" ({', '.join(status_parts)})" if status_parts else ""
        console.print(
            f"  [{BRIGHT}]{i:2d}[/{BRIGHT}]. {agent.display_name:<22s}{status}"
        )

    console.print()
    console.print("[dim]Enter agent numbers separated by commas (e.g. 1,3,5)[/dim]")
    console.print(
        "[dim]Or type 'all' to install all, 'detected' for detected only[/dim]"
    )
    console.print()

    choice = typer.prompt("Select agents").strip().lower()

    if choice == "all":
        selected = [a.name for a in all_agents]
    elif choice == "detected":
        selected = list(detected)
        if not selected:
            console.print("[yellow]No agents detected in this project.[/yellow]")
            raise typer.Exit(0)
    elif choice == "q" or choice == "quit":
        raise typer.Exit(0)
    else:
        # Parse comma-separated numbers
        selected = []
        for part in choice.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(all_agents):
                    selected.append(all_agents[idx].name)
                else:
                    console.print(f"[yellow]Skipping invalid number: {part}[/yellow]")
            elif part in AGENT_REGISTRY:
                selected.append(part)
            else:
                console.print(f"[yellow]Skipping unknown: {part}[/yellow]")

    if not selected:
        console.print("[yellow]No agents selected.[/yellow]")
        raise typer.Exit(0)

    console.print()
    console.print(
        f"[{BOLD_PRIMARY}]Installing to {len(selected)} agent(s)...[/{BOLD_PRIMARY}]"
    )
    console.print()

    success_count = 0
    error_count = 0

    for name in selected:
        agent = AGENT_REGISTRY[name]
        result = install_agent(name, project_dir, is_global)
        steps = result["steps"]
        errors = result["errors"]

        if errors:
            console.print(f"  [red]✗[/red] {agent.display_name}")
            for err in errors:
                console.print(f"    [red]{err}[/red]")
            error_count += 1
        else:
            step_summary = ", ".join(steps) if steps else "no changes needed"
            console.print(f"  [green]✓[/green] {agent.display_name} — {step_summary}")
            success_count += 1

    console.print()
    scope_label = "globally" if is_global else f"in {project_path}"
    console.print(
        Panel(
            f"[bold green]Connected {success_count} agent(s) {scope_label}![/bold green]"
            + (f"\n[yellow]{error_count} error(s)[/yellow]" if error_count else "")
            + "\n\n[dim]Run 'memanto connect list' to see all installations[/dim]"
            + "\n[dim]Run 'memanto memory sync --project-dir .' to populate MEMORY.md[/dim]",
            title="Done",
            border_style=SUCCESS,
        )
    )


# `memanto connect` with no tool: sign in, pick tools and an agent, connect.


def _choose_tools(project_path: Path, assume_yes: bool) -> list[str]:
    """Pick tools to connect; tools detected in the project are pre-selected."""
    all_tools = list_agents()
    detected = [a.name for a in detect_agents_in_project(project_path)]
    if assume_yes:
        if not detected:
            _error(
                "No coding tools detected in this project.",
                hint="Name one instead, e.g. 'memanto connect claude-code'.",
            )
        return detected

    console.print(f"[{BOLD_PRIMARY}]Which tools should use Memanto?[/{BOLD_PRIMARY}]")
    for i, tool in enumerate(all_tools, 1):
        mark = "[green]x[/green]" if tool.name in detected else " "
        note = " [dim](detected)[/dim]" if tool.name in detected else ""
        console.print(
            f"  \\[{mark}] [{BRIGHT}]{i:2d}[/{BRIGHT}]. {tool.display_name}{note}"
        )
    default = ",".join(str(i) for i, t in enumerate(all_tools, 1) if t.name in detected)
    console.print("[dim]Numbers separated by commas, or 'all'.[/dim]")
    choice = typer.prompt("Tools", default=default or None).strip().lower()

    if choice == "all":
        return [t.name for t in all_tools]
    selected: list[str] = []
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= len(all_tools):
            selected.append(all_tools[int(part) - 1].name)
        elif part in AGENT_REGISTRY:
            selected.append(part)
        elif part:
            console.print(f"[yellow]Skipping unknown choice: {part}[/yellow]")
    return list(dict.fromkeys(selected))


def _choose_agent(assume_yes: bool) -> str:
    """Pick the Memanto agent the tools share; default is the most recently created."""
    client = get_client()
    agents = sorted(
        client.list_agents().get("agents", []),
        key=lambda a: a.get("created_at") or "",
        reverse=True,
    )
    ids: list[str] = [str(a["agent_id"]) for a in agents if a.get("agent_id")]

    if assume_yes and ids:
        return ids[0]
    if not assume_yes:
        console.print()
        console.print(
            f"[{BOLD_PRIMARY}]Which agent should these tools share?[/{BOLD_PRIMARY}]"
        )
        for i, agent_id in enumerate(ids, 1):
            console.print(f"  [{BRIGHT}]{i:2d}[/{BRIGHT}]. {agent_id}")
        console.print(f"  [{BRIGHT}] n[/{BRIGHT}]. Create a new agent")
        choice: str = typer.prompt("Agent", default="1" if ids else "n").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(ids):
            return ids[int(choice) - 1]
        if choice in ids:
            return choice
        if choice.lower() != "n":
            _error(f"Unknown choice: {choice}")

    name = (
        DEFAULT_AGENT_ID
        if assume_yes
        else typer.prompt("New agent name", default=DEFAULT_AGENT_ID).strip()
    )
    if name in ids:
        return name
    try:
        client.create_agent(name, pattern="tool")
    except Exception as e:
        _error(f"Could not create agent '{name}': {e}")
    console.print(f"[green]Created agent '{name}'.[/green]")
    return name


@connect_app.callback(invoke_without_command=True)
def connect_interactive(
    ctx: typer.Context,
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Target project directory"
    ),
    is_global: bool = typer.Option(False, "--global", "-g", help="Install globally"),
    assume_yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Accept defaults: detected tools, most recent agent (or create 'my-agent').",
    ),
):
    """Set up Memanto in your coding tools.

    With no tool name: signs in to Memanto Cloud if needed, lets you pick the
    tools (detected ones are pre-selected) and the agent they share, then
    connects them all. Name a tool to connect just that one.

    Examples:
        memanto connect
        memanto connect --yes
        memanto connect claude-code
    """
    if ctx.invoked_subcommand is not None:
        return

    _ensure_signed_in()
    project_path = Path(project_dir).resolve()
    if not is_global and project_path == Path.home().resolve():
        _error(
            "Cannot install as a local project in your home directory.",
            hint="Use the --global / -g flag instead to install globally.",
        )

    tools = _choose_tools(project_path, assume_yes)
    if not tools:
        console.print("[yellow]No tools selected.[/yellow]")
        raise typer.Exit(0)
    agent_id = _choose_agent(assume_yes)

    console.print()
    connected: list[str] = []
    for name in tools:
        tool = AGENT_REGISTRY[name]
        result = install_agent(name, project_dir, is_global, mcp_agent_id=agent_id)
        if result["errors"]:
            console.print(f"  [red]x[/red] {tool.display_name}")
            for err in result["errors"]:
                console.print(f"    [red]{err}[/red]")
        else:
            console.print(f"  [green]✓[/green] {tool.display_name}")
            connected.append(tool.display_name)

    _activate_for_hooks(agent_id, replace_active=True)

    if not connected:
        _error("No tools were connected.")
    lines = [f"[bold green]Connected to agent '{agent_id}'.[/bold green]\n"]
    lines += [f"Open a new {display} session to start." for display in connected]
    if config_manager.get_backend() == Backend.MEMANTO_CLOUD:
        lines.append(
            f"\n[dim]See your connections at {MEMANTO_CONSOLE_URL}/memory/connections[/dim]"
        )
    console.print()
    console.print(Panel("\n".join(lines), title="Done", border_style=SUCCESS))
