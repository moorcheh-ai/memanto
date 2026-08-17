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

    class FakeTokenizer:
        @staticmethod
        def encode(text: str, disallowed_special=()):
            # Mirrors tiktoken's signature: production passes
            # disallowed_special=() so special-token markers in session prose
            # are encoded as ordinary text instead of raising ValueError.
            return list(text.encode("utf-8"))

        @staticmethod
        def decode(token_ids):
            return bytes(token_ids).decode("utf-8", errors="ignore")

    tokenizer = FakeTokenizer()

    def reject_oversized_embedding_query(**kwargs):
        query = kwargs["query"]
        if len(tokenizer.encode(query)) > module._EMBEDDING_QUERY_TOKEN_BUDGET:
            raise RuntimeError("embedding input exceeds context length")
        return {"answer": "# Daily Summary"}

    client.answer.generate.side_effect = reject_oversized_embedding_query
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: "test-model")
    monkeypatch.setattr(
        module, "get_active_embedding_model", lambda: "test-embedding-model"
    )
    monkeypatch.setattr(module, "_get_embedding_tokenizer", lambda _: tokenizer)

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
    assert (
        len(call_kwargs["query"].encode("utf-8"))
        <= module._EMBEDDING_QUERY_TOKEN_BUDGET
    )
    assert long_content in call_kwargs["header_prompt"]
    assert "Format the output as a Markdown report" in call_kwargs["footer_prompt"]


def test_short_day_summary_preserves_session_text_as_retrieval_query(
    tmp_path, monkeypatch
):
    """Short inputs should retain their full content for relevant retrieval."""
    short_content = "Decision: ship the authentication change on Friday."
    service, client = _make_summary_service(tmp_path, monkeypatch, short_content)

    service.generate_summary("agent-1", "2026-06-28")

    call_kwargs = client.answer.generate.call_args.kwargs
    assert call_kwargs["query"] == short_content
    assert call_kwargs["ai_model"] == "test-model"


def test_dense_unicode_fallback_stays_inside_conservative_byte_budget(monkeypatch):
    """Unknown model tokenizers must still stay safely below 2,048 tokens."""
    monkeypatch.setattr(module, "_get_embedding_tokenizer", lambda _: None)
    dense_content = "界" * 5_000

    query = module._truncate_embedding_query(
        dense_content,
        model="server-managed-model",
    )

    assert len(query.encode("utf-8")) <= module._EMBEDDING_QUERY_TOKEN_BUDGET
    assert dense_content.startswith(query)
    assert module._EMBEDDING_QUERY_TOKEN_BUDGET < module._EMBEDDING_CONTEXT_TOKENS
