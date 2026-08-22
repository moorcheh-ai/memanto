#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import random
import re
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).parent
SAMPLE_DIR = SCRIPT_DIR.parent / "sample_data"
REPO_ROOT = SCRIPT_DIR.parents[2]

_GEMINI_INNER = "Takeout/My Activity/Gemini Apps/My Activity.json"

def _default_path(env_var: str, *fallback_globs: str) -> Path | None:
    """Resolve a path from an environment variable or repository-relative fallback patterns.
    
    Parameters:
    	env_var (str): Name of the environment variable containing the preferred path.
    	fallback_globs (str): Glob patterns used to find a fallback path relative to the repository root.
    
    Returns:
    	Path | None: The existing configured or first matching fallback path, or `None` if no path is found.
    """
    val = os.environ.get(env_var)
    if val:
        p = Path(val)
        return p if p.exists() else None
    for pattern in fallback_globs:
        matches = list(REPO_ROOT.glob(pattern))
        if matches:
            return matches[0]
    return None

def _default_gemini_zip() -> Path | None:
    """
    Find the Gemini export ZIP specified by the environment or by scanning repository-root takeout archives.
    
    Returns:
    	Path | None: An existing path containing the expected Gemini activity JSON, or `None` if no matching archive is found.
    """
    val = os.environ.get("GEMINI_EXPORT_ZIP")
    if val:
        p = Path(val)
        return p if p.exists() else None
    for p in REPO_ROOT.glob("takeout*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                if _GEMINI_INNER in z.namelist():
                    return p
        except Exception:
            continue
    return None

DEFAULT_CHATGPT = _default_path("CHATGPT_EXPORT_ZIP", "chatgpt*.zip", "99b05f78*.zip")
DEFAULT_CLAUDE  = _default_path("CLAUDE_EXPORT_ZIP",  "data-*.zip", "claude-data.zip")
DEFAULT_GEMINI  = _default_gemini_zip()

TITLES = [
    "Implementing async Rust with Tokio",
    "Debugging lifetime errors in Rust",
    "Comparing LLM embedding models",
    "Comparing agent memory systems: mem0, Memanto, and plain vector DB",
    "Running Qdrant with Docker and Rust client",
    "Open-sourcing an LLM memory benchmarking tool",
    "Optimizing Rust binary size",
    "Building a RAG pipeline for a codebase",
    "Contributing to ripgrep",
    "Tracking memory provenance for AI agents",
]

EXCHANGES = [
    (
        "I am working on a Rust library for async file I/O using Tokio. "
        "The read_to_string calls are blocking — should I use spawn_blocking or tokio::fs?",
        "tokio::fs is the idiomatic choice here. It wraps spawn_blocking internally "
        "but gives you the async fn ergonomics. Use std::fs only when you are in a "
        "sync context or when the file is tiny.",
    ),
    (
        "Getting a lifetime error in my parser: `error[E0597]: borrowed value does not live long enough`. "
        "The borrow is inside a loop and I store references to it. What is the pattern here?",
        "You probably need owned data in the collection. Either clone the value or "
        "use an arena allocator like `bumpalo` so the lifetime outlives the loop.",
    ),
    (
        "Comparing text-embedding-3-small vs bge-m3 for a semantic search index over Rust docs. "
        "My queries are short, documents are medium length. Which would you pick?",
        "bge-m3 is stronger for technical retrieval with asymmetric queries. "
        "text-embedding-3-small is faster and cheaper if you are on OpenAI already. "
        "Run a quick BEIR-style eval on a sample before committing.",
    ),
    (
        "My LLM agent needs persistent memory across sessions. "
        "I am evaluating mem0, Memanto and a plain vector DB. "
        "What are the tradeoffs from an architecture standpoint?",
        "Plain vector DB gives you full control but you manage chunking, deduplication "
        "and retrieval logic yourself. mem0 adds an extraction layer but the schema is "
        "opinionated. Memanto focuses on typed memories and provenance, which matters "
        "when you want to audit what the agent knows.",
    ),
    (
        "How do I set up Qdrant locally with Docker and connect it from a Rust client?",
        "Run `docker run -p 6333:6333 qdrant/qdrant`. "
        "Then add the `qdrant-client` crate and use `QdrantClient::new(None)` for localhost. "
        "Create a collection with the vector size matching your embedding model.",
    ),
    (
        "I want to open-source my LLM memory benchmarking tool. "
        "What license and repo structure would you recommend?",
        "MIT is the default choice for maximum adoption. "
        "Apache 2.0 adds patent protection if that matters. "
        "For structure: keep the core library in `src/`, CLI in `cli/`, "
        "benchmarks in `benches/`, and examples in `examples/`.",
    ),
    (
        "Trying to shrink my Rust binary for a CLI tool. "
        "Currently 8 MB stripped. What levers should I pull?",
        "Set `opt-level = 'z'`, `lto = true`, `codegen-units = 1` and `strip = true` "
        "in your release profile. If you have a heavy dependency, check `cargo bloat` "
        "to find the culprit. Consider `upx --best` as a last resort.",
    ),
    (
        "Building a RAG pipeline for a codebase. "
        "Should I chunk by file, by function, or by token window?",
        "Function-level chunks work best for code retrieval — they preserve semantic "
        "boundaries and give the LLM a complete, runnable unit. "
        "Fall back to fixed-size token windows for prose documentation.",
    ),
    (
        "What is the recommended way to submit a first contribution to ripgrep?",
        "Start with a bug fix or a well-scoped feature from the issue tracker. "
        "Run `cargo test` and `cargo clippy` before opening a PR. "
        "Keep the diff small — Andrew Gallant reviews quickly when the scope is tight.",
    ),
    (
        "I need a simple way to track which memories my AI agent added vs which it "
        "inherited from a migration. Is there a provenance field I should use?",
        "Yes — store a `provenance` field with values like `agent`, `imported`, or `seeded`. "
        "That lets you filter or weight memories differently depending on their origin.",
    ),
]

_rng = random.Random(42)


def _fake_uuid() -> str:
    """Generate a deterministic UUID string using the module's random number generator."""
    return str(uuid.UUID(int=_rng.getrandbits(128)))


def _fake_ts(base: float = 1_750_000_000.0) -> float:
    """Generate a deterministic timestamp offset from the specified base value.
    
    Parameters:
    	base (float): The starting timestamp value.
    
    Returns:
    	float: The base value plus a deterministic random offset of up to 60 days.
    """
    return base + _rng.uniform(0, 86_400 * 60)


def _fake_iso(base: float = 1_750_000_000.0) -> str:
    """
    Convert a generated timestamp to an ISO 8601 string in UTC.
    
    Parameters:
    	base (float): The base Unix timestamp used to generate the timestamp.
    
    Returns:
    	str: A timezone-aware UTC timestamp in ISO 8601 format.
    """
    t = _fake_ts(base)
    return datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).isoformat()


