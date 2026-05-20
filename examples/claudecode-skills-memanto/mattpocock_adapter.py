#!/usr/bin/env python3
"""Generate memory-aware command specs for mattpocock/skills-style commands."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


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


def render_claude_command(spec: MemoryAwareSkillSpec) -> str:
    """Render a copyable Claude Code slash-command wrapper."""
    pre_hook = " ".join(_quote_arg(arg) for arg in spec.pre_hook)
    post_hook = " ".join(_quote_arg(arg) for arg in spec.post_hook)
    return (
        f"# {spec.command}\n\n"
        f"{spec.purpose.capitalize()}.\n\n"
        "Before doing the requested work, run this command and prepend any stdout "
        "to the prompt context:\n\n"
        f"```bash\n{pre_hook}\n```\n\n"
        "After completing the skill, save the transcript path in "
        "`$TRANSCRIPT_FILE` and run:\n\n"
        f"```bash\n{post_hook}\n```\n\n"
        "Use recalled Memanto context as constraints, not as user-visible output.\n"
    )


def write_command_wrappers(
    output_dir: str | Path,
    task: str,
    files: list[str] | None = None,
    backend: str = "memanto-cli",
    store: str | None = None,
) -> list[Path]:
    """Write wrapper command files for all supported mattpocock skills."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for skill in sorted(SUPPORTED_SKILLS):
        spec = build_skill_spec(
            skill=skill,
            task=task,
            files=files or [],
            backend=backend,
            store=store,
        )
        path = target / f"{skill}.md"
        path.write_text(render_claude_command(spec), encoding="utf-8")
        written.append(path)
    return written


def _quote_arg(value: str) -> str:
    if value == "$TRANSCRIPT_FILE":
        return value
    escaped = value.replace("'", "'\"'\"'")
    return f"'{escaped}'"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print a memory-aware command spec for mattpocock/skills."
    )
    parser.add_argument(
        "command",
        choices=[*sorted(SUPPORTED_SKILLS), "install"],
        help="Skill to print as JSON, or `install` to write all wrapper files.",
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--task", required=True)
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument(
        "--backend",
        choices=("memanto-sdk", "memanto-cli", "local-jsonl"),
        default="memanto-cli",
    )
    parser.add_argument("--store")
    args = parser.parse_args(argv)

    if args.command == "install":
        if not args.output_dir:
            parser.error("install requires --output-dir")
        paths = write_command_wrappers(
            output_dir=args.output_dir,
            task=args.task,
            files=args.file,
            backend=args.backend,
            store=args.store,
        )
        print(json.dumps([str(path) for path in paths], indent=2))
        return 0

    spec = build_skill_spec(
        skill=args.command,
        task=args.task,
        files=args.file,
        backend=args.backend,
        store=args.store,
    )
    print(json.dumps(asdict(spec), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
