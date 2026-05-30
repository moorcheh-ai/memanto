#!/usr/bin/env python3
# Generates all source files for the Memanto + skills integration
import pathlib

DIR = pathlib.Path(__file__).parent

# ---- memory_backend.py ----
(DIR / "memory_backend.py").write_text(
    pathlib.Path(__file__).parent.joinpath("memory_backend.py").read_text()
)

# This script validates and fixes source files
import py_compile
import sys

files = ["memory_backend.py", "skill_memory.py", "claude_hooks.py", "mattpocock_adapter.py", "install_hooks.py", "validate.py", "test_skill_memory.py"]
for f in files:
    try:
        py_compile.compile(DIR / f, doraise=True)
        print(f"OK: {f}")
    except Exception as e:
        print(f"FAIL: {f}: {e}")
