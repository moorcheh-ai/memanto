#!/usr/bin/env python
"""Print the memanto FastAPI app's OpenAPI spec to stdout.

Used by both the CI drift check (.github/workflows/sdk-typescript.yml) and
the local `npm run openapi:regenerate` so the two can never diverge. The
"version" field is pinned to a fixed fallback rather than the real
hatch-vcs-derived version, since that value is different on every commit
and would make the spec drift on every run otherwise.
"""

import json
from pathlib import Path

FALLBACK_VERSION = "0.0.0.dev0"
VERSION_FILE = (
    Path(__file__).resolve().parent.parent / "memanto" / "app" / "_version.py"
)

VERSION_FILE.write_text(f'__version__ = "{FALLBACK_VERSION}"\n')

from memanto.app.main import app  # noqa: E402

print(json.dumps(app.openapi(), indent=2))
