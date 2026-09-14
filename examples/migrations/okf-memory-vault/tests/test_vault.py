"""Tests for the OKF Memory Vault showcase.

Run with:  pytest -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

import okf_diff
import okf_view
import scenario
from okf_bundle import Memory, all_memories, load_bundle, slugify, write_bundle

HERE = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# okf_bundle
# ---------------------------------------------------------------------------


def test_slugify():
    assert slugify("Maya's timezone is UTC-7 (Pacific)") == "maya-s-timezone-is-utc-7-pacific"
    assert slugify("  Hello   World  ") == "hello-world"
    assert slugify("API / v1") == "api-v1"


def test_roundtrip_markdown(tmp_path):
    mem = Memory(
        type="fact",
        title="Free tier limit is 500 events",
        body="Free accounts ingest up to 500 events/month.",
        description="pricing fact",
        tags=["pricing"],
        timestamp="2026-08-04T13:20:00Z",
        x_memanto={"confidence": 0.96, "status": "active"},
    )
    md = mem.to_markdown()
    parsed = Memory.from_markdown(md)
    assert parsed.type == "fact"
    assert parsed.title == mem.title
    assert parsed.body == mem.body
    assert parsed.tags == ["pricing"]
    assert parsed.x_memanto["confidence"] == 0.96


def test_write_and_load_bundle(tmp_path):
    write_bundle(tmp_path / "bundle", [scenario.S1_BASELINE[0]])
    by_type = load_bundle(tmp_path / "bundle")
    assert by_type["instruction"]
    assert by_type["instruction"][0].title.startswith("Every PR")


# ---------------------------------------------------------------------------
# Scenario integrity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "memories",
    [scenario.S1_BASELINE, scenario.S2_EVOLVE, scenario.S3_CONFLICT, scenario.S4_RESOLVED],
)
def test_scenario_slug_uniqueness(memories):
    slugs = [slugify(m.title) for m in memories]
    assert len(slugs) == len(set(slugs)), f"duplicate slugs: {slugs}"


def test_scenario_growth():
    assert len(scenario.S2_EVOLVE) > len(scenario.S1_BASELINE)
    assert len(scenario.S3_CONFLICT) > len(scenario.S2_EVOLVE)


def test_conflict_memories_present_in_v3():
    titles = {m.title for m in scenario.S3_CONFLICT}
    assert any("1.8 hours" in t for t in titles)
    assert any("4.2 hours" in t for t in titles)
    assert "Maya's birthday is August 15" in titles


def test_conflict_resolved_in_v4():
    titles = {m.title for m in scenario.S4_RESOLVED}
    assert "Maya's birthday is August 15" not in titles
    assert "September 2" in " ".join(titles)


# ---------------------------------------------------------------------------
# okf_diff
# ---------------------------------------------------------------------------


def test_diff_between_v1_and_v2(tmp_path):
    d1 = tmp_path / "v1"
    d2 = tmp_path / "v2"
    write_bundle(d1, scenario.S1_BASELINE)
    write_bundle(d2, scenario.S2_EVOLVE)
    diff = okf_diff.diff_bundles(d1, d2)
    assert diff["counts"]["added"] >= 3
    assert diff["counts"]["modified"] >= 1  # the docs preference correction
    assert diff["counts"]["removed"] == 0


def test_diff_detects_conflicts_in_v3(tmp_path):
    d2 = tmp_path / "v2"
    d3 = tmp_path / "v3"
    write_bundle(d2, scenario.S2_EVOLVE)
    write_bundle(d3, scenario.S3_CONFLICT)
    diff = okf_diff.diff_bundles(d2, d3)
    assert diff["counts"]["added"] >= 5
    assert len(diff["conflicts"]) >= 2  # response time + birthday


def test_diff_resolution_in_v4(tmp_path):
    d3 = tmp_path / "v3"
    d4 = tmp_path / "v4"
    write_bundle(d3, scenario.S3_CONFLICT)
    write_bundle(d4, scenario.S4_RESOLVED)
    diff = okf_diff.diff_bundles(d3, d4)
    assert diff["counts"]["removed"] >= 1  # wrong birthday entry
    assert diff["counts"]["modified"] >= 2  # resolution + confirmed birthday


def test_render_markdown_includes_sections():
    md = okf_diff.render_markdown(
        {
            "old_bundle": "a", "new_bundle": "b",
            "counts": {"added": 1, "modified": 0, "removed": 0, "unchanged": 0},
            "added": [{"type": "fact", "title": "x", "provenance": "agent_session"}],
            "removed": [], "modified": [], "conflicts": [],
        }
    )
    assert "## Added" in md
    assert "## Potential conflicts" in md


# ---------------------------------------------------------------------------
# okf_view
# ---------------------------------------------------------------------------


def test_view_tree_counts(tmp_path):
    write_bundle(tmp_path / "b", scenario.S1_BASELINE)
    tree = okf_view.render_tree(tmp_path / "b")
    assert "fact/" in tree
    assert "instruction/" in tree


def test_view_search(tmp_path):
    write_bundle(tmp_path / "b", scenario.S1_BASELINE)
    tree = okf_view.render_tree(tmp_path / "b", search="birthday")
    assert "September" in tree or "maya-s-birthday" in tree
    assert "onboarding" not in tree


# ---------------------------------------------------------------------------
# End-to-end sample outputs exist
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not (HERE / "sample").exists(), reason="sample not built")
def test_sample_git_log_exists():
    assert (HERE / "sample" / "git-log.txt").exists()
    assert (HERE / "sample" / "vault" / ".git").exists()
