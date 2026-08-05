"""Skill-aware routing for the mattpocock/skills catalogue.

Each skill cares about a different slice of the engineering profile. When the
user invokes ``/tdd`` we bias recall toward testing conventions; ``/grill-with-docs``
biases toward architecture and domain terminology. This module maps the real
mattpocock skill names to:

  * a natural-language ``query`` (semantic bias for what to recall), and
  * ``tags`` to stamp on memories captured from that skill.

Recall is intentionally *not* hard-filtered by memory type — live testing
showed that combining a type filter with Memanto's semantic threshold can
return nothing even when matching-typed memories exist. The ``query`` provides
the skill-awareness instead, and Memanto returns relevant results only.

Skill names are taken from the mattpocock/skills repository
(github.com/mattpocock/skills): engineering skills (tdd, diagnose,
grill-with-docs, triage, to-prd, to-issues, improve-codebase-architecture,
zoom-out, prototype) and productivity skills (grill-me, caveman, handoff,
write-a-skill).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillRoute:
    """How to recall context for, and tag memories from, a given skill."""

    query: str
    tags: list[str] = field(default_factory=list)


# Curated routes for the real mattpocock skills. The query is phrased as
# natural language because Memanto recall is semantic, not keyword-based.
_ROUTES: dict[str, SkillRoute] = {
    "tdd": SkillRoute(
        query="testing conventions, test framework, mocking strategy, and test structure preferences",
        tags=["testing", "tdd"],
    ),
    "diagnose": SkillRoute(
        query="known failure modes, past bugs, root causes, and debugging conventions",
        tags=["debugging", "diagnose"],
    ),
    "grill-with-docs": SkillRoute(
        query="architectural decisions, domain model, terminology, and documented design constraints",
        tags=["architecture", "domain", "docs"],
    ),
    "grill-me": SkillRoute(
        query="prior plans, resolved questions, decisions already made, and stated goals",
        tags=["planning"],
    ),
    "improve-codebase-architecture": SkillRoute(
        query="architecture decisions, module boundaries, and refactoring direction",
        tags=["architecture", "refactoring"],
    ),
    "zoom-out": SkillRoute(
        query="system-level architecture, component relationships, and high-level design",
        tags=["architecture"],
    ),
    "prototype": SkillRoute(
        query="prototyping preferences, throwaway-code conventions, and stack choices",
        tags=["prototyping"],
    ),
    "triage": SkillRoute(
        query="issue triage conventions, priority rules, and labelling decisions",
        tags=["triage", "issues"],
    ),
    "to-prd": SkillRoute(
        query="product requirements conventions and how issues should be written",
        tags=["planning", "prd"],
    ),
    "to-issues": SkillRoute(
        query="how work is sliced into issues and tracker conventions",
        tags=["planning", "issues"],
    ),
    "handoff": SkillRoute(
        query="recent decisions, open threads, and session context to carry forward",
        tags=["handoff"],
    ),
}

# Generic fallback for any skill not explicitly routed (covers caveman,
# write-a-skill, custom skills, and bare prompts).
_DEFAULT_ROUTE = SkillRoute(
    query="engineering decisions, coding preferences, conventions, and codebase facts",
    tags=[],
)


def normalize_skill(skill_name: str | None) -> str | None:
    """Canonicalise a skill name for routing and tagging.

    Strips whitespace, lowercases, and removes any leading ``/`` so that
    ``"/TDD "``, ``"tdd"``, and ``" TDD"`` all map to the same skill identity.
    Returns ``None`` for empty input.
    """
    if not skill_name:
        return None
    cleaned = skill_name.strip().lower().lstrip("/")
    return cleaned or None


def route_for(skill_name: str | None) -> SkillRoute:
    """Return the recall route for a skill, falling back to a generic one."""
    normalized = normalize_skill(skill_name)
    if normalized is None:
        return _DEFAULT_ROUTE
    return _ROUTES.get(normalized, _DEFAULT_ROUTE)


def known_skills() -> list[str]:
    """Names of skills with curated routes (for docs/tests)."""
    return sorted(_ROUTES)
