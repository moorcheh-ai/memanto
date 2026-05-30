"""Skill Memory Hook - Cross-session memory for mattpocock/skills."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from memory_backend import LocalBackend, get_backend


# Extraction patterns: (regex, memory_type, confidence)
_PATTERNS = [
    (re.compile(r"(?:always|never|must|shall|should)\s+.{10,}", re.I), "instruction", 0.90),
    (re.compile(r"(?:decided|decision|chose|chosen|agreed|resolved)\s+(?:to|on|that)\s+.{10,}", re.I), "decision", 0.85),
    (re.compile(r"(?:prefer|preference|favour|favor|like better|standard is)\s+.{10,}", re.I), "preference", 0.75),
    (re.compile(r"(?:pattern|convention|approach|strategy|architecture|paradigm)\s*(?:is|are|:)\s+.{10,}", re.I), "decision", 0.80),
    (re.compile(r"(?:use|using|adopt|follow)\s+(?:the\s+)?(?:pattern|convention|style|approach|library|framework)\s+.{5,}", re.I), "preference", 0.70),
    (re.compile(r"(?:TODO|FIXME|HACK|NOTE|IMPORTANT|WARNING)[:\s].{5,}"), "context", 0.60),
    (re.compile(r"(?:test|testing|spec)\s+(?:first|driven|strategy|approach)\s+.{5,}", re.I), "instruction", 0.80),
    (re.compile(r"(?:file|module|directory|folder)\s+(?:structure|organization|layout|naming)\s*[:=]\s*.{5,}", re.I), "decision", 0.75),
    (re.compile(r"(?:naming|variable|function|class)\s+(?:convention|style|pattern)\s*[:=]\s*.{5,}", re.I), "preference", 0.70),
    (re.compile(r"(?:error|exception|failure|bug)\s+(?:handling|strategy|pattern)\s*[:=]\s*.{5,}", re.I), "instruction", 0.80),
]

_SKILL_TAG_MAP = {
    "grill-with-docs": ["architecture", "domain", "documentation"],
    "tdd": ["testing", "tdd", "implementation"],
    "handoff": ["handoff", "context-transfer"],
    "diagnose": ["debugging", "diagnosis"],
    "triage": ["issues", "prioritization"],
    "to-issues": ["planning", "issues"],
    "to-prd": ["planning", "prd"],
    "zoom-out": ["architecture", "planning"],
    "prototype": ["prototyping", "implementation"],
    "improve-codebase-architecture": ["architecture", "refactoring"],
    "caveman": ["productivity"],
    "grill-me": ["interview", "planning"],
    "write-a-skill": ["meta", "skill-creation"],
}


def extract_skill_name(input_text: str) -> str | None:
    """Extract the skill name from user input."""
    m = re.search(r"/(\w[\w-]*)", input_text)
    if m:
        return m.group(1)
    return os.environ.get("CLAUDE_SKILL_NAME")


def extract_signals(text: str, skill_name: str | None = None) -> list[dict[str, Any]]:
    """Extract engineering signals from skill I/O text."""
    signals = []
    seen = set()
    for pat, mem_type, confidence in _PATTERNS:
        for match in pat.finditer(text):
            content = match.group(0).strip()
            key = content.lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            tags = list(_SKILL_TAG_MAP.get(skill_name or "", []))
            signals.append({
                "type": mem_type,
                "title": content[:100],
                "content": content,
                "confidence": confidence,
                "tags": tags,
                "source": f"skill:{skill_name}" if skill_name else "skill",
                "provenance": "observed",
            })
    return signals


def extract_from_file_references(text: str, skill_name: str | None = None) -> list[dict[str, Any]]:
    """Extract file-path-based context memories."""
    signals = []
    ext_pat = re.compile(r"[\w./-]+\.(?:py|ts|js|go|rs|rb|java|md|yaml|yml|json|toml)")
    files = ext_pat.findall(text)
    if files:
        unique_files = list(dict.fromkeys(files))[:5]
        tags = list(_SKILL_TAG_MAP.get(skill_name or "", []))
        file_list = ", ".join(unique_files)
        signals.append({
            "type": "context",
            "title": f"Files referenced in {skill_name or 'skill'} session",
            "content": f"Files touched: {file_list}",
            "confidence": 0.60,
            "tags": tags + ["file-references"],
            "source": f"skill:{skill_name}" if skill_name else "skill",
            "provenance": "observed",
        })
    return signals


def format_memory_context(memories: list[dict[str, Any]], max_chars: int = 2000) -> str:
    """Format recalled memories into a concise system constraint block."""
    if not memories:
        return ""

    lines = ["## Engineering Memory Context (from Memanto)"]
    lines.append("The following are your established engineering decisions and preferences. Honor them.")
    lines.append("")

    for m in memories:
        mtype = m.get("type", "context").upper()
        content = m.get("content", "")
        confidence = m.get("confidence", 0.8)
        tags = m.get("tags", [])
        if len(content) > 200:
            content = content[:197] + "..."
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        lines.append(f"- [{mtype}] {content}{tag_str} (confidence: {confidence:.0%})")

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars - 3] + "..."
    return result


def pre_hook(user_input: str, skill_name: str | None = None) -> str:
    """Called BEFORE a skill executes. Recalls and injects relevant memories."""
    detected_skill = skill_name or extract_skill_name(user_input)
    backend = get_backend()

    query_parts = [user_input[:200]]
    if detected_skill:
        query_parts.append(detected_skill)
    query = " ".join(query_parts)

    memories = backend.recall(query=query, limit=5)

    if detected_skill:
        skill_tags = _SKILL_TAG_MAP.get(detected_skill, [])
        domain_memories = backend.recall(query=detected_skill, limit=3, tags=skill_tags)
        seen_ids = {m.get("id") for m in memories}
        for m in domain_memories:
            if m.get("id") not in seen_ids:
                memories.append(m)
                seen_ids.add(m.get("id"))

    context = format_memory_context(memories)
    if context:
        os.environ["MEMANTO_SKILL_CONTEXT"] = context
    return context


def post_hook(user_input: str, skill_output: str, skill_name: str | None = None) -> list[str]:
    """Called AFTER a skill completes. Extracts and stores engineering signals."""
    detected_skill = skill_name or extract_skill_name(user_input)
    backend = get_backend()
    full_text = f"{user_input}\n\n{skill_output}"
    signals = extract_signals(full_text, detected_skill)
    signals.extend(extract_from_file_references(full_text, detected_skill))
    memory_ids = []
    for signal in signals:
        try:
            mid = backend.store(signal)
            memory_ids.append(mid)
        except Exception:
            pass
    return memory_ids


def wrap_skill(user_input: str, skill_name: str | None = None) -> dict[str, Any]:
    """Convenience: run pre-hook and return results for CLI wrapper."""
    context = pre_hook(user_input, skill_name)
    return {
        "skill_name": skill_name or extract_skill_name(user_input),
        "injected_context": context,
        "env_var_set": "MEMANTO_SKILL_CONTEXT" in os.environ,
    }


def main() -> None:
    """CLI entry point for Claude Code hook integration."""
    hook_type = os.environ.get("MEMANTO_HOOK_TYPE", "")
    user_input = os.environ.get("MEMANTO_USER_INPUT", "")
    skill_output = os.environ.get("MEMANTO_SKILL_OUTPUT", "")
    skill_name = os.environ.get("MEMANTO_SKILL_NAME")

    if hook_type == "pre":
        context = pre_hook(user_input, skill_name)
        if context:
            print(context)
    elif hook_type == "post":
        memory_ids = post_hook(user_input, skill_output, skill_name)
        if memory_ids:
            print(f"[Memanto] Stored {len(memory_ids)} engineering memories.")
    else:
        print("Usage: Set MEMANTO_HOOK_TYPE=pre|post and relevant env vars", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
