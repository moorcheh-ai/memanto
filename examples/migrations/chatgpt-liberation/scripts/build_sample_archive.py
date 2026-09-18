# ruff: noqa: E501, E402
"""Deterministic lived-in ChatGPT export generator — 28 days, contradictions, evolving prefs."""

from __future__ import annotations

import hashlib
import json
import random
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SEED = 42
random.seed(SEED)

BASE = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)

# Narrative: Alex, product manager, building AI feature, evolves
CONVERSATIONS_SPEC = [
    # Week 1 — early prefs
    {"title": "Morning routine", "day": 0, "msgs": [
        ("user", "I prefer concise summaries, bullet points over paragraphs. My mornings are packed."),
        ("assistant", "Got it — I'll keep summaries short and bulleted."),
        ("user", "I love coffee, usually 2 cups before noon. Remember that."),
        ("assistant", "Noted — 2 coffees before noon."),
    ]},
    {"title": "Project Atlas kickoff", "day": 1, "msgs": [
        ("user", "My main goal is to ship Project Atlas by Aug 30 — it's a graph-augmented retrieval system for our docs."),
        ("assistant", "Locked in: Project Atlas, deadline Aug 30, graph-augmented retrieval."),
        ("user", "I work with Maya on Atlas. She's the designer, I'm PM."),
        ("assistant", "Team noted: Maya (design), you (PM) on Atlas."),
    ]},
    {"title": "Research notes: retrieval", "day": 2, "msgs": [
        ("user", "Observation: dense retrieval fails on our 4PB doc-intel when queries are multi-hop. Need graph walk."),
        ("assistant", "Logged as observation — multi-hop needs graph walk."),
        ("user", "Decision: we'll use Pinecone + Neo4j hybrid, not pure vector. Going with hybrid."),
        ("assistant", "Decision recorded: Pinecone + Neo4j hybrid."),
    ]},
    {"title": "Weekend trip", "day": 5, "msgs": [
        ("user", "My sister Priya is visiting next weekend, we'll hike Mt. Rainier."),
        ("assistant", "Event noted — Priya visiting, Rainier hike."),
        ("user", "Remember: I'm vegetarian, no meat. And allergic to peanuts — serious."),
        ("assistant", "Dietary constraints saved: vegetarian, peanut allergy."),
        ("user", "Please always remind me to carry my EpiPen on hikes."),
        ("assistant", "Instruction saved: remind EpiPen on hikes."),
    ]},
    # Week 2 — evolving
    {"title": "Atlas architecture", "day": 8, "msgs": [
        ("user", "Update: Atlas deadline moved to Sep 10, not Aug 30 — stakeholder delay."),
        ("assistant", "Updated: Atlas deadline Sep 10 (was Aug 30)."),
        ("user", "I changed my mind — I switched from coffee to green tea, 1 cup. Coffee gives me jitters now."),
        ("assistant", "Preference updated: green tea, 1 cup (was coffee)."),
        ("user", "My manager Raj wants weekly Friday demos. Commitment: I'll deliver Atlas demo every Friday."),
        ("assistant", "Commitment: Friday demos to Raj."),
    ]},
    {"title": "Team dynamics", "day": 10, "msgs": [
        ("user", "Learning: Maya prefers Figma comments over Slack for feedback. Noted for next time."),
        ("assistant", "Learning captured — Maya → Figma comments."),
        ("user", "Fact: our doc store is GE RADAR mock, 4PB, n8n + LangGraph pipeline."),
        ("assistant", "Fact stored: GE RADAR 4PB, n8n/LangGraph."),
    ]},
    {"title": "Evening reflection", "day": 12, "msgs": [
        ("user", "Goal: I want to run a half-marathon by Dec — training 3x per week."),
        ("assistant", "Goal logged: half-marathon Dec, 3x/week training."),
        ("user", "Don't forget: deployment window is Tuesdays 2am UTC only."),
        ("assistant", "Instruction: deploy Tuesdays 2am UTC."),
    ]},
    # Week 3 — contradictions & relationships
    {"title": "Atlas blocker", "day": 15, "msgs": [
        ("user", "Error we hit: Pinecone upsert rate-limited at 5k/min on batch import. Need backoff."),
        ("assistant", "Error noted: Pinecone 5k/min limit, needs backoff."),
        ("user", "I will fix retrieval latency to <200ms p95 by next sprint."),
        ("assistant", "Commitment: <200ms p95 retrieval by next sprint."),
    ]},
    {"title": "Family call", "day": 17, "msgs": [
        ("user", "My partner Alex (not me — partner is also Alex) prefers we cook at home on weekdays."),
        ("assistant", "Relationship: partner Alex, home-cook weekdays."),
        ("user", "We adopted a dog, Luna, golden retriever, 2 years old."),
        ("assistant", "Fact: Luna, golden retriever, 2yo."),
    ]},
    {"title": "Research deep dive", "day": 19, "msgs": [
        ("user", "Artifact: draft PRD for Atlas — 12 pages, link https://example.com/prd-atlas.pdf"),
        ("assistant", "Artifact noted: PRD 12 pages."),
        ("user", "Instruction: from now on, always include a risks section in PRDs."),
        ("assistant", "Instruction: always include risks in PRDs."),
    ]},
    # Week 4 — final
    {"title": "Demo prep", "day": 23, "msgs": [
        ("user", "Observation: graph walk improved recall from 0.62 to 0.81 on multi-hop QA."),
        ("assistant", "Observation: recall 0.62→0.81 with graph walk."),
        ("user", "Decision: we will open-source the Atlas graph layer under MIT after Sep 10."),
        ("assistant", "Decision: MIT open-source graph layer post-Sep 10."),
    ]},
    {"title": "Health check", "day": 25, "msgs": [
        ("user", "I quit tea too — now just water, 3L daily. Health kick."),
        ("assistant", "Preference updated: 3L water daily (was tea)."),
        ("user", "My dentist appointment is 2026-08-28T15:00:00Z, don't schedule over it."),
        ("assistant", "Event: dentist 2026-08-28T15:00Z."),
    ]},
    {"title": "Ship it", "day": 27, "msgs": [
        ("user", "Context: Atlas runs on AWS us-east-1, costs $1.2k/mo so far."),
        ("assistant", "Context: AWS us-east-1, $1.2k/mo."),
        ("user", "Goal: after Atlas, I want to build a personal AI companion with persistent memory — that's why Memanto matters."),
        ("assistant", "Goal: personal AI companion with persistent memory."),
    ]},
]

