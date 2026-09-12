"""Make the adapter package importable for the test suite.

pytest loads this file before collecting test modules, so ``test_adapter.py``
can import ``claude_code_adapter`` with plain top-level imports regardless of
the directory pytest is invoked from.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
