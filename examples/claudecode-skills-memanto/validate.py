"""Credential-free validation script."""

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def check(condition: bool, name: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    return condition


def main() -> int:
    print("=" * 60)
    print("Memanto + mattpocock/skills Integration Validation")
    print("=" * 60)
    print()
    all_pass = True

    # 1. Module compilation
    print("1. Module Compilation")
    modules = ["memory_backend", "skill_memory", "claude_hooks", "mattpocock_adapter", "install_hooks"]
    for mod_name in modules:
        try:
            importlib.import_module(mod_name)
            all_pass = check(True, f"Import {mod_name}") and all_pass
        except Exception as e:
            all_pass = check(False, f"Import {mod_name}: {e}") and all_pass
    print()

    # 2. LocalBackend
    print("2. LocalBackend Store/Recall")
    from memory_backend import LocalBackend
    tmpdir = tempfile.mkdtemp()
    backend = LocalBackend(data_dir=tmpdir)
    mid = backend.store({"type": "decision", "content": "Use event sourcing", "tags": ["architecture"]})
    all_pass = check(isinstance(mid, str) and len(mid) > 0, "store() returns ID") and all_pass
    results = backend.recall("event sourcing")
    all_pass = check(len(results) >= 1, f"recall() finds stored memory ({len(results)} results)") and all_pass
    by_type = backend.recall_by_type("decision")
    all_pass = check(len(by_type) >= 1, f"recall_by_type() filters correctly ({len(by_type)} results)") and all_pass
    empty = backend.recall("zzz_nonexistent_xyz")
    all_pass = check(len(empty) == 0, "recall() returns empty for no match") and all_pass
    print()

    # 3. Signal extraction
    print("3. Signal Extraction")
    from skill_memory import extract_signals, extract_from_file_references
    sigs = extract_signals("We decided to use PostgreSQL for the write model")
    all_pass = check(len(sigs) >= 1, f"Extract decision signals ({len(sigs)} found)") and all_pass
    sigs2 = extract_signals("You must always write tests for new features", "tdd")
    all_pass = check(len(sigs2) >= 1 and "tdd" in sigs2[0].get("tags", []), "Skill tags added") and all_pass
    file_sigs = extract_from_file_references("Created src/auth/login.py and tests/test_auth.py")
    all_pass = check(len(file_sigs) >= 1, f"File reference extraction ({len(file_sigs)} found)") and all_pass
    print()

    # 4. Memory context formatting
    print("4. Memory Context Formatting")
    from skill_memory import format_memory_context
    formatted = format_memory_context([
        {"type": "decision", "content": "Use event sourcing", "confidence": 0.85, "tags": ["architecture"]},
        {"type": "instruction", "content": "Always use strict TypeScript", "confidence": 0.9, "tags": ["typescript"]},
    ])
    all_pass = check("DECISION" in formatted, "Formats decision type") and all_pass
    all_pass = check("INSTRUCTION" in formatted, "Formats instruction type") and all_pass
    all_pass = check("85%" in formatted, "Shows confidence percentage") and all_pass
    empty_fmt = format_memory_context([])
    all_pass = check(empty_fmt == "", "Empty context returns empty string") and all_pass
    print()

    # 5. Pre/post hooks
    print("5. Pre/Post Hook Lifecycle")
    os.environ["MEMANTO_SKILLS_DATA"] = tmpdir
    from skill_memory import pre_hook, post_hook
    context = pre_hook("/grill-with-docs Design the order system", "grill-with-docs")
    all_pass = check(isinstance(context, str), "pre_hook returns string") and all_pass
    ids = post_hook(
        "/grill-with-docs Design the order system",
        "We decided to use event sourcing for the order module",
        "grill-with-docs",
    )
    all_pass = check(len(ids) >= 1, f"post_hook stores signals ({len(ids)} stored)") and all_pass
    context2 = pre_hook("What is our order module architecture?", "tdd")
    all_pass = check(isinstance(context2, str), "Subsequent pre_hook works") and all_pass
    del os.environ["MEMANTO_SKILLS_DATA"]
    print()

    # 6. Skill wrapper generation
    print("6. Skill Wrapper Generation")
    from mattpocock_adapter import generate_wrappers
    wrapper_dir = tempfile.mkdtemp()
    wrappers = generate_wrappers(output_dir=wrapper_dir)
    all_pass = check(len(wrappers) >= 10, f"Generated {len(wrappers)} wrapper scripts") and all_pass
    for w in wrappers[:3]:
        all_pass = check(w.exists() and os.access(w, os.X_OK), f"Wrapper {w.name} is executable") and all_pass
    print()

    # 7. Skill listing
    print("7. Skill Manifest")
    from mattpocock_adapter import list_skills
    skills = list_skills()
    all_pass = check(len(skills) >= 10, f"Lists {len(skills)} skills") and all_pass
    skill_names = [s["name"] for s in skills]
    for expected in ["grill-with-docs", "tdd", "handoff"]:
        all_pass = check(expected in skill_names, f"Skill /{expected} in manifest") and all_pass
    print()

    # Summary
    print("=" * 60)
    if all_pass:
        print("ALL CHECKS PASSED - Integration is valid!")
    else:
        print("SOME CHECKS FAILED - Review output above")
    print("=" * 60)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
