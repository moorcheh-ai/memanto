"""Tests for the live capture handler."""

from __future__ import annotations

import logging

import pytest
from conftest import make_span

from langfuse_memanto import MemantoLangfuseHandler


def build(errors_only, memanto_client, **kwargs):
    return MemantoLangfuseHandler(
        agent_id="test-agent", client=memanto_client, **kwargs
    )


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------


def test_requires_an_agent(errors_only, memanto_client):
    with pytest.raises(ValueError, match="agent_id"):
        MemantoLangfuseHandler(client=memanto_client)


def test_agent_can_come_from_the_environment(errors_only, memanto_client, monkeypatch):
    monkeypatch.setenv("MEMANTO_LANGFUSE_AGENT_ID", "from-env")
    assert MemantoLangfuseHandler(client=memanto_client).agent_id == "from-env"


def test_capture_settings_come_from_the_shared_profile(errors_only, memanto_client):
    """The app must not need its own copy of the capture rules."""
    handler = build(errors_only, memanto_client)
    assert handler._config.modes == frozenset({"errors"})


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------


def test_errored_spans_are_captured_and_healthy_ones_ignored(
    errors_only, memanto_client
):
    handler = build(errors_only, memanto_client)

    for i in range(5):
        handler.on_end(make_span(span_id=i))
    for i in range(10):
        handler.on_end(make_span(span_id=100 + i, level="DEFAULT", status_code="OK"))

    assert handler.stats()["captured"] == 5
    assert handler.stats()["pending"] == 5


def test_a_retry_storm_collapses_to_one_memory(errors_only, memanto_client):
    """The core promise: 500 identical failures are one memory, not 500."""
    handler = build(errors_only, memanto_client)
    for i in range(500):
        handler.on_end(make_span(span_id=i, status_message=f"Boom on attempt {i}"))

    written = handler.flush()

    assert written == 1
    assert memanto_client.batch_remember.call_count == 1
    memories = memanto_client.batch_remember.call_args.kwargs["memories"]
    assert len(memories) == 1
    assert memories[0]["occurrences"] == 500
    assert memories[0]["confidence"] == 0.95  # capped


def test_distinct_faults_stay_distinct(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span(span_id=1, status_message="Model returned junk"))
    handler.on_end(make_span(span_id=2, status_message="Vector store timed out"))

    assert handler.flush() == 2


def test_flushing_twice_writes_nothing_the_second_time(errors_only, memanto_client):
    """The ledger is shared with the CLI, so repeats are not rewritten."""
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())
    assert handler.flush() == 1

    handler.on_end(make_span(span_id=999))  # same signature, new span
    handler.flush()

    assert memanto_client.batch_remember.call_count == 1


