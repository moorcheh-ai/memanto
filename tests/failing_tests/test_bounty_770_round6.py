"""Bounty #770 round 6 — daily summary must fail loudly on empty AI answer.

Run:  python -m pytest tests/failing_tests/test_bounty_770_round6.py -v
      (or:  python tests/failing_tests/test_bounty_770_round6.py)

Bug:
    DailyAnalysisService.generate_summary used
        summary_text = result.get("answer", "Failed to generate summary.")
    When the backend returns an empty/missing answer (rate limit, model
    error, malformed response), the placeholder text or empty string was
    written to the summary file and the method returned
    {"status": "success", ...} — a silent failure that looks like a
    successful daily summary.

    The legacy summarizer (context_summarization_service.py) raises
    MemoryError on an empty response ("Failed to generate summary - empty
    response from AI"). The new service lost that guard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _FakeClient:
    """Minimal moorcheh client whose answer.generate returns a canned dict."""

    def __init__(self, answer_payload):
        self._payload = answer_payload

    class _Answer:
        def __init__(self, payload):
            self._payload = payload

        def generate(self, **kwargs):
            return self._payload

    @property
    def answer(self):
        return self._Answer(self._payload)


def _setup(module, tmp_path, answer_payload):
    """Build a service wired to tmp dirs + fake client; returns svc."""
    import memanto.app.services.daily_analysis_service as m

    class FakeSessions:
        sessions_dir = tmp_path / "sessions"

    FakeSessions.sessions_dir.mkdir(parents=True, exist_ok=True)
    (FakeSessions.sessions_dir / "agent1_2026-01-15_x_summary.md").write_text(
        "[FACT] hello\n\nworld", encoding="utf-8"
    )

    svc = m.DailyAnalysisService.__new__(m.DailyAnalysisService)
    svc.session_service = FakeSessions()
    svc.sessions_dir = FakeSessions.sessions_dir
    svc.summaries_dir = tmp_path / "summaries"
    svc.summaries_dir.mkdir(parents=True, exist_ok=True)

    m.get_moorcheh_client = lambda: _FakeClient(answer_payload)
    m.get_active_llm_model = lambda *a, **k: None
    m.get_active_embedding_model = lambda *a, **k: None
    m.format_current_local_time = lambda: "2026-01-15 12:00:00"
    return svc, m


def test_empty_answer_must_not_report_success(tmp_path):
    """answer key present but empty string -> must raise MemoryError and
    must NOT write a summary file claiming success."""
    import memanto.app.services.daily_analysis_service as m

    svc, _ = _setup(m, tmp_path, {"answer": ""})

    from memanto.app.utils.errors import MemoryError as MemantoError

    try:
        svc.generate_summary("agent1", "2026-01-15")
        raise AssertionError("empty answer must raise MemoryError")
    except MemantoError:
        pass

    out = svc.summaries_dir / "agent1_2026-01-15.md"
    assert not out.exists(), (
        "empty answer must not write a summary file, but found one"
    )


def test_missing_answer_key_must_not_write_placeholder(tmp_path):
    """No answer key at all -> must not write 'Failed to generate summary.'
    into the summary file and claim success."""
    import memanto.app.services.daily_analysis_service as m

    svc, _ = _setup(m, tmp_path, {"foo": "bar"})

    from memanto.app.utils.errors import MemoryError as MemantoError

    try:
        svc.generate_summary("agent1", "2026-01-15")
        raise AssertionError("missing answer key must raise MemoryError")
    except MemantoError:
        pass

    out = svc.summaries_dir / "agent1_2026-01-15.md"
    assert not out.exists(), (
        "missing answer must not write a summary file, but found one"
    )


def test_valid_answer_still_writes_summary(tmp_path):
    """A real answer must still produce the summary file (no regression)."""
    import memanto.app.services.daily_analysis_service as m

    svc, _ = _setup(m, tmp_path, {"answer": "# Daily Summary\n\nAll good."})

    result = svc.generate_summary("agent1", "2026-01-15")
    assert result["status"] == "success"
    out = svc.summaries_dir / "agent1_2026-01-15.md"
    assert out.exists()
    assert "All good." in out.read_text(encoding="utf-8")


if __name__ == "__main__":
    import tempfile

    failures = 0
    for t in (
        test_empty_answer_must_not_report_success,
        test_missing_answer_key_must_not_write_placeholder,
        test_valid_answer_still_writes_summary,
    ):
        try:
            t(Path(tempfile.mkdtemp(prefix="memanto_r6_")))
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")
    sys.exit(1 if failures else 0)
