"""Generate Claude Code command specs for mattpocock-style developer skills."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillCommandSpec:
    name: str
    description: str
    task_template: str
    default_files: tuple[str, ...] = ()

    @property
    def command_name(self) -> str:
        return self.name.strip("/")


DEFAULT_SKILLS = (
    SkillCommandSpec(
        name="/grill-with-docs",
        description="Review an implementation against docs and durable project memory.",
        task_template="Review the current change against the relevant docs.",
        default_files=("docs/",),
    ),
    SkillCommandSpec(
        name="/tdd",
        description="Run a test-first implementation loop with recalled constraints.",
        task_template="Write the next focused test and implementation step.",
        default_files=("tests/",),
    ),
    SkillCommandSpec(
        name="/handoff",
        description="Capture decisions and next steps for a future skill run.",
        task_template="Summarize the current state and durable handoff notes.",
        default_files=(),
    ),
)


def command_payload(spec: SkillCommandSpec) -> dict[str, object]:
    return {
        "name": spec.command_name,
        "description": spec.description,
        "wrapper": "run_skill_with_memory.py",
        "backend_env": "MEMANTO_SKILLS_BACKEND",
        "memory_env": "MEMANTO_SKILLS_MEMORY",
        "task_template": spec.task_template,
        "default_files": list(spec.default_files),
    }


def render_markdown(spec: SkillCommandSpec) -> str:
    files = " ".join(f"--file {file}" for file in spec.default_files)
    file_args = f" {files}" if files else ""
    return "\n".join(
        [
            f"# {spec.name}",
            "",
            spec.description,
            "",
            "```bash",
            "python run_skill_with_memory.py "
            f"--skill {spec.name} "
            f"--task {json.dumps(spec.task_template)}"
            f"{file_args} "
            "-- <underlying skill command>",
            "```",
            "",
        ]
    )


def write_command_specs(output_dir: str | Path) -> list[Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in DEFAULT_SKILLS:
        target = output_path / f"{spec.command_name}.md"
        target.write_text(render_markdown(spec), encoding="utf-8")
        written.append(target)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Memanto-aware Claude Code command wrappers."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print command specs as JSON instead of Markdown.",
    )
    parser.add_argument(
        "--write",
        metavar="DIR",
        help="Write Markdown command specs into DIR.",
    )
    args = parser.parse_args()

    if args.write:
        written = write_command_specs(args.write)
        for path in written:
            print(path)
        return

    if args.json:
        print(json.dumps([command_payload(spec) for spec in DEFAULT_SKILLS], indent=2))
        return

    for spec in DEFAULT_SKILLS:
        print(render_markdown(spec))


if __name__ == "__main__":
    main()
