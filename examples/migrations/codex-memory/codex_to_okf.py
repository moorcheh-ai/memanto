#!/usr/bin/env python3
"""
codex_to_okf.py — migrate OpenAI Codex CLI agent memory into Memanto.

Codex keeps your agent's accumulated memory in a proprietary local store:

    ~/.codex/memories_1.sqlite   stage1_outputs  -- the distilled memories
    ~/.codex/goals_1.sqlite      thread_goals    -- long-running objectives
    ~/.codex/state_5.sqlite      threads         -- session/episode registry
    ~/.codex/sessions/**/*.jsonl rollout-*       -- full transcripts, incl.
                                                    hidden reasoning traces
                                                    and compaction checkpoints

None of it is portable. There is no `codex export`. This adapter turns the
whole store into a standards-based **OKF (Open Knowledge Format)** bundle —
plain markdown with YAML frontmatter — that `memanto migrate okf` ingests
directly, and that you can also read, grep, git-version and review yourself.

Usage
-----
    python codex_to_okf.py --out ./okf-bundle                # migrate everything
    python codex_to_okf.py --out ./okf-bundle --dry-run      # preview mapping
    python codex_to_okf.py --include-reasoning               # also take the CoT
    python codex_to_okf.py --no-redact                       # keep raw paths

Then:

    memanto migrate okf ./okf-bundle --dry-run
    memanto migrate okf ./okf-bundle
    memanto memory export --okf -o ./roundtrip

Field mapping (Codex concept -> Memanto memory type) is documented in
MAPPING.md; the authoritative Memanto type is written to the namespaced
``x_memanto.type`` frontmatter key, while OKF's free-form ``type`` keeps the
source concept name so non-Memanto consumers still see where it came from.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

MEMANTO_TYPES = {
    "artifact", "commitment", "context", "decision", "error", "event", "fact",
    "goal", "instruction", "learning", "observation", "preference", "relationship",
}

ENTRY_DELIMITER = "<!-- okf-entry -->"
BUNDLE_VERSION = "okf/0.2"

# ---------------------------------------------------------------- redaction --
# Codex stores absolute paths, user names, e-mail addresses and host names.
# Migration output is meant to be shareable, so redaction is on by default.
_HOME = str(Path.home())
_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(re.escape(_HOME), re.IGNORECASE), "~"),
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+", re.IGNORECASE), "~"),
    (re.compile(r"/Users/[^/\s\"']+"), "~"),
    (re.compile(r"/home/[^/\s\"']+"), "~"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"),
    (re.compile(r"\b(?:ghp|gho|ghs|sk|xox[baprs])[-_][A-Za-z0-9_-]{16,}\b"), "<token>"),
]


def redact(text: str, enabled: bool) -> str:
    if not enabled or not text:
        return text
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


# ------------------------------------------------------------------- helpers --
def slugify(value: str, max_len: int = 60) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii") or "entry"
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return (value or "entry")[:max_len].rstrip("-")


def iso(ts: Any) -> str | None:
    """Best-effort timestamp -> ISO-8601 UTC string."""
    if ts in (None, "", 0):
        return None
    if isinstance(ts, (int, float)):
        seconds = ts / 1000.0 if ts > 1e11 else float(ts)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(ts)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{text}"'


def frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None or value == [] or value == {}:
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {yaml_scalar(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key, sub_value in value.items():
                if sub_value is None or sub_value == "":
                    continue
                lines.append(f"  {sub_key}: {yaml_scalar(sub_value)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


class Memory:
    """One portable memory destined for the OKF bundle."""

    __slots__ = ("type", "title", "description", "body", "tags", "timestamp", "extra")

    def __init__(
        self,
        *,
        type: str,
        title: str,
        body: str,
        description: str = "",
        tags: Iterable[str] = (),
        timestamp: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if type not in MEMANTO_TYPES:
            raise ValueError(f"unknown Memanto memory type: {type}")
        self.type = type
        self.title = title.strip() or "(untitled)"
        self.body = body.strip()
        self.description = description.strip()
        self.tags = [t for t in tags if t]
        self.timestamp = timestamp
        self.extra = extra or {}

    def render(self) -> str:
        meta: dict[str, Any] = {
            "type": self.extra.pop("_okf_type", self.type),
            "title": self.title,
            "description": self.description or None,
            "tags": self.tags or None,
            "timestamp": self.timestamp,
            "x_memanto": {
                "type": self.type,
                "source": self.extra.get("source", "codex"),
                "provenance": self.extra.get("provenance", "imported"),
                "confidence": self.extra.get("confidence"),
                "updated_at": self.extra.get("updated_at"),
            },
        }
        for key, value in self.extra.items():
            if key.startswith("_") or key in {"source", "provenance", "confidence", "updated_at"}:
                continue
            meta[key] = value
        return f"{frontmatter(meta)}\n\n{self.body}\n"


# ------------------------------------------------------------------ Codex IO --
class CodexStore:
    def __init__(self, home: Path, *, redact_enabled: bool = True, include_reasoning: bool = False):
        self.home = home
        self.redact_enabled = redact_enabled
        self.include_reasoning = include_reasoning
        self.counts: Counter[str] = Counter()

    # -- sqlite helpers ------------------------------------------------------
    def _connect(self, name: str) -> sqlite3.Connection | None:
        path = self.home / name
        if not path.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as exc:  # pragma: no cover - environment dependent
            print(f"[warn] cannot open {name}: {exc}", file=sys.stderr)
            return None

    @staticmethod
    def _has_table(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "select 1 from sqlite_master where type='table' and name=?", (table,)
        ).fetchone()
        return row is not None

    # -- source 1: distilled memories ---------------------------------------
    def stage1_outputs(self, limit: int | None) -> Iterator[Memory]:
        conn = self._connect("memories_1.sqlite")
        if conn is None or not self._has_table(conn, "stage1_outputs"):
            return
        sql = (
            "select thread_id, raw_memory, rollout_summary, rollout_slug, generated_at, "
            "usage_count, source_updated_at from stage1_outputs order by generated_at desc"
        )
        if limit:
            sql += f" limit {int(limit)}"
        for row in conn.execute(sql):
            raw = redact(row["raw_memory"] or "", self.redact_enabled)
            summary = redact(row["rollout_summary"] or "", self.redact_enabled)
            if not raw and not summary:
                continue
            title = (row["rollout_slug"] or summary.splitlines()[0] if summary else "codex memory")[:120]
            body_parts = []
            if summary:
                body_parts.append("## Codex rollout summary\n\n" + summary)
            if raw:
                body_parts.append("## Raw memory\n\n" + raw)
            self.counts["stage1_outputs"] += 1
            yield Memory(
                type="fact",
                title=f"Codex memory · {title}",
                description=(summary.splitlines()[0] if summary else raw.splitlines()[0])[:200],
                body="\n\n".join(body_parts),
                tags=["codex", "distilled-memory"],
                timestamp=iso(row["generated_at"]),
                extra={
                    "source": "codex:memories_1.stage1_outputs",
                    "provenance": "inferred",
                    "thread_id": row["thread_id"],
                    "usage_count": row["usage_count"],
                    "_okf_type": "codex-distilled-memory",
                },
            )
        conn.close()

    # -- source 2: long-running objectives -----------------------------------
    def thread_goals(self, limit: int | None) -> Iterator[Memory]:
        conn = self._connect("goals_1.sqlite")
        if conn is None or not self._has_table(conn, "thread_goals"):
            return
        sql = "select thread_id, goal_id, objective, status from thread_goals"
        if limit:
            sql += f" limit {int(limit)}"
        for row in conn.execute(sql):
            objective = redact(row["objective"] or "", self.redact_enabled)
            if not objective:
                continue
            self.counts["thread_goals"] += 1
            yield Memory(
                type="goal",
                title=f"Codex goal · {objective.splitlines()[0][:100]}",
                description=f"status: {row['status']}",
                body=f"**Objective**\n\n{objective}\n\n**Status:** `{row['status']}`\n",
                tags=["codex", "goal", f"status:{row['status']}"],
                extra={
                    "source": "codex:goals_1.thread_goals",
                    "provenance": "explicit_statement",
                    "thread_id": row["thread_id"],
                    "goal_id": row["goal_id"],
                    "_okf_type": "codex-thread-goal",
                },
            )
        conn.close()

    # -- source 3: session registry ------------------------------------------
    def threads(self, limit: int | None) -> Iterator[Memory]:
        conn = self._connect("state_5.sqlite")
        if conn is None or not self._has_table(conn, "threads"):
            return
        cols = {r["name"] for r in conn.execute("pragma table_info(threads)")}
        wanted = [c for c in ("id", "thread_id", "title", "cwd", "created_at", "updated_at",
                              "model", "model_provider", "status", "source") if c in cols]
        if not wanted:
            return
        sql = f"select {', '.join(wanted)} from threads"
        if limit:
            sql += f" limit {int(limit)}"
        for row in conn.execute(sql):
            record = {k: row[k] for k in wanted}
            thread_id = str(record.get("id") or record.get("thread_id") or "")
            cwd = redact(str(record.get("cwd") or ""), self.redact_enabled)
            title = redact(str(record.get("title") or ""), self.redact_enabled)
            self.counts["threads"] += 1
            lines = [f"- `{k}`: {redact(str(v), self.redact_enabled)}" for k, v in record.items()
                     if v not in (None, "")]
            yield Memory(
                type="context",
                title=f"Codex session · {(title or cwd or thread_id)[:90]}",
                description=f"Codex session {thread_id[:8]} in {cwd}" if cwd else f"Codex session {thread_id[:8]}",
                body="**Codex session metadata (trapped in state_5.sqlite)**\n\n" + "\n".join(lines),
                tags=["codex", "session", "episode"],
                timestamp=iso(record.get("created_at") or record.get("updated_at")),
                extra={
                    "source": "codex:state_5.threads",
                    "provenance": "observed",
                    "thread_id": thread_id,
                    "_okf_type": "codex-session",
                },
            )
        conn.close()

    # -- source 4: rollout transcripts ---------------------------------------
    def rollout_files(self) -> list[Path]:
        sessions = self.home / "sessions"
        if not sessions.is_dir():
            archived = self.home / "archived_sessions"
            sessions = archived if archived.is_dir() else sessions
        if not sessions.is_dir():
            return []
        files = [p for p in sessions.rglob("*.jsonl") if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def rollout_memories(self, per_file: int) -> Iterator[Memory]:
        for path in self.rollout_files():
            produced = 0
            thread_id = path.stem
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if produced >= per_file:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    memory = self._rollout_line_to_memory(obj, thread_id)
                    if memory is not None:
                        produced += 1
                        yield memory

    def _rollout_line_to_memory(self, obj: dict[str, Any], thread_id: str) -> Memory | None:
        kind = obj.get("type")
        payload = obj.get("payload") or {}
        ts = iso(obj.get("timestamp"))

        if kind == "session_meta":
            instructions = payload.get("base_instructions")
            if not instructions:
                return None
            self.counts["base_instructions"] += 1
            return Memory(
                type="instruction",
                title=f"Codex base instructions · {thread_id[:8]}",
                description="System-level instructions Codex ran this session under.",
                body="**Base instructions this session was governed by**\n\n"
                     + redact(str(instructions), self.redact_enabled),
                tags=["codex", "instruction", "system-prompt"],
                timestamp=ts,
                extra={
                    "source": "codex:rollout.session_meta",
                    "provenance": "explicit_statement",
                    "thread_id": thread_id,
                    "cwd": redact(str(payload.get("cwd") or ""), self.redact_enabled),
                    "_okf_type": "codex-base-instructions",
                },
            )

        if kind == "compacted":
            self.counts["compacted"] += 1
            body = json.dumps(payload, ensure_ascii=False, indent=2)[:4000]
            return Memory(
                type="decision",
                title=f"Codex compaction checkpoint · {thread_id[:8]}",
                description="A memory-compaction event: Codex decided what to forget.",
                body="**Compaction event (the moment memory was rewritten)**\n\n"
                     f"```json\n{redact(body, self.redact_enabled)}\n```",
                tags=["codex", "compaction", "checkpoint"],
                timestamp=ts,
                extra={
                    "source": "codex:rollout.compacted",
                    "provenance": "observed",
                    "thread_id": thread_id,
                    "_okf_type": "codex-compaction",
                },
            )

        if kind != "response_item":
            return None

        item_type = payload.get("type")

        if item_type == "message":
            role = payload.get("role")
            text = self._extract_text(payload.get("content"))
            if not text:
                return None
            text = redact(text, self.redact_enabled)
            if role == "user":
                self.counts["user_message"] += 1
                return Memory(
                    type="preference",
                    title=f"Codex request · {text.splitlines()[0][:90]}",
                    description="What the human asked Codex to do — their intent, recorded.",
                    body=f"**User request (role: {role})**\n\n{text}",
                    tags=["codex", "user-intent"],
                    timestamp=ts,
                    extra={
                        "source": "codex:rollout.message",
                        "provenance": "explicit_statement",
                        "thread_id": thread_id,
                        "_okf_type": "codex-user-message",
                    },
                )
            self.counts["assistant_message"] += 1
            return Memory(
                type="observation",
                title=f"Codex answer · {text.splitlines()[0][:90]}",
                description="What Codex concluded or produced.",
                body=f"**Assistant message (role: {role})**\n\n{text}",
                tags=["codex", "assistant-output"],
                timestamp=ts,
                extra={
                    "source": "codex:rollout.message",
                    "provenance": "observed",
                    "thread_id": thread_id,
                    "_okf_type": "codex-assistant-message",
                },
            )

        if item_type == "reasoning":
            if not self.include_reasoning:
                self.counts["reasoning_skipped"] += 1
                return None
            text = self._extract_reasoning(payload)
            if not text:
                return None
            self.counts["reasoning"] += 1
            return Memory(
                type="learning",
                title=f"Codex reasoning trace · {thread_id[:8]}",
                description="Hidden chain-of-thought Codex never exposes through any export.",
                body="**Reasoning trace (normally invisible, never exportable from Codex)**\n\n"
                     + redact(text, self.redact_enabled),
                tags=["codex", "reasoning", "chain-of-thought"],
                timestamp=ts,
                extra={
                    "source": "codex:rollout.reasoning",
                    "provenance": "inferred",
                    "thread_id": thread_id,
                    "_okf_type": "codex-reasoning",
                },
            )

        if item_type in ("function_call", "custom_tool_call"):
            name = payload.get("name") or payload.get("tool_name") or "tool"
            args = payload.get("arguments") or payload.get("input") or ""
            self.counts["tool_call"] += 1
            return Memory(
                type="artifact",
                title=f"Codex tool call · {name}",
                description=f"Codex invoked `{name}`.",
                body=f"**Tool call:** `{name}`\n\n```json\n{redact(str(args), self.redact_enabled)[:3000]}\n```",
                tags=["codex", "tool-call", f"tool:{name}"],
                timestamp=ts,
                extra={
                    "source": "codex:rollout.tool_call",
                    "provenance": "observed",
                    "thread_id": thread_id,
                    "_okf_type": "codex-tool-call",
                },
            )

        return None

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        chunks = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
            elif isinstance(block, dict):
                for key in ("text", "content", "value"):
                    if isinstance(block.get(key), str):
                        chunks.append(block[key])
                        break
        return "\n\n".join(c for c in chunks if c).strip()

    @staticmethod
    def _extract_reasoning(payload: dict[str, Any]) -> str:
        parts: list[str] = []
        for key in ("summary", "content", "text"):
            value = payload.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                for block in value:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        parts.append(block["text"])
        return "\n\n".join(parts).strip()


# ------------------------------------------------------------------- writing --
def write_bundle(memories: Iterable[Memory], out_dir: Path, *, stacked: bool) -> dict[str, Any]:
    """Write memories as an OKF bundle (one folder per Memanto type)."""
    by_type: dict[str, list[Memory]] = defaultdict(list)
    for memory in memories:
        by_type[memory.type].append(memory)

    memories_root = out_dir / "memories"
    memories_root.mkdir(parents=True, exist_ok=True)

    used: set[str] = set()
    written: dict[str, int] = {}
    for mem_type, items in sorted(by_type.items()):
        type_dir = memories_root / mem_type
        type_dir.mkdir(parents=True, exist_ok=True)
        if stacked:
            # One file per type; documents separated by the okf-entry sentinel.
            text = f"\n\n{ENTRY_DELIMITER}\n\n".join(m.render().rstrip() for m in items)
            (type_dir / f"{mem_type}.md").write_text(text + "\n", encoding="utf-8")
            written[mem_type] = len(items)
            continue
        for index, memory in enumerate(items, start=1):
            base = slugify(memory.title)
            name = f"{index:04d}-{base}.md"
            while name in used:
                name = f"{index:04d}-{base}-{len(used)}.md"
            used.add(name)
            (type_dir / name).write_text(memory.render(), encoding="utf-8")
        written[mem_type] = len(items)

    (out_dir / "README.md").write_text(
        "# Codex → OKF memory bundle\n\n"
        "Portable, human-readable export of an OpenAI Codex CLI memory store.\n\n"
        "Import it into Memanto:\n\n"
        "```bash\nmemanto migrate okf . --dry-run\nmemanto migrate okf .\n```\n\n"
        "Every document under `memories/<type>/` is one memory: YAML frontmatter +\n"
        "Markdown body. `x_memanto.type` carries the authoritative Memanto memory\n"
        "type; the top-level `type` preserves the original Codex concept.\n",
        encoding="utf-8",
    )
    # index.md is skipped by the loader; it exists purely for human navigation.
    index_lines = ["# Codex memory bundle — index", "", "| Memanto type | memories |", "|---|---|"]
    for mem_type, count in sorted(written.items()):
        index_lines.append(f"| `{mem_type}` | {count} |")
    (out_dir / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    return {"per_type": written, "total": sum(written.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate an OpenAI Codex CLI memory store into a portable OKF bundle."
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
                        help="Path to the Codex store (default: ~/.codex).")
    parser.add_argument("--out", default="./okf-bundle", help="Output OKF bundle directory.")
    parser.add_argument("--limit", type=int, default=None, help="Max rows per SQLite source.")
    parser.add_argument("--rollout-per-file", type=int, default=40,
                        help="Max memories taken from each rollout transcript.")
    parser.add_argument("--include-reasoning", action="store_true",
                        help="Also migrate hidden reasoning traces (private; off by default).")
    parser.add_argument("--no-redact", action="store_true",
                        help="Keep absolute paths, e-mails and tokens verbatim.")
    parser.add_argument("--stacked", action="store_true",
                        help="Write one stacked file per type instead of one file per memory.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the mapping summary without writing any file.")
    args = parser.parse_args(argv)

    home = Path(args.codex_home).expanduser()
    if not home.is_dir():
        print(f"[error] Codex store not found: {home}", file=sys.stderr)
        print("        Pass --codex-home or set CODEX_HOME.", file=sys.stderr)
        return 2

    store = CodexStore(home, redact_enabled=not args.no_redact,
                       include_reasoning=args.include_reasoning)

    sources = [
        ("memories_1.stage1_outputs", store.stage1_outputs(args.limit)),
        ("goals_1.thread_goals", store.thread_goals(args.limit)),
        ("state_5.threads", store.threads(args.limit)),
        ("sessions/rollout-*.jsonl", store.rollout_memories(args.rollout_per_file)),
    ]

    def stream() -> Iterator[Memory]:
        for label, iterator in sources:
            try:
                for memory in iterator:
                    yield memory
            except sqlite3.Error as exc:
                print(f"[warn] {label}: {exc}", file=sys.stderr)

    bundle_source: Iterable[Memory]
    if args.dry_run:
        counter: Counter[str] = Counter()
        sample: list[str] = []
        total = 0
        for memory in stream():
            counter[memory.type] += 1
            total += 1
            if len(sample) < 8:
                sample.append(f"  {memory.type:12s} <- {memory.extra.get('source', '?')}  ::  {memory.title[:70]}")
        print(f"Codex store : {home}")
        print(f"Memories    : {total}")
        print("Mapping preview:")
        for line in sample:
            print(line)
        print("\nPer Memanto type:")
        for mem_type, count in sorted(counter.items()):
            print(f"  {mem_type:14s} {count}")
        print("\nSource counters:")
        for key, value in sorted(store.counts.items()):
            print(f"  {key:22s} {value}")
        print("\n[dry-run] nothing written. Re-run without --dry-run to build the bundle.")
        return 0

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    result = write_bundle(stream(), out_dir, stacked=args.stacked)

    print(f"Codex store : {home}")
    print(f"OKF bundle  : {out_dir}")
    print(f"Memories    : {result['total']}")
    for mem_type, count in sorted(result["per_type"].items()):
        print(f"  {mem_type:14s} {count}")
    print("\nNext:")
    print(f"  memanto migrate okf {out_dir} --dry-run")
    print(f"  memanto migrate okf {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
