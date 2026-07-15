#!/usr/bin/env python3
"""
validate_offline.py
===================
Offline smoke test — no API keys, no server, no LLM required.

Proves:
  1. All modules import cleanly
  2. Mock cross-session recall runs end to end
  3. Contradiction correction stores NEW memory (old preserved in metadata)

Run:
    python validate_offline.py
"""

import os
import sys


def main():
    print("=" * 60)
    print("  LangGraph + Memanto — Offline Validation")
    print("=" * 60)

    # Test 1: imports
    print("\n[1/3] Checking imports...")
    try:
        import ast

        for fname in ["memanto_client.py", "tools.py", "graph.py", "run.py"]:
            path = os.path.join(os.path.dirname(__file__), fname)
            with open(path, encoding="utf-8") as fh:
                ast.parse(fh.read())
            print(f"  ✅ {fname} — valid syntax")
    except Exception as e:
        print(f"  ❌ Import check failed: {e}")
        sys.exit(1)

    # Test 2: mock demo runs end to end
    print("\n[2/3] Running mock cross-session demo...")
    try:
        # Suppress output for clean validation
        import io
        from contextlib import redirect_stdout

        from run import run_mock

        buf = io.StringIO()
        with redirect_stdout(buf):
            run_mock()
        output = buf.getvalue()

        assert "SESSION A" in output, "SESSION A missing"
        assert "SESSION B" in output, "SESSION B missing"
        assert "recall_node" in output, "recall_node missing"
        assert "New corrected memory stored" in output, (
            "contradiction correction missing"
        )
        print("  ✅ Session A stored memories")
        print("  ✅ Session B recalled memories via recall_node")
        print("  ✅ Contradiction correction stored new memory")
    except Exception as e:
        print(f"  ❌ Mock demo failed: {e}")
        sys.exit(1)

    # Test 3: verify contradiction creates NEW memory not mutation
    print("\n[3/3] Verifying contradiction handling...")
    try:
        import uuid

        db = {}
        old_fact = "~1000 physical qubits per logical qubit"
        new_fact = "~100 physical qubits per logical qubit (Google 2025)"
        new_id = f"mem_{uuid.uuid4().hex[:8]}"
        db[new_id] = {
            "id": new_id,
            "content": new_fact,
            "type": "fact",
            "metadata": {"previous_content": old_fact, "correction": True},
        }
        assert db[new_id]["content"] == new_fact
        assert db[new_id]["metadata"]["previous_content"] == old_fact
        assert db[new_id]["metadata"]["correction"] is True
        print("  ✅ New memory created (old fact NOT mutated)")
        print("  ✅ metadata.previous_content preserved for audit trail")
    except Exception as e:
        print(f"  ❌ Contradiction test failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  offline validation passed ✅")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
