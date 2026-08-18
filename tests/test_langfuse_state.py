"""Tests for the Langfuse sync ledger — the thing that makes re-syncing safe.

Memanto does not deduplicate on write, so without this ledger a second
``memanto migrate langfuse`` (or a second click on the UI tile) would write
every signature again.
"""

from __future__ import annotations

import json

from memanto.cli.migrate.langfuse_state import (
    Reconciliation,
    fingerprint,
    last_synced_at,
    load_state,
    reconcile,
    record_updated,
    record_written,
    save_state,
    scope_key,
    state_path,
)


def row(signature="sig-a", content="RateLimitError happened", occurrences=1, **extra):
    base = {
        "title": "RateLimitError in summarize_node",
        "content": content,
        "type": "error",
        "tags": ["langfuse", f"sig={signature}"],
        "confidence": 0.6,
        "signature": signature,
        "occurrences": occurrences,
    }
    base.update(extra)
    return base


def ok(memory_id):
    """A successful per-item result from batch_store_memories."""
    return {"id": memory_id, "status": "queued"}


SCOPE = scope_key("proj-1", "agent-a")


def empty_state(scope=SCOPE):
    return {"version": 1, "scope": scope, "last_synced_at": None, "signatures": {}}


# --------------------------------------------------------------------------
# Fingerprinting
# --------------------------------------------------------------------------


def test_fingerprint_ignores_irrelevant_fields_and_tag_order():
    a = row(occurrences=1, source_ref="https://x/1")
    b = row(occurrences=999, source_ref="https://x/2")
    b["tags"] = list(reversed(b["tags"]))

    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_changes_when_the_memory_would_read_differently():
    assert fingerprint(row()) != fingerprint(row(content="TimeoutError happened"))
    assert fingerprint(row()) != fingerprint(row(confidence=0.9))


# --------------------------------------------------------------------------
# Reconciliation — the idempotency contract
# --------------------------------------------------------------------------


def test_first_sync_treats_every_signature_as_new():
    plan = reconcile([row("sig-a"), row("sig-b")], empty_state())

    assert len(plan.new_rows) == 2
    assert plan.updates == []
    assert plan.unchanged == 0


def test_second_sync_of_identical_data_writes_nothing():
    """The critical test: syncing twice must not duplicate memories."""
    rows = [row("sig-a"), row("sig-b")]
    state = empty_state()

    first = reconcile(rows, state)
    record_written(state, first.new_rows, [ok("mem-a"), ok("mem-b")])

    second = reconcile(rows, state)

    assert second.new_rows == []
    assert second.updates == []
    assert second.unchanged == 2


def test_recurring_signature_is_updated_in_place_not_rewritten():
    state = empty_state()
    first = reconcile([row("sig-a", occurrences=1)], state)
    record_written(state, first.new_rows, [ok("mem-a")])

    louder = row("sig-a", content="RateLimitError happened 400x", occurrences=400)
    second = reconcile([louder], state)

    assert second.new_rows == []
    assert second.unchanged == 0
    assert len(second.updates) == 1

    update = second.updates[0]
    assert update["memory_id"] == "mem-a"
    assert update["occurrences"] == 400
    assert set(update["updates"]) <= {"title", "content", "confidence", "tags", "type"}


def test_updating_the_ledger_settles_the_signature():
    state = empty_state()
    first = reconcile([row("sig-a")], state)
    record_written(state, first.new_rows, [ok("mem-a")])

    louder = row("sig-a", content="now louder", occurrences=9)
    plan = reconcile([louder], state)
    record_updated(state, plan.updates[0])

    assert reconcile([louder], state).unchanged == 1
    assert state["signatures"]["sig-a"]["occurrences"] == 9


def test_failed_writes_are_not_recorded_so_the_next_sync_retries():
    state = empty_state()
    rows = [row("sig-a"), row("sig-b")]
    plan = reconcile(rows, state)

    record_written(
        state,
        plan.new_rows,
        [ok("mem-a"), {"id": "mem-b", "status": "failed", "error": "boom"}],
    )

    retry = reconcile(rows, state)
    assert [r["signature"] for r in retry.new_rows] == ["sig-b"]
    assert retry.unchanged == 1


def test_rows_without_a_signature_are_always_written():
    plan = reconcile([row(signature=None)], empty_state())
    assert len(plan.new_rows) == 1


