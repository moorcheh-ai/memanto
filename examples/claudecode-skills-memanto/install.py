#!/usr/bin/env python3
"""Install the Memanto mattpocock/skills bridge into a Claude Code project."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


HOOK_EVENTS = {
    "UserPromptSubmit": {"timeout": 10, "statusMessage": "Recalling Memanto memory"},
    "UserPromptExpansion": {"timeout": 10, "statusMessage": "Recalling Memanto memory"},
    "PostToolUse": {
        "timeout": 5,
        "matcher": "Bash|Edit|Write|MultiEdit",
        "statusMessage": "Capturing skill tool context",
    },
    "PostToolUseFailure": {
        "timeout": 5,
        "matcher": "*",
        "statusMessage": "Capturing skill failure",
    },
    "Stop": {"timeout": 12, "statusMessage": "Storing Memanto skill memory"},
    "PostCompact": {"timeout": 8, "statusMessage": "Storing compact summary"},
}


def build_hook_settings(
    script_path: str = ".claude/hooks/memanto_skill_memory.py",
    python_command: str = "python",
) -> dict[str, Any]:
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event, config in HOOK_EVENTS.items():
        handler = {
            "type": "command",
            "command": python_command,
            "args": [script_path, "--hook", event],
            "timeout": config["timeout"],
            "statusMessage": config["statusMessage"],
        }
        group: dict[str, Any] = {"hooks": [handler]}
        if "matcher" in config:
            group["matcher"] = config["matcher"]
        hooks[event] = [group]
    return {"hooks": hooks}


def merge_settings(existing: dict[str, Any], addition: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    hooks = dict(merged.get("hooks") or {})
    for event, groups in addition.get("hooks", {}).items():
        current = list(hooks.get(event) or [])
        for group in groups:
            if not _group_exists(current, group):
                current.append(group)
        hooks[event] = current
    merged["hooks"] = hooks
    return merged


def install(project_dir: Path, python_command: str, dry_run: bool = False) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    source_script = Path(__file__).with_name("memanto_skill_memory.py")
    target_dir = project_dir / ".claude" / "hooks"
    target_script = target_dir / "memanto_skill_memory.py"
    settings_path = project_dir / ".claude" / "settings.json"

    addition = build_hook_settings(python_command=python_command)
    existing = _load_json(settings_path)
    merged = merge_settings(existing, addition)

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_script, target_script)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        if settings_path.exists():
            backup = settings_path.with_suffix(".json.bak")
            shutil.copy2(settings_path, backup)
        settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    return {
        "project_dir": str(project_dir),
        "hook_script": str(target_script),
        "settings_path": str(settings_path),
        "dry_run": dry_run,
        "settings": merged,
    }


def _group_exists(groups: list[dict[str, Any]], wanted: dict[str, Any]) -> bool:
    wanted_command = _command_signature(wanted)
    for group in groups:
        if _command_signature(group) == wanted_command:
            return True
    return False


def _command_signature(group: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    hooks = group.get("hooks") or []
    if not hooks:
        return ("", ())
    first = hooks[0]
    return (str(first.get("command") or ""), tuple(first.get("args") or []))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=".", help="Target Claude Code project")
    parser.add_argument("--python", default="python", help="Python executable for hooks")
    parser.add_argument("--dry-run", action="store_true", help="Print settings only")
    args = parser.parse_args(argv)

    result = install(Path(args.project_dir), args.python, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
