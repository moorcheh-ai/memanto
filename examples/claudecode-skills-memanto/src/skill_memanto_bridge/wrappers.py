from __future__ import annotations

import os
from pathlib import Path


DEFAULT_COMMANDS = [
    "grill-with-docs",
    "tdd",
    "handoff",
    "diagnose",
    "triage",
    "to-prd",
    "to-issues",
    "improve-codebase-architecture",
    "zoom-out",
]


def normalise_env_name(command: str) -> str:
    return "SKILL_MEMANTO_" + "".join(
        character.upper() if character.isalnum() else "_"
        for character in command
    ) + "_COMMAND"


def generate_wrappers(
    *,
    output_dir: Path | str,
    commands: list[str] | None = None,
    runner: str = "python -m skill_memanto_bridge.cli",
) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for command in commands or DEFAULT_COMMANDS:
        shell_path = output / command
        ps_path = output / f"{command}.ps1"
        shell_path.write_text(
            shell_wrapper(command=command, runner=runner),
            encoding="utf-8",
        )
        ps_path.write_text(
            powershell_wrapper(command=command, runner=runner),
            encoding="utf-8",
        )
        shell_path.chmod(shell_path.stat().st_mode | 0o755)
        generated.extend([shell_path, ps_path])

    return generated


def shell_wrapper(*, command: str, runner: str) -> str:
    env_name = normalise_env_name(command)
    return f"""#!/usr/bin/env bash
set -euo pipefail
skill="{command}"
target_env="{env_name}"
task="${{*:-$skill}}"
tmp="$(mktemp)"
cleanup() {{ rm -f "$tmp"; }}
trap cleanup EXIT

{runner} pre-run --skill {command} --task "$task" --path "$PWD"
if [[ -z "${{!target_env:-}}" ]]; then
  echo "Set $target_env to the real command this wrapper should run." >&2
  exit 64
fi

set +e
{runner} exec-target --target "${{!target_env}}" -- "$@" 2>&1 | tee "$tmp"
status=${{PIPESTATUS[0]}}
set -e
{runner} post-run --skill {command} --task "$task" --path "$PWD" --transcript-file "$tmp" >/dev/null || true
exit "$status"
"""


def powershell_wrapper(*, command: str, runner: str) -> str:
    env_name = normalise_env_name(command)
    return f"""$ErrorActionPreference = "Stop"
$skill = "{command}"
$targetEnv = "{env_name}"
$task = if ($args.Count -gt 0) {{ $args -join " " }} else {{ $skill }}
$tmp = [System.IO.Path]::GetTempFileName()
try {{
  {runner} pre-run --skill {command} --task "$task" --path (Get-Location).Path
  $target = [Environment]::GetEnvironmentVariable($targetEnv)
  if ([string]::IsNullOrWhiteSpace($target)) {{
    [Console]::Error.WriteLine("Set $targetEnv to the real command this wrapper should run.")
    exit 64
  }}
  {runner} exec-target --target "$target" -- @args 2>&1 | Tee-Object -FilePath $tmp
  $status = if ($LASTEXITCODE -ne $null) {{ $LASTEXITCODE }} else {{ 0 }}
  {runner} post-run --skill {command} --task "$task" --path (Get-Location).Path --transcript-file "$tmp" | Out-Null
  exit $status
}} finally {{
  Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
}}
"""