def test_every_row_lands_in_exactly_one_bucket():
    state = empty_state()
    rows = [row("sig-a"), row("sig-b"), row("sig-c")]
    first = reconcile(rows, state)
    record_written(state, first.new_rows, [ok("m-a"), ok("m-b"), ok("m-c")])

    rows[0] = row("sig-a", content="changed", occurrences=5)
    plan: Reconciliation = reconcile(rows, state)

    assert (len(plan.new_rows), len(plan.updates), plan.unchanged) == (0, 1, 2)
    assert len(plan.new_rows) + len(plan.updates) + plan.unchanged == len(rows)


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def test_state_round_trips_through_disk(tmp_path):
    path = state_path(tmp_path)
    state = empty_state()
    plan = reconcile([row("sig-a")], state)
    record_written(state, plan.new_rows, [ok("mem-a")])
    save_state(path, state)

    reloaded = load_state(path, SCOPE)

    assert reloaded["signatures"]["sig-a"]["memory_id"] == "mem-a"
    assert last_synced_at(reloaded) is not None
    assert reconcile([row("sig-a")], reloaded).unchanged == 1


def test_missing_ledger_starts_empty(tmp_path):
    state = load_state(state_path(tmp_path / "never-synced"), SCOPE)

    assert state["signatures"] == {}
    assert state["last_synced_at"] is None


def test_corrupt_ledger_does_not_block_a_sync(tmp_path):
    """Starting over re-writes memories, which is visible; refusing to sync isn't."""
    path = state_path(tmp_path)
    path.write_text("{ this is not json", encoding="utf-8")

    state = load_state(path, SCOPE)

    assert state["signatures"] == {}


def test_save_state_stamps_the_cursor(tmp_path):
    path = state_path(tmp_path)
    save_state(path, empty_state())

    written = json.loads(path.read_text(encoding="utf-8"))
    scope = written["scopes"][SCOPE]
    assert scope["last_synced_at"] is not None
    assert last_synced_at(scope).tzinfo is not None


# --------------------------------------------------------------------------
# Scoping — one ledger per (Langfuse project, destination agent)
# --------------------------------------------------------------------------


def test_two_agents_do_not_shadow_each_other(tmp_path):
    """A signature written to agent A must still be written to agent B.

    With a single flat ledger, the second agent's sync would see the
    signature as 'already synced' and skip a write it never received.
    """
    path = state_path(tmp_path)
    rows = [row("sig-a")]

    a = load_state(path, scope_key("proj-1", "agent-a"))
    plan_a = reconcile(rows, a)
    record_written(a, plan_a.new_rows, [ok("mem-a")])
    save_state(path, a, scope_key("proj-1", "agent-a"))

    b = load_state(path, scope_key("proj-1", "agent-b"))
    plan_b = reconcile(rows, b)

    assert len(plan_a.new_rows) == 1
    assert len(plan_b.new_rows) == 1, "agent B never received this memory"


def test_two_projects_do_not_shadow_each_other(tmp_path):
    path = state_path(tmp_path)
    rows = [row("sig-a")]

    one = load_state(path, scope_key("proj-1", "agent-a"))
    record_written(one, reconcile(rows, one).new_rows, [ok("mem-1")])
    save_state(path, one, scope_key("proj-1", "agent-a"))

    two = load_state(path, scope_key("proj-2", "agent-a"))

    assert len(reconcile(rows, two).new_rows) == 1


def test_saving_one_scope_leaves_the_others_intact(tmp_path):
    path = state_path(tmp_path)
    first = scope_key("proj-1", "agent-a")
    second = scope_key("proj-2", "agent-b")

    a = load_state(path, first)
    record_written(a, reconcile([row("sig-a")], a).new_rows, [ok("mem-a")])
    save_state(path, a, first)

    b = load_state(path, second)
    record_written(b, reconcile([row("sig-b")], b).new_rows, [ok("mem-b")])
    save_state(path, b, second)

    assert load_state(path, first)["signatures"]["sig-a"]["memory_id"] == "mem-a"
    assert load_state(path, second)["signatures"]["sig-b"]["memory_id"] == "mem-b"


def test_an_unknown_scope_starts_empty(tmp_path):
    """A scope nobody has synced yet must not inherit another scope's state."""
    path = state_path(tmp_path)
    known = empty_state()
    record_written(known, reconcile([row("sig-a")], known).new_rows, [ok("mem-a")])
    save_state(path, known)

    fresh = load_state(path, scope_key("proj-9", "agent-z"))

    assert fresh["signatures"] == {}
    assert fresh["last_synced_at"] is None


def test_last_synced_at_tolerates_junk():
    assert last_synced_at({"last_synced_at": None}) is None
    assert last_synced_at({"last_synced_at": "not-a-date"}) is None
    assert last_synced_at({"last_synced_at": "2026-08-01T12:00:00Z"}) is not None


# --------------------------------------------------------------------------
# Concurrent writers — a multi-worker app flushes from several processes
# --------------------------------------------------------------------------


