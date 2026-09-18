"""Generate a synthetic opencode export for reproducible demos.

Creates a fictional, lived-in coding history (several sessions over weeks:
preferences, a correction, a contradiction resolution) in the exact schema
``export_opencode.py`` produces, so the showcase runs without touching
anyone's real ``~/.local/share/opencode/opencode.db``.

Usage:
    python make_sample_store.py [--out opencode_export.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE_MS = 1789000000000
DAY_MS = 86_400_000


def _msg(mid: str, role: str, parts: list[dict], offset_ms: int) -> dict:
    return {
        "id": mid,
        "session_id": "",
        "time_created": BASE_MS + offset_ms,
        "time_updated": BASE_MS + offset_ms,
        "data": {"role": role, "agent": "build"},
        "parts": [
            {"id": f"{mid}-p{i}", "data": p, "time_created": BASE_MS + offset_ms}
            for i, p in enumerate(parts)
        ],
    }


def _session(sid: str, title: str, day: int, messages: list[dict]) -> dict:
    for m in messages:
        m["session_id"] = sid
    return {
        "id": sid,
        "project_id": "demo-shop",
        "title": title,
        "slug": title.lower().replace(" ", "-"),
        "directory": "/home/demo/shop",
        "agent": "build",
        "model": '{"id":"demo-model","providerID":"demo"}',
        "tokens_input": 12000,
        "tokens_output": 3000,
        "cost": 0.02,
        "time_created": BASE_MS + day * DAY_MS,
        "time_updated": BASE_MS + day * DAY_MS + 3600_000,
        "messages": messages,
    }


def build() -> dict:
    sessions = [
        _session("ses_demo001", "Add cart drawer", 0, [
            _msg("m1", "user", [
                {"type": "text", "text": "Add a slide-in cart drawer to the storefront. Use Tailwind, no new dependencies."},
            ], 0),
            _msg("m2", "assistant", [
                {"type": "text", "text": "Done — CartDrawer component with Tailwind transitions. Remember: this repo forbids new npm dependencies without approval."},
                {"type": "tool", "tool": "edit", "state": {"status": "completed",
                 "input": {"file": "src/components/CartDrawer.tsx"},
                 "output": "created CartDrawer.tsx (180 lines)"}},
            ], 1000),
        ]),
        _session("ses_demo002", "Fix checkout totals bug", 6, [
            _msg("m3", "user", [
                {"type": "text", "text": "Checkout totals are off by one cent on discount orders. Find and fix."},
            ], 0),
            _msg("m4", "assistant", [
                {"type": "tool", "tool": "bash", "state": {"status": "completed",
                 "input": {"command": "pytest tests/test_totals.py"},
                 "output": "3 failed, 41 passed"}},
                {"type": "tool", "tool": "bash", "state": {"status": "error",
                 "input": {"command": "pytest tests/test_totals.py -k rounding"},
                 "output": "ModuleNotFoundError: No module named 'shopmath'"}},
                {"type": "text", "text": "Root cause: banker's rounding in totals.py. Fixed with Decimal quantize. Lesson: always reproduce with the failing test first before editing."},
            ], 1000),
        ]),
        _session("ses_demo003", "Switch package manager", 13, [
            _msg("m5", "user", [
                {"type": "text", "text": "Actually, forget npm — we moved the whole monorepo to yarn. Use yarn from now on."},
            ], 0),
            _msg("m6", "assistant", [
                {"type": "text", "text": "Noted — contradiction resolved: yarn is now the package manager, npm instructions from earlier sessions are superseded."},
                {"type": "tool", "tool": "bash", "state": {"status": "completed",
                 "input": {"command": "yarn install"},
                 "output": "Done in 12.4s"}},
            ], 1000),
        ]),
    ]
    return {"source": "opencode", "sessions": sessions}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="opencode_export.json")
    args = ap.parse_args()
    data = build()
    Path(args.out).write_text(json.dumps(data, indent=2))
    n = sum(len(s["messages"]) for s in data["sessions"])
    print(f"wrote {len(data['sessions'])} sessions, {n} messages -> {args.out}")


if __name__ == "__main__":
    main()
