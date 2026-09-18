"""Convert an opencode export to a portable OKF bundle.

Reads ``opencode_export.json`` (see ``export_opencode.py`` or
``make_sample_store.py``) and writes one markdown file per memory into an
OKF bundle directory that ``memanto migrate okf <bundle>`` can import
losslessly — unmapped fields travel in ``x_memanto``/frontmatter extras.

Memory mapping (see MAPPING.md):
    session                -> context   (project/session summary + cost/tokens)
    user text part         -> goal      (what the user asked for)
    assistant text part    -> decision  (conclusions, or learning when it
                                         states a reusable lesson)
    tool part (completed)  -> artifact  (command + truncated output)
    tool part (error)      -> observation (failures worth remembering)
    step-finish            -> skipped (folded into the session context)

Usage:
    python opencode_to_okf.py [--in opencode_export.json] [--out ./okf-bundle]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VALID_TYPES = {
    "fact", "preference", "goal", "decision", "artifact", "learning",
    "event", "instruction", "relationship", "context", "observation",
    "procedure", "opinion",
}

TEXT_TRUNCATE = 2000
TOOL_TRUNCATE = 1200


def _slug(text: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "memory")[:limit]


def _ts(ms: int | None) -> str:
    if not ms:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _frontmatter(meta: dict, body: str) -> str:
    lines = ["---"]
    for key in ("type", "title", "description", "resource", "tags", "timestamp"):
        value = meta.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(json.dumps(str(v)) for v in value)}]")
        else:
            lines.append(f"{key}: {json.dumps(value)}")
    # Top-level extras: the OKF loader preserves unknown frontmatter keys as
    # "extra" and map_okf surfaces them in the row footer, so session
    # metadata survives real imports (x_memanto alone is lossy).
    for k, v in (meta.get("extra") or {}).items():
        lines.append(f"{k}: {json.dumps(v, default=str)}")
    if meta.get("x_memanto"):
        lines.append("x_memanto:")
        for k, v in meta["x_memanto"].items():
            lines.append(f"  {k}: {json.dumps(v, default=str)}")
    lines.append("---")
    lines.append(body.strip() + "\n")
    return "\n".join(lines)


def _provenance_extra(*, session_id, project_id=None, message_id=None,
                      role=None, tool=None, status=None, model=None,
                      tokens_input=None, tokens_output=None, cost=None) -> dict:
    """Top-level frontmatter extras (survive import via the loader's extra path)."""
    extra = {"opencode_session_id": session_id}
    if project_id is not None:
        extra["opencode_project_id"] = project_id
    if message_id is not None:
        extra["opencode_message_id"] = message_id
    if role is not None:
        extra["opencode_role"] = role
    if tool is not None:
        extra["opencode_tool"] = tool
    if status is not None:
        extra["opencode_tool_status"] = status
    if model:
        extra["opencode_model"] = model
    if tokens_input is not None:
        extra["opencode_tokens_input"] = tokens_input
    if tokens_output is not None:
        extra["opencode_tokens_output"] = tokens_output
    if cost is not None:
        extra["opencode_cost_usd"] = cost
    return extra


def convert(export: dict) -> list[dict]:
    """Return a list of ``{"path": ..., "meta": ..., "body": ...}`` memories."""
    memories: list[dict] = []
    for s in export.get("sessions", []):
        title = s.get("title") or s.get("slug") or s["id"]
        directory = s.get("directory") or ""
        agent = s.get("agent") or "unknown"
        model = s.get("model") or ""
        n_msg = len(s.get("messages", []))

        # 1. session -> context
        memories.append({
            "dir": "context",
            "meta": {
                "type": "context",
                "title": f"opencode session: {title}",
                "description": (
                    f"Coding session '{title}' in {directory} "
                    f"({n_msg} messages, agent={agent})."
                ),
                "tags": ["opencode", "session", f"agent:{agent}"],
                "timestamp": _ts(s.get("time_updated") or s.get("time_created")),
                "extra": _provenance_extra(
                    session_id=s["id"], project_id=s.get("project_id"),
                    model=model, tokens_input=s.get("tokens_input"),
                    tokens_output=s.get("tokens_output"), cost=s.get("cost"),
                ),
                "x_memanto": {
                    "source": "opencode",
                    "provenance": "imported",
                    "session_id": s["id"],
                    "project_id": s.get("project_id"),
                    "model": model,
                    "tokens_input": s.get("tokens_input"),
                    "tokens_output": s.get("tokens_output"),
                    "cost": s.get("cost"),
                    "type": "context",
                },
            },
            "body": (
                f"# {title}\n\nopencode session `{s['id']}` in `{directory}` "
                f"used {n_msg} messages "
                f"({s.get('tokens_input', 0)} in / {s.get('tokens_output', 0)} out tokens, "
                f"cost ${s.get('cost', 0)})."
            ),
        })

        for m in s.get("messages", []):
            mdata = m.get("data", {}) or {}
            role = mdata.get("role", "user")
            for p in m.get("parts", []):
                pdata = p.get("data", {}) or {}
                ptype = pdata.get("type")
                if ptype == "text":
                    text = (pdata.get("text") or "").strip()
                    if not text or len(text) < 3:
                        continue
                    text = text[:TEXT_TRUNCATE]
                    if role == "user":
                        mtype, mdir = "goal", "goal"
                        desc = f"User request in '{title}'."
                        tags = ["opencode", "user-request"]
                    else:
                        lowered = text.lower()
                        if any(k in lowered for k in (
                            "lesson", "remember", "note that", "keep in mind",
                            "going forward", "rule of thumb",
                        )):
                            mtype, mdir = "learning", "learning"
                        else:
                            mtype, mdir = "decision", "decision"
                        desc = f"Assistant conclusion in '{title}'."
                        tags = ["opencode", "assistant-output"]
                    memories.append({
                        "dir": mdir,
                        "meta": {
                            "type": mtype,
                            "title": text[:80],
                            "description": desc,
                            "tags": tags,
                            "timestamp": _ts(p.get("time_created")),
                            "extra": _provenance_extra(
                                session_id=s["id"], message_id=m.get("id"),
                                role=role,
                            ),
                            "x_memanto": {
                                "source": "opencode",
                                "provenance": "imported",
                                "session_id": s["id"],
                                "message_id": m.get("id"),
                                "role": role,
                                "type": mtype,
                            },
                        },
                        "body": text,
                    })
                elif ptype == "tool":
                    tool = pdata.get("tool", "tool")
                    state = pdata.get("state", {}) or {}
                    status = state.get("status", "unknown")
                    # Only finished calls become durable memories: explicit
                    # success -> artifact, error -> observation. Anything still
                    # in flight (pending/running/cancelled/unknown) is skipped
                    # so we never persist an unfinished call as a success.
                    if status in ("completed", "success"):
                        mtype, mdir = "artifact", "artifact"
                        desc = f"{tool} call in '{title}' ({status})."
                    elif status == "error":
                        mtype, mdir = "observation", "observation"
                        desc = f"Failed {tool} call in '{title}'."
                    else:
                        continue
                    cmd = json.dumps(state.get("input", ""), default=str)[:300]
                    output = state.get("output", "")
                    if not isinstance(output, str):
                        output = json.dumps(output, default=str)
                    output = output[:TOOL_TRUNCATE]
                    memories.append({
                        "dir": mdir,
                        "meta": {
                            "type": mtype,
                            "title": f"{tool}: {cmd[:70]}",
                            "description": desc,
                            "tags": ["opencode", "tool-call", f"tool:{tool}", f"status:{status}"],
                            "timestamp": _ts(p.get("time_created")),
                            "extra": _provenance_extra(
                                session_id=s["id"], message_id=m.get("id"),
                                tool=tool, status=status,
                            ),
                            "x_memanto": {
                                "source": "opencode",
                                "provenance": "imported",
                                "session_id": s["id"],
                                "tool": tool,
                                "status": status,
                                "type": mtype,
                            },
                        },
                        "body": f"## {tool} ({status})\n\nInput: `{cmd}`\n\nOutput:\n\n```\n{output}\n```",
                    })
                # step-start / step-finish / reasoning folded into context
    return memories


def _replace_bundle(staging: Path, out: Path) -> None:
    """Swap a fully rendered bundle into place (mirrors
    ``OkfExportService._replace_bundle``): under the exclusive bundle lock,
    rename the existing bundle to a backup, install staging, restore the
    backup if installation fails. Falls back to plain replace when memanto
    itself is not importable (standalone converter use).
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from memanto.app.utils.atomic_write import okf_bundle_lock
    except ImportError:  # standalone use: no lock coordination available
        if out.exists():
            shutil.rmtree(out)
        os.replace(staging, out)
        return

    with okf_bundle_lock(out, shared=False):
        backup = None
        if out.exists():
            backup = Path(tempfile.mkdtemp(
                prefix=f".{out.name}.backup-", dir=str(out.parent)))
            backup.rmdir()
            out.rename(backup)
        try:
            staging.rename(out)
        except Exception:
            if backup is not None and backup.exists() and not out.exists():
                backup.rename(out)
            raise
        else:
            if backup is not None:
                shutil.rmtree(backup)


def write_bundle(memories: list[dict], out: Path) -> list[Path]:
    """Write memories to ``out`` via a staging dir + atomic replace.

    The loader imports every ``*.md`` under ``memories/``, so re-running
    into an existing bundle must not leave stale files behind.
    """
    import shutil
    import tempfile

    for mem in memories:
        assert mem["meta"]["type"] in VALID_TYPES, f"invalid OKF type: {mem['meta']['type']}"
    staging_parent = out.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=out.name + ".", dir=staging_parent))
    try:
        written: list[Path] = []
        counters: dict[str, int] = {}
        for mem in memories:
            counters[mem["dir"]] = counters.get(mem["dir"], 0) + 1
            fname = f"{counters[mem['dir']]:04d}-{_slug(mem['meta']['title'])}.md"
            dest = staging / "memories" / mem["dir"] / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_frontmatter(mem["meta"], mem["body"]))
            written.append(out / "memories" / mem["dir"] / fname)
        (staging / "index.md").write_text(
            "# opencode memory export\n\n"
            f"{len(written)} memories migrated from opencode sessions. "
            "Import with `memanto migrate okf <this-dir>`.\n"
        )
        _replace_bundle(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="opencode_export.json")
    ap.add_argument("--out", default="okf-bundle")
    args = ap.parse_args()

    export = json.loads(Path(args.inp).read_text())
    memories = convert(export)
    written = write_bundle(memories, Path(args.out))
    by_type: dict[str, int] = {}
    for mem in memories:
        by_type[mem["meta"]["type"]] = by_type.get(mem["meta"]["type"], 0) + 1
    print(f"wrote {len(written)} memories -> {args.out}")
    print("by type:", json.dumps(by_type, indent=2))


if __name__ == "__main__":
    main()
