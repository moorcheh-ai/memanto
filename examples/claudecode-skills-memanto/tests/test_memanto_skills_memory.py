from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "memanto_skills_memory.py"


def run_cli(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def test_cross_skill_recall_round_trip(tmp_path: Path) -> None:
    store = tmp_path / "memory.jsonl"

    output = run_cli(
        "--store",
        str(store),
        "post",
        "--skill",
        "grill-with-docs",
        "--tags",
        "payments,architecture",
        "--transcript",
        "\n".join(
            [
                "Decision: Use FastAPI routers for HTTP boundaries.",
                "Preference: Write pytest coverage before changing shared behavior.",
                "Instruction: Keep service functions pure unless persistence is required.",
            ]
        ),
    )
    assert "extracted=3 stored=3" in output

    context = run_cli(
        "--store",
        str(store),
        "pre",
        "--skill",
        "tdd",
        "--prompt",
        "Implement invoice endpoint with pytest around service behavior",
    )
    assert "FastAPI routers" in context
    assert "pytest coverage" in context
    assert "service functions pure" in context


def test_post_is_idempotent_for_duplicate_memory(tmp_path: Path) -> None:
    store = tmp_path / "memory.jsonl"
    args = [
        "--store",
        str(store),
        "post",
        "--skill",
        "handoff",
        "--transcript",
        "Decision: Keep migrations backward compatible.",
    ]

    first = run_cli(*args)
    second = run_cli(*args)

    assert "extracted=1 stored=1" in first
    assert "extracted=1 stored=0" in second


def test_run_injects_context_and_stores_child_output(tmp_path: Path) -> None:
    store = tmp_path / "memory.jsonl"
    run_cli(
        "--store",
        str(store),
        "post",
        "--skill",
        "grill-with-docs",
        "--transcript",
        "Decision: Use FastAPI routers for HTTP boundaries.",
    )

    child = (
        "import os; "
        "print('context present', 'FastAPI routers' in "
        "os.environ.get('MEMANTO_SKILL_CONTEXT', '')); "
        "print('Decision: Prefer service-layer fakes in tdd.')"
    )
    output = run_cli(
        "--store",
        str(store),
        "run",
        "--skill",
        "tdd",
        "--prompt",
        "Implement the invoice endpoint",
        "--tags",
        "payments",
        "--",
        sys.executable,
        "-c",
        child,
    )

    assert "context present True" in output
    assert "run exit=0 stored=1" in output

    context = run_cli(
        "--store",
        str(store),
        "pre",
        "--skill",
        "handoff",
        "--prompt",
        "Summarize testing decisions for the invoice endpoint",
    )
    assert "Prefer service-layer fakes" in context


def test_post_omits_tags_that_normalize_to_empty(tmp_path: Path) -> None:
    store = tmp_path / "memory.jsonl"

    run_cli(
        "--store",
        str(store),
        "post",
        "--skill",
        "handoff",
        "--tags",
        "payments,!!!, -- ",
        "--transcript",
        "Decision: Keep migrations backward compatible.",
    )

    assert '""' not in store.read_text(encoding="utf-8")
    assert '"payments"' in store.read_text(encoding="utf-8")
