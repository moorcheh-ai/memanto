#!/usr/bin/env python3
"""Reproducible test for broken import in demo_session_1.py

The demo script at ``examples/claudecode-skills-memanto/lifecycle-hooks/demo_session_1.py``
imports ``SkillMemory`` from ``memanto_skills``, which does not exist in the
repository. The correct import is ``memanto.SkillMemory``.

This causes an ``ModuleNotFoundError`` when users try to run the demo after
installing the ``memanto`` package.

Run: pytest tests/failing_tests/test_skill_memory_import.py
"""

import subprocess
import sys
from pathlib import Path


def test_demo_session_1_import() -> None:
    """Verify that demo_session_1.py can be imported without ModuleNotFoundError."""
    demo_path = Path(__file__).parents[2] / "examples" / "claudecode-skills-memanto" / "lifecycle-hooks" / "demo_session_1.py"
    
    # Try to import the module
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib.util; spec = importlib.util.spec_from_file_location('demo', '{demo_path}'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"],
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"Import failed with:\n{result.stderr}"