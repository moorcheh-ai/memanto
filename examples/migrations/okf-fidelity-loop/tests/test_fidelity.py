"""The harness must report convergence, and catch a loop that never converges."""

import sys
from pathlib import Path

from memanto.app.services.okf_export_service import OkfExportService

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fidelity import report, round_trip  # noqa: E402


def _bundle(tmp_path):
    service = OkfExportService(exports_dir=tmp_path / "exports")
    memories = {
        "fact": [
            {
                "id": "m1",
                "title": "Postgres is the DB",
                "content": "The project uses PostgreSQL 16.",
                "tags": ["infra"],
                "confidence": 0.9,
                "source": "seed",
                "created_at": "2026-01-02T03:04:05+00:00",
                "source_ref": "https://example.com/db",
            }
        ]
    }
    result = service.write_okf_bundle(
        "agent1", memories, output_dir=tmp_path / "src", split="file"
    )
    return Path(result["output_path"])


def test_round_trips_converge(tmp_path):
    history = round_trip(_bundle(tmp_path), 3, tmp_path / "work")
    text, converged = report(tmp_path / "src", history)

    assert converged is not None, text
    assert all(r["content"].count("[Supporting data]") == 1 for r in history[-1])
    assert "PostgreSQL 16" in history[-1][0]["content"]


def test_growing_content_is_reported_as_drift(tmp_path):
    history = round_trip(_bundle(tmp_path), 2, tmp_path / "work")
    # Simulate the pre-fix behaviour: every generation a little longer.
    for generation, rows in enumerate(history):
        for row in rows:
            row["content"] += "\n" * generation

    text, converged = report(tmp_path / "src", history)

    assert converged is None
    assert "Not converged" in text
