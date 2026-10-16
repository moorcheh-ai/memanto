"""Demonstrate module-level environment state leaking between test imports."""

from __future__ import annotations

import os
import subprocess
import sys


SCRIPT = """
import os
os.environ['MEMANTO_AUDIT_FLAG'] = 'leaked'
print(os.environ.get('MEMANTO_AUDIT_FLAG', 'missing'))
"""


def main() -> int:
    original = os.environ.pop("MEMANTO_AUDIT_FLAG", None)
    try:
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            capture_output=True,
            text=True,
            check=True,
        )
        leaked_to_parent = os.environ.get("MEMANTO_AUDIT_FLAG")
        print(f"child_module_value={result.stdout.strip()}")
        print(f"parent_value_after_child={leaked_to_parent or 'missing'}")
        print("observation=process-local module mutation remains for the importing test process")
    finally:
        if original is not None:
            os.environ["MEMANTO_AUDIT_FLAG"] = original
        else:
            os.environ.pop("MEMANTO_AUDIT_FLAG", None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
