"""Tests for skill-aware recall routing."""

from __future__ import annotations

from claudecode_memanto import skill_map


def test_known_skill_routes() -> None:
    route = skill_map.route_for("tdd")
    assert "testing" in route.query
    assert "testing" in route.tags


def test_skill_name_is_normalised() -> None:
    assert skill_map.route_for("/TDD").tags == skill_map.route_for("tdd").tags


def test_unknown_skill_falls_back_to_default() -> None:
    route = skill_map.route_for("some-custom-skill")
    assert route is skill_map._DEFAULT_ROUTE


def test_none_falls_back_to_default() -> None:
    assert skill_map.route_for(None) is skill_map._DEFAULT_ROUTE


def test_grill_with_docs_targets_architecture() -> None:
    route = skill_map.route_for("grill-with-docs")
    assert "architecture" in route.tags
    assert "architectural" in route.query


def test_known_skills_listed() -> None:
    skills = skill_map.known_skills()
    assert "tdd" in skills
    assert "diagnose" in skills
    assert "handoff" in skills


class TestNormalizeSkill:
    def test_strips_slash_lower_and_whitespace(self) -> None:
        assert skill_map.normalize_skill("/TDD ") == "tdd"
        assert skill_map.normalize_skill(" Grill-With-Docs") == "grill-with-docs"

    def test_empty_inputs_return_none(self) -> None:
        assert skill_map.normalize_skill(None) is None
        assert skill_map.normalize_skill("") is None
        assert skill_map.normalize_skill("   ") is None
        assert skill_map.normalize_skill("/") is None
