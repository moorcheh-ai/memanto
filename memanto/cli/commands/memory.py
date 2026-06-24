"""
MEMANTO CLI - Memory commands (remember, recall, answer, daily-summary,
detect-conflicts, conflicts).
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import typer
from rich.panel import Panel

from memanto.cli.commands._shared import (
    BOLD_PRIMARY,
    BRIGHT,
    DIM,
    PRIMARY,
    SUCCESS,
    _error,
    app,
    config_manager,
    console,
    format_local_time,
    get_client,
    parse_relative_time,
)


@app.command()
def remember(
    content: str | None = typer.Argument(None, help="Memory content to store"),
    memory_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Memory type (fact, preference, goal, decision, artifact, learning, event, instruction, relationship, context, observation, commitment, error)",
    ),
    title: str | None = typer.Option(
        None, "--title", help="Memory title (defaults to truncated content)"
    ),
    confidence: float = typer.Option(
        0.8, "--confidence", "-c", help="Confidence score (0.0-1.0)"
    ),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags"),
    source: str = typer.Option(
        "user", "--source", "-s", help="Source of the memory (e.g., user, agent_name)"
    ),
    provenance: str = typer.Option(
        "explicit_statement",
        "--provenance",
        "-p",
        help="Provenance/origin of memory (e.g., inferred, corrected)",
    ),
    batch: str | None = typer.Option(
        None, "--batch", help="Path to JSON file with batch memories (array of objects)"
    ),
    from_conversation: str | None = typer.Option(
        None,
        "--from-conversation",
        help="Path to JSON conversation messages, or '-' to read from stdin",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview extracted conversation memories without storing them",
    ),
    max_memories: int = typer.Option(
        20,
        "--max-memories",
        help="Maximum memories to extract from a conversation",
    ),
    ai_model: str | None = typer.Option(
        None,
        "--ai-model",
        help="Optional model override for conversation extraction",
    ),
):
    """Store a new memory for the active agent.

    Single memory:  memanto remember "some fact"
    Batch mode:     memanto remember --batch memories.json
    """
    start = time.perf_counter()
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not active_agent_id or not active_session_token:
        _error(
            "No active agent.", hint="Run 'memanto agent activate <agent-id>' first."
        )

    client = get_client()
    agent_id = active_agent_id

    # Conversation extraction mode
    if from_conversation:
        if batch or content:
            _error(
                "--from-conversation cannot be combined with CONTENT or --batch.",
                hint="Use one input mode at a time.",
            )
        if max_memories < 1 or max_memories > 100:
            _error("--max-memories must be between 1 and 100.")

        try:
            if from_conversation == "-":
                raw = sys.stdin.read()
            else:
                conversation_path = Path(from_conversation)
                if not conversation_path.exists():
                    _error(
                        f"File not found: {from_conversation}",
                        hint="Provide a valid path to a JSON file.",
                    )
                raw = conversation_path.read_text(encoding="utf-8")
            messages = json.loads(raw)
        except json.JSONDecodeError as e:
            _error(
                f"Invalid JSON: {e}",
                hint="Conversation file must contain an array of {role, content} objects.",
            )

        if not isinstance(messages, list):
            _error("Conversation JSON must contain an array of message objects.")

        try:
            with console.status(
                "[cyan]Extracting memories from conversation...", spinner="dots"
            ):
                result = client.extract_memories_from_conversation(
                    agent_id=agent_id,
                    messages=messages,
                    dry_run=dry_run,
                    max_memories=max_memories,
                    ai_model=ai_model,
                )
            elapsed = time.perf_counter() - start
            candidates = result.get("candidates", [])

            if dry_run:
                console.print(
                    f"[yellow]Dry run:[/yellow] extracted {len(candidates)} memory candidate(s)."
                )
            else:
                successful = result.get("successful", 0)
                failed = result.get("failed", 0)
                total = result.get("total_submitted", len(candidates))
                console.print(
                    f"[green]Stored {successful}/{total} extracted memories[/green]"
                    + (f" [yellow]({failed} failed)[/yellow]" if failed else "")
                )

            for i, item in enumerate(candidates, 1):
                console.print(
                    Panel(
                        f"[bold]{item.get('title', 'Untitled')}[/bold]\n\n"
                        f"{item.get('content', '')}\n\n"
                        f"[dim]Type: {item.get('type', 'fact')} | "
                        f"Confidence: {item.get('confidence', 0.8):.2f}[/dim]",
                        title=f"Candidate {i}",
                        border_style="yellow" if dry_run else SUCCESS,
                    )
                )
            console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")
        except Exception as e:
            _error(f"Failed to extract memories: {e}")

        return

    # Batch mode
    if batch:
        if dry_run:
            _error("--dry-run is only supported with --from-conversation.")

        batch_path = Path(batch)
        if not batch_path.exists():
            _error(
                f"File not found: {batch}", hint="Provide a valid path to a JSON file."
            )

        try:
            raw = batch_path.read_text(encoding="utf-8")
            memories = json.loads(raw)
        except json.JSONDecodeError as e:
            _error(
                f"Invalid JSON: {e}",
                hint="File must contain a JSON array of memory objects.",
            )

        if not isinstance(memories, list):
            _error("JSON file must contain an array of memory objects.")

        if len(memories) == 0:
            _error("JSON file contains an empty array.")

        if len(memories) > 100:
            _error(
                f"Batch size {len(memories)} exceeds limit of 100.",
                hint="Split the file into smaller batches.",
            )

        # Validate each item has at least 'content'
        for i, item in enumerate(memories):
            if not isinstance(item, dict) or "content" not in item:
                _error(
                    f"Item {i} is missing required 'content' field.",
                    hint="Each object must have at least a 'content' field.",
                )

        try:
            with console.status(
                f"[cyan]Storing {len(memories)} memories in batch...", spinner="dots"
            ):
                result = client.batch_remember(agent_id=agent_id, memories=memories)
            elapsed = time.perf_counter() - start

            successful = result.get("successful", 0)
            failed = result.get("failed", 0)
            total = result.get("total_submitted", len(memories))

            if failed == 0:
                console.print(
                    f"[green]Stored {successful}/{total} memories successfully![/green]"
                )
            else:
                console.print(
                    f"[yellow]Stored {successful}/{total} memories "
                    f"({failed} failed)[/yellow]"
                )

            console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")

        except Exception as e:
            _error(f"Failed to batch store memories: {e}")

        return

    # Single memory mode
    if not content:
        _error(
            "Missing argument 'CONTENT'.",
            hint="Provide memory content or use --batch for batch mode.\n"
            "Try 'memanto remember --help' for help.",
        )

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        with console.status("[cyan]Storing memory...", spinner="dots"):
            result = client.remember(
                agent_id=agent_id,
                memory_type=memory_type,
                title=title or content[:50] + "..." if len(content) > 50 else content,
                content=content,
                confidence=confidence,
                tags=tag_list,
                source=source,
                provenance=provenance,
            )
        elapsed = time.perf_counter() - start

        console.print("[green]Memory stored successfully![/green]")
        console.print(f"[dim]Memory ID: {result.get('memory_id', 'unknown')}[/dim]")
        parsed_type = result.get("type") or memory_type or "fact"
        console.print(f"[dim]Type: {parsed_type} | Confidence: {confidence}[/dim]")
        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")

    except Exception as e:
        _error(f"Failed to store memory: {e}")


@app.command()
def forget(
    memory_id: str = typer.Argument(..., help="Memory ID to delete"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Delete without asking for confirmation",
    ),
):
    """Delete a single memory from the active agent."""
    start = time.perf_counter()
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not active_agent_id or not active_session_token:
        _error(
            "No active agent.", hint="Run 'memanto agent activate <agent-id>' first."
        )

    if not force and not typer.confirm(
        f"Delete memory '{memory_id}' from agent '{active_agent_id}'?"
    ):
        console.print("[yellow]Delete cancelled.[/yellow]")
        return

    client = get_client()

    try:
        with console.status("[cyan]Deleting memory...", spinner="dots"):
            result = client.delete_memory(
                agent_id=active_agent_id,
                memory_id=memory_id,
            )
        elapsed = time.perf_counter() - start

        console.print("[green]Memory deleted successfully![/green]")
        console.print(f"[dim]Memory ID: {result.get('memory_id', memory_id)}[/dim]")
        console.print(f"[dim]Agent: {result.get('agent_id', active_agent_id)}[/dim]")
        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")

    except Exception as e:
        _error(f"Failed to delete memory: {e}")


@app.command()
def upload(
    file_path: str = typer.Argument(..., help="Path to the file to upload"),
):
    """Upload a file to the active agent's memory namespace.

    Supported formats: .pdf, .docx, .xlsx, .json, .txt, .csv, .md

    Examples:
        memanto upload report.pdf
        memanto upload notes.txt
    """
    from pathlib import Path

    start = time.perf_counter()
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not active_agent_id or not active_session_token:
        _error(
            "No active agent.", hint="Run 'memanto agent activate <agent-id>' first."
        )

    path = Path(file_path)
    if not path.exists():
        _error(f"File not found: {file_path}", hint="Provide a valid file path.")

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".json", ".txt", ".csv", ".md"}
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
        _error(
            f"File type '{suffix}' is not supported.",
            hint=f"Allowed types: {allowed_str}",
        )

    client = get_client()
    agent_id = active_agent_id
    file_size_mb = path.stat().st_size / (1024 * 1024)

    try:
        with console.status(
            f"[cyan]Uploading [bold]{path.name}[/bold] ({file_size_mb:.2f} MB)...",
            spinner="dots",
        ):
            result = client.upload_file(agent_id=agent_id, file_path=str(path))
        elapsed = time.perf_counter() - start

        if result.get("success"):
            console.print("[green]File uploaded successfully![/green]")
        else:
            console.print(
                f"[yellow]Upload completed with status: {result.get('message')}[/yellow]"
            )

        console.print(f"[dim]File: {result.get('file_name', path.name)}[/dim]")
        reported_size = result.get("file_size")
        if reported_size:
            console.print(f"[dim]Size: {reported_size / (1024 * 1024):.2f} MB[/dim]")
        console.print(f"[dim]Namespace: {result.get('namespace', 'unknown')}[/dim]")
        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")

    except Exception as e:
        _error(f"Failed to upload file: {e}")


@app.command()
def recall(
    query: str | None = typer.Argument(
        None,
        help="Search query (omit when using --as-of, --changed-since, or --recent)",
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-n", help="Maximum number of results"
    ),
    memory_type: str | None = typer.Option(
        None, "--type", "-t", help="Filter by memory type"
    ),
    min_similarity: float | None = typer.Option(
        None, "--min-similarity", help="Minimum similarity score"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Filter by tags (comma-separated)"
    ),
    as_of: str | None = typer.Option(
        None,
        "--as-of",
        help="Point-in-time query: What was true at this date? (ISO format: 2025-11-01T00:00:00Z)",
    ),
    changed_since: str | None = typer.Option(
        None,
        "--changed-since",
        help="Differential query: What changed since this date? (ISO format)",
    ),
    recent: bool = typer.Option(
        False,
        "--recent",
        help="Chronological query: return the most recently stored memories (newest first). No search query needed.",
    ),
):
    """Search and retrieve memories for the active agent with temporal query support."""
    start = time.perf_counter()
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not active_agent_id or not active_session_token:
        _error(
            "No active agent.", hint="Run 'memanto agent activate <agent-id>' first."
        )

    # Check for mutually exclusive temporal flags
    temporal_flags = [as_of, changed_since, recent]
    temporal_count = sum(1 for flag in temporal_flags if flag)
    if temporal_count > 1:
        _error(
            "Cannot use multiple temporal query modes together.",
            hint="Use only one of: --as-of, --changed-since, --recent",
        )

    # Temporal queries list memories directly and don't take a query argument.
    if query and (as_of or changed_since or recent):
        _error(
            "Cannot provide a search query with temporal flags.",
            hint="Temporal queries (--as-of, --changed-since, --recent) list memories directly. Remove the search query to continue.",
        )

    client = get_client()
    agent_id = active_agent_id

    # CLI-side validation for timestamps to fail fast with a clear error
    def _validate_and_parse_timestamp(ts: str, flag_name: str) -> str:
        """Normalize an ISO or relative timestamp passed to a temporal flag."""

        if not ts:
            return ts

        # Try parsing as relative time (e.g., "today", "last 2 hours")
        rel_ts = parse_relative_time(ts)
        if isinstance(rel_ts, str):
            return rel_ts

        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return ts
        except ValueError:
            _error(
                f"Invalid timestamp format for {flag_name}: '{ts}'",
                hint="Use ISO format ('2025-11-01T00:00:00Z' or '2025-11-01') or relative time ('today', 'yesterday', 'last 2 days', 'last 5 hours, 'this month', 'this week')",
            )

    if as_of:
        as_of = _validate_and_parse_timestamp(as_of, "--as-of")
    if changed_since:
        changed_since = _validate_and_parse_timestamp(changed_since, "--changed-since")

    # Parse filters
    type = [memory_type] if memory_type else None
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        # Determine which API method to call based on temporal flags
        temporal_mode = "standard"
        with console.status("[cyan]Searching memories...", spinner="dots"):
            if as_of:
                results = client.recall_as_of(
                    agent_id=agent_id,
                    as_of=as_of,
                    limit=limit,
                    type=type,
                )
                temporal_mode = "as_of"
            elif changed_since:
                results = client.recall_changed_since(
                    agent_id=agent_id,
                    since=changed_since,
                    limit=limit,
                    type=type,
                )
                temporal_mode = "changed_since"
            elif recent:
                results = client.recall_recent(
                    agent_id=agent_id,
                    limit=limit,
                    type=type,
                )
                temporal_mode = "recent"
            elif query:
                # Standard recall
                results = client.recall(
                    agent_id=agent_id,
                    query=query,
                    limit=limit,
                    type=type,
                    tags=tag_list,
                    min_similarity=min_similarity,
                )
            else:
                _error(
                    "Missing argument 'QUERY'.",
                    hint="Try 'memanto recall --help' for help.",
                )
        elapsed = time.perf_counter() - start

        memories = results.get("memories", [])

        if not memories:
            console.print("[yellow]No memories found matching your query[/yellow]")
            console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")
            return

        # Display temporal mode information
        mode_labels = {
            "as_of": f"Point-in-time (as of {as_of})",
            "changed_since": f"Differential (since {changed_since})",
            "recent": "Recent (newest first)",
            "standard": "Standard search",
        }
        mode_label = mode_labels.get(temporal_mode, "Standard search")

        console.print(
            f"\n[{BOLD_PRIMARY}]Found {len(memories)} memories[/{BOLD_PRIMARY}] [dim]({mode_label})[/dim]\n"
        )

        for i, memory in enumerate(memories, 1):
            score = memory.get("score") or 0.0
            mem_type = memory.get("type") or "unknown"
            conf = memory.get("confidence") or 0.0
            comp_conf = memory.get("computed_confidence")
            title = memory.get("title") or "Untitled"
            content = memory.get("content") or ""
            created = memory.get("created_at") or ""
            status = memory.get("status") or "active"
            change_type = memory.get("change_type")
            source = memory.get("source") or ""
            source_ref = memory.get("source_ref") or ""
            provenance = memory.get("provenance") or ""
            mem_tags = memory.get("tags") or []

            # Determine memory source from ID pattern
            id_str = memory.get("id", "unknown")
            if "_summary_" in id_str:
                source_tag = "[yellow] · file upload · summary [/yellow]"
            elif "_chunk_" in id_str:
                source_tag = "[yellow] · file upload · chunk [/yellow]"
            else:
                source_tag = "[cyan] · memory [/cyan]"

            # Create panel for each memory
            panel_content = f"[bold]{title}[/bold]\n\n{content[:200]}{'...' if len(content) > 200 else ''}\n\n"

            # Show ID and confidence (computed if available)
            if comp_conf is not None:
                panel_content += f"[dim]ID: {id_str} | Type: {mem_type} | Confidence: {comp_conf:.2f} (computed) | Score: {score:.3f}[/dim]"
            else:
                panel_content += f"[dim]ID: {id_str} | Type: {mem_type} | Confidence: {conf:.2f} | Score: {score:.3f}[/dim]"

            if created:
                panel_content += f"\n[dim]Created: {format_local_time(created)}[/dim]"
            elif "_summary_" in id_str or "_chunk_" in id_str:
                panel_content += "\n[dim]Created: not available (file upload)[/dim]"

            # Show provenance metadata. `source` is unified: it holds the
            # uploaded file name for file-upload memories and the origin
            # (user, agent, ...) for everything else.
            origin_parts = []
            if source:
                origin_parts.append(f"Source: {source}")
            if source_ref:
                origin_parts.append(f"Ref: {source_ref}")
            if provenance:
                origin_parts.append(f"Provenance: {provenance}")
            if origin_parts:
                panel_content += f"\n[dim]{' | '.join(origin_parts)}[/dim]"

            # Show tags when present
            if mem_tags:
                panel_content += f"\n[dim]Tags: {', '.join(mem_tags)}[/dim]"

            # Show status for non-standard queries
            if temporal_mode != "standard" and status != "active":
                panel_content += f"\n[dim]Status: {status}[/dim]"

            # Show change type for differential queries
            if change_type:
                panel_content += f"\n[yellow]Change: {change_type}[/yellow]"

            # Determine border style
            border_style = BRIGHT if score > 0.8 else PRIMARY
            if status == "superseded":
                border_style = DIM
            elif change_type == "created":
                border_style = SUCCESS

            console.print(
                Panel(
                    panel_content,
                    title=f"Memory {i} {source_tag}",
                    border_style=border_style,
                )
            )
            console.print()

        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")

    except Exception as e:
        _error(f"Failed to recall memories: {e}")


@app.command()
def answer(
    question: str = typer.Argument(..., help="Question to ask"),
    limit: int | None = typer.Option(
        None, "--limit", "-n", help="Number of context memories to use"
    ),
):
    """Answer a question using RAG (Retrieval-Augmented Generation)."""
    start = time.perf_counter()
    active_agent_id, active_session_token = config_manager.get_active_session()

    if not active_agent_id or not active_session_token:
        _error(
            "No active agent.", hint="Run 'memanto agent activate <agent-id>' first."
        )

    client = get_client()
    agent_id = active_agent_id

    try:
        with console.status(f"[{PRIMARY}]Thinking...", spinner="dots"):
            result = client.answer(agent_id, question, limit)
        elapsed = time.perf_counter() - start

        answer = result.get("answer", "No answer generated")
        context = result.get("context_memories", [])

        # Display answer
        console.print(
            Panel(
                f"[{BOLD_PRIMARY}]Question:[/{BOLD_PRIMARY}] {question}\n\n"
                f"[bold green]Answer:[/bold green]\n{answer}",
                title="RAG Response",
                border_style=SUCCESS,
            )
        )

        # Display context
        if context:
            console.print(f"\n[dim]Used {len(context)} memories as context:[/dim]")
            for i, mem in enumerate(context, 1):
                console.print(
                    f"  {i}. {mem.get('title', 'Untitled')} (score: {mem.get('score', 0):.3f})"
                )

        console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")

    except Exception as e:
        _error(f"Failed to process question: {e}")


@app.command()
def daily_summary(
    date: str | None = typer.Option(
        None, "--date", "-d", help="Date in YYYY-MM-DD format (defaults to today)"
    ),
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Agent identifier (defaults to active agent)"
    ),
    output_path: str | None = typer.Option(
        None, "--output", "-o", help="Custom output path for the summary MD file"
    ),
):
    """Generate a daily AI summary from session memories."""
    start = time.perf_counter()
    active_agent_id, _ = config_manager.get_active_session()

    # Resolve agent_id
    if not agent_id:
        if not active_agent_id:
            _error(
                "No active agent.",
                hint="Provide an agent ID or run 'memanto agent activate <agent-id>' first.",
            )
        agent_id = active_agent_id

    # Resolve date
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    client = get_client()

    try:
        with console.status(
            f"[cyan]Generating daily summary for '{agent_id}' on {date}...",
            spinner="dots",
        ):
            result = client.generate_daily_summary(
                agent_id=agent_id, date=date, output_path=output_path
            )
        elapsed = time.perf_counter() - start

        summary = result.get("summary", {})

        # Display Summary Status
        if summary.get("status") == "success":
            console.print(
                f"[green]Daily summary generated:[/green] {summary.get('summary_path')}"
            )
        else:
            console.print(f"[yellow]! Summary:[/yellow] {summary.get('status')}")

        # Display Auto-Export Status
        export = result.get("export")
        if export:
            if export.get("status") != "error":
                export_count = export.get("total_memories", 0)
                console.print(
                    f"[green]Memory export generated:[/green] {export_count} memories saved to cache"
                )
            else:
                console.print(
                    f"[yellow]  ! Auto-export failed:[/yellow] {export.get('error')}"
                )

        console.print(
            "\n[dim]Conflict detection runs separately. "
            "Run 'memanto detect-conflicts' or enable the schedule "
            "with 'memanto schedule enable'.[/dim]"
        )
        console.print(f"\n[dim]Completed in {elapsed:.2f}s[/dim]")

    except Exception as e:
        _error(f"Failed to generate daily summary: {e}")


@app.command("detect-conflicts")
def detect_conflicts(
    date: str | None = typer.Option(
        None, "--date", "-d", help="Date in YYYY-MM-DD format (defaults to today)"
    ),
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Agent identifier (defaults to active agent)"
    ),
):
    """Generate the conflict report for an agent/date.

    Runs the LLM conflict-detection pass over the day's session memories
    and writes the JSON report to ``~/.memanto/conflicts/``. Resolve the
    detected conflicts interactively with ``memanto conflicts``.

    This is the command the schedule runs — see ``memanto schedule``.
    """
    start = time.perf_counter()
    active_agent_id, _ = config_manager.get_active_session()

    if not agent_id:
        if not active_agent_id:
            _error(
                "No active agent.",
                hint="Provide an agent ID or run 'memanto agent activate <agent-id>' first.",
            )
        agent_id = active_agent_id

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    client = get_client()

    try:
        with console.status(
            f"[cyan]Detecting conflicts for '{agent_id}' on {date}...",
            spinner="dots",
        ):
            result = client.generate_conflict_report(agent_id=agent_id, date=date)
        elapsed = time.perf_counter() - start

        conflicts = result.get("conflicts", {})

        if conflicts.get("status") == "success":
            count = conflicts.get("conflict_count", 0)
            console.print(
                f"[green]Conflict report generated:[/green] {conflicts.get('json_path')}"
            )
            if count > 0:
                console.print(f"[yellow]  ! {count} conflict(s) detected[/yellow]")
                console.print(
                    "[dim]  Run 'memanto conflicts' to resolve interactively[/dim]"
                )
            else:
                console.print("[dim]  No conflicts detected[/dim]")
        elif conflicts.get("status") == "no_sessions":
            console.print("[dim]No sessions found for conflict detection.[/dim]")
        else:
            console.print(f"[yellow]! Conflicts:[/yellow] {conflicts.get('status')}")

        console.print(f"\n[dim]Completed in {elapsed:.2f}s[/dim]")

    except Exception as e:
        _error(f"Failed to detect conflicts: {e}")


@app.command()
def conflicts(
    date: str | None = typer.Option(
        None, "--date", "-d", help="Date in YYYY-MM-DD format (defaults to today)"
    ),
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Agent identifier (defaults to active agent)"
    ),
    list_only: bool = typer.Option(
        False, "--list", "-l", help="List conflicts without interactive resolution"
    ),
):
    """Interactively resolve memory conflicts for an agent.

    Reads the conflict report JSON and walks through each unresolved
    conflict, letting you choose how to resolve it.

    Examples:
        memanto conflicts
        memanto conflicts --date 2026-03-01
        memanto conflicts --list
        memanto conflicts --agent my-agent
    """
    active_agent_id, active_session_token = config_manager.get_active_session()

    # Resolve agent_id
    if not agent_id:
        if not active_agent_id:
            _error(
                "No active agent.",
                hint="Provide an agent ID or run 'memanto agent activate <agent-id>' first.",
            )
        agent_id = active_agent_id

    # Resolve date
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    client = get_client()

    # Load unresolved conflicts
    try:
        unresolved = client.list_conflicts(agent_id=agent_id, date=date)
    except Exception as e:
        _error(f"Failed to load conflicts: {e}")

    if not unresolved:
        console.print(
            f"\n[green]No unresolved conflicts for agent '{agent_id}' on {date}[/green]"
        )
        console.print(
            "[dim]Run 'memanto detect-conflicts' to generate a conflict report.[/dim]"
        )
        return

    console.print(
        f"\n[{BOLD_PRIMARY}]Found {len(unresolved)} unresolved conflict(s)[/{BOLD_PRIMARY}] "
        f"[dim]for agent '{agent_id}' on {date}[/dim]\n"
    )

    # List-only mode
    if list_only:
        for i, c in enumerate(unresolved, 1):
            ctype = c.get("type", "conflict").upper()
            type_colors = {
                "CONTRADICTION": "red",
                "CONFLICT": "yellow",
                "UPDATE": PRIMARY,
                "DUPLICATE": "dim",
            }
            color = type_colors.get(ctype, "white")
            console.print(
                f"  [{color}]{i}. [{ctype}][/{color}] {c.get('title', 'Untitled')}"
            )
            if c.get("old_content"):
                console.print(f"     [dim]Old: {c['old_content'][:80]}[/dim]")
            if c.get("new_content"):
                console.print(f"     [dim]New: {c['new_content'][:80]}[/dim]")
            console.print(
                f"     [dim]Recommendation: {c.get('recommendation', '—')}[/dim]"
            )
            console.print()
        return

    # Interactive mode
    if not active_session_token:
        _error(
            "No active agent activation.",
            hint="Resolving conflicts requires an active agent.\n"
            "Run 'memanto agent activate <agent-id>' first.",
        )

    # Load full conflict list to get original indices

    json_path = (
        Path.home() / ".memanto" / "conflicts" / f"{agent_id}_{date}_conflicts.json"
    )
    with open(json_path, encoding="utf-8") as f:
        all_conflicts = json.load(f)

    # Map unresolved conflicts to their original indices
    unresolved_indices = [
        idx for idx, c in enumerate(all_conflicts) if not c.get("resolved", False)
    ]

    resolved_count = 0
    skipped_count = 0

    for display_num, original_idx in enumerate(unresolved_indices, 1):
        c = all_conflicts[original_idx]
        ctype = c.get("type", "conflict").upper()
        type_colors = {
            "CONTRADICTION": "red",
            "CONFLICT": "yellow",
            "UPDATE": PRIMARY,
            "DUPLICATE": "dim",
        }
        color = type_colors.get(ctype, "white")
        rec = c.get("recommendation", "merge")

        # Build the display panel
        lines = []
        lines.append(
            f"[bold][{color}][{ctype}][/{color}][/bold]  {c.get('title', 'Untitled')}\n"
        )
        if c.get("description"):
            lines.append(f"[italic]{c['description']}[/italic]\n")
        lines.append("")

        # Memory A (old)
        old_id = c.get("old_memory_id") or "unknown"
        old_content = c.get("old_content") or "—"
        old_ts_str = format_local_time(c.get("old_created_at"))
        old_ts = f" · {old_ts_str}" if old_ts_str else ""
        lines.append(f"[bold]Memory A (old):[/bold]  [dim]ID: {old_id}{old_ts}[/dim]")
        lines.append(f"  {old_content}\n")

        # Memory B (new)
        new_id = c.get("new_memory_id") or "unknown"
        new_content = c.get("new_content") or "—"
        new_ts_str = format_local_time(c.get("new_created_at"))
        new_ts = f" · {new_ts_str}" if new_ts_str else ""
        lines.append(f"[bold]Memory B (new):[/bold]  [dim]ID: {new_id}{new_ts}[/dim]")
        lines.append(f"  {new_content}\n")

        # Recommendation badge
        rec_display = {
            "keep_new": "[green]Keep B (new)[/green]",
            "keep_old": f"[{BRIGHT}]Keep A (old)[/{BRIGHT}]",
            "merge": "[yellow]Merge/Manual[/yellow]",
            "remove_both": "[red]Remove Both[/red]",
        }
        lines.append(f"[bold]AI Recommendation:[/bold]  {rec_display.get(rec, rec)}")

        console.print(
            Panel(
                "\n".join(lines),
                title=f"Conflict {display_num}/{len(unresolved_indices)}",
                border_style=color,
            )
        )

        # Prompt options with recommendation markers
        def _opt(key, label, rec_val, current_rec=rec):
            """Print a conflict-resolution choice with its recommendation marker."""

            marker = " [green]<< recommended[/green]" if current_rec == rec_val else ""
            console.print(f"  [{BRIGHT}][{key}][/{BRIGHT}] {label}{marker}")

        _opt("1", "Keep A (old memory)", "keep_old")
        _opt("2", "Keep B (new memory)", "keep_new")
        _opt("3", "Keep both", None)
        _opt("4", "Remove both", "remove_both")
        _opt("5", "Manual: type replacement", "merge")
        console.print("  [dim]\\[s] Skip  \\[q] Quit[/dim]\n")

        choice = typer.prompt("Choose", default="s").strip().lower()

        action_map = {
            "1": "keep_old",
            "2": "keep_new",
            "3": "keep_both",
            "4": "remove_both",
            "5": "manual",
        }

        if choice == "q":
            console.print("\n[dim]Quitting conflict resolution.[/dim]")
            break
        elif choice == "s":
            console.print("[dim]  Skipped.[/dim]\n")
            skipped_count += 1
            continue
        elif choice not in action_map:
            console.print("[yellow]  Invalid choice, skipping.[/yellow]\n")
            skipped_count += 1
            continue

        action = action_map[choice]
        manual_content = None

        if action == "manual":
            manual_content = typer.prompt("  Enter replacement memory content")
            if not manual_content or not manual_content.strip():
                console.print("[yellow]  Empty content, skipping.[/yellow]\n")
                skipped_count += 1
                continue

        # Execute resolution
        try:
            result = client.resolve_conflict(
                agent_id=agent_id,
                date=date,
                conflict_index=original_idx,
                action=action,
                manual_content=manual_content,
            )

            status_msgs = {
                "keep_old": "[green]  OK Kept A (old). New memory deleted.[/green]",
                "keep_new": "[green]  OK Kept B (new). Old memory deleted.[/green]",
                "keep_both": "[green]  OK Both memories kept.[/green]",
                "remove_both": "[green]  OK Both memories removed.[/green]",
            }
            if action == "manual":
                new_id = result.get("new_memory_id", "unknown")
                console.print(f"[green]  OK Replaced with new memory: {new_id}[/green]")
            else:
                console.print(status_msgs.get(action, "[green]  OK Resolved.[/green]"))

            if result.get("warning"):
                console.print(f"[yellow]  ! {result['warning']}[/yellow]")

            resolved_count += 1
        except Exception as e:
            console.print(f"[red]  Failed: {e}[/red]")

        console.print()

    # Summary
    console.print(
        f"\n[bold]Done:[/bold] [green]{resolved_count} resolved[/green], [dim]{skipped_count} skipped[/dim]"
    )

    # Auto-export if any conflicts were resolved to update the local MD cache
    if resolved_count > 0:
        try:
            with console.status(
                f"[{PRIMARY}]Updating local memory cache...", spinner="dots"
            ):
                export_result = client.export_memory_md(agent_id)
            export_count = export_result.get("total_memories", 0)
            console.print(f"[dim]Cache updated: {export_count} memories synced[/dim]")
        except Exception as e:
            console.print(
                f"[yellow]Warning: Failed to auto-update memory cache: {e}[/yellow]"
            )
