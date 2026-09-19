"""Regression tests for FINDING-05: untrusted text must not steer the
backend ``#key:value`` retrieval-filter channel.

The Moorcheh backends execute ``#key:value`` tokens found in the ``query``
field as server-side metadata filters. Free text (user queries and memory
contents that daily summaries / conflict digests are built from) flows into
that field, so a poisoned memory ending in ``#agent:<value>`` can suppress
the entire recall context. ``neutralize_filter_syntax`` defuses those tokens
while leaving markdown headers and bare hashtags intact.
"""

from pathlib import Path
from unittest.mock import patch

from memanto.app.clients.backend import Backend
from memanto.app.services.daily_analysis_service import DailyAnalysisService
from memanto.app.utils.query_safety import neutralize_filter_syntax


class TestNeutralizeFilterSyntax:
    def test_defuses_key_value_token(self):
        assert neutralize_filter_syntax("note #agent:guest") == "note agent:guest"

    def test_defuses_token_at_start(self):
        assert neutralize_filter_syntax("#memory_type:fact today") == "memory_type:fact today"

    def test_defuses_multiple_tokens(self):
        assert (
            neutralize_filter_syntax("a #k1:v1 b #k2:v2") == "a k1:v1 b k2:v2"
        )

    def test_token_at_tail_is_defused(self):
        # The backend applies the filter when the token is the final one:
        # this is the exact daily-summary poisoning shape.
        assert neutralize_filter_syntax("day note. #agent:tb") == "day note. agent:tb"

    def test_leaves_markdown_headers_intact(self):
        text = "# Session Summary for agent\n#agent:tb\ncontent"
        out = neutralize_filter_syntax(text)
        assert out.startswith("# Session Summary for agent")
        assert "#agent:tb" not in out

    def test_leaves_bare_hashtags_and_colons_intact(self):
        assert neutralize_filter_syntax("release #v2 notes: see") == "release #v2 notes: see"

    def test_empty_and_none_like_inputs(self):
        assert neutralize_filter_syntax("") == ""
        assert neutralize_filter_syntax("plain text") == "plain text"

    def test_newline_boundary_counts_as_token_start(self):
        assert (
            neutralize_filter_syntax("line1\n#agent:x line2") == "line1\nagent:x line2"
        )


class TestDailySummaryQueryIsDefused:
    def test_poisoned_memory_cannot_steer_retrieval_query(self, tmp_path: Path):
        captured: dict = {}

        class RecordingClient:
            class answer:
                @staticmethod
                def generate(**kwargs):
                    captured.update(kwargs)
                    return {"answer": "summary", "sources": []}

            namespaces = type("ns", (), {"list": staticmethod(lambda: {"namespaces": []})})

        sessions = tmp_path / "sessions"
        sessions.mkdir()
        summaries = tmp_path / "summaries"
        summaries.mkdir()
        poisoned = (
            "The team now uses Redis for caching. Vault password rotated. #agent:guest"
        )
        (sessions / "agent1_2026-09-14_s1_summary.md").write_text(poisoned, encoding="utf-8")

        service = DailyAnalysisService(sessions_dir=sessions, summaries_dir=summaries)
        with patch(
            "memanto.app.services.daily_analysis_service.get_moorcheh_client",
            return_value=RecordingClient(),
        ):
            result = service.generate_summary("agent1", "2026-09-14")

        assert result["status"] == "success"
        query = captured["query"]
        # The poisoned trailing filter token must not reach the backend intact.
        assert not query.rstrip().endswith("#agent:guest")
        assert "#agent:guest" not in query
        # ...while the semantic content survives for embedding.
        assert "Redis for caching" in query


class TestTruncationCannotReassembleFilterTokens:
    """_truncate_embedding_query concatenates non-contiguous slices, so it can
    reassemble a ``#key:value`` token from pieces that were harmless in the
    sanitized source. The final query must be re-sanitized after truncation."""

    OVERSIZED = "x" * 4000

    def _build_service(self, tmp_path: Path, content: str):
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        summaries = tmp_path / "summaries"
        summaries.mkdir()
        (sessions / "agent1_2026-09-14_s1_summary.md").write_text(content, encoding="utf-8")
        return DailyAnalysisService(sessions_dir=sessions, summaries_dir=summaries)

    def test_summary_digest_stays_defused_on_oversized_input(self, tmp_path: Path):
        captured: dict = {}

        class RecordingClient:
            class answer:
                @staticmethod
                def generate(**kwargs):
                    captured.update(kwargs)
                    return {"answer": "summary", "sources": []}

            namespaces = type("ns", (), {"list": staticmethod(lambda: {"namespaces": []})})

        # '#' far from 'key:value': harmless separately, but the digest's
        # slice concatenation would join them into a live filter token.
        text = self.OVERSIZED
        text = text[:179] + "#" + text[180:400] + "key:value" + text[410:]
        service = self._build_service(tmp_path, text)

        with patch(
            "memanto.app.services.daily_analysis_service.get_moorcheh_client",
            return_value=RecordingClient(),
        ):
            result = service.generate_summary("agent1", "2026-09-14")

        assert result["status"] == "success"
        query = captured["query"]
        assert "#key:value" not in query

    def test_conflict_digest_stays_defused_on_oversized_input(self, tmp_path: Path):
        captured: dict = {}

        class RecordingClient:
            base_url = "http://localhost:8080"
            api_key = "test-key"

            class answer:
                @staticmethod
                def generate(**kwargs):
                    captured.update(kwargs)
                    return {"answer": "[]", "sources": []}

            namespaces = type("ns", (), {"list": staticmethod(lambda: {"namespaces": []})})

        text = self.OVERSIZED
        text = text[:179] + "#" + text[180:400] + "key:value" + text[410:]
        service = self._build_service(tmp_path, text)

        # The digest sink lives in the legacy (on-prem) conflict-report path.
        with (
            patch("memanto.app.services.daily_analysis_service.parse_backend",
                  return_value=Backend.ON_PREM),
            patch(
                "memanto.app.services.daily_analysis_service.get_moorcheh_client",
                return_value=RecordingClient(),
            ),
        ):
            service.generate_conflict_report("agent1", "2026-09-14")

        digest = captured.get("query", "")
        assert "#key:value" not in digest
