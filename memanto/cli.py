import click
from pathlib import Path
from typing import List, Optional

from memanto.conflict_reports import (
    get_conflict_path,
    list_conflicts,
    resolve_conflict,
    get_latest_conflict,
)

@click.group()
def cli():
    """MEMANTO CLI for managing conflict reports."""
    pass

@cli.command()
@click.option("--agent-id", required=True, help="The agent ID.")
@click.option("--date", required=True, help="The date of the conflict.")
def generate_conflict_report(agent_id: str, date: str):
    """Generate a conflict report for a specific agent and date."""
    conflict_path = get_conflict_path(agent_id, date)
    # Generate conflict report logic here
    click.echo(f"Conflict report generated at: {conflict_path}")

@cli.command()
def list_conflicts():
    """List all conflict reports for the active backend."""
    conflicts = list_conflicts()
    for conflict in conflicts:
        click.echo(conflict)

@cli.command()
@click.option("--agent-id", required=True, help="The agent ID.")
@click.option("--date", required=True, help="The date of the conflict.")
def resolve_conflict(agent_id: str, date: str):
    """Mark a conflict as resolved."""
    resolve_conflict(agent_id, date)
    click.echo(f"Conflict resolved for agent {agent_id} on date {date}")

@cli.command()
@click.option("--agent-id", required=True, help="The agent ID.")
def get_latest_conflict(agent_id: str):
    """Get the latest conflict report for a specific agent."""
    latest_conflict = get_latest_conflict(agent_id)
    if latest_conflict:
        click.echo(f"Latest conflict report: {latest_conflict}")
    else:
        click.echo("No conflict reports found for the specified agent.")