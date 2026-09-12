import json
from pathlib import Path

from submission_gate import evaluate


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_submission_gate_requires_real_live_evidence_and_publication_inputs(
    tmp_path: Path,
):
    reports = tmp_path / "reports"
    write_json(
        reports / "source-generation.json",
        {"hermes_commit": "a" * 40, "sqlite_integrity_check": "ok"},
    )
    fidelity = {
        "status": "PASS",
        "mismatches": [],
        "memanto_loader_mapper": {"checked": True},
    }
    for name in (
        "fidelity.json",
        "live-roundtrip-fidelity.json",
        "fresh-destination-fidelity.json",
    ):
        write_json(reports / name, fidelity)
    (reports / "primary-golden-recall.txt").write_text("all expected text present")
    (reports / "fresh-golden-recall.txt").write_text("all expected text present")

    env = {
        "DEMO_VIDEO_URL": "https://video.example/demo",
        "SOCIAL_URLS": "https://social.example/post",
        "MEMANTO_ONBOARDING_CONFIRMED": "1",
    }
    assert evaluate(tmp_path, env) == []

    del env["DEMO_VIDEO_URL"]
    blockers = evaluate(tmp_path, env)
    assert any("DEMO_VIDEO_URL" in blocker for blocker in blockers)
