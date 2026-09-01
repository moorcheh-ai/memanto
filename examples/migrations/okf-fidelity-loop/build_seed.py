#!/usr/bin/env python3
"""Build the seed batches for the source agent from this repository.

Every memory is derived from code that is actually in the tree — a CLI command
and its docstring, a service module, a test file — so the source store is
reproducible rather than invented. The hand-written insights in
``seed_memories.json`` are prepended.

    python build_seed.py            # writes seed/batch-01.json, ...

``memanto remember --batch`` accepts at most 100 memories per call, so the
output is chunked to match.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BATCH_LIMIT = 100

# (directory, glob, memory type, sentence template)
SOURCES = [
    ("memanto/app/services", "*.py", "fact", "Service {name} — {doc}"),
    ("memanto/app/routes", "*.py", "relationship", "Router {name} — {doc}"),
    ("memanto/app/utils", "*.py", "artifact", "Utility {name} — {doc}"),
    ("memanto/app/clients", "*.py", "fact", "Client {name} — {doc}"),
    ("tests", "test_*.py", "observation", "{name} covers: {doc}"),
]


def first_line(text: str | None) -> str:
    """First sentence-ish line of a docstring, lowercased for the template."""
    if not text:
        return ""
    line = " ".join(text.strip().splitlines()[:2]).strip()
    return line[0].lower() + line[1:] if line else ""


def commands() -> list[dict[str, Any]]:
    """Every registered CLI command, from its decorator and docstring."""
    out = []
    for path in sorted((REPO / "memanto/cli/commands").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not (
                    isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                ):
                    continue
                if dec.func.attr != "command":
                    continue
                app = getattr(dec.func.value, "id", "")
                name = dec.args[0].value if dec.args else node.name
                group = app.replace("_app", "").replace("app", "")
                label = f"{group} {name}".strip() if group else name
                doc = first_line(ast.get_docstring(node))
                if not doc:
                    continue
                out.append(
                    {
                        "content": f"Run `memanto {label}` to {doc}",
                        "type": "instruction",
                        "title": f"memanto {label}"[:100],
                        "tags": ["cli", group or "core"],
                        "source": "repo-scan",
                        "provenance": "validated",
                        "source_ref": f"memanto/cli/commands/{path.name}",
                    }
                )
    return out


def modules() -> list[dict[str, Any]]:
    """One memory per documented module in the mapped source directories."""
    out = []
    for rel, glob, mem_type, template in SOURCES:
        for path in sorted((REPO / rel).glob(glob)):
            if path.name == "__init__.py":
                continue
            doc = first_line(
                ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
            )
            if not doc:
                continue
            name = path.stem
            out.append(
                {
                    "content": template.format(name=name, doc=doc),
                    "type": mem_type,
                    "title": name.replace("_", " ")[:100],
                    "tags": [rel.split("/")[-1]],
                    "source": "repo-scan",
                    "provenance": "validated",
                    "source_ref": f"{rel}/{path.name}",
                }
            )
    return out


def main() -> int:
    curated = json.loads((HERE / "seed_memories.json").read_text(encoding="utf-8"))
    memories = curated + commands() + modules()

    out_dir = HERE / "seed"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("batch-*.json"):
        old.unlink()

    for index in range(0, len(memories), BATCH_LIMIT):
        batch = memories[index : index + BATCH_LIMIT]
        path = out_dir / f"batch-{index // BATCH_LIMIT + 1:02d}.json"
        path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
        print(f"{path.relative_to(HERE)}: {len(batch)} memories")

    counts: dict[str, int] = {}
    for mem in memories:
        counts[mem["type"]] = counts.get(mem["type"], 0) + 1
    print(f"\ntotal: {len(memories)} memories across {len(counts)} types")
    for mem_type, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {mem_type:14} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
