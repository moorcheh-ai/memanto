"""Tests for bridge.py — credential-free."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMANTO_BACKEND"] = "local"
sys.path.insert(0, str(Path(__file__).parent))
import bridge


class TestEngineeringProfile:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".json")
        bridge.PROFILE_FILE = Path(self.tmp)
        bridge._local_profile = {}

    def teardown_method(self):
        Path(self.tmp).unlink(missing_ok=True)

    def test_profile_creation(self):
        profile = bridge.EngineeringProfile(Path(self.tmp))
        assert profile._data["entries"] == []
        assert "created" in profile._data

    def test_add_entry(self):
        profile = bridge.EngineeringProfile(Path(self.tmp))
        eid = profile.add("decision", "Use OAuth 2.1", 0.85, "/grill-with-docs", "src/auth.ts")
        assert eid.startswith("insight-")
        assert len(profile._data["entries"]) == 1

    def test_deduplication(self):
        profile = bridge.EngineeringProfile(Path(self.tmp))
        eid1 = profile.add("decision", "Use Postgres as primary DB", 0.8, "/architect", "src/db.ts")
        eid2 = profile.add("decision", "Use Postgres as the primary database", 0.8, "/review", "src/db.ts")
        # Should update existing entry, not create new one
        assert eid2 == eid1
        assert profile._data["entries"][0]["version"] == 2

    def test_search(self):
        profile = bridge.EngineeringProfile(Path(self.tmp))
        profile.add("decision", "Use OAuth 2.1 with PKCE", 0.85, "/grill-with-docs", "src/auth.ts")
        profile.add("preference", "Prefer JWT over sessions", 0.7, "/handoff", "src/auth.ts")
        profile.add("pattern", "Use Repository pattern", 0.8, "/architect", "src/db.ts")

        results = profile.search("src/auth.ts")
        assert len(results) == 2
        assert "OAuth" in results[0]["content"] or "JWT" in results[0]["content"]

    def test_supersede(self):
        profile = bridge.EngineeringProfile(Path(self.tmp))
        eid = profile.add("decision", "Use old auth system", 0.6, "/grill", "src/auth.ts")
        new_id = profile.supersede(eid, "Use OAuth 2.1 instead", "/review")
        assert new_id.startswith("insight-")
        # Old entry should be superseded
        old = profile._find(eid)
        assert old["superseded_by"] is not None
        assert old["confidence"] == 0.0

    def test_contradiction_detection(self):
        profile = bridge.EngineeringProfile(Path(self.tmp))
        profile.add("preference", "Avoid class-based components", 0.8, "/capture", "src/ui.tsx")
        conflicts = profile.detect_contradictions("Use class-based components for all UI")
        assert len(conflicts) == 1

    def test_render(self):
        profile = bridge.EngineeringProfile(Path(self.tmp))
        profile.add("decision", "Use hexagonal architecture", 0.9, "/architect", "src/api.ts")
        rendered = profile.render()
        assert "hexagonal architecture" in rendered
        assert "Technical Decisions" in rendered


class TestExtraction:
    def test_heuristic_extracts_decisions(self):
        transcript = "Decision: Use OAuth 2.1 for auth.\nAlso, we should prefer JWT.\nRandom chat."
        insights = bridge._heuristic_extract("/grill-with-docs", "src/auth.ts", transcript)
        assert len(insights) >= 1
        assert any("OAuth" in i["content"] for i in insights)

    def test_heuristic_empty_transcript(self):
        insights = bridge._heuristic_extract("/tdd", "src/test.ts", "")
        assert insights == []

    def test_skill_to_category(self):
        assert bridge._SKILL_TO_CATEGORY["grill"] == "decision"
        assert bridge._SKILL_TO_CATEGORY["architect"] == "architecture"
        assert bridge._SKILL_TO_CATEGORY["tdd"] == "pattern"
        assert bridge._SKILL_TO_CATEGORY["capture"] == "preference"


class TestPre:
    def test_pre_empty_profile(self, capfd):
        old = bridge.PROFILE_FILE
        bridge.PROFILE_FILE = Path(tempfile.mktemp(suffix=".json"))
        try:
            result = bridge.pre("/grill-with-docs", "src/auth.ts")
            assert result == ""
        finally:
            bridge.PROFILE_FILE.unlink(missing_ok=True)
            bridge.PROFILE_FILE = old

    def test_pre_with_profile(self, capfd):
        old = bridge.PROFILE_FILE
        bridge.PROFILE_FILE = Path(tempfile.mktemp(suffix=".json"))
        try:
            profile = bridge.EngineeringProfile(bridge.PROFILE_FILE)
            profile.add("decision", "Use OAuth 2.1", 0.85, "/grill-with-docs", "src/auth.ts")
            result = bridge.pre("/tdd", "src/auth.ts")
            assert "OAuth" in result
        finally:
            bridge.PROFILE_FILE.unlink(missing_ok=True)
            bridge.PROFILE_FILE = old


class TestPost:
    def test_post_stores_insights(self):
        old = bridge.PROFILE_FILE
        bridge.PROFILE_FILE = Path(tempfile.mktemp(suffix=".json"))
        try:
            stored = bridge.post("/grill-with-docs", "src/auth.ts",
                               "Decision: Use OAuth 2.1 with PKCE. Must support MFA.")
            assert len(stored) >= 1
            profile = bridge.EngineeringProfile(bridge.PROFILE_FILE)
            assert len(profile._data["entries"]) >= 1
        finally:
            bridge.PROFILE_FILE.unlink(missing_ok=True)
            bridge.PROFILE_FILE = old


class TestWrap:
    def test_wrap_calls_pre_and_post(self, capfd):
        old = bridge.PROFILE_FILE
        bridge.PROFILE_FILE = Path(tempfile.mktemp(suffix=".json"))
        try:
            result = bridge.wrap("/tdd", "src/test.ts", "Added tests for edge cases.")
            assert isinstance(result["context_entries"], bool)
            assert result["insights_stored"] >= 1
        finally:
            bridge.PROFILE_FILE.unlink(missing_ok=True)
            bridge.PROFILE_FILE = old


class TestBenchmark:
    def test_benchmark_runs(self):
        old = bridge.PROFILE_FILE
        bridge.PROFILE_FILE = Path(tempfile.mktemp(suffix=".json"))
        try:
            old_mem = bridge.MEMORY_FILE
            bridge.MEMORY_FILE = Path(tempfile.mktemp(suffix=".jsonl"))
            try:
                result = bridge.benchmark()
                assert "repeated_instruction_reduction_pct" in result
                assert result["skill_runs"] == 3
            finally:
                bridge.MEMORY_FILE.unlink(missing_ok=True)
                bridge.MEMORY_FILE = old_mem
        finally:
            bridge.PROFILE_FILE.unlink(missing_ok=True)
            bridge.PROFILE_FILE = old


class TestValidate:
    def test_validate_runs(self, capfd):
        old = bridge.PROFILE_FILE
        bridge.PROFILE_FILE = Path(tempfile.mktemp(suffix=".json"))
        old_mem = bridge.MEMORY_FILE
        bridge.MEMORY_FILE = Path(tempfile.mktemp(suffix=".jsonl"))
        try:
            bridge.validate()
        finally:
            bridge.PROFILE_FILE.unlink(missing_ok=True)
            bridge.PROFILE_FILE = old
            bridge.MEMORY_FILE.unlink(missing_ok=True)
            bridge.MEMORY_FILE = old_mem


class TestLocalBackend:
    def test_store_and_search(self):
        old = bridge.MEMORY_FILE
        bridge.MEMORY_FILE = Path(tempfile.mktemp(suffix=".jsonl"))
        try:
            bridge._local_store({"content": "Use OAuth 2.1", "title": "Auth decision"})
            results = bridge._local_search("OAuth", 5)
            assert len(results) == 1
        finally:
            bridge.MEMORY_FILE.unlink(missing_ok=True)
            bridge.MEMORY_FILE = old