# Add ~25 more micro-conversations to reach 38 total (fill with synthetic variations)
EXTRA_TITLES = [
    "Quick sync with Raj", "Figma feedback", "Pipeline debug", "EpiPen check", "Tea vs coffee", "Atlas metrics",
    "Weekend hike plan", "Luna walk", "Grocery: vegetarian", "Neon retro analysis", "Slack vs Figma",
    "Pinecone backoff impl", "Neo4j schema", "Q&A benchmark", "Evals: recall parity", "Handoff to Maya",
    "Deploy Tuesday", "Risks doc", "Dog park", "Rainier prep", "Half-marathon week2", "Docs pipeline", "n8n cron",
    "Atlas OKF export", "Freedom demo"
]
for i, title in enumerate(EXTRA_TITLES):
    day = (i * 3) % 28
    # single user message per micro-convo to inflate count but stay realistic
    facts = [
        "Note: Atlas uses LangGraph cyclic multi-agent net for contradiction resolution.",
        "Fact: we eval on GE RADAR 4PB slice, 10k docs.",
        "Preference: I like dark mode, muted colors, no emojis in docs.",
        "Instruction: always cite sources in research summaries.",
        "Event: all-hands 2026-08-20T16:00:00Z.",
        "Relationship: Maya handles UX, I handle data layer.",
        "Learning: EpiPen reminder should be proactive, not reactive.",
        "Commitment: I will document Atlas trade-offs in ADR-04.",
        "Observation: vector-only recall drops 23% on temporal queries.",
        "Decision: keep GE mock data, don't use prod PII.",
    ]
    txt = facts[i % len(facts)]
    CONVERSATIONS_SPEC.append({"title": title, "day": day+1, "msgs": [("user", txt), ("assistant", "Noted.")]  })