def _pick_exchange(i: int) -> tuple[str, str]:
    """Select a user query and assistant response from the available exchanges.
    
    Parameters:
    	i (int): Index used to select an exchange, wrapping around when necessary.
    
    Returns:
    	tuple[str, str]: The selected user query and assistant response.
    """
    return EXCHANGES[i % len(EXCHANGES)]


def _read_zip_json(src: Path, inner_path: str) -> object:
    """Read and parse a JSON file from a ZIP archive.
    
    Parameters:
        src (Path): Path to the ZIP archive.
        inner_path (str): Path of the JSON file inside the archive.
    
    Returns:
        object: The parsed JSON value.
    """
    with zipfile.ZipFile(src) as z:
        with z.open(inner_path) as f:
            return json.load(f)


def _write_zip(entries: dict[str, object]) -> bytes:
    """Create an in-memory ZIP archive containing the provided JSON entries.
    
    Parameters:
    	entries (dict[str, object]): Mapping of archive paths to JSON-serializable data.
    
    Returns:
    	bytes: The encoded ZIP archive.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc_path, data in entries.items():
            z.writestr(arc_path, json.dumps(data, indent=2))
    return buf.getvalue()


def _verify(zip_bytes: bytes, inner_path: str, to_memories: Callable, mapper: Callable) -> int:
    """
    Count the mapped memories produced from JSON stored in a ZIP archive.
    
    Parameters:
    	zip_bytes (bytes): ZIP archive contents.
    	inner_path (str): Path of the JSON file inside the archive.
    	to_memories (Callable): Converts the decoded JSON to memory data.
    	mapper (Callable): Maps the memory data to migration payloads.
    
    Returns:
    	int: Number of payloads produced by the mapper.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        with z.open(inner_path) as f:
            raw = json.load(f)
    return len(mapper({"memories": to_memories(raw)}))


# ---------------------------------------------------------------------------
# ChatGPT
# ---------------------------------------------------------------------------

