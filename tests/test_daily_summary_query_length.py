"""Regression coverage for daily-summary embedding context overflow."""

from __future__ import annotations

from unittest.mock import MagicMock

from memanto.app.services import daily_analysis_service as module


def _make_summary_service(tmp_path, monkeypatch, session_content: str):
    sessions_dir = tmp_path / "sessions"
    summaries_dir = tmp_path / "summaries"
    sessions_dir.mkdir()
    (sessions_dir / "agent-1_2026-06-28_001_summary.md").write_text(
        session_content,
        encoding="utf-8",
    )

    client = MagicMock()

    def reject_oversized_embedding_query(**kwargs):
        query = kwargs["query"]
        if len(query) > 6_000:
            raise RuntimeError("embedding input exceeds context length")
        return {"answer": "# Daily Summary"}

    client.answer.generate.side_effect = reject_oversized_embedding_query
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: "test-model")

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=summaries_dir,
    )
    return service, client


def test_busy_day_summary_keeps_embedded_query_within_context_window(
    tmp_path, monkeypatch
):
    """Long session content must not be sent as an oversized embedding query."""
    long_content = "Important decision: use PostgreSQL for the project. " * 300
    service, client = _make_summary_service(tmp_path, monkeypatch, long_content)

    result = service.generate_summary("agent-1", "2026-06-28")

    assert result["status"] == "success"
    call_kwargs = client.answer.generate.call_args.kwargs
    assert len(call_kwargs["query"]) <= 6_000
    assert long_content in call_kwargs["header_prompt"]
    assert "Format the output as a Markdown report" in call_kwargs["footer_prompt"]


def test_short_day_summary_preserves_session_text_as_retrieval_query(
    tmp_path, monkeypatch
):
    """Short inputs should retain their full content for relevant retrieval."""
    short_content = "Decision: ship the authentication change on Friday."
    service, client = _make_summary_service(tmp_path, monkeypatch, short_content)

    result = service.generate_summary("agent-1", "2026-06-28")

    assert result["status"] == "success"
    call_kwargs = client.answer.generate.call_args.kwargs
    assert call_kwargs["query"] == short_content
    assert call_kwargs["ai_model"] == "test-model"
