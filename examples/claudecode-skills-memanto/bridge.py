"""
Memanto Skill Memory Bridge — Engineering Profile Evolution

Eliminates context fragmentation across mattpocock developer skills by
building and maintaining an evolving "Engineering Profile" through Memanto's
LLM backend.

Unlike simple store→search→inject pipelines, this implements:
  - Engineering Profile: structured, evolving document with categories
  - Active LLM extraction: Memanto.answer() distills transcripts into insights
  - Profile evolution: contradiction detection, supersession, version tracking
  - Structured injection: context-rich system blocks, not raw text dumps
  - Profile visualization: `python bridge.py profile` shows what Memanto knows

Architecture:
  pre  ── profile.inject(target, skill)  ── structured context block
  post ── profile.evolve(transcript, skill, target) ── updated profile

Backends:
  - live: Memanto SDK + Moorcheh API (full LLM extraction + RAG injection)
  - local: JSONL file (keyword extraction, light search — no credentials)

Usage:
  python bridge.py pre     /grill-with-docs src/auth.ts
  python bridge.py post    /grill-with-docs src/auth.ts "[transcript]"
  python bridge.py wrap    /tdd src/auth.ts "[transcript]"
  python bridge.py profile
  python bridge.py validate
  python bridge.py benchmark
"""

import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


# ── Config ───────────────────────────────────────────────────────

BACKEND = os.environ.get("MEMANTO_BACKEND", "local").strip()
MEMORY_FILE = Path(os.environ.get("MEMANTO_LOCAL_FILE", ".memanto-skills-memory.jsonl"))
PROFILE_FILE = Path(os.environ.get("MEMANTO_PROFILE_FILE", ".memanto-engineering-profile.json"))


def _api_key() -> Optional[str]:
    return os.environ.get("MOORCHEH_API_KEY") if BACKEND == "live" else None


def _agent_id() -> str:
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        name = remote.rstrip("/").split("/")[-1].replace(".git", "")
        slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
        return f"skills-{slug}"
    except Exception:
        return f"skills-{Path.cwd().name}"


# ── Engineering Profile ──────────────────────────────────────────

@dataclass
class ProfileEntry:
    """A single learned fact about the engineering context."""
    id: str
    category: str         # architecture, preference, constraint, pattern, decision, convention
    content: str
    confidence: float     # 0.0–1.0
    source_skill: str     # e.g. "/grill-with-docs"
    target: str           # file or concept this applies to
    superseded_by: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1


