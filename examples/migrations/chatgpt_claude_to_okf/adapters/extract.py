"""Deterministic memory extraction from conversation turns.

Strategy:
  1. Split each user/assistant message into sentences (keeping list items).
  2. Score each sentence against ordered per-type regex rules; first match wins.
  3. Fall back to `fact` (low confidence) only for substantive first-person
     statements, so we do not drown the bundle in chit-chat.
  4. Drop junk (questions, pleasantries, meta-talk).
  5. Dedupe by normalized text; repeated statements bump confidence.

Twelve types have explicit rules below; `fact` is the low-confidence fallback
for substantive first-person statements. Together they cover all 13 MEMANTO
types: fact, preference, goal, decision, artifact, learning, event,
instruction, context, observation, commitment, relationship, error.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Sentence splitting (naive but robust for chat text)
# ---------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[\u00c0-\u1ef9])|(?<=\n)\s*[-*•]\s+|\n+")

# ---------------------------------------------------------------------------
# Type rules: (type, [compiled patterns]) — evaluated in order, first wins.
# ---------------------------------------------------------------------------
def _p(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]

TYPE_RULES: list[tuple[str, list[re.Pattern]]] = [
    ("instruction", _p(
        r"\bremember( that)?\b", r"\bnote that\b", r"\bfrom now on\b",
        r"\bmake sure (to|that)\b", r"\bnever (use|do|say|run)\b",
        r"\b(rule|constraint|requirement)s?:?\b", r"\balways (use|run|check|keep)\b",
        r"\bdo not (use|run|forget|share)\b", r"\bdon't (use|forget|share|commit)\b",
        r"\bplease (make sure|always|never)\b",
    )),
    ("decision", _p(
        r"\b(we|i) (have )?decided\b", r"\bdecided to\b",
        r"\blet'?s (go with|use|stick with|switch to)\b",
        r"\b(we|i)'?ll (go with|use|stick with|switch to)\b",
        r"\b(we|i) (are|will be|'m|'re) (going with|using)\b",
        r"\bchose\b", r"\bwent with\b", r"\bwe settled on\b",
    )),
    ("commitment", _p(
        r"\b(i|we)'?ll (send|follow up|get back|share|take care|do|review|prepare)\b",
        r"\b(i|we) will (send|follow up|get back|share|take care)\b",
        r"\bi owe you\b", r"\bi promise\b", r"\bcount on me\b",
    )),
    # high-signal correction/learning statements must beat generic event/context
    ("learning", _p(
        r"\bi (learned|learnt|found out|realized|realised|discovered)\b",
        r"\bturns out\b", r"\bactually it'?s\b", r"\bi was wrong\b",
        r"\bi made a mistake\b", r"\blesson learned\b", r"\bi didn'?t know\b",
        r"\bcorrect me if\b", r"\btoday i learned\b", r"\btil\b",
    )),
    ("error", _p(
        r"\b(error|bug|crash|broken|failing|not working|failed)\b",
    )),
    ("goal", _p(
        r"\bmy goal (is|was)\b", r"\b(i|we)'?m? trying to\b", r"\bi am trying to\b",
        r"\bi'?m working on\b", r"\bi am working on\b", r"\bi'?m building\b",
        r"\bi am building\b", r"\bi'?m learning\b", r"\bi am learning\b",
        r"\bi'?m planning (to|on)\b", r"\bi am planning\b", r"\baiming to\b",
        r"\bi'?d like to\b", r"\bi would like to\b", r"\bi need to (build|finish|learn|ship|get)\b",
    )),
    ("preference", _p(
        r"\bi prefer\b", r"\bi like\b", r"\bi love\b", r"\bi enjoy\b",
        r"\bi'?d rather\b", r"\bi would rather\b", r"\bmy favorite\b",
        r"\bi usually\b", r"\bi normally\b", r"\bi (always|never) (use|drink|eat|watch|listen)\b",
        r"\bprefer .{0,40} over\b", r"\bplease use\b", r"\bi'?m a fan of\b",
        r"\bi use\b", r"\bi'?m using\b", r"\bi am using\b",
    )),
    ("relationship", _p(
        r"\bmy (wife|husband|partner|girlfriend|boyfriend|fianc[ée])\b",
        r"\bmy (best )?friend\b", r"\bmy colleague\b", r"\bmy coworker\b",
        r"\bmy (manager|boss|teammate|team)\b", r"\bmy (brother|sister)\b",
        r"\bmy (mom|mother|dad|father|parents|family)\b",
        r"\bmy (son|daughter|kids|children|child)\b",
    )),
    ("event", _p(
        r"\b(yesterday|last night|last week|this weekend|next week|tomorrow)\b",
        r"\bon (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\bi (have|had) a (meeting|call|interview|demo|doctor'?s appointment)\b",
        r"\bi'?m meeting\b", r"\bi attended\b", r"\bi went to\b",
        r"\b(interview|conference|workshop|hackathon|event) (was|is)\b",
    )),
    ("artifact", _p(
        r"\bi (created|wrote|built|made|published|recorded|posted|uploaded|attached|deployed)\b",
        r"\bgithub\.com\b", r"\bthe repo\b", r"\bmy (website|blog|portfolio|resume|app|project)\b",
        r"\bhere'?s (the|a) (file|link|doc|spreadsheet|repo)\b",
    )),
    ("context", _p(
        r"\bby the way\b", r"\bfor (some )?context\b", r"\bjust so you know\b",
        r"\bfyi\b", r"\bquick (update|status)\b", r"\bstatus update\b",
    )),
    ("observation", _p(
        r"\bi notice(d)? that\b", r"\bi'?ve noticed\b", r"\bit (seems|looks) like\b",
        r"\bi see that\b",
    )),
]

# ---------------------------------------------------------------------------
# Junk filters — never emit these as memories
# ---------------------------------------------------------------------------
_JUNK = _p(
    r"^(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you|you'?re welcome|no problem)",
    r"\b(that'?s|that is) (great|awesome|amazing|perfect|good|fine|cool|interesting)\b",
    r"\bsounds (good|great|perfect)\b", r"\bno worries\b", r"\bno problem\b",
    r"\b(my|i'?m|i am) (pleasure|sorry)\b", r"\bglad to help\b",
    r"\bhow (are|can|do|does|would|is|was)\b", r"\bwhat (is|are|was|were|should|does|do)\b",
    r"\bwhere (is|are|can)\b", r"\bwhen (is|are|did|will|can)\b", r"\bwhy (is|are|did|does)\b",
    r"\bcan you\b", r"\bcould you\b", r"\bplease (help|explain|tell|show)\b",
    r"\blet me know\b", r"\bi'?m not sure\b", r"\bi don'?t know\b", r"\bi don'?t understand\b",
    r"\bi have a question\b", r"\bgood question\b", r"\bgreat question\b",
    r"\bcould we schedule\b", r"\bdoes that (work|make sense)\b",
    r"\bi'?ll (check|look|see)\b", r"\byou'?re (right|correct)\b",
    r"\bthat makes sense\b", r"\bgot it\b", r"\bperfect,?\s*thanks?\b",
)

# ---------------------------------------------------------------------------
# Memory extraction
# ---------------------------------------------------------------------------
def _sentences(text: str) -> list[str]:
    out = []
    for chunk in _SENT_SPLIT.split(text):
        chunk = chunk.strip()
        if len(chunk) < 12:
            continue
        out.append(chunk)
    return out


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9\u00c0-\u1ef9]+", "", s.lower())


def _is_junk(s: str) -> bool:
    lower = s.lower()
    if lower.endswith("?") and not re.search(r"\b(i|we|my|our)\b", lower):
        return True
    for pat in _JUNK:
        if pat.search(s):
            return True
    return False


def _classify(s: str) -> tuple[str | None, float, str]:
    """Return (type, confidence, provenance) for a sentence."""
    for mem_type, patterns in TYPE_RULES:
        if any(p.search(s) for p in patterns):
            conf = 0.8
            if mem_type == "error" and not re.search(r"\b(i|my|we|our|it)\b", s, re.I):
                continue  # error term without a subject → skip
            # explicit first-person + capitalized entity → higher confidence
            if re.search(r"\b(i|my|we|our)\b", s, re.I) and re.search(r"\b[A-ZÀ-Ỹ][a-zà-ỹ]{2,}\b", s):
                conf = 0.9
            prov = "explicit_statement" if mem_type in ("preference", "instruction", "decision", "commitment") else "inferred"
            if mem_type == "learning" and re.search(r"\b(wrong|mistake)\b", s, re.I):
                prov = "corrected"
            return mem_type, conf, prov
    # fallback: substantive first-person statement → low-confidence fact
    if re.search(r"\b(i|my|we|our)\b", s, re.I) and len(s) > 40:
        return "fact", 0.55, "inferred"
    return None, 0.0, ""


def _title_from(s: str, limit: int = 9) -> str:
    words = re.split(r"\s+", s.strip())
    t = " ".join(words[:limit])
    if len(words) > limit:
        t += "…"
    return t[:80]


def _ts_iso(ts) -> str | None:
    if not isinstance(ts, (int, float)) or ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _slug(s: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9\u00c0-\u1ef9]+", "-", s.lower()).strip("-")
    return s[:max_len].rstrip("-") or "memory"


def extract_memories(conversations: list[dict], source: str | None = None,
                     max_per_type: int = 40, max_total: int = 250) -> dict:
    """Return {"memories": [...], "stats": {...}, "sessions": [...]}."""
    memories: list[dict] = []
    seen: dict[str, int] = {}
    sessions = []

    for conv in conversations:
        src = source or conv.get("source", "chatgpt")
        conv_memories = []
        unmatched = []
        for turn in conv.get("turns", []):
            if turn["role"] != "user":
                # Assistant replies (acknowledgements, summaries, confirmations)
                # are not memories — only user statements are mined.
                continue
            for sent in _sentences(turn["text"]):
                if _is_junk(sent):
                    unmatched.append(sent)
                    continue
                mem_type, conf, prov = _classify(sent)
                if mem_type is None:
                    unmatched.append(sent)
                    continue
                norm = _normalize(sent)
                if norm in seen:
                    # Repeated statement: keep the first occurrence and bump
                    # its confidence (bounded), per the docstring strategy.
                    first = memories[seen[norm]]
                    first["x_memanto"]["confidence"] = min(
                        1.0, first["x_memanto"]["confidence"] + 0.1)
                    continue
                seen[norm] = len(memories)
                memories.append({
                    "type": mem_type,
                    "title": _title_from(sent),
                    "description": sent[:200],
                    "content": sent,
                    "tags": [mem_type, src],
                    "timestamp": _ts_iso(turn.get("ts")),
                    "resource": f"{conv['title']} ({src})",
                    "session_id": conv["id"],
                    "x_memanto": {
                        "confidence": conf,
                        "provenance": prov,
                        "source": src,
                        "type": mem_type,
                    },
                })
                conv_memories.append(mem_type)
        sessions.append({
            "id": conv["id"],
            "title": conv["title"],
            "source": src,
            "created": conv.get("created"),
            "turns": len(conv.get("turns", [])),
            "memories": conv_memories,
            "unmatched": unmatched[:20],
        })

    # cap per type (keep highest confidence first)
    by_type: dict[str, list[dict]] = {}
    for m in memories:
        by_type.setdefault(m["type"], []).append(m)
    capped: list[dict] = []
    for mem_type, items in by_type.items():
        items.sort(key=lambda m: m["x_memanto"]["confidence"], reverse=True)
        capped.extend(items[:max_per_type])
    capped.sort(key=lambda m: m["timestamp"] or "")
    capped = capped[:max_total]

    # Session records must reflect the *capped* memory set — otherwise they
    # reference memories trimmed away by max-per-type / max-total.
    capped_by_session: dict[str, list[str]] = {}
    for m in capped:
        capped_by_session.setdefault(m.get("session_id", ""), []).append(m["type"])
    for s in sessions:
        s["memories"] = capped_by_session.get(s["id"], [])

    from collections import Counter
    counts = Counter(m["type"] for m in capped)
    stats = {"total": len(capped), "by_type": dict(counts),
             "conversations": len(conversations), "turns": sum(len(c["turns"]) for c in conversations)}
    return {"memories": capped, "stats": stats, "sessions": sessions}
