"""Tiny fake skills used by the credential-free demo and tests."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["grill-with-docs", "tdd", "handoff"])
    args = parser.parse_args()

    context = os.getenv("MEMANTO_SKILL_CONTEXT", "")
    if args.mode == "grill-with-docs":
        print(
            "Decision: Use a repository-local adapter instead of patching upstream skills."
        )
        print("Convention: Keep generated prompts short and source-linked.")
        return

    if args.mode == "tdd":
        if "repository-local adapter" in context:
            print("saw prior architecture decision")
        print("Must: Exercise the memory bridge without network credentials.")
        return

    if "without network credentials" in context:
        print("handoff includes test constraint from prior skill")
    print("Avoid: Storing secrets or raw hidden prompts in Memanto.")


if __name__ == "__main__":
    main()