class EngineeringProfile:
    """Evolving structured profile of engineering context.

    Categories:
      architecture  — system design decisions (hexagonal, microservices, etc.)
      preference    — developer preferences (tab width, naming, etc.)
      constraint    — hard constraints (must support IE11, max 100MB, etc.)
      pattern       — recurring code patterns (Repository, Factory, etc.)
      decision      — explicit technical decisions (use OAuth 2.1, etc.)
      convention    — team conventions (commit message format, branch naming)
    """

    def __init__(self, path: Path = PROFILE_FILE):
        self.path = path
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                pass
        return {
            "agent_id": _agent_id(),
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
            "entries": [],
            "metadata": {
                "total_skills_tracked": 0,
                "total_insights": 0,
                "categories_covered": [],
            },
        }

    def _save(self) -> None:
        self._data["updated"] = datetime.now(timezone.utc).isoformat()
        self._data["metadata"]["total_insights"] = len(self._data["entries"])
        cats = sorted(set(e["category"] for e in self._data["entries"]))
        self._data["metadata"]["categories_covered"] = cats
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def add(self, category: str, content: str, confidence: float,
            source_skill: str, target: str) -> str:
        """Add a new entry. Detects near-duplicates and updates confidence instead."""
        # Check for near-duplicate
        for entry in self._data["entries"]:
            if self._similar(entry["content"], content) and not entry.get("superseded_by"):
                # Increase confidence of existing entry instead of creating new
                entry["confidence"] = min(1.0, entry["confidence"] + 0.1)
                entry["version"] += 1
                entry["timestamp"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return entry["id"]

        eid = f"insight-{int(time.time() * 1000)}"
        entry = ProfileEntry(
            id=eid,
            category=category,
            content=content,
            confidence=confidence,
            source_skill=source_skill,
            target=target,
        )
        self._data["entries"].append(entry.__dict__)
        self._data["metadata"]["total_skills_tracked"] += 1
        self._save()
        return eid

    def supersede(self, old_id: str, new_content: str, source_skill: str) -> str:
        """Mark an old insight as superseded and add the replacement."""
        for entry in self._data["entries"]:
            if entry["id"] == old_id:
                entry["superseded_by"] = f"insight-{int(time.time() * 1000)}"
                entry["confidence"] = 0.0
                break
        return self.add(
            category=self._find(old_id).get("category", "decision"),
            content=new_content,
            confidence=0.9,
            source_skill=source_skill,
            target=self._find(old_id).get("target", ""),
        )

    def detect_contradictions(self, new_content: str) -> list[dict]:
        """Find entries that semantically contradict the new insight."""
        # Simple heuristic: check for opposite keywords
        opposites = {
            "use": "avoid", "always": "never", "prefer": "avoid",
            "must": "should not", "do": "don't",
        }
        conflicts = []
        new_lower = new_content.lower()
        for entry in self._data["entries"]:
            if entry.get("superseded_by"):
                continue
            entry_lower = entry["content"].lower()
            for pos, neg in opposites.items():
                if pos in new_lower and neg in entry_lower:
                    conflicts.append(entry)
                elif neg in new_lower and pos in entry_lower:
                    conflicts.append(entry)
        return conflicts

    def search(self, target: str, skill: str = "", limit: int = 5) -> list[dict]:
        """Find profile entries relevant to target + skill."""
        results = []
        terms = target.lower().replace(".ts", "").replace(".js", "").replace("/", " ").split()
        terms = [t for t in terms if len(t) > 1]
        for entry in self._data["entries"]:
            if entry.get("superseded_by"):
                continue
            haystack = entry["content"].lower() + " " + entry.get("target", "").lower()
            score = sum(1 for t in terms if t in haystack)
            # Boost entries from matching skills
            if skill and skill.lstrip("/").lower() in entry.get("source_skill", "").lower():
                score += 2
            if score > 0:
                results.append((score, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def _find(self, eid: str) -> dict:
        for e in self._data["entries"]:
            if e["id"] == eid:
                return e
        return {}

    @staticmethod
    def _similar(a: str, b: str, threshold: float = 0.7) -> bool:
        """Simple similarity check based on word overlap."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return False
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) > threshold

    def render(self) -> str:
        """Render the engineering profile as a readable summary."""
        if not self._data["entries"]:
            return "No engineering insights recorded yet."

        by_category: dict[str, list] = {}
        for e in self._data["entries"]:
            if e.get("superseded_by"):
                continue
            cat = e.get("category", "other")
            by_category.setdefault(cat, []).append(e)

        lines = ["# Engineering Profile", f"Agent: {_agent_id()}",
                 f"Last updated: {self._data['updated']}\n"]

        labels = {
            "architecture": "System Architecture",
            "preference": "Developer Preferences",
            "constraint": "Hard Constraints",
            "pattern": "Code Patterns",
            "decision": "Technical Decisions",
            "convention": "Team Conventions",
        }

        for cat, label in labels.items():
            entries = by_category.get(cat, [])
            if not entries:
                continue
            lines.append(f"## {label}")
            for e in sorted(entries, key=lambda x: x["confidence"], reverse=True):
                source = e.get("source_skill", "unknown")
                lines.append(f"- [{e['confidence']:.0%}] {e['content']}  *(from {source})*")
            lines.append("")

        return "\n".join(lines)


# ── LLM-Powered Extraction ──────────────────────────────────────

_SKILL_TO_CATEGORY = {
    "grill": "decision", "challenge": "decision", "decide": "decision", "board": "decision",
    "architect": "architecture", "design": "architecture",
    "tdd": "pattern", "test": "pattern",
    "handoff": "convention", "freeze": "constraint",
    "capture": "preference", "reflect": "preference",
    "review": "convention", "plan": "decision",
    "fix": "pattern", "execute": "constraint",
    "docs": "convention",
}

_EXTRACTION_PROMPT = (
    "You are analyzing a developer skill execution transcript. "
    "Extract the key engineering insights as a structured JSON object "
    "with this exact format:\n\n"
    '{"insights": [\n'
    '  {"category": "<architecture|preference|constraint|pattern|decision|convention>",\n'
    '   "content": "<single clear statement>",\n'
    '   "confidence": <0.0 to 1.0>}\n'
    ']}\n\n'
    "Categories:\n"
    "  - architecture: system design, component layout, tech stack\n"
    "  - preference: coding style, tooling choices, personal defaults\n"
    "  - constraint: hard limits, must-haves, compatibility requirements\n"
    "  - pattern: recurring code patterns, templates, naming conventions\n"
    "  - decision: explicit technical choices with trade-offs\n"
    "  - convention: team rules, workflow standards, commit guidelines\n\n"
    "Only include insights that are durable — useful across future sessions.\n"
    "Skip vague statements, small talk, and transient details.\n\n"
    "Transcript:\n"
)


def _extract_insights(skill: str, target: str, transcript: str) -> list[dict[str, Any]]:
    """Extract structured insights from a skill transcript.

    Live mode: uses Memanto.answer() with a structured extraction prompt.
    Local mode: heuristic keyword extraction.
    """
    if not transcript.strip():
        return []

    if BACKEND == "live" and _api_key():
        try:
            from memanto.cli.client.direct_client import DirectClient
            client = DirectClient(_api_key())
            client.activate_agent(_agent_id())
            result = client.answer(
                agent_id=_agent_id(),
                question=_EXTRACTION_PROMPT + transcript,
                limit=3,
                temperature=0.2,
            )
            answer = result.get("answer", "")
            # Try parsing JSON from the answer
            start = answer.find("{")
            end = answer.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(answer[start:end])
                if "insights" in parsed:
                    return parsed["insights"]
        except Exception:
            pass

    # Local heuristic extraction
    return _heuristic_extract(skill, target, transcript)


def _heuristic_extract(skill: str, target: str, transcript: str) -> list[dict[str, Any]]:
    """Keyword-based extraction for credential-free mode."""
    insights = []
    lines = transcript.strip().split("\n")
    category = _SKILL_TO_CATEGORY.get(
        skill.lower().lstrip("/").split("-")[0], "decision"
    )

    decision_markers = [
        "decision", "decided", "chose", "selected", "picked",
        "must", "should", "need to", "will use", "going with",
        "prefer", "convention", "pattern", "architecture", "trade-off",
        "constraint", "rule", "standard", "avoid", "always", "never",
    ]

    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if any(m in line.lower() for m in decision_markers):
            confidence = 0.85 if ":" in line else 0.7
            insights.append({
                "category": category,
                "content": line[:300],
                "confidence": confidence,
            })
            if len(insights) >= 5:
                break

    if not insights and len(transcript) > 20:
        insights.append({
            "category": category,
            "content": transcript.strip()[:300],
            "confidence": 0.5,
        })

    return insights


# ── Live Memanto Backend ─────────────────────────────────────────

class _LiveClient:
    """Lazy-initialized DirectClient over Memanto."""

    def __init__(self, api_key: str, agent_id: str):
        self._key = api_key
        self._agent = agent_id
        self._c = None

    def _client(self):
        if self._c is None:
            from memanto.cli.client.direct_client import DirectClient
            self._c = DirectClient(self._key)
            self._c.activate_agent(self._agent)
        return self._c

    def remember(self, mem_type: str, title: str, content: str, tags: list[str]) -> Optional[str]:
        try:
            r = self._client().remember(
                agent_id=self._agent, memory_type=mem_type,
                title=title, content=content, confidence=0.85,
                tags=tags, source="tool", provenance="observed",
            )
            return r.get("memory_id")
        except Exception:
            return None

    def answer(self, question: str, limit: int = 5) -> str:
        try:
            r = self._client().answer(
                agent_id=self._agent, question=question,
                limit=limit, temperature=0.3,
            )
            ans = r.get("answer", "")
            return ans if "No answer generated" not in ans else ""
        except Exception:
            return ""

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            r = self._client().recall(
                agent_id=self._agent, query=query, limit=limit,
                type=["decision", "preference", "instruction", "goal", "context"],
            )
            return r.get("memories", [])
        except Exception:
            return []


# ── Local JSONL Backend ──────────────────────────────────────────

def _local_store(record: dict[str, Any]) -> None:
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
        f.write("\n")


def _local_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    if not MEMORY_FILE.exists():
        return []
    results = []
    terms = query.lower().split()
    with open(MEMORY_FILE, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            haystack = (record.get("content", "") + " " +
                       record.get("title", "") + " " +
                       record.get("target", "")).lower()
            score = sum(1 for t in terms if t in haystack)
            if score > 0:
                results.append((score, record))
    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:limit]]


# ── Public API ───────────────────────────────────────────────────

def pre(skill: str, target: str) -> str:
    """Run before a skill. Returns context block to inject."""
    profile = EngineeringProfile()
    entries = profile.search(target, skill)

    if not entries:
        # Fallback to local memory search
        entries_raw = _local_search(target, limit=5)
        if entries_raw:
            lines = []
            for i, e in enumerate(entries_raw, 1):
                lines.append(f"{i}. {e.get('content', str(e))[:200]}")
            context = "\n".join(lines)
        else:
            print(f"[memanto] No prior context for {target}")
            return ""
    else:
        lines = []
        for i, e in enumerate(entries, 1):
            lines.append(f"{i}. [{e['category']}] {e['content'][:200]}")
        context = "\n".join(lines)

    print(f"[memanto] Injected {len(entries) if entries else 0} context entries for {target}")
    return context


def post(skill: str, target: str, transcript: str) -> list[dict]:
    """Run after a skill. Extract insights and evolve the profile."""
    insights = _extract_insights(skill, target, transcript)
    profile = EngineeringProfile()
    stored = []

    for insight in insights:
        # Detect contradictions
        conflicts = profile.detect_contradictions(insight["content"])
        if conflicts:
            # Supersede the first conflicting entry
            old = conflicts[0]
            eid = profile.supersede(
                old["id"], insight["content"], skill
            )
        else:
            eid = profile.add(
                category=insight["category"],
                content=insight["content"],
                confidence=insight["confidence"],
                source_skill=skill,
                target=target,
            )
        stored.append({"id": eid, "category": insight["category"],
                       "content": insight["content"][:80]})

        # Also store in local JSONL for raw search
        _local_store({
            "id": eid,
            "type": insight["category"],
            "title": f"{skill} -> {target}"[:100],
            "content": insight["content"],
            "skill": skill,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    if stored:
        print(f"[memanto] Profile evolved: {len(stored)} insight(s) added")
    else:
        print(f"[memanto] No insights extracted from {skill}")

    return stored


def wrap(skill: str, target: str, transcript: str = "") -> dict[str, Any]:
    """Full lifecycle: pre → run → post."""
    context = pre(skill, target)
    stored = post(skill, target, transcript)
    return {"context_entries": len(context) > 0,
            "insights_stored": len(stored)}


def show_profile() -> None:
    """Display what Memanto has learned about your engineering context."""
    profile = EngineeringProfile()
    print(profile.render())
    print(f"Profile: {profile.path.resolve()}")
    print(f"Total insights: {len(profile._data['entries'])}")
    print(f"Categories: {', '.join(profile._data['metadata'].get('categories_covered', []))}")


# ── Benchmark ────────────────────────────────────────────────────

def benchmark() -> dict[str, Any]:
    """Simulate multi-skill workflow and measure cross-skill context transfer."""
    print("=== Memanto Skill Memory Bridge — Productivity Benchmark ===\n")

    target = "src/auth.ts"
    skills = [
        ("/grill-with-docs", target,
         "Decision: Use OAuth 2.1 with PKCE. Prefer JWT over sessions. Must support MFA."),
        ("/tdd", target,
         "Added 12 unit tests for OAuth flow. Edge cases: expired tokens, rate limiting."),
        ("/handoff", target,
         "Auth module complete. Token refresh stored. Next: session management."),
    ]

    contexts_found = 0
    total_stored = 0

    for skill, tgt, transcript in skills:
        print(f"--- {skill} {tgt} ---")
        ctx = pre(skill, tgt)
        ctx_status = f"FOUND ({len(ctx)} chars)" if ctx else "NONE"
        print(f"  pre : context = {ctx_status}")
        if ctx:
            contexts_found += 1
        stored = post(skill, tgt, transcript)
        total_stored += len(stored)
        print()

    reducible = len(skills) - 1
    reduction = round((contexts_found / reducible) * 100) if reducible > 0 else 0

    print("--- Summary ---")
    print(f"  Total runs         : {len(skills)}")
    print(f"  Reducible runs     : {reducible}")
    print(f"  Context hits       : {contexts_found}")
    print(f"  Insights stored    : {total_stored}")
    print(f"  Backend            : {BACKEND}")
    print(f"  Reduction          : {contexts_found}/{reducible} = {reduction}%")
    print(f"\n=== Repeated instruction reduction: {reduction}% ===")

    # Display the evolved profile
    print("\n--- Evolved Engineering Profile ---")
    profile = EngineeringProfile()
    print(profile.render())

    return {
        "skill_runs": len(skills),
        "insights_stored": total_stored,
        "contexts_found": contexts_found,
        "reducible_runs": reducible,
        "repeated_instruction_reduction_pct": reduction,
    }


# ── Validate ─────────────────────────────────────────────────────

def validate() -> None:
    """Credential-free dry-run validation."""
    print("=== Memanto Skill Memory Bridge — Validation ===\n")
    print(f"  Backend : {BACKEND}")
    print(f"  API Key : {'configured' if _api_key() else 'not set'}")
    print(f"  Agent   : {_agent_id()}")
    print(f"  Profile : {PROFILE_FILE}")
    print(f"  Store   : {MEMORY_FILE}\n")

    for cmd in ["pre", "post", "wrap", "profile"]:
        print(f"--- {cmd} ---")
        if cmd == "pre":
            pre("/grill-with-docs", "src/auth.ts")
        elif cmd == "post":
            post("/grill-with-docs", "src/auth.ts",
                 "Decision: Use OAuth 2.1 with PKCE. Prefer JWT over sessions.")
        elif cmd == "wrap":
            wrap("/tdd", "src/auth.ts",
                 "Added tests for auth edge cases: expired tokens, rate limiting.")
        elif cmd == "profile":
            show_profile()
        print()

    print("=== Validation Complete ===")


# ── CLI ──────────────────────────────────────────────────────────

_HELP = """Memanto Skill Memory Bridge

  python bridge.py pre       <skill> <target>
  python bridge.py post      <skill> <target> [transcript]
  python bridge.py wrap      <skill> <target> [transcript]
  python bridge.py profile
  python bridge.py validate
  python bridge.py benchmark"""


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print(_HELP)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "validate":
        validate()
    elif cmd == "benchmark":
        # Reset profile and memory for clean benchmark
        PROFILE_FILE.unlink(missing_ok=True)
        MEMORY_FILE.unlink(missing_ok=True)
        benchmark()
    elif cmd == "profile":
        show_profile()
    elif cmd == "pre" and len(sys.argv) >= 4:
        pre(sys.argv[2], sys.argv[3])
    elif cmd == "post" and len(sys.argv) >= 4:
        post(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "wrap" and len(sys.argv) >= 4:
        wrap(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(_HELP, file=sys.stderr)
        sys.exit(1)
