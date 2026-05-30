#!/usr/bin/env python3
"""Validates all source files for the Memanto + skills integration."""
import py_compile
import sys
from pathlib import Path

DIR = Path(__file__).parent

files = [
    "memory_backend.py",
    "skill_memory.py",
    "claude_hooks.py",
    "mattpocock_adapter.py",
    "install_hooks.py",
    "validate.py",
    "test_skill_memory.py",
]

all_ok = True
for f in files:
    try:
        py_compile.compile(DIR / f, doraise=True)
        print(f"OK: {f}")
    except py_compile.PyCompileError as e:
        print(f"FAIL: {f}: {e}")
        all_ok = False

if not all_ok:
    sys.exit(1)
print(f"\nAll {len(files)} files validated successfully.")