def test_concurrent_writers_do_not_lose_each_others_scopes(tmp_path):
    """Regression: save_state read the whole file then rewrote it, so two
    writers racing would drop one another's scope."""
    import threading

    path = state_path(tmp_path)
    scopes = [scope_key(f"proj-{i}", f"agent-{i}") for i in range(12)]
    barrier = threading.Barrier(len(scopes))

    def write(scope):
        state = load_state(path, scope)
        plan = reconcile([row(f"sig-{scope}")], state)
        record_written(state, plan.new_rows, [ok(f"mem-{scope}")])
        barrier.wait()  # maximise overlap
        save_state(path, state, scope)

    threads = [threading.Thread(target=write, args=(s,)) for s in scopes]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    written = json.loads(path.read_text(encoding="utf-8"))["scopes"]
    assert set(written) == set(scopes), "a concurrent writer lost a scope"


def test_the_ledger_is_never_left_truncated(tmp_path):
    """Write-then-rename: readers only ever see a complete file."""
    path = state_path(tmp_path)
    state = empty_state()
    record_written(state, reconcile([row("sig-a")], state).new_rows, [ok("mem-a")])
    save_state(path, state)

    assert json.loads(path.read_text(encoding="utf-8"))["scopes"]
    assert not list(tmp_path.glob("*.tmp*")), "temp file left behind"
    assert not list(tmp_path.glob("*.lock")), "lock file left behind"


def test_a_stale_lock_does_not_deadlock(tmp_path):
    """A crashed holder leaves a lock file; it must be broken, not waited on."""
    import os
    import time

    from memanto.cli.migrate.langfuse_state import _LOCK_STALE_SECONDS

    path = state_path(tmp_path)
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()
    old = time.time() - _LOCK_STALE_SECONDS - 5
    os.utime(lock, (old, old))

    started = time.monotonic()
    save_state(path, empty_state())

    assert time.monotonic() - started < 5
    assert json.loads(path.read_text(encoding="utf-8"))["scopes"]


# --------------------------------------------------------------------------
# Review findings: same-scope merge and the failure cursor
# --------------------------------------------------------------------------


def test_two_writers_on_one_scope_do_not_erase_each_other(tmp_path):
    """The lock alone only protects *other* scopes.

    Regression: save_state replaced the scope wholesale with the caller's
    in-memory view, so a writer that loaded before another's write landed
    would erase it — producing the duplicate this ledger exists to prevent.
    """
    path = state_path(tmp_path)

    # Both load the same (empty) scope before either saves.
    a = load_state(path, SCOPE)
    b = load_state(path, SCOPE)

    record_written(a, reconcile([row("sig-a")], a).new_rows, [ok("mem-a")])
    save_state(path, a, SCOPE)

    record_written(b, reconcile([row("sig-b")], b).new_rows, [ok("mem-b")])
    save_state(path, b, SCOPE)

    merged = load_state(path, SCOPE)["signatures"]
    assert set(merged) == {"sig-a", "sig-b"}, "a writer erased the other's signature"


def test_the_later_writer_wins_where_keys_collide(tmp_path):
    """Two writers that each recorded the same signature independently.

    Merging must not resurrect the earlier entry over the later one.
    """
    path = state_path(tmp_path)

    a = load_state(path, SCOPE)
    b = load_state(path, SCOPE)  # both start empty, so both see it as new

    record_written(a, reconcile([row("sig-a")], a).new_rows, [ok("first")])
    record_written(b, reconcile([row("sig-a")], b).new_rows, [ok("second")])

    save_state(path, a, SCOPE)
    save_state(path, b, SCOPE)

    assert load_state(path, SCOPE)["signatures"]["sig-a"]["memory_id"] == "second"


def test_the_cursor_does_not_advance_past_a_failure(tmp_path):
    """Regression: the cursor was stamped unconditionally, so the next run's
    window started after observations that were never stored — and Langfuse
    would not return them again."""
    path = state_path(tmp_path)

    state = load_state(path, SCOPE)
    record_written(state, reconcile([row("sig-a")], state).new_rows, [ok("mem-a")])
    save_state(path, state, SCOPE)
    good_cursor = last_synced_at(load_state(path, SCOPE))
    assert good_cursor is not None

    # A later run where a write failed must leave the cursor where it was.
    failed = load_state(path, SCOPE)
    save_state(path, failed, SCOPE, advance_cursor=False)

    assert last_synced_at(load_state(path, SCOPE)) == good_cursor


def test_a_first_run_that_fails_leaves_no_cursor(tmp_path):
    path = state_path(tmp_path)
    save_state(path, load_state(path, SCOPE), SCOPE, advance_cursor=False)

    assert last_synced_at(load_state(path, SCOPE)) is None
