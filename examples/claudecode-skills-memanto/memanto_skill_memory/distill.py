from __future__ import annotations

import re

from memanto_skill_memory.models import MemoryCandidate, SkillEvent
from memanto_skill_memory.redaction import redact_secrets

_PREFIX_RULES: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (re.compile(r"(?i)^decision\s*:\s*(?P<body>.+)$"), "decision", 0.9),
    (re.compile(r"(?i)^preference\s*:\s*(?P<body>.+)$"), "preference", 0.84),
    (re.compile(r"(?i)^constraint\s*:\s*(?P<body>.+)$"), "instruction", 0.84),
    (re.compile(r"(?i)^learning\s*:\s*(?P<body>.+)$"), "learning", 0.78),
)
_INSTRUCTION_RE = re.compile(
    r"(?i)\b(must|must not|do not|don't|never|always|avoid|require)\b"
)
_LEARNING_RE = re.compile(r"(?i)\b(we learned|learned|existing|current|observed)\b")
_NOISE_RE = re.compile(r"^\s*(?:[-*]|\d+[.)]|>|#+)\s*")
_TITLE_SPLIT_RE = re.compile(
    r"(?i)\s+(?:so|because|instead of|when|while|for|to keep|to avoid)\s+|[.;]"
)


class HeuristicSkillDistiller:
    """Offline distiller used when no live Memanto/Moorcheh key is available.

    The live path stores the same typed records in Memanto. This deterministic
    distiller makes the example reviewable in CI and local checkouts without
    private credentials.
    """

    def distill(self, event: SkillEvent) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        seen: set[tuple[str, str]] = set()

        for line in _iter_signal_lines(event):
            memory_type, confidence, content = _classify(line)
            if not memory_type:
                continue

            content = redact_secrets(content)
            title = _make_title(content, memory_type)
            key = (memory_type, title.casefold())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                MemoryCandidate(
                    memory_type=memory_type,
                    title=title,
                    content=content,
                    confidence=confidence,
                )
            )

        return candidates


def _iter_signal_lines(event: SkillEvent) -> list[str]:
    text = "\n".join(part for part in [event.prompt, event.transcript] if part)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _NOISE_RE.sub("", raw_line.strip())
        if len(line) < 12:
            continue
        lines.append(line)
    return lines


def _classify(line: str) -> tuple[str | None, float, str]:
    for pattern, memory_type, confidence in _PREFIX_RULES:
        match = pattern.match(line)
        if match:
            return (
                memory_type,
                confidence,
                _strip_terminal_punctuation(match.group("body").strip()),
            )

    if _INSTRUCTION_RE.search(line):
        return "instruction", 0.82, _strip_terminal_punctuation(line)
    if _LEARNING_RE.search(line):
        body = re.sub(r"(?i)^we learned\s+(?:that\s+|the\s+)?", "", line).strip()
        return "learning", 0.76, _strip_terminal_punctuation(body)
    return None, 0.0, line


def _make_title(content: str, memory_type: str) -> str:
    title = _TITLE_SPLIT_RE.split(content, maxsplit=1)[0].strip(" -:,.")
    title = re.sub(r"(?i)^we learned\s+(?:that\s+|the\s+)?", "", title).strip()
    title = re.sub(r"(?i)^(use|keep|must|avoid|do not|don't)\b", _capitalize, title)
    if title:
        title = title[0].upper() + title[1:]
    if not title:
        title = memory_type.title()
    return title[:80]


def _capitalize(match: re.Match[str]) -> str:
    word = match.group(0)
    return word[0].upper() + word[1:]


def _strip_terminal_punctuation(value: str) -> str:
    return value.strip().rstrip(".")