def _build_chatgpt_conv(ci: int) -> dict:
    """
    Build a synthetic ChatGPT conversation record with deterministic identifiers, timestamps, and sample exchange content.
    
    Parameters:
    	ci (int): Index used to select the sample exchange and conversation title.
    
    Returns:
    	dict: A ChatGPT-compatible conversation mapping containing user and assistant messages.
    """
    user_q, asst_a = _pick_exchange(ci)
    root_id, user_id, asst_id = _fake_uuid(), _fake_uuid(), _fake_uuid()
    conv_id = _fake_uuid()
    return {
        "id": conv_id,
        "conversation_id": conv_id,
        "title": TITLES[ci % len(TITLES)],
        "create_time": _fake_ts(),
        "update_time": _fake_ts(),
        "current_node": asst_id,
        "mapping": {
            root_id: {"id": root_id, "message": None, "parent": None},
            user_id: {
                "id": user_id,
                "message": {
                    "id": user_id,
                    "author": {"role": "user", "name": None},
                    "create_time": _fake_ts(),
                    "content": {"content_type": "text", "parts": [user_q]},
                    "metadata": {},
                },
                "parent": root_id,
            },
            asst_id: {
                "id": asst_id,
                "message": {
                    "id": asst_id,
                    "author": {"role": "assistant", "name": None},
                    "create_time": _fake_ts(),
                    "content": {"content_type": "text", "parts": [asst_a]},
                    "metadata": {},
                },
                "parent": user_id,
            },
        },
    }


def deidentify_chatgpt(src: Path) -> bytes:
    """
    Create a de-identified ChatGPT export ZIP from a source export.
    
    Parameters:
        src (Path): Path to the source ZIP containing ``conversations.json``.
    
    Returns:
        bytes: ZIP archive containing up to five synthetic conversations in
            ``conversations.json``.
    """
    real = _read_zip_json(src, "conversations.json")
    convs = [_build_chatgpt_conv(i) for i in range(min(5, len(real)))]
    return _write_zip({"conversations.json": convs})


def verify_chatgpt(zip_bytes: bytes) -> int:
    """Validate a ChatGPT export ZIP by mapping its conversation data.
    
    Parameters:
    	zip_bytes (bytes): ZIP archive containing a `conversations.json` file.
    
    Returns:
    	int: Number of mapped memories produced from the export.
    """
    from examples.migrations.mappers import map_chatgpt
    return _verify(zip_bytes, "conversations.json", lambda raw: raw, map_chatgpt)


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

def _build_claude_conv(ci: int) -> dict:
    """Build a synthetic Claude conversation with deterministic identifiers, timestamps, and message content.
    
    Parameters:
    \tci (int): Index used to select the conversation title and exchange content.
    
    Returns:
    \ta dictionary containing the generated Claude conversation.
    """
    user_q, asst_a = _pick_exchange(ci + 5)
    base_ts = _fake_ts()
    human_uuid, asst_uuid = _fake_uuid(), _fake_uuid()
    return {
        "uuid": _fake_uuid(),
        "name": TITLES[(ci + 5) % len(TITLES)],
        "created_at": _fake_iso(base_ts),
        "updated_at": _fake_iso(base_ts + 3600),
        "chat_messages": [
            {
                "uuid": human_uuid,
                "text": user_q,
                "content": [{"start_timestamp": _fake_iso(base_ts), "stop_timestamp": _fake_iso(base_ts + 1), "flags": None, "type": "text", "text": user_q}],
                "sender": "human",
                "created_at": _fake_iso(base_ts),
                "updated_at": _fake_iso(base_ts + 1),
                "attachments": [],
                "files": [],
                "parent_message_uuid": None,
            },
            {
                "uuid": asst_uuid,
                "text": asst_a,
                "content": [{"start_timestamp": _fake_iso(base_ts + 2), "stop_timestamp": _fake_iso(base_ts + 5), "flags": None, "type": "text", "text": asst_a}],
                "sender": "assistant",
                "created_at": _fake_iso(base_ts + 2),
                "updated_at": _fake_iso(base_ts + 5),
                "attachments": [],
                "files": [],
                "parent_message_uuid": human_uuid,
            },
        ],
    }


def deidentify_claude(src: Path) -> bytes:
    """
    Create a de-identified Claude export ZIP from a source export.
    
    Parameters:
        src (Path): Path to the source ZIP containing ``conversations.json``.
    
    Returns:
        bytes: ZIP archive containing up to five synthetic conversations in
            ``conversations.json``.
    """
    real = _read_zip_json(src, "conversations.json")
    convs = [_build_claude_conv(i) for i in range(min(5, len(real)))]
    return _write_zip({"conversations.json": convs})


