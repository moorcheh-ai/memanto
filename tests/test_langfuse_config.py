"""Tests for per-project Langfuse capture settings and score rules.

Langfuse guarantees nothing about score semantics: names, data types, and
numeric ranges are user-defined, and the docs state no convention for whether
a higher score is better. These tests pin the consequence — that direction and
threshold are always the user's explicit choice, never inferred.
"""

from __future__ import annotations

import json

import pytest

from memanto.cli.migrate.langfuse_config import (
    ProjectConfig,
    ScoreRuleError,
    config_path,
    load_project,
    parse_score_rule,
    project_key,
    save_project,
    unconfigured_modes,
)


def score(name="correctness", value=0.5, **extra):
    return {"name": name, "value": value, **extra}


# --------------------------------------------------------------------------
# Rule parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,name,op,value",
    [
        ("correctness<0.7", "correctness", "<", 0.7),
        ("correctness <= 0.7", "correctness", "<=", 0.7),
        ("toxicity>0.3", "toxicity", ">", 0.3),
        ("rating>=4", "rating", ">=", 4.0),
        ("thumbs_up=false", "thumbs_up", "==", False),
        ("thumbs_up==true", "thumbs_up", "==", True),
        ("verdict!=pass", "verdict", "!=", "pass"),
    ],
)
def test_parse_rule_forms(raw, name, op, value):
    rule = parse_score_rule(raw)
    assert (rule.name, rule.op, rule.value) == (name, op, value)


def test_parse_membership_rule():
    rule = parse_score_rule("tone in rude, evasive")
    assert rule.name == "tone"
    assert rule.op == "in"
    assert rule.value == ["rude", "evasive"]


@pytest.mark.parametrize("bad", ["", "correctness", "<0.7", "correctness<abc"])
def test_bad_rules_are_rejected_with_guidance(bad):
    with pytest.raises(ScoreRuleError) as exc:
        parse_score_rule(bad)
    assert "score" in str(exc.value).lower() or "parse" in str(exc.value).lower()


def test_rules_round_trip_through_their_string_form():
    for raw in ("correctness<0.7", "thumbs_up==false", "tone in rude,evasive"):
        rule = parse_score_rule(raw)
        assert parse_score_rule(str(rule)) == rule


# --------------------------------------------------------------------------
# Rule matching across Langfuse's four score types
# --------------------------------------------------------------------------


def test_numeric_rule_matches_on_the_named_score_only():
    rule = parse_score_rule("correctness<0.7")

    assert rule.matches(score(value=0.2))
    assert not rule.matches(score(value=0.9))
    assert not rule.matches(score(name="helpfulness", value=0.2))


def test_arbitrary_numeric_ranges_work():
    """A 1-5 rating scale is as valid as 0-1 — a fixed 0.5 threshold is not."""
    rule = parse_score_rule("rating<3")

    assert rule.matches(score(name="rating", value=2))
    assert not rule.matches(score(name="rating", value=4))


def test_inverted_metrics_are_expressed_by_the_rule_direction():
    rule = parse_score_rule("hallucination_rate>0.2")

    assert rule.matches(score(name="hallucination_rate", value=0.5))
    assert not rule.matches(score(name="hallucination_rate", value=0.05))


def test_boolean_scores():
    rule = parse_score_rule("thumbs_up=false")

    assert rule.matches(score(name="thumbs_up", value=0))
    assert not rule.matches(score(name="thumbs_up", value=1))


def test_categorical_scores():
    rule = parse_score_rule("verdict in refusal,hallucination")

    assert rule.matches(score(name="verdict", value="refusal"))
    assert rule.matches(score(name="verdict", value="HALLUCINATION"))
    assert not rule.matches(score(name="verdict", value="ok"))


def test_a_numeric_rule_against_a_text_score_does_not_explode():
    """A user mistake must not abort a sync mid-run."""
    rule = parse_score_rule("correctness<0.7")
    assert rule.matches(score(value="not a number")) is False


def test_missing_value_never_matches():
    assert parse_score_rule("correctness<0.7").matches(score(value=None)) is False


# --------------------------------------------------------------------------
# Unconfigured modes
# --------------------------------------------------------------------------


def test_every_mode_but_errors_needs_configuration():
    missing = unconfigured_modes(
        modes={"errors", "low_score", "success", "slow", "costly"},
        score_fail_rules=[],
        score_pass_rules=[],
        latency_ms=None,
        latency_percentile=None,
        cost_usd=None,
        cost_percentile=None,
    )

    assert set(missing) == {"low_score", "success", "slow", "costly"}
    assert "errors" not in missing
    # Each message must say what to do, not just that something is missing.
    assert all(("--" in reason) for reason in missing.values())


