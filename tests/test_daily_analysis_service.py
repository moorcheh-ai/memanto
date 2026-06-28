import json
from unittest.mock import MagicMock


def test_conflict_report_handles_non_object_json_items(tmp_path, monkeypatch):
    """Malformed conflict-item schemas should be preserved instead of crashing."""
    from memanto.app.services import daily_analysis_service as module

    sessions_dir = tmp_path / "sessions"
    summaries_dir = tmp_path / "summaries"
    sessions_dir.mkdir()
    (sessions_dir / "agent-1_2026-06-28_001_summary.md").write_text(
        "# Session\n\nRemembered a conflicting preference.",
        encoding="utf-8",
    )

    client = MagicMock()
    client.answer.generate.return_value = {"answer": '["not an object", 1]'}
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: "test-model")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=summaries_dir,
    )

    result = service.generate_conflict_report("agent-1", "2026-06-28")

    assert result["status"] == "success"
    assert result["conflict_count"] == 1

    conflicts_path = tmp_path / ".memanto" / "conflicts" / (
        "agent-1_2026-06-28_conflicts.json"
    )
    conflicts = json.loads(conflicts_path.read_text(encoding="utf-8"))
    assert conflicts[0]["title"] == "Unparsed conflict report"
    assert conflicts[0]["description"] == '["not an object", 1]'
