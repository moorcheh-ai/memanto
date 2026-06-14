"""
hooks/_common.py
================
Shared utilities for all Claude Code lifecycle hooks.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

SKILL_PATTERNS = [
    "/tdd", "/grill-with-docs", "/grill-me", "/handoff",
    "/improve-codebase-architecture", "/diagnose",
    "/to-issues", "/to-prd",
]

FILE_RE = re.compile(
    r"[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|md|yml|yaml|json|toml)"
)

EXPLICIT_RE = re.compile(
    r"^\s*(?:DECISION|CONSTRAINT|PREFERENCE|GOTCHA|ARTIFACT|ERROR)\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)

MEMORY_TYPE_MAP = {
    "decision": "decision",
    "constraint": "instruction",
    "preference": "preference",
    "gotcha": "error",
    "artifact": "artifact",
    "error": "error",
}


def get_client():
    """Get SkillsClient with official moorcheh-sdk. Raises ValueError if no key."""
    from memanto_client import SkillsClient
    return SkillsClient()


def detect_skill(payload: Dict) -> str:
    """Detect which mattpocock skill is being invoked from hook payload."""
    # Check tool use, transcript, prompt
    for field in ("tool_name", "skill", "prompt", "transcript"):
        text = str(payload.get(field, "")).lower()
        for skill in SKILL_PATTERNS:
            if skill in text or skill.lstrip("/") in text:
                return skill
    return "general"


def extract_files_from_prompt(text: str) -> List[str]:
    """Extract file paths mentioned in a prompt."""
    return list(set(FILE_RE.findall(text)))[:10]


def extract_files_from_transcript(transcript: str) -> List[str]:
    """Extract file paths mentioned in a skill transcript."""
    return list(set(FILE_RE.findall(transcript)))[:10]


def extract_decisions_with_llm(
    client,
    transcript: str,
    skill: str,
    files: List[str],
) -> List[Dict]:
    """
    Use answer.generate() (LLM) to extract engineering memories from transcript.

    This is the key differentiator vs Suraj's regex-only approach:
    the LLM reads the full transcript and identifies what's worth remembering,
    including implicit decisions not marked with explicit keywords.

    Falls back to heuristic extraction if LLM returns nothing parseable.
    """
    file_context = ", ".join(files[:5]) if files else "the codebase"

    extraction_prompt = (
        f"From this {skill} skill transcript, extract ALL engineering decisions, "
        f"architectural constraints, coding preferences, and gotchas that a developer "
        f"would need to remember in a future session working on {file_context}.\n\n"
        f"Return ONLY a JSON array of objects with keys: "
        f"'content' (the decision/preference text), 'type' (one of: decision, "
        f"instruction, preference, error, artifact, fact), 'confidence' (0.0-1.0).\n\n"
        f"Transcript:\n{transcript[:3000]}"
    )

    try:
        # Store extraction query as a temporary document then use answer
        client._client.documents.upload(
            namespace_name=client.namespace,
            documents=[{
                "id": f"extract-{hash(transcript) % 999999}",
                "text": extraction_prompt,
                "metadata": {"type": "artifact", "temporary": True},
            }],
        )
        raw = client.answer(extraction_prompt)
        if raw:
            # Try to parse JSON from LLM response
            import json as _json
            # Strip markdown fences
            clean = re.sub(r"```(?:json)?|```", "", raw).strip()
            # Find JSON array
            match = re.search(r"\[.*\]", clean, re.DOTALL)
            if match:
                parsed = _json.loads(match.group())
                if isinstance(parsed, list) and parsed:
                    return [m for m in parsed if isinstance(m, dict) and m.get("content")]
    except Exception:
        pass

    # Fallback: heuristic extraction
    return _heuristic_extract(transcript, skill)


def _heuristic_extract(transcript: str, skill: str) -> List[Dict]:
    """Heuristic fallback for memory extraction."""
    memories = []

    # Explicit markers
    for match in EXPLICIT_RE.finditer(transcript):
        line = match.group(0).strip()
        marker = line.split(":")[0].strip().lower()
        content = match.group(1).strip()
        memories.append({
            "content": content,
            "type": MEMORY_TYPE_MAP.get(marker, "observation"),
            "confidence": 0.90,
            "tags": [skill],
        })

    # Inferred patterns
    for line in transcript.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) < 20:
            continue
        lowered = stripped.lower()

        if any(k in lowered for k in ("we decided", "we chose", "decision:")):
            memories.append({"content": stripped, "type": "decision", "confidence": 0.82})
        elif any(k in lowered for k in ("must not", "never ", "do not", "constraint")):
            memories.append({"content": stripped, "type": "instruction", "confidence": 0.78})
        elif any(k in lowered for k in ("prefer", "style guide", "convention")):
            memories.append({"content": stripped, "type": "preference", "confidence": 0.75})

    # Deduplicate
    seen = set()
    deduped = []
    for m in memories:
        key = m["content"].lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(m)

    return deduped


def render_profile(
    skill: str,
    memories: List[Dict],
    rag_context: str = "",
) -> str:
    """Render engineering profile for injection into Claude's context."""
    if not memories and not rag_context:
        return ""

    lines = [
        f"<engineering-profile skill=\"{skill}\">",
        "The following decisions and preferences were stored from previous sessions.",
        "Apply them automatically — do not re-ask the developer to confirm:",
        "",
    ]

    if rag_context:
        lines.append(f"[RAG Summary]\n{rag_context}\n")

    for m in memories:
        mtype = m.get("type", "observation")
        content = m.get("content", "")
        conf = m.get("confidence", m.get("score", 0.8))
        lines.append(f"  [{mtype} {conf:.2f}] {content}")

    lines.append("</engineering-profile>")
    return "\n".join(lines)


def write_hook_output(data: Dict) -> None:
    """Write hook output as JSON to stdout for Claude Code to consume."""
    try:
        json.dump(data, sys.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass
