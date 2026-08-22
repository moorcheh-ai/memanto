#!/usr/bin/env python3
"""
Liberate the memory ChatGPT and Claude have built about you into an OKF bundle.

Assistant memory is the most locked-in memory there is: you can read it in a
settings pane, but you cannot take it anywhere. This adapter turns an official
data export into an Open Knowledge Format bundle, plain markdown you own,
which ``memanto migrate okf`` imports like any other bundle.

It adds no CLI surface and no extraction, classification or serialization logic
of its own. Three shipped services do the work:

* ``ConversationMemoryExtractionService`` distills conversations into typed
  memories (the engine behind ``memanto remember --from-conversation``), so
  there is no second extraction prompt to keep in sync, and its prompt already
  refuses to emit secrets, keys and tokens.
* ``MemoryParsingService`` types saved memories using the same rule-based
  classifier that runs on every write, so no memory type is ever guessed here.
* ``OkfExportService`` serializes the bundle, so the output is identical in
  shape to Memanto's own ``memory export --okf`` and round-trips cleanly.

This file only does what those services cannot: read the two export formats.

Usage:
    python liberate.py --agent my-agent --chatgpt chatgpt_export.zip
    python liberate.py --agent my-agent --saved saved_memories.txt --out ./bundle
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
import zipfile
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

import okf_v02  # noqa: E402  (local module, sits beside this file)

from memanto.app.core import MemoryRecord
from memanto.app.services.conversation_memory_extraction_service import (
    ConversationMemoryExtractionService as Extractor,
)
from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.commands._shared import get_client

# Actor string for OKF v0.2 `generated.by`, per spec section 7. Deliberately a
# stable adapter version rather than memanto's build version, which carries a
# git hash and would churn committed bundles on every upstream commit.
PRODUCER = "memanto-liberate/1.0"


class Conversation(NamedTuple):
    """One source conversation, normalized across providers."""

    id: str
    title: str
    created_at: datetime | None
    messages: list[dict[str, str]]


def _parse_dt(value: Any) -> datetime | None:
    """Parse a source timestamp (epoch seconds or ISO 8601) into UTC."""
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            # A corrupt epoch (year 3170843, say) is not worth aborting a
            # migration over; treat it as no date at all.
            return None
    if isinstance(value, str) and value.strip():
        # Only the trailing Zulu marker is a timezone; a blanket replace would
        # corrupt any other Z in the string.
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


# Large ChatGPT exports no longer ship a single conversations.json. History is
# sharded into conversations-000.json, conversations-001.json and so on, 100
# conversations per shard, so every shard has to be read and concatenated.
_CONVERSATION_FILE = re.compile(r"^conversations(-\d+)?\.json$")


def _conversation_members(names: Iterable[str]) -> list[str]:
    """Pick the conversation files out of an archive or folder listing.

    Matching is on the exact file name rather than a suffix test. An export also
    contains ``shared_conversations.json``, which ends with the same text but
    holds only id/title stubs with no ``mapping``; selecting it silently yields
    a handful of empty conversations instead of the whole history.

    Sorted by shard number rather than by name, so ordering stays correct past
    999 shards where a plain string sort would put 1000 before 999. Order is
    what ``--limit`` slices, so it has to be stable and it has to be right.
    """
    matches = []
    for name in names:
        found = _CONVERSATION_FILE.match(PurePosixPath(name).name)
        if found:
            shard = found.group(1)
            matches.append((int(shard[1:]) if shard else -1, name))
    return [name for _, name in sorted(matches)]


def _load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read the conversation shards from an export zip, folder, or bare file."""
    conversations: list[dict[str, Any]] = []
    current = str(path)
    try:
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                members = _conversation_members(archive.namelist())
                if not members:
                    raise SystemExit(f"No conversations.json inside {path}")
                for member in members:
                    current = member
                    payload = json.loads(archive.read(member))
                    if isinstance(payload, list):
                        conversations.extend(payload)
        elif path.is_dir():
            members = _conversation_members(p.name for p in path.iterdir())
            if not members:
                raise SystemExit(f"No conversations.json inside {path}")
            for member in members:
                current = member
                payload = json.loads((path / member).read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    conversations.extend(payload)
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                conversations.extend(payload)
    except zipfile.BadZipFile as exc:
        raise SystemExit(f"{path} is not a readable zip archive: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{current} in {path} is not valid JSON: {exc}\n"
            "The archive may be truncated. Try downloading the export again."
        ) from exc
    return conversations


def read_chatgpt(path: Path) -> Iterator[Conversation]:
    """Yield conversations from a ChatGPT export.

    ChatGPT stores each conversation as a node graph. The active thread is the
    parent chain hanging off ``current_node``, so we walk it upward and reverse.
    ``user_editable_context`` nodes (custom instructions, repeated verbatim in
    every conversation) are skipped, use ``--saved`` for those instead.
    """
    for conv in _load_conversations(path):
        if not isinstance(conv, dict):
            continue
        mapping = conv.get("mapping") or {}
        node_id, seen, chain = conv.get("current_node"), set(), []
        while node_id and node_id not in seen:
            seen.add(node_id)
            node = mapping.get(node_id) or {}
            message = node.get("message") or {}
            content = message.get("content") or {}
            role = (message.get("author") or {}).get("role")
            if role in ("user", "assistant") and content.get("content_type") == "text":
                parts = content.get("parts") or []
                text = "\n".join(p.strip() for p in parts if isinstance(p, str)).strip()
                if text:
                    chain.append({"role": role, "content": text})
            node_id = node.get("parent")
        if chain:
            yield Conversation(
                id=str(conv.get("conversation_id") or conv.get("id") or ""),
                title=str(conv.get("title") or "Untitled conversation"),
                created_at=_parse_dt(conv.get("create_time")),
                messages=list(reversed(chain)),
            )


def inspect_export(path: Path, source: str) -> dict[str, Any]:
    """Report what an export actually contains, without calling any API.

    Export contents vary by account and by when the archive was produced, so
    this counts rather than assumes. For ChatGPT it also looks for the traces a
    saved memory leaves behind, ``bio`` tool calls (the moment ChatGPT commits
    a memory) and the replayed memory snapshot, because whether those survive
    into an export is exactly the question worth settling on real data.
    """
    counts: dict[str, Any] = {"conversations": 0, "messages": 0}
    dates: list[datetime] = []

    if source == "claude":
        for conv in read_claude(path):
            counts["conversations"] += 1
            counts["messages"] += len(conv.messages)
            if conv.created_at:
                dates.append(conv.created_at)
    else:
        counts.update(bio_writes=0, memory_snapshots=0, custom_instructions=0)
        for conv in _load_conversations(path):
            if not isinstance(conv, dict):
                continue
            counts["conversations"] += 1
            when = _parse_dt(conv.get("create_time"))
            if when:
                dates.append(when)
            for node in (conv.get("mapping") or {}).values():
                message = (node or {}).get("message") or {}
                if not message:
                    continue
                counts["messages"] += 1
                content = message.get("content") or {}
                content_type = content.get("content_type")
                if message.get("recipient") == "bio":
                    counts["bio_writes"] += 1
                if content_type == "model_editable_context":
                    counts["memory_snapshots"] += 1
                elif content_type == "user_editable_context":
                    counts["custom_instructions"] += 1

    if dates:
        counts["oldest"] = min(dates).date().isoformat()
        counts["newest"] = max(dates).date().isoformat()
    return counts


def read_claude(path: Path) -> Iterator[Conversation]:
    """Yield conversations from a Claude export.

    Claude stores a flat ``chat_messages`` list. Older exports carry the text on
    ``text``; newer ones split it into typed ``content`` blocks.
    """
    for conv in _load_conversations(path):
        if not isinstance(conv, dict):
            continue
        messages = []
        for message in conv.get("chat_messages") or []:
            if not isinstance(message, dict):
                continue
            text = (message.get("text") or "").strip()
            if not text:
                blocks = message.get("content") or []
                text = "\n".join(
                    b.get("text", "").strip()
                    for b in blocks
                    if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
            if text:
                role = "user" if message.get("sender") == "human" else "assistant"
                messages.append({"role": role, "content": text})
        if messages:
            yield Conversation(
                id=str(conv.get("uuid") or ""),
                title=str(conv.get("name") or "Untitled conversation"),
                created_at=_parse_dt(conv.get("created_at")),
                messages=messages,
            )


def _record(
    *,
    title: str,
    content: str,
    memory_type: str,
    source: str,
    source_ref: str,
    source_title: str,
    created_at: datetime | None,
    confidence: float,
) -> dict[str, Any]:
    """Build one memory dict in the shape ``OkfExportService`` renders."""
    return {
        "id": str(uuid.uuid4()),
        "title": title[:100],
        "content": content,
        "type": memory_type,
        "confidence": confidence,
        "tags": [source, "assistant-memory"],
        "created_at": created_at.isoformat() if created_at else None,
        "source": source,
        "source_ref": source_ref,
        "source_title": source_title,
        "provenance": "imported",
        "status": "active",
    }


def distill(
    client: SdkClient,
    agent_id: str,
    conversations: Iterator[Conversation],
    source: str,
    max_per_conversation: int,
) -> list[dict[str, Any]]:
    """Distill conversations into typed memories via the shipped extractor.

    Runs with ``dry_run=True`` so nothing is written: the memories reach Memanto
    only later, through ``memanto migrate okf``. A conversation that fails
    extraction is reported and skipped rather than aborting the whole export.
    """
    records: list[dict[str, Any]] = []
    for index, conv in enumerate(conversations, 1):
        label = conv.title[:60]
        try:
            result = client.extract_memories_from_conversation(
                agent_id=agent_id,
                messages=conv.messages[: Extractor.MAX_MESSAGES],
                dry_run=True,
                max_memories=max_per_conversation,
            )
        except Exception as exc:  # noqa: BLE001, one bad thread must not abort
            print(f"  [{index}] skipped {label!r}: {exc}", file=sys.stderr)
            continue

        candidates = result.get("candidates") or []
        print(f"  [{index}] {label!r} -> {len(candidates)} memories")
        for candidate in candidates:
            content = (candidate.get("content") or "").strip()
            if not content:
                continue
            records.append(
                _record(
                    title=candidate.get("title") or content[:80],
                    content=content,
                    memory_type=candidate.get("type") or "fact",
                    source=source,
                    source_ref=conv.id,
                    source_title=conv.title,
                    created_at=conv.created_at,
                    confidence=float(candidate.get("confidence") or 0.8),
                )
            )
    return records


def classify_saved(path: Path, source: str) -> list[dict[str, Any]]:
    """Type saved memories with Memanto's own classifier.

    Saved memories are already distilled statements, so they need no LLM, only
    a type. ``MemoryParsingService`` is the same rule-based classifier Memanto
    runs on every write, and it falls back to ``fact`` when inconclusive.
    """
    parser = MemoryParsingService()
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip().lstrip("-* ").strip()
        if not text or text.startswith("#"):
            continue
        parsed = parser.parse_memory(
            MemoryRecord(
                title=text[:100],
                content=text,
                agent_id="okf-adapter",
                actor_id="okf-adapter",
                source=source,
            )
        )
        records.append(
            _record(
                title=text[:80],
                content=text,
                memory_type=parsed.type or "fact",
                source=source,
                source_ref=f"{source}:saved-memories",
                source_title="Saved memories, pasted from the assistant settings",
                created_at=None,
                confidence=0.9,
            )
        )
    return records


def _require_paths(*candidates: tuple[Path | None, str]) -> None:
    """Fail loudly on a path that does not exist.

    A mistyped export path must not fall through to a different source or to the
    sample fixtures: quoting migration numbers from the wrong data is worse than
    not running at all.
    """
    missing = [
        f"{flag} {path}" for path, flag in candidates if path and not path.exists()
    ]
    if missing:
        raise SystemExit("Path does not exist:\n  " + "\n  ".join(missing))


_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def verify_links(bundle: Path) -> list[str]:
    """Return every relative markdown link in the bundle that does not resolve.

    OKF consumers must tolerate broken cross-links (spec 11), but a producer has
    no excuse for emitting them. External links and bare anchors are skipped
    because neither is ours to resolve.
    """
    broken: list[str] = []
    for doc in sorted(bundle.rglob("*.md")):
        for target in _MD_LINK.findall(doc.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            root = bundle if target.startswith("/") else doc.parent
            if not (root / target.lstrip("/")).exists():
                broken.append(f"{doc.relative_to(bundle)} -> {target}")
    return broken


def _clear_stale_bundle(out: Path) -> None:
    """Remove a previous bundle so the output reflects only this run.

    Filenames are slugs of memory titles, and extraction is not deterministic,
    so re-running would otherwise leave last run's documents sitting alongside
    this run's, silently inflating the bundle. Only a directory that actually
    looks like an OKF bundle is removed; anything else is left alone rather
    than risking a user's data.
    """
    if not out.exists():
        return
    if (out / "index.md").exists() or (out / "memories").is_dir():
        shutil.rmtree(out)
    elif any(out.iterdir()):
        raise SystemExit(f"{out} is not empty and is not an OKF bundle, refusing")


def exclude_matching(
    records: list[dict[str, Any]], pattern: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop memories whose title or content matches ``pattern``.

    Filtering happens before the bundle is written, never by deleting files
    afterwards: index documents repeat titles, so a post-hoc delete would leave
    the excluded text sitting in plain sight in the listings.
    """
    try:
        matcher = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise SystemExit(f"Invalid exclusion pattern {pattern!r}: {exc}") from exc
    kept, dropped = [], []
    for record in records:
        haystack = f"{record.get('title', '')}\n{record.get('content', '')}"
        if matcher.search(haystack):
            # Report the type, never the title. A title that matched a privacy
            # pattern is sensitive by definition, and echoing it would leak the
            # text through the console and into any captured log, which is
            # exactly what the caller asked to prevent.
            dropped.append(record.get("type") or "untyped")
        else:
            kept.append(record)
    return kept, dropped


def write_bundle(records: list[dict[str, Any]], out: Path, name: str) -> dict[str, Any]:
    """Serialize records as an OKF bundle using Memanto's own exporter."""
    _clear_stale_bundle(out)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_type.setdefault(record["type"], []).append(record)
    return OkfExportService(exports_dir=out.parent).write_okf_bundle(
        agent_id=name,
        memories_by_type=by_type,
        output_dir=out,
        split="file",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a ChatGPT/Claude export into a portable OKF bundle."
    )
    parser.add_argument("--chatgpt", type=Path, help="ChatGPT export zip/json")
    parser.add_argument("--claude", type=Path, help="Claude export zip/json")
    parser.add_argument("--saved", type=Path, help="Saved memories, one per line")
    parser.add_argument("--agent", help="Memanto agent used for distillation")
    parser.add_argument("--out", type=Path, default=Path("okf_bundle"))
    parser.add_argument("--max-per-conversation", type=int, default=5)
    parser.add_argument("--limit", type=int, help="Only process the first N threads")
    parser.add_argument(
        "--exclude",
        metavar="REGEX",
        help="Drop memories whose title or content matches this pattern "
        "(case-insensitive). Use it to keep private details out of a bundle "
        "you intend to publish.",
    )
    parser.add_argument(
        "--exclude-file",
        type=Path,
        metavar="PATH",
        help="File of exclusion patterns, one regex per line, '#' for comments. "
        "Preferred over --exclude for real identifiers: a pattern on the command "
        "line ends up in your shell history and in any captured log.",
    )
    parser.add_argument(
        "--okf-version",
        choices=["0.1", "0.2"],
        default="0.2",
        help="OKF spec revision to emit (default 0.2; 0.1 matches memanto's exporter)",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Report what an export contains, then exit (no writes, no API, no key)",
    )
    args = parser.parse_args()

    # Validate every supplied path up front, before touching an agent or the API.
    _require_paths(
        (args.chatgpt, "--chatgpt"),
        (args.claude, "--claude"),
        (args.saved, "--saved"),
        (args.exclude_file, "--exclude-file"),
    )

    if args.inspect:
        targets = [(args.chatgpt, "chatgpt"), (args.claude, "claude")]
        if not any(path for path, _ in targets):
            parser.error("--inspect needs --chatgpt and/or --claude <export>")
        for path, source in targets:
            if not path:
                continue
            print(f"\n{source}, {path}")
            for key, value in inspect_export(path, source).items():
                print(f"  {key.replace('_', ' '):<20} {value}")
        return 0

    if not (args.chatgpt or args.claude or args.saved):
        parser.error("give at least one of --chatgpt, --claude, --saved")

    records: list[dict[str, Any]] = []

    for path, source in ((args.saved, "chatgpt"),):
        if path:
            print(f"Classifying saved memories from {path}...")
            saved = classify_saved(path, source)
            print(f"  {len(saved)} saved memories typed")
            records += saved

    conversation_sources = [
        (args.chatgpt, "chatgpt", read_chatgpt),
        (args.claude, "claude", read_claude),
    ]
    if any(path for path, _, _ in conversation_sources):
        if not args.agent:
            parser.error("--agent is required to distill conversations")
        # The CLI's own factory: resolves the API key, picks cloud vs on-prem
        # and restores the active session, exactly as every memanto command does.
        client = get_client()
        # Distillation is a session-based operation. run.sh activates the agent
        # before calling this script, but liberate.py is documented as a
        # standalone command too, and with no live session every thread fails
        # with the same opaque "No active session" error, one per thread, after
        # the extraction call has already been paid for. Activate once, up
        # front, so the failure is immediate and says what to do about it.
        try:
            client.activate_agent(args.agent)
        except Exception as exc:  # noqa: BLE001, reported as a clean message
            raise SystemExit(
                f"Could not activate agent {args.agent!r}: {exc}\n"
                f"Create it first: memanto agent create {args.agent} --pattern tool"
            ) from exc
        for path, source, reader in conversation_sources:
            if not path:
                continue
            print(f"Distilling {source} conversations from {path}...")
            threads = reader(path)
            if args.limit:
                threads = (c for i, c in enumerate(threads) if i < args.limit)
            records += distill(
                client, args.agent, threads, source, args.max_per_conversation
            )

    patterns = [args.exclude] if args.exclude else []
    if args.exclude_file:
        patterns += [
            line.strip()
            for line in args.exclude_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    if patterns:
        records, dropped = exclude_matching(records, "|".join(patterns))
        by_type: dict[str, int] = {}
        for memory_type in dropped:
            by_type[memory_type] = by_type.get(memory_type, 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in sorted(by_type.items())) or "none"
        print(f"\nPrivacy filter excluded {len(dropped)} memory(ies): {summary}")
        print("  (titles withheld: a title that matched the pattern is sensitive)")

    if not records:
        print("No memories extracted, nothing to write.", file=sys.stderr)
        return 1

    result = write_bundle(records, args.out, args.out.name)

    if args.okf_version == "0.2":
        counts = okf_v02.upgrade(args.out, records, PRODUCER)
        print(
            f"OKF v0.2: upgraded {counts['documents']} document(s), "
            f"rewrote {counts['indexes']} index file(s)"
        )

    broken = verify_links(args.out)
    if broken:
        print(
            f"\nWARNING: {len(broken)} unresolved link(s) in the bundle:",
            file=sys.stderr,
        )
        for item in broken[:10]:
            print(f"  {item}", file=sys.stderr)

    print(f"\nOKF bundle: {result['output_path']}")
    print(f"Memories:   {result['total_memories']}")
    for memory_type, count in sorted(result["per_type_counts"].items()):
        print(f"  {memory_type:<12} {count}")
    print(f"\nNext:  memanto migrate okf {args.out} --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
