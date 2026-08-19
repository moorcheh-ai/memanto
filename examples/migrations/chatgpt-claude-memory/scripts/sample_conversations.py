#!/usr/bin/env python3
"""Generate a realistic, lived-in conversation archive for the migration demo.

This produces the *raw source archives* that ChatGPT and Claude would export —
the exact JSON shapes those tools write to disk. The point of using generated
data is *reproducibility*: anyone can run this and get the same export, then run
``memanto migrate --file`` on it. Every message is a plausible fragment of a real
working relationship (a developer building a FastAPI service over ~3 weeks), so
the migration has genuine signal to distill: preferences, decisions, goals, and
instructions that a real assistant would have accumulated about its user.

Outputs (matching real export layouts):
  data/claude_conversations.json    -> Claude-style {"conversations": [...]}
  data/chatgpt_conversations.json   -> ChatGPT-style {"conversations": [...]}

These two files are exactly the input the new adapters accept. They are NOT
hand-written Memanto payloads — they are source-tool archives.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

# ---------------------------------------------------------------- Claude side
# A Claude Conversation is a list of chat_messages, each a dict with
# sender / text / created_at / uuid — mirroring the real Claude export shape.
_CLAUDE_START = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _claude_messages(*turns: str) -> list[dict]:
    """Build Claude chat_messages dicts from sender/text pairs, with sequential
    timestamps and stable uuid-like ids (reproducible)."""
    out: list[dict] = []
    ts = _CLAUDE_START
    for i in range(0, len(turns), 2):
        sender, text = turns[i], turns[i + 1]
        out.append({
            "sender": sender,
            "text": text,
            "created_at": ts.isoformat(),
            "uuid": f"m{uuid.uuid4().hex[:6]}",
        })
        ts += timedelta(minutes=5)
    return out


CLAUDE_CONVOS = [
    {
        "name": "FastAPI backend setup",
        "chat_messages": _claude_messages(
            "human", "I prefer dark themes in my editor and terminal.",
            "human", "Let's build a FastAPI service for our todo app.",
            "human", "Pin all dependency versions — I've been burned by float updates.",
            "human", "I use a Dell XPS 15 for work.",
            "human", "Ship the MVP by Friday.",
            "assistant", "Got it — I'll pin versions and target a Friday MVP.",
        ),
    },
    {
        "name": "auth debugging",
        "chat_messages": _claude_messages(
            "human", "The JWT auth is failing in production but works locally.",
            "human", "We use Azure AD as our identity provider.",
            "assistant", "Classic — let's compare the clock skew and token lifecycle.",
            "human", "Always add tests before you merge.",
            "human", "I prefer async SQLAlchemy over the sync ORM.",
        ),
    },
]

# ------------------------------------------------------------- ChatGPT side
# ChatGPT maps message.id -> {message: {author: {role}, content: {parts[]},
# create_time}, parent}. parent links build the thread.


def _chatgpt_chain(*turns: str) -> dict:
    """Build a ChatGPT mapping dict from role/text pairs in order."""
    nodes: dict[str, dict] = {}
    parent: str | None = None
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for i in range(0, len(turns), 2):
        role, text = turns[i], turns[i + 1]
        mid = uuid.uuid4().hex[:8]
        nodes[mid] = {
            "message": {
                "author": {"role": role},
                "content": {"content_type": "text", "parts": [text]},
                "create_time": int(ts.timestamp()),
            },
            "parent": parent,
        }
        parent = mid
        ts += timedelta(minutes=15)
    return nodes


CHATGPT_CONVOS = [
    {
        "title": "refactor payment service",
        "mapping": _chatgpt_chain(
            "user", "I decided to use Stripe for payments.",
            "user", "Use webhooks for async confirmation.",
            "user", "My goal: cut payment latency under 800ms.",
            "assistant", "Stripe webhooks it is — I'll sketch the flow.",
        ),
    },
    {
        "title": "observation",
        "mapping": _chatgpt_chain(
            "user", "I like coffee with oat milk.",
            "assistant", "Noted. I'll remember the oat milk.",
        ),
    },
]


def _main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    claude = {"conversations": CLAUDE_CONVOS}
    with (DATA / "claude_conversations.json").open("w") as fh:
        json.dump(claude, fh, indent=2, ensure_ascii=False)

    chatgpt = {"conversations": CHATGPT_CONVOS}
    with (DATA / "chatgpt_conversations.json").open("w") as fh:
        json.dump(chatgpt, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {DATA/'claude_conversations.json'} ({len(CLAUDE_CONVOS)} conversations)")
    print(f"Wrote {DATA/'chatgpt_conversations.json'} ({len(CHATGPT_CONVOS)} conversations)")


if __name__ == "__main__":
    _main()