def test_a_configured_mode_is_not_reported():
    missing = unconfigured_modes(
        modes={"slow", "costly"},
        score_fail_rules=[],
        score_pass_rules=[],
        latency_ms=None,
        latency_percentile=95,
        cost_usd=2.0,
        cost_percentile=None,
    )
    assert missing == {}


# --------------------------------------------------------------------------
# Persistence, scoped per project
# --------------------------------------------------------------------------


def test_config_round_trips(tmp_path):
    path = config_path(tmp_path)
    config = ProjectConfig(
        capture=frozenset({"errors", "low_score"}),
        score_fail_rules=[parse_score_rule("correctness<0.7")],
        latency_percentile=95,
        group_by="metadata.error_code",
    )
    save_project(path, "proj-1", config)

    loaded = load_project(path, "proj-1")

    assert loaded.capture == frozenset({"errors", "low_score"})
    assert [str(r) for r in loaded.score_fail_rules] == ["correctness<0.7"]
    assert loaded.latency_percentile == 95
    assert loaded.group_by == "metadata.error_code"


def test_projects_are_stored_independently(tmp_path):
    path = config_path(tmp_path)
    save_project(path, "proj-1", ProjectConfig(capture=frozenset({"errors"})))
    save_project(path, "proj-2", ProjectConfig(capture=frozenset({"slow"})))

    assert load_project(path, "proj-1").capture == frozenset({"errors"})
    assert load_project(path, "proj-2").capture == frozenset({"slow"})


def test_unknown_project_falls_back_to_default_then_to_errors(tmp_path):
    path = config_path(tmp_path)
    assert load_project(path, "never-seen").capture == frozenset({"errors"})

    save_project(path, "default", ProjectConfig(capture=frozenset({"slow"})))
    assert load_project(path, "never-seen").capture == frozenset({"slow"})


def test_a_corrupt_config_does_not_block_a_sync(tmp_path):
    path = config_path(tmp_path)
    path.write_text("{ not json", encoding="utf-8")

    assert load_project(path, "proj-1").capture == frozenset({"errors"})


def test_a_hand_edited_bad_rule_is_skipped_not_fatal(tmp_path):
    path = config_path(tmp_path)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "projects": {
                    "proj-1": {
                        "capture": ["low_score"],
                        "score_fail_rules": ["correctness<0.7", "!!broken!!"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_project(path, "proj-1")
    assert [str(r) for r in loaded.score_fail_rules] == ["correctness<0.7"]


# --------------------------------------------------------------------------
# Project identity
# --------------------------------------------------------------------------


def test_project_key_prefers_the_observed_project_id():
    assert project_key(project_id="clx123", api_key="pk-lf-a:sk-lf-b") == "clx123"


def test_project_key_hashes_the_public_key_so_no_credential_is_stored():
    key = project_key(api_key="pk-lf-abcdef:sk-lf-secret")

    assert key.startswith("pk-")
    assert "abcdef" not in key
    assert "secret" not in key


def test_project_key_is_stable_and_distinguishes_projects():
    a = project_key(api_key="pk-lf-aaa:sk-1")
    b = project_key(api_key="pk-lf-bbb:sk-1")

    assert a == project_key(api_key="pk-lf-aaa:sk-2")  # secret doesn't matter
    assert a != b
    assert project_key() == "default"


def test_unknown_capture_modes_are_dropped_on_load(tmp_path):
    """Regression: a typo in a hand-edited config.json loaded cleanly and then
    raised from CaptureConfig.__post_init__ mid-command, aborting with a
    traceback. The rest of this module tolerates a damaged file; so does this."""
    path = config_path(tmp_path)
    path.write_text(
        json.dumps(
            {"version": 1, "projects": {"p": {"capture": ["errors", "error", "nope"]}}}
        ),
        encoding="utf-8",
    )

    loaded = load_project(path, "p")

    assert loaded.capture == frozenset({"errors"})
    # And it must survive the conversion that used to blow up.
    from memanto.cli.migrate.langfuse_rules import CaptureConfig

    assert CaptureConfig.from_project(loaded).modes == frozenset({"errors"})


def test_an_all_invalid_capture_list_falls_back_to_errors(tmp_path):
    path = config_path(tmp_path)
    path.write_text(
        json.dumps({"version": 1, "projects": {"p": {"capture": ["bogus"]}}}),
        encoding="utf-8",
    )
    assert load_project(path, "p").capture == frozenset({"errors"})
