#!/usr/bin/env python3
"""Generate memory-aware command specs for mattpocock/skills-style commands."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass


SUPPORTED_SKILLS = {
    "grill-with-docs": {
        "command": "/grill-with-docs",
        "purpose": "review code or architecture against supplied docs",
    },
    "tdd": {
        "command": "/tdd",
        "purpose": "drive implementation with tests first",
    },
    "handoff": {
        "command": "/handoff",
        "purpose": "summarize current work for another session",
    },
}


@dataclass(frozen=True)
class MemoryAwareSkillSpec:
    """Serializable command contract a skill runner can consume."""

    skill: str
    command: str
    purpose: str
    pre_hook: list[str]
    post_hook: list[str]
    prompt_prefix: str


def build_skill_spec(
    skill: str,
    task: str,
    files: list[str] | None = None,
    backend: str = "memanto-cli",
    store: str | None = None,
) -> MemoryAwareSkillSpec:
    """Return pre/post hook commands for a supported mattpocock skill."""
    if skill not in SUPPORTED_SKILLS:
        known = ", ".join(sorted(SUPPORTED_SKILLS))
        raise ValueError(f"unsupported skill {skill!r}; expected one of: {known}")

    files = files or []
    base_hook = [
        "python",
        "examples/claudecode-skills-memanto/memanto_skills_hook.py",
    ]

    common = ["--backend", backend, "--skill", skill, "--task", task]
    if store:
        common.extend(["--store", store])
    for path in files:
        common.extend(["--file", path])

    metadata = json.dumps({"adapter": "mattpocock-skills", "command": f"/{skill}"})
    common.extend(["--metadata", metadata])

    pre_hook = [*base_hook, "pre", *common]
    post_hook = [*base_hook, "post", *common, "--transcript-file", "$TRANSCRIPT_FILE"]
    info = SUPPORTED_SKILLS[skill]
    return MemoryAwareSkillSpec(
        skill=skill,
        command=str(info["command"]),
        purpose=str(info["purpose"]),
        pre_hook=pre_hook,
        post_hook=post_hook,
        prompt_prefix=(
            "Run the pre_hook first and prepend its stdout to the skill prompt. "
            "After the skill finishes, write the transcript to $TRANSCRIPT_FILE "
            "and run post_hook."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print a memory-aware command spec for mattpocock/skills."
    )
    parser.add_argument("skill", choices=sorted(SUPPORTED_SKILLS))
    parser.add_argument("--task", required=True)
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument(
        "--backend",
        choices=("memanto-sdk", "memanto-cli", "local-jsonl"),
        default="memanto-cli",
    )
    parser.add_argument("--store")
    args = parser.parse_args(argv)

    spec = build_skill_spec(
        skill=args.skill,
        task=args.task,
        files=args.file,
        backend=args.backend,
        store=args.store,
    )
    print(json.dumps(asdict(spec), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
