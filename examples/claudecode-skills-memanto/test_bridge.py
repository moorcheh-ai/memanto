"""Tests for bridge.py — credential-free, runs against JSONL backend only."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Force local backend for tests
os.environ["MEMANTO_BACKEND"] = "local"

sys.path.insert(0, str(Path(__file__).parent))
import bridge


class TestClassify:
    def test_grill(self):
        assert bridge._classify("/grill-with-docs") == "decision"

    def test_tdd(self):
        assert bridge._classify("/tdd") == "learning"

    def test_handoff(self):
        assert bridge._classify("/handoff") == "instruction"

    def test_architect(self):
        assert bridge._classify("/architect") == "goal"

    def test_capture(self):
        assert bridge._classify("/capture") == "context"

    def test_unknown(self):
        assert bridge._classify("/xyz-random") == "context"


class TestExtractDecisions:
    def test_extraction_live_uses_answer(self):
        with patch.dict(os.environ, {"MEMANTO_BACKEND": "live", "MOORCHEH_API_KEY": "k"}):
            with patch.object(bridge, "_LiveClient") as mock:
                inst = mock.return_value
                inst.answer.return_value = "Use OAuth 2.1 with PKCE"
                result = bridge._extract_decisions("/grill-with-docs", "src/auth.ts", "Some transcript about auth")
                assert "OAuth 2.1" in result

    def test_local_extraction_keywords(self):
        raw = "Line 1\nDecision: Use Postgres\nPattern: Repository pattern\nRandom text"
        result = bridge._extract_decisions("/architect", "src/db.ts", raw)
        assert "Decision: Use Postgres" in result
        assert "Pattern: Repository pattern" in result

    def test_local_fallback_no_keywords(self):
        raw = "Some text\nWithout keywords\nJust talk"
        result = bridge._extract_decisions("/fix", "src/bug.ts", raw)
        assert len(result) > 0

    def test_extraction_empty_transcript(self):
        result = bridge._extract_decisions("/tdd", "src/test.ts", "")
        assert "Executed /tdd on src/test.ts" in result


class TestLocalBackend:
    def setup_method(self):
        bridge.MEMORY_FILE = Path(tempfile.mktemp(suffix=".jsonl"))

    def teardown_method(self):
        if bridge.MEMORY_FILE.exists():
            bridge.MEMORY_FILE.unlink()

    def test_store_and_search(self):
        bridge._local_store({"content": "Use OAuth 2.1 with PKCE for auth"})
        bridge._local_store({"content": "Prefer hexagonal architecture pattern"})
        results = bridge._local_search("OAuth", limit=5)
        assert len(results) == 1
        assert "OAuth 2.1" in results[0]["content"]

    def test_search_no_matches(self):
        bridge._local_store({"content": "Use Redis for caching"})
        results = bridge._local_search("PostgreSQL", limit=5)
        assert len(results) == 0


class TestPre:
    def test_pre_local_first_run(self):
        context = bridge._inject_context("src/unknown.ts")
        assert context == ""

    def test_pre_local_with_memory(self):
        bridge._local_store({"content": "Use JWT for authentication"})
        bridge._local_store({"content": "Hexagonal architecture"})
        ctx = bridge._inject_context("auth")
        assert "JWT" in ctx


class TestPost:
    def test_post_local_stores(self):
        old_path = bridge.MEMORY_FILE
        bridge.MEMORY_FILE = Path(tempfile.mktemp(suffix=".jsonl"))
        try:
            result = bridge.post("/grill-with-docs", "src/auth.ts", "Decision: Use OAuth 2.1")
            assert result is not None
            assert bridge.MEMORY_FILE.exists()
            with open(bridge.MEMORY_FILE) as f:
                record = json.loads(f.readline())
                assert "OAuth 2.1" in record["content"]
                assert record["type"] == "decision"
        finally:
            bridge.MEMORY_FILE.unlink()
            bridge.MEMORY_FILE = old_path


class TestWrap:
    def test_wrap_calls_pre_and_post(self):
        with patch("bridge.pre", return_value="ctx") as mock_pre:
            with patch("bridge.post", return_value="mem-1") as mock_post:
                result = bridge.wrap("/tdd", "src/test.ts", "Added tests")
                assert result["context"] is True
                assert result["memory_id"] == "mem-1"
                mock_pre.assert_called_once()
                mock_post.assert_called_once()


class TestBenchmark:
    def test_benchmark_returns_metrics(self):
        result = bridge.benchmark()
        assert "skill_runs" in result
        assert "memories_stored" in result
        assert "repeated_instruction_reduction_pct" in result
        assert result["skill_runs"] == 4


class TestValidate:
    def test_validate_runs(self):
        bridge.validate()