# Ensure 38 total (we have 13 +25 =38)
assert len(CONVERSATIONS_SPEC) == 38

def build_conversations() -> list[dict[str, Any]]:
    """Build conversations."""
    out = []
    for idx, spec in enumerate(CONVERSATIONS_SPEC):
        cid = f"conv-{idx:03d}-{hashlib.sha256(spec['title'].encode()).hexdigest()[:8]}"
        created = BASE + timedelta(days=spec["day"], hours=random.randint(0, 10))
        # mapping shape mimicking real export
        mapping: dict[str, Any] = {}
        parent = None
        for midx, (role, content) in enumerate(spec["msgs"]):
            node_id = f"m-{idx:03d}-{midx}"
            msg_time = created + timedelta(minutes=midx*7)
            node: dict[str, Any] = {
                "id": node_id,
                "message": {
                    "id": node_id,
                    "author": {"role": role},
                    "create_time": msg_time.timestamp(),
                    "content": {"parts": [content]},
                },
                "parent": parent,
                "children": [],
            }
            if parent:
                mapping[parent]["children"].append(node_id)
            mapping[node_id] = node
            parent = node_id
        out.append({
            "id": cid,
            "title": spec["title"],
            "create_time": created.timestamp(),
            "mapping": mapping,
        })
    return out

def build_memory_json() -> list[dict[str, Any]]:
    """Build memory json."""
    # explicit ChatGPT memory.json style — 5 curated memories spanning weeks
    return [
        {"id": "mem-001", "memory": "User prefers concise, bulleted summaries.", "type": "preference", "created_at": (BASE + timedelta(days=0)).isoformat()},
        {"id": "mem-002", "memory": "User is vegetarian and has a serious peanut allergy — carries EpiPen on hikes.", "type": "fact", "created_at": (BASE + timedelta(days=5)).isoformat()},
        {"id": "mem-003", "memory": "Project Atlas is a graph-augmented retrieval system, deadline Sep 10 (moved from Aug 30). Team: Maya (design), user (PM).", "type": "goal", "created_at": (BASE + timedelta(days=8)).isoformat()},
        {"id": "mem-004", "memory": "User switched from coffee to green tea to water 3L daily — latest is water only.", "type": "preference", "created_at": (BASE + timedelta(days=25)).isoformat()},
        {"id": "mem-005", "memory": "Dog Luna, golden retriever, 2 years old, adopted on day 17.", "type": "fact", "created_at": (BASE + timedelta(days=17)).isoformat()},
    ]

def write_sample_archive(output_dir: str | Path) -> dict[str, Any]:
    """Write sample archive."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    conversations = build_conversations()
    memories = build_memory_json()
    (out / "conversations.json").write_text(json.dumps(conversations, indent=2), encoding="utf-8")
    (out / "memory.json").write_text(json.dumps(memories, indent=2), encoding="utf-8")
    # zip as real export would be
    zpath = out / "chatgpt-export.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(out / "conversations.json", "conversations.json")
        zf.write(out / "memory.json", "memory.json")
    return {
        "conversations": len(conversations),
        "memories": len(memories),
        "messages": sum(len(c.get("mapping", {})) for c in conversations),
        "output_dir": str(out),
        "zip": str(zpath),
    }

if __name__ == "__main__":
    stats = write_sample_archive(Path(__file__).parent.parent / "sample-data")
    print(json.dumps(stats, indent=2))
