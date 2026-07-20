"""
Tests for conflict detection query length (issue #1329).

detect-conflicts fails when the day's session content exceeds the embedding
model's context window because generate_conflict_report() stuffs the entire
prompt (instructions + session content) into the ``query`` parameter of
client.answer.generate().  The ``query`` is embedded for retrieval, so any
input exceeding the model's context length (e.g. 2048 tokens for the default
nomic-embed-text) causes a hard error.

The fix: move instructions into header_prompt / footer_prompt (which are NOT
embedded) and keep ``query`` as a compact digest that stays within context
limits.
"""

from unittest.mock import MagicMock

from memanto.app.services import daily_analysis_service as module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Conservative char-to-token estimate: 1 token ~ 4 chars for English text.
# 2048 tokens x 4 chars/token = 8192 chars.  We use a safety margin of
# roughly 6000 chars to account for tokeniser variability.
_MAX_QUERY_CHARS = 6000


def _make_service_with_session_content(tmp_path, session_content, monkeypatch):
    """Create a DailyAnalysisService with faked session file and client."""
    sessions_dir = tmp_path / "sessions"
    summaries_dir = tmp_path / "summaries"
    sessions_dir.mkdir()

    (sessions_dir / "agent-1_2026-06-28_001_summary.md").write_text(
        session_content, encoding="utf-8"
    )

    client = MagicMock()
    client.answer.generate.return_value = {"answer": "[]"}
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: "test-model")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=summaries_dir,
    )
    return service, client


# ---------------------------------------------------------------------------
# Tests -- conflict query must stay within embedding context window
# ---------------------------------------------------------------------------


class TestConflictQueryContextOverflow:
    """Issue #1329: detect-conflicts must not exceed the embedding context
    window with the query parameter."""

    def test_conflict_report_query_stays_within_context_window(
        self, tmp_path, monkeypatch
    ):
        """The ``query`` passed to answer.generate() must not exceed a
        context-window-safe length, even when the day's session content is
        very long (11KB+ as reported in the issue)."""
        # Simulate a day with a lot of session content (~11KB as in the issue)
        long_content = "Important decision: we chose PostgreSQL. " * 250  # ~11KB
        service, client = _make_service_with_session_content(
            tmp_path, long_content, monkeypatch
        )

        service.generate_conflict_report("agent-1", "2026-06-28")

        call_kwargs = client.answer.generate.call_args.kwargs
        query = call_kwargs["query"]

        # The query must be short enough to fit within an embedding model's
        # context window (conservative limit: 6000 chars ~ 1500 tokens).
        assert len(query) <= _MAX_QUERY_CHARS, (
            f"Query is {len(query)} chars -- exceeds safe embedding context limit "
            f"of {_MAX_QUERY_CHARS} chars. This will break with nomic-embed-text "
            f"(2048 token context window) on days with substantial session content."
        )

    def test_conflict_report_uses_header_and_footer_prompts(
        self, tmp_path, monkeypatch
    ):
        """Instructions for the LLM must be in header_prompt/footer_prompt,
        not crammed into the embedded query parameter."""
        long_content = "We use Django and it is maintained. " * 250
        service, client = _make_service_with_session_content(
            tmp_path, long_content, monkeypatch
        )

        service.generate_conflict_report("agent-1", "2026-06-28")

        call_kwargs = client.answer.generate.call_args.kwargs

        # The instructions must be separated from the query -- they belong in
        # header_prompt and footer_prompt which are NOT embedded.
        assert "header_prompt" in call_kwargs, (
            "header_prompt must be provided to keep LLM instructions out of "
            "the embedded query (issue #1329)"
        )
        assert "footer_prompt" in call_kwargs, (
            "footer_prompt must be provided to keep LLM instructions out of "
            "the embedded query (issue #1329)"
        )

        # header_prompt should contain the conflict analysis instructions
        header = call_kwargs["header_prompt"]
        assert "conflict" in header.lower() or "contradiction" in header.lower(), (
            "header_prompt should contain the conflict-detection instructions "
            "that were previously embedded in the query"
        )

    def test_conflict_report_query_does_not_contain_instruction_text(
        self, tmp_path, monkeypatch
    ):
        """The query should be a compact digest of session content, not the
        full instruction-laden prompt that was previously used."""
        long_content = "The project uses Redis for caching. " * 250
        service, client = _make_service_with_session_content(
            tmp_path, long_content, monkeypatch
        )

        service.generate_conflict_report("agent-1", "2026-06-28")

        call_kwargs = client.answer.generate.call_args.kwargs
        query = call_kwargs["query"]

        # The old bug stuffed the entire instruction prompt into the query.
        # After the fix, the query should NOT contain instruction directives
        # like "You MUST respond with ONLY a valid JSON array" or
        # "CRITICAL INSTRUCTIONS".
        instruction_markers = [
            "CRITICAL INSTRUCTIONS",
            "You MUST respond with ONLY a valid JSON array",
            "If there are NO conflicts",
        ]
        for marker in instruction_markers:
            assert marker not in query, (
                f"Instruction text '{marker}' should be in header/footer_prompt, "
                f"not in the embedded query (issue #1329)"
            )

    def test_conflict_report_short_content_still_works(self, tmp_path, monkeypatch):
        """Even with short session content, the fix must produce a valid
        conflict report with proper header/footer prompts."""
        short_content = "We decided to use PostgreSQL instead of MySQL."
        service, client = _make_service_with_session_content(
            tmp_path, short_content, monkeypatch
        )

        result = service.generate_conflict_report("agent-1", "2026-06-28")

        assert result["status"] == "success"
        call_kwargs = client.answer.generate.call_args.kwargs
        assert "header_prompt" in call_kwargs
        assert "footer_prompt" in call_kwargs
        # query should still contain the session content (or a digest of it)
        assert len(call_kwargs["query"]) > 0

    def test_conflict_report_preserves_ai_model_kwarg(self, tmp_path, monkeypatch):
        """The fix must preserve the ai_model kwarg that was already being
        passed to answer.generate()."""
        short_content = "Small session content."
        service, client = _make_service_with_session_content(
            tmp_path, short_content, monkeypatch
        )

        service.generate_conflict_report("agent-1", "2026-06-28")

        call_kwargs = client.answer.generate.call_args.kwargs
        assert call_kwargs.get("ai_model") == "test-model"

    def test_conflict_report_no_ai_model_when_unset(self, tmp_path, monkeypatch):
        """When no active AI model is set, ai_model should be omitted from
        the generate call (existing behaviour must be preserved)."""
        short_content = "Small session content."
        sessions_dir = tmp_path / "sessions"
        summaries_dir = tmp_path / "summaries"
        sessions_dir.mkdir()
        (sessions_dir / "agent-1_2026-06-28_001_summary.md").write_text(
            short_content, encoding="utf-8"
        )

        client = MagicMock()
        client.answer.generate.return_value = {"answer": "[]"}
        monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
        monkeypatch.setattr(module, "get_active_llm_model", lambda _: None)
        monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

        service = module.DailyAnalysisService(
            sessions_dir=sessions_dir,
            summaries_dir=summaries_dir,
        )
        service.generate_conflict_report("agent-1", "2026-06-28")

        call_kwargs = client.answer.generate.call_args.kwargs
        assert "ai_model" not in call_kwargs
