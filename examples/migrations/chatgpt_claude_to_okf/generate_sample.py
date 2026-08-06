#!/usr/bin/env python3
"""Generate a realistic, lived-in ChatGPT export for demos and tests.

This is NOT toy data: it mirrors the exact conversations.json schema, spans
~12 conversations / ~200 turns across work, coding preferences, health,
family, travel and side projects — the kind of store a real user builds over
months. `convert.py` must produce a meaningful multi-type bundle from it.

Usage:
    python generate_sample.py --out sample_data/chatgpt_export
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

BASE_TS = time.time() - 90 * 24 * 3600  # ~90 days ago

CONVERSATIONS = [
    ("Postgres migration planning", [
        ("user", "I prefer Postgres over MySQL for new projects. We decided to migrate the billing service from MySQL to Postgres 16 this quarter."),
        ("user", "Remember: never run migrations during peak hours. Always make a backup before ALTER TABLE."),
        ("assistant", "Got it. I'll note Postgres 16 for the billing migration and the backup rule."),
        ("user", "My colleague Anna from the data team will handle the data sync. My manager David approved the timeline."),
        ("user", "I'll send you the migration checklist tomorrow."),
    ]),
    ("Frontend stack choices", [
        ("user", "I'm building a new dashboard for our analytics product. I'd rather use React with TypeScript and Vite."),
        ("user", "Let's go with Tailwind for styling, not CSS modules. I prefer utility classes."),
        ("assistant", "React + TS + Vite with Tailwind — noted."),
        ("user", "From now on, always use the company design system components instead of custom CSS."),
        ("user", "My friend Minh said the new shadcn components are great, but we decided to stick with our design system."),
    ]),
    ("Learning Go", [
        ("user", "I'm learning Go for backend services. My goal is to build a small CLI tool by next month."),
        ("user", "I found out that Go's context package is essential for timeouts — I didn't know that before."),
        ("assistant", "Great progress! The context package is indeed key."),
        ("user", "I prefer reading docs over video tutorials. I usually start with the official docs."),
        ("user", "I'll share my first CLI tool repo with you when it's ready."),
    ]),
    ("Health and fitness", [
        ("user", "I'm trying to run a 5K. I usually run on Tuesday and Thursday mornings before work."),
        ("user", "My doctor told me to cut down on coffee. I made a mistake last week drinking three cups a day."),
        ("user", "I have a check-up appointment next Monday at 9am."),
        ("assistant", "Noted — Tuesday/Thursday runs, coffee limit, Monday check-up."),
        ("user", "I love pho but I'm trying to eat less red meat these days."),
    ]),
    ("Family plans", [
        ("user", "My wife and I are planning a trip to Da Nang in October. We prefer beach hotels over city hotels."),
        ("user", "My son starts school on September 5th. My parents will visit us that weekend."),
        ("user", "We decided to rent a car instead of taking the train."),
        ("assistant", "Da Nang trip, school start, parents visiting — saved."),
    ]),
    ("Side project: recipe bot", [
        ("user", "I'm building a Telegram bot that suggests recipes from leftovers. I'm using Python and the Telegram Bot API."),
        ("user", "My goal is to launch it by the end of the month. I published the first version on GitHub yesterday."),
        ("user", "I learned that Telegram webhooks need a public HTTPS URL — turns out ngrok works fine for testing."),
        ("assistant", "The webhook requirement is a classic gotcha. Good find."),
        ("user", "Remember: keep the bot stateless, store state in Redis."),
    ]),
    ("Job interview prep", [
        ("user", "I have a system design interview next Wednesday for an AI engineer role at a startup."),
        ("user", "I'm working on system design — I'm reading the DDIA book. I prefer hands-on mock interviews over reading alone."),
        ("assistant", "Good plan. Want me to quiz you on rate limiting?"),
        ("user", "Yes please. I'll record the mock session to review later."),
    ]),
    ("Budget and finance", [
        ("user", "I'm trying to save 20% of my income every month. I usually track expenses in a spreadsheet."),
        ("user", "We decided to switch to a digital bank for better interest rates. My wife handles the monthly budget."),
        ("user", "I made a mistake with the credit card payment last month. Never pay credit card bills late again."),
    ]),
    ("Travel: Japan", [
        ("user", "I'm planning a trip to Japan in December. I prefer traveling in the off-season to avoid crowds."),
        ("user", "My friend Lan lived in Tokyo for 3 years and recommended staying in Shinjuku."),
        ("user", "We decided to get the JR Pass and skip the Disney parks."),
        ("assistant", "Shinjuku base, JR Pass, no Disney — noted for the itinerary."),
    ]),
    ("Open source contributions", [
        ("user", "I'm contributing to an open source AI agent project on GitHub. I'm working on a new memory adapter."),
        ("user", "The repo maintainer asked me to always run lint before pushing. I'll follow that rule from now on."),
        ("user", "I found a bug in the CLI yesterday — the error handling for missing API keys is broken."),
        ("assistant", "Good catch. The maintainer should appreciate a fix with a test."),
    ]),
    ("Content creation", [
        ("user", "I'm writing a blog about AI agents in Vietnamese and English. My goal is 2 posts per week."),
        ("user", "I created a Notion template to track drafts. I prefer writing long-form posts over short threads."),
        ("user", "I'll send you the draft for review before publishing."),
        ("assistant", "Happy to review the draft when it's ready."),
    ]),
    ("House hunting", [
        ("user", "My family and I are looking for a new apartment near District 2. We prefer quiet neighborhoods."),
        ("user", "We have a viewing appointment this Saturday at 10am."),
        ("user", "I decided to cap the budget at 3 billion VND. We'll use a real estate agent we found through my sister."),
    ]),
]


def build() -> list[dict]:
    out = []
    now = BASE_TS
    for idx, (title, turns) in enumerate(CONVERSATIONS):
        mapping = {}
        prev = None
        conv_id = f"conv_{idx:03d}"
        first_ts = now
        last_ts = now
        for t_idx, (role, text) in enumerate(turns):
            node_id = f"{conv_id}_n{t_idx}"
            ts = now + t_idx * 3600 * 7  # ~7h between messages
            last_ts = ts
            mapping[node_id] = {
                "id": node_id,
                "message": {
                    "id": node_id,
                    "author": {"role": role, "name": None, "metadata": {}},
                    "create_time": ts,
                    "update_time": None,
                    "content": {"content_type": "text", "parts": [text]},
                    "status": "finished_successfully",
                    "end_turn": None,
                    "weight": 1.0,
                    "metadata": {},
                    "recipient": "all",
                },
                "parent": prev,
                "children": [] if t_idx == len(turns) - 1 else [f"{conv_id}_n{t_idx + 1}"],
            }
            prev = node_id
        out.append({
            "title": title,
            "create_time": first_ts,
            "update_time": last_ts,
            "mapping": mapping,
            "current_node": prev,
            "conversation_id": conv_id,
            "id": conv_id,
        })
        now = last_ts + 3600 * 26  # next conversation ~ a day later
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="sample_data/chatgpt_export")
    args = ap.parse_args()
    root = Path(args.out)
    chatgpt_dir = root / "chatgpt"
    chatgpt_dir.mkdir(parents=True, exist_ok=True)
    data = build()
    (chatgpt_dir / "conversations.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    turns = sum(len(c["mapping"]) for c in data)
    print(f"Wrote {len(data)} conversations ({turns} messages) -> {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
