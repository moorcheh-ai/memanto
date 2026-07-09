#!/usr/bin/env python3
"""One-command setup for the Memanto + Claude Code skills memory layer.

    python install.py            # install hooks into ./.claude/settings.json
    python install.py --global   # install into ~/.claude/settings.json
    python install.py --uninstall

Thin wrapper around ``memanto_skills.installer`` so the example is usable
without pip-installing the package first.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memanto_skills.installer import install_hooks, uninstall_hooks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--global",
        dest="global_scope",
        action="store_true",
        help="Use ~/.claude/settings.json instead of ./.claude/settings.json.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the hooks instead of installing them.",
    )
    args = parser.parse_args()

    if args.uninstall:
        return uninstall_hooks(global_scope=args.global_scope)
    return install_hooks(global_scope=args.global_scope)


if __name__ == "__main__":
    raise SystemExit(main())
