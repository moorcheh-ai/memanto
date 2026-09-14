"""run.py - One-command reproduction of the OKF Memory Vault showcase.

Builds the complete demo from scratch:

    1. Seeds the initial OKF bundle (v1) - two weeks of lived-in agent memory.
    2. Evolves it through three more sessions (v2/v3/v4): a preference
       correction, a two-agent contradiction, a human review + rollback.
    3. Initializes a git repo around the bundle so the memory has a real
       version history - `git log` and `git diff` become memory audit tools.
    4. Renders human-readable diffs between every session into sample/diffs/.
    5. Runs the bundled test suite.

Run from this directory:

    python run.py            # full reproduction
    python run.py --no-git   # skip git (still renders all snapshots + diffs)

Outputs (all under sample/):

    sample/vault/            the git-versioned OKF bundle (checkout = v4)
    sample/vault-v1/ ...     frozen snapshots of each session
    sample/diffs/*.md        human-readable memory diffs
    sample/git-log.txt       the memory audit trail
    sample/migration_summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import scenario
from okf_bundle import all_memories, summary_table, write_bundle
from okf_diff import diff_bundles, render_markdown

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "sample"
VAULT = SAMPLE / "vault"


def _force_rmtree(path: Path, retries: int = 6, delay: float = 0.5) -> None:
    """Remove a directory tree on Windows, where git object files are
    read-only and must be writable before deletion."""
    def _clear_readonly(root: str) -> None:
        for dirpath, dirnames, filenames in os.walk(root):
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                try:
                    os.chmod(full, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass

    for attempt in range(retries):
        try:
            if path.exists():
                _clear_readonly(str(path))
                shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(delay)


def _log(msg: str) -> None:
    print(f"  … {msg}")


def build_snapshots() -> dict[str, Path]:
    """Write each session's memory set as a frozen OKF bundle."""
    versions = {
        "v1": scenario.S1_BASELINE,
        "v2": scenario.S2_EVOLVE,
        "v3": scenario.S3_CONFLICT,
        "v4": scenario.S4_RESOLVED,
    }
    out: dict[str, Path] = {}
    for name, memories in versions.items():
        target = SAMPLE / f"vault-{name}"
        if target.exists():
            _force_rmtree(target)
        n = write_bundle(target, memories)
        _log(f"{name}: wrote {n} memory files -> sample/vault-{name}")
        out[name] = target
    return out


def build_git_vault(snapshots: dict[str, Path]) -> None:
    """Turn the bundle into a git-versioned memory vault with one commit per session."""
    if VAULT.exists():
        _force_rmtree(VAULT)
    VAULT.mkdir(parents=True)

    def _sh(*args: str) -> None:
        subprocess.run(args, cwd=VAULT, check=True, capture_output=True)

    _sh("git", "init", "-b", "main")
    _sh("git", "config", "user.name", "Lumenly Agent")
    _sh("git", "config", "user.email", "agent@lumenly.example")
    # Commits happen in chronological order; sessions are independent snapshots.
    for name in ("v1", "v2", "v3", "v4"):
        src = snapshots[name]
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                dest = VAULT / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
        _sh("git", "add", "-A")
        _sh("git", "commit", "-q", "-m", f"{name}: {scenario.SESSION_NARRATIVES[name]['name']}")
        _sh("git", "tag", name)
        _log(f"git commit {name} (tag {name})")


def render_diffs(snapshots: dict[str, Path]) -> None:
    diffs_dir = SAMPLE / "diffs"
    if diffs_dir.exists():
        shutil.rmtree(diffs_dir)
    diffs_dir.mkdir(parents=True)
    pairs = [("v1", "v2"), ("v2", "v3"), ("v3", "v4")]
    for a, b in pairs:
        diff = diff_bundles(snapshots[a], snapshots[b])
        md = render_markdown(diff)
        (diffs_dir / f"{a}-to-{b}.md").write_text(md, encoding="utf-8")
        _log(f"diff {a} -> {b} rendered")


def render_git_log() -> None:
    out = subprocess.run(
        ["git", "-C", str(VAULT), "log", "--oneline", "--decorate"],
        capture_output=True, text=True,
    ).stdout
    (SAMPLE / "git-log.txt").write_text(out, encoding="utf-8")
    _log("git log captured")


def write_summary(snapshots: dict[str, Path]) -> None:
    summary = {
        "showcase": "okf-memory-vault",
        "bundle": "sample/vault",
        "sessions": {},
        "conflict_resolution": {
            "contradiction": "average-customer-response-time",
            "wrong_entry": "maya-s-birthday-is-august-15",
            "outcome": "resolved in v4 via human review; single source of truth assigned",
        },
    }
    for name in ("v1", "v2", "v3", "v4"):
        mems = all_memories(snapshots[name])
        counts: dict[str, int] = {}
        for m in mems:
            counts[m.type] = counts.get(m.type, 0) + 1
        summary["sessions"][name] = {
            "name": scenario.SESSION_NARRATIVES[name]["name"],
            "narrative": scenario.SESSION_NARRATIVES[name]["narrative"],
            "memory_count": len(mems),
            "by_type": dict(sorted(counts.items())),
        }
    (SAMPLE / "migration_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _log("migration_summary.json written")


def run_tests() -> None:
    import pytest
    code = pytest.main([str(HERE / "tests"), "-q", "--no-header"])
    if code != 0:
        raise SystemExit(f"pytest failed with exit code {code}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-git", action="store_true", help="skip the git vault")
    parser.add_argument("--no-tests", action="store_true", help="skip pytest")
    args = parser.parse_args(argv)

    print("OKF Memory Vault - building the demo")
    snapshots = build_snapshots()
    if not args.no_git:
        build_git_vault(snapshots)
        render_git_log()
    else:
        _log("skipping git vault (--no-git)")
    render_diffs(snapshots)
    write_summary(snapshots)
    if not args.no_tests:
        run_tests()
    print("\nDone. Open README.md for the tour, or run:")
    print("  python okf_view.py sample/vault")
    print("  python okf_diff.py sample/vault-v2 sample/vault-v3")
    print("  git -C sample/vault log --oneline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