def verify_claude(zip_bytes: bytes) -> int:
    """
    Verify a generated Claude export ZIP with the Claude migration mapper.
    
    Parameters:
    	zip_bytes (bytes): ZIP archive containing a Claude `conversations.json` file.
    
    Returns:
    	int: Number of mapped memories produced from the archive.
    """
    from examples.migrations.mappers import map_claude
    return _verify(zip_bytes, "conversations.json", lambda raw: raw, map_claude)


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def _build_gemini_entry(ci: int) -> dict:
    """Build a synthetic Gemini activity entry for the specified exchange index.
    
    Parameters:
    	ci (int): Index used to select the source exchange.
    
    Returns:
    	dict: A de-identified Gemini activity entry containing the selected prompt and a generated timestamp.
    """
    user_q, _ = _pick_exchange(ci + 2)
    entry: dict = {
        "header": "Gemini Apps",
        "title": f"Prompted {user_q[:80]}",
        "subtitles": [],
        "time": _fake_iso(_fake_ts()),
        "products": ["Gemini Apps"],
        "activityControls": ["Gemini Apps Activity"],
    }
    return entry


def deidentify_gemini(src: Path) -> bytes:
    """Create a de-identified Gemini export ZIP from a source export.
    
    Parameters:
    	src (Path): Path to the source Gemini export ZIP.
    
    Returns:
    	bytes: ZIP data containing synthetic Gemini activity entries.
    """
    real = _read_zip_json(src, _GEMINI_INNER)
    entries = [_build_gemini_entry(i) for i in range(min(5, len(real)))]
    return _write_zip({_GEMINI_INNER: entries})


def verify_gemini(zip_bytes: bytes) -> int:
    """
    Verify that a generated Gemini export can be processed by the Gemini mapper.
    
    Parameters:
    	zip_bytes (bytes): Generated Gemini export ZIP data.
    
    Returns:
    	int: Number of mapped memories produced from matching Gemini entries.
    """
    from examples.migrations.mappers import map_gemini

    def to_memories(raw: list) -> list:
        """Convert matching Gemini activity entries into memory objects.
        
        Parameters:
        	raw (list): Gemini activity entries to transform.
        
        Returns:
        	list: Memory objects created from entries whose titles start with "Prompted ".
        """
        return [
            {"messages": [{"role": "user", "text": e["title"].removeprefix("Prompted ")}], "createdTime": e.get("time"), "id": _fake_uuid()}
            for e in raw if e.get("title", "").startswith("Prompted ")
        ]

    return _verify(zip_bytes, _GEMINI_INNER, to_memories, map_gemini)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PROVIDERS: list[tuple[str, Path | None, str, Callable, Callable]] = [
    ("chatgpt", DEFAULT_CHATGPT, "chatgpt_export.zip", deidentify_chatgpt, verify_chatgpt),
    ("claude", DEFAULT_CLAUDE, "claude_export.zip", deidentify_claude, verify_claude),
    ("gemini", DEFAULT_GEMINI, "gemini_export.zip", deidentify_gemini, verify_gemini),
]


def main() -> None:
    """
    Generate de-identified sample export ZIP files and verify their mapper output.
    
    Command-line options specify source exports for ChatGPT, Claude, and Gemini. Missing sources are skipped; the process exits with status 1 if any processed export produces no mapped payloads.
    """
    parser = argparse.ArgumentParser(description="Generate de-identified sample export ZIPs")
    parser.add_argument("--chatgpt", type=Path, default=DEFAULT_CHATGPT)
    parser.add_argument("--claude", type=Path, default=DEFAULT_CLAUDE)
    parser.add_argument("--gemini", type=Path, default=DEFAULT_GEMINI)
    args = parser.parse_args()

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO_ROOT))

    src_map = {"chatgpt": args.chatgpt, "claude": args.claude, "gemini": args.gemini}
    all_ok = True

    for name, _default, out_name, deident_fn, verify_fn in PROVIDERS:
        src = src_map[name]
        out_path = SAMPLE_DIR / out_name

        if src is None or not Path(src).exists():
            print(f"[skip] {name}: source not found ({src})")
            continue

        print(f"[{name}] reading {src} ...")
        zip_bytes = deident_fn(Path(src))
        out_path.write_bytes(zip_bytes)
        print(f"[{name}] wrote {out_path} ({len(zip_bytes):,} bytes)")

        n = verify_fn(zip_bytes)
        if n > 0:
            print(f"[{name}] mapper produced {n} payload(s) — OK")
        else:
            print(f"[{name}] ERROR: mapper produced 0 payloads", file=sys.stderr)
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