def test_the_buffer_is_bounded_during_a_storm(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    cap = handler.settings.max_buffer * 20

    for i in range(cap + 50):
        handler.on_end(make_span(span_id=i))

    stats = handler.stats()
    assert stats["pending"] == cap
    assert stats["dropped"] == 50


def test_an_empty_flush_is_a_no_op(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    assert handler.flush() == 0
    memanto_client.batch_remember.assert_not_called()


# --------------------------------------------------------------------------
# The application must never be harmed
# --------------------------------------------------------------------------


def test_a_junk_span_does_not_raise(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    handler.on_end(object())
    handler.on_end(None)
    assert handler.stats()["captured"] == 0


def test_a_failing_write_does_not_raise(errors_only, memanto_client):
    """Losing an observability memory must not take the app down."""
    memanto_client.batch_remember.side_effect = RuntimeError("moorcheh is down")
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())

    assert handler.flush() == 0  # reported, not raised


def test_a_broken_client_does_not_raise(errors_only):
    handler = MemantoLangfuseHandler(agent_id="a", client=None, api_key=None)
    handler.on_end(make_span())
    assert handler.flush() == 0


# --------------------------------------------------------------------------
# Live limits are stated, not hidden
# --------------------------------------------------------------------------


def test_score_modes_warn_that_they_cannot_work_live(
    capture_dir, memanto_client, caplog
):
    from memanto.cli.migrate.langfuse_config import (
        ProjectConfig,
        config_path,
        parse_score_rule,
        save_project,
    )

    save_project(
        config_path(capture_dir),
        "default",
        ProjectConfig(
            capture=frozenset({"errors", "low_score"}),
            score_fail_rules=[parse_score_rule("correctness<0.7")],
        ),
    )
    with caplog.at_level(logging.WARNING, logger="langfuse_memanto.handler"):
        MemantoLangfuseHandler(agent_id="a", client=memanto_client)

    assert any("low-score" in r.getMessage() for r in caplog.records)


def test_percentile_only_budgets_warn(capture_dir, memanto_client, caplog):
    from memanto.cli.migrate.langfuse_config import (
        ProjectConfig,
        config_path,
        save_project,
    )

    save_project(
        config_path(capture_dir),
        "default",
        ProjectConfig(capture=frozenset({"slow"}), latency_percentile=95),
    )
    with caplog.at_level(logging.WARNING, logger="langfuse_memanto.handler"):
        MemantoLangfuseHandler(agent_id="a", client=memanto_client)

    assert any("latency" in r.message.lower() for r in caplog.records)


# --------------------------------------------------------------------------
# Attaching
# --------------------------------------------------------------------------


def test_attach_registers_on_the_tracer_provider(errors_only, memanto_client):
    from unittest.mock import MagicMock

    provider = MagicMock()
    handler = build(errors_only, memanto_client).attach(provider)

    provider.add_span_processor.assert_called_once_with(handler)


def test_attach_explains_a_provider_that_cannot_take_processors(
    errors_only, memanto_client
):
    """OTel's ProxyTracerProvider has no add_span_processor before setup."""

    class Proxy:
        pass

    with pytest.raises(RuntimeError, match="Initialise Langfuse"):
        build(errors_only, memanto_client).attach(Proxy())


def test_shutdown_flushes_what_is_pending(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())
    handler.shutdown()

    assert memanto_client.batch_remember.call_count == 1
    assert handler.stats()["pending"] == 0


def test_force_flush_satisfies_the_otel_contract(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())
    assert handler.force_flush() is True
    assert handler.stats()["pending"] == 0


# --------------------------------------------------------------------------
# Zero-setup developer experience
# --------------------------------------------------------------------------


def test_capture_rules_can_be_set_entirely_in_code(capture_dir, memanto_client):
    """A fresh app must not need the CLI to configure capture."""
    handler = MemantoLangfuseHandler(
        agent_id="a",
        client=memanto_client,
        capture=["errors", "slow"],
        latency_ms=5000,
    )

    assert handler._config.modes == frozenset({"errors", "slow"})
    assert handler._config.latency_ms == 5000


def test_in_code_settings_win_over_the_stored_profile(errors_only, memanto_client):
    handler = MemantoLangfuseHandler(
        agent_id="a", client=memanto_client, capture=["costly"], cost_usd=0.5
    )

    assert handler._config.modes == frozenset({"costly"})
    assert handler._config.cost_usd == 0.5


def test_omitted_settings_fall_back_to_the_stored_profile(errors_only, memanto_client):
    """Teams managing rules centrally shouldn't repeat them per service."""
    handler = MemantoLangfuseHandler(agent_id="a", client=memanto_client)
    assert handler._config.modes == frozenset({"errors"})


def test_score_rules_can_be_given_in_code(capture_dir, memanto_client):
    handler = MemantoLangfuseHandler(
        agent_id="a",
        client=memanto_client,
        capture=["low_score"],
        score_fail=["correctness<0.7"],
    )
    assert [str(r) for r in handler._config.score_fail_rules] == ["correctness<0.7"]


def test_a_bad_in_code_rule_fails_loudly_at_startup(capture_dir, memanto_client):
    """Better to fail at attach() than to silently capture nothing."""
    from memanto.cli.migrate.langfuse_config import ScoreRuleError

    with pytest.raises(ScoreRuleError):
        MemantoLangfuseHandler(
            agent_id="a", client=memanto_client, score_fail=["correctness<<oops"]
        )

    with pytest.raises(ValueError, match="Unknown capture mode"):
        MemantoLangfuseHandler(agent_id="a", client=memanto_client, capture=["nope"])


def test_the_agent_is_created_and_activated_on_first_write(errors_only, memanto_client):
    """A dev with only an API key should never touch the CLI."""
    from memanto.app.utils.errors import AgentNotFoundError

    memanto_client.activate_agent.side_effect = [AgentNotFoundError("nope"), None]

    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())
    handler.flush()

    memanto_client.create_agent.assert_called_once_with(
        agent_id="test-agent", pattern="tool"
    )
    assert memanto_client.activate_agent.call_count == 2


def test_an_existing_agent_is_only_activated(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())
    handler.flush()

    memanto_client.activate_agent.assert_called_once()
    memanto_client.create_agent.assert_not_called()


def test_provisioning_happens_once_across_flushes(errors_only, memanto_client):
    handler = build(errors_only, memanto_client)
    for i in range(3):
        handler.on_end(make_span(span_id=i, status_message=f"fault {i}"))
        handler.flush()

    assert memanto_client.activate_agent.call_count == 1


def test_auto_create_can_be_turned_off(errors_only, memanto_client):
    from memanto.app.utils.errors import AgentNotFoundError

    memanto_client.activate_agent.side_effect = AgentNotFoundError("nope")
    handler = build(errors_only, memanto_client, auto_create_agent=False)
    handler.on_end(make_span())

    assert handler.flush() == 0  # reported, not raised
    memanto_client.create_agent.assert_not_called()


def test_project_scope_matches_the_cli_so_the_sync_does_not_duplicate(
    capture_dir, memanto_client, monkeypatch
):
    """Regression: the handler filed writes under 'default' while the CLI used
    a key-derived scope, so a later sync re-wrote every memory the app stored."""
    from memanto.cli.migrate.langfuse_config import project_key

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-abc123")
    handler = MemantoLangfuseHandler(agent_id="a", client=memanto_client)

    assert handler._project_key == project_key(api_key="pk-lf-abc123")
    assert handler._project_key != "default"


def test_project_scope_falls_back_when_no_langfuse_key_is_set(
    capture_dir, memanto_client
):
    assert MemantoLangfuseHandler(agent_id="a", client=memanto_client)._project_key == (
        "default"
    )


def test_an_explicit_project_key_still_wins(capture_dir, memanto_client, monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-abc123")
    handler = MemantoLangfuseHandler(
        agent_id="a", client=memanto_client, project_key="chosen"
    )
    assert handler._project_key == "chosen"


# --------------------------------------------------------------------------
# Reliability: a failed write must not lose the observations
# --------------------------------------------------------------------------


def test_a_failed_flush_retains_the_observations(errors_only, memanto_client):
    """Regression: the buffer was cleared before writing, so a network blip
    silently discarded everything it was holding."""
    memanto_client.batch_remember.side_effect = ConnectionError("network blip")
    handler = build(errors_only, memanto_client)
    for i in range(5):
        handler.on_end(make_span(span_id=i))

    handler.flush()

    assert handler.stats()["pending"] == 5, "observations must survive a failure"
    assert handler.stats()["dropped"] == 0


def test_the_retry_succeeds_once_the_backend_recovers(errors_only, memanto_client):
    memanto_client.batch_remember.side_effect = ConnectionError("blip")
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())
    handler.flush()

    memanto_client.batch_remember.side_effect = lambda agent_id, memories: {
        "successful": len(memories),
        "failed": 0,
        "results": [{"id": "m1", "status": "queued"}],
    }
    assert handler.flush() == 1
    assert handler.stats()["pending"] == 0


def test_retries_are_bounded_so_a_dead_backend_cannot_fill_memory(
    errors_only, memanto_client
):
    memanto_client.batch_remember.side_effect = ConnectionError("permanently down")
    handler = build(errors_only, memanto_client)
    for i in range(3):
        handler.on_end(make_span(span_id=i))

    for _ in range(6):
        handler.flush()

    assert handler.stats()["pending"] == 0
    assert handler.stats()["dropped"] == 3


def test_a_partial_failure_is_retried_not_dropped(errors_only, memanto_client):
    """Reconciliation makes a whole-batch retry safe: what was written comes
    back as unchanged."""
    memanto_client.batch_remember.side_effect = lambda agent_id, memories: {
        "successful": 0,
        "failed": len(memories),
        "results": [{"id": "x", "status": "failed", "error": "rejected"}],
    }
    handler = build(errors_only, memanto_client)
    handler.on_end(make_span())
    handler.flush()

    assert handler.stats()["pending"] == 1


def test_project_scope_honours_the_combined_langfuse_api_key(
    capture_dir, memanto_client, monkeypatch
):
    """Regression: the handler read only LANGFUSE_PUBLIC_KEY while the CLI
    prefers the combined LANGFUSE_API_KEY, so a user who set only the combined
    form got 'default' here and the key-derived scope there — reintroducing
    the duplicate-write bug the scope fix was meant to close."""
    from memanto.cli.migrate.langfuse_config import project_key

    monkeypatch.setenv("LANGFUSE_API_KEY", "pk-lf-abc123:sk-lf-secret")
    handler = MemantoLangfuseHandler(agent_id="a", client=memanto_client)

    assert handler._project_key == project_key(api_key="pk-lf-abc123")
    assert handler._project_key != "default"


def test_the_combined_key_wins_over_the_public_key(
    capture_dir, memanto_client, monkeypatch
):
    from memanto.cli.migrate.langfuse_config import project_key

    monkeypatch.setenv("LANGFUSE_API_KEY", "pk-lf-combined:sk-lf-x")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-other")
    handler = MemantoLangfuseHandler(agent_id="a", client=memanto_client)

    assert handler._project_key == project_key(api_key="pk-lf-combined")


def test_concurrent_flushes_do_not_lose_signatures(errors_only, memanto_client):
    """Regression: the worker thread and an app calling flush() could overlap,
    each saving its own view of the ledger scope — the slower one erasing the
    other's newly recorded signatures."""
    import threading

    handler = build(errors_only, memanto_client)
    # Distinct *operations*: varying only a number in the message would be
    # normalized away and collapse into a single signature.
    for i in range(40):
        handler.on_end(make_span(name=f"op-{i}", span_id=i))

    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        handler.flush()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    from memanto.cli.config.manager import ConfigManager
    from memanto.cli.migrate.langfuse_state import load_state, scope_key, state_path

    ledger = state_path(ConfigManager().get_migrate_dir("langfuse"))
    stored = load_state(ledger, scope_key(handler._project_key, "test-agent"))

    assert len(stored["signatures"]) == 40, "a concurrent flush lost signatures"
    assert handler.stats()["pending"] == 0
