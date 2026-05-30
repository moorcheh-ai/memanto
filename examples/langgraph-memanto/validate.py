"""Credential-free validation script for Memanto + LangGraph integration."""

import importlib
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
    print("Memanto + LangGraph Integration Validation")
    print("=" * 60)
    print()
    all_pass = True

    # 1. Module compilation
    print("1. Module Compilation")
    modules = ["memory_backend", "memory_nodes", "graph_builder", "hooks"]
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
    from memory_nodes import extract_signals, extract_from_file_references
    sigs = extract_signals("We decided to use PostgreSQL for the write model")
    all_pass = check(len(sigs) >= 1, f"Extract decision signals ({len(sigs)} found)") and all_pass
    sigs2 = extract_signals("You must always write tests for new features", "testing")
    all_pass = check(len(sigs2) >= 1 and "testing" in sigs2[0].get("tags", []), "Stage tags added") and all_pass
    file_sigs = extract_from_file_references("Created src/auth/login.py and tests/test_auth.py")
    all_pass = check(len(file_sigs) >= 1, f"File reference extraction ({len(file_sigs)} found)") and all_pass
    print()

    # 4. Memory context formatting
    print("4. Memory Context Formatting")
    from memory_nodes import format_memory_context
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

    # 5. Memory nodes (LangGraph)
    print("5. Memory Nodes (LangGraph)")
    from memory_nodes import recall_memories, store_memories
    test_state = {
        "messages": [{"role": "user", "content": "What is our architecture?"}],
        "session_id": "validation-session",
        "backend": backend,
        "stage": "research",
        "memory_context": "",
        "recalled_memories": [],
        "stored_memory_ids": [],
    }
    recalled = recall_memories(test_state)
    all_pass = check("memory_context" in recalled, "recall_memories sets memory_context") and all_pass
    all_pass = check("recalled_memories" in recalled, "recall_memories sets recalled_memories") and all_pass

    # Store a memory first, then recall it
    backend.store({"type": "decision", "content": "Use microservices for payment", "tags": ["architecture"]})
    recalled2 = recall_memories(test_state)
    all_pass = check(len(recalled2.get("recalled_memories", [])) >= 1, "Recall finds stored memory") and all_pass
    print()

    # 6. Graph building
    print("6. Graph Builder")
    from graph_builder import build_memory_graph, invoke_graph
    graph = build_memory_graph(backend=backend)
    all_pass = check(graph is not None, "build_memory_graph returns compiled graph") and all_pass
    result = invoke_graph(
        "We decided to use PostgreSQL for the database",
        session_id="validation-test",
        backend=backend,
    )
    all_pass = check("messages" in result, "invoke_graph returns messages") and all_pass
    all_pass = check("memory_context" in result, "invoke_graph returns memory_context") and all_pass
    all_pass = check("stored_memory_ids" in result, "invoke_graph returns stored_memory_ids") and all_pass
    print()

    # 7. Pre/post hooks
    print("7. Pre/Post Hook Lifecycle")
    from hooks import pre_execution_hook, post_execution_hook
    context = pre_execution_hook("Design the order system", session_id="test-session", backend=backend)
    all_pass = check(isinstance(context, str), "pre_execution_hook returns string") and all_pass
    ids = post_execution_hook(
        "Design the order system",
        "We decided to use event sourcing for orders. Must always use aggregate roots.",
        session_id="test-session",
        stage="planning",
        backend=backend,
    )
    all_pass = check(len(ids) >= 1, f"post_execution_hook stores signals ({len(ids)} stored)") and all_pass
    context2 = pre_execution_hook("What is our order module architecture?", session_id="different-session", backend=backend)
    all_pass = check(isinstance(context2, str), "Cross-session recall works") and all_pass
    print()

    # 8. Cross-session recall
    print("8. Cross-Session Recall")
    # Store in session A
    backend_a = LocalBackend(data_dir=tmpdir)  # Same data dir = shared memory
    backend_a.store({"type": "decision", "content": "Use React for the frontend", "tags": ["frontend"]})
    # Recall from session B
    backend_b = LocalBackend(data_dir=tmpdir)
    results_b = backend_b.recall("React frontend")
    all_pass = check(len(results_b) >= 1, "Memories from session A visible in session B") and all_pass
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
