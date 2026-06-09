from skill_memory_hook import (
    extract_memories,
    main,
    normalize_spaces,
    recall_local,
    run_memanto,
)


def test_normalize_spaces_collapses_whitespace():
    """Whitespace normalization should preserve words and collapse spacing."""

    assert normalize_spaces("  one\n two\t three  ") == "one two three"


def test_extract_memories_classifies_typed_summary():
    """Typed summary clauses should become semantic memory candidates."""

    memories = extract_memories(
        "Decision: use hexagonal architecture. "
        "Convention: tests live beside fixtures. "
        "Preference: short review comments. "
        "Gotcha: legacy imports use Decimal strings. "
        "Bugfix: cleared stale cache invalidation."
    )

    assert [memory.memory_type for memory in memories] == [
        "decision",
        "instruction",
        "preference",
        "learning",
        "error",
    ]
    assert memories[0].content == "use hexagonal architecture"
    assert memories[-1].title.startswith("Bugfix:")


def test_extract_memories_ignores_untyped_noise():
    """Untyped summary prose should not create noisy memories."""

    memories = extract_memories("Ran the command. Decision: keep adapters thin. Done.")

    assert len(memories) == 1
    assert memories[0].memory_type == "decision"
    assert memories[0].content == "keep adapters thin"


def test_extract_memories_handles_semicolons_and_whitespace():
    """Semicolon-separated typed clauses should be extracted independently."""

    memories = extract_memories(
        "Decision: keep adapters thin; Convention: tests stay near fixtures"
    )

    assert [memory.content for memory in memories] == [
        "keep adapters thin",
        "tests stay near fixtures",
    ]


def test_extract_memories_handles_multiline_bullets():
    """Bullet-prefixed multiline summaries should still classify memories."""

    memories = extract_memories(
        "- Decision: keep ports framework-agnostic\n"
        "* Preferences: write short review comments\n"
        "- Bug: stale cache invalidation was fixed"
    )

    assert [memory.memory_type for memory in memories] == [
        "decision",
        "preference",
        "error",
    ]
    assert memories[1].content == "write short review comments"


def test_dry_run_preserves_argument_boundaries():
    """Dry-run output should quote arguments so boundaries are reviewable."""

    output = run_memanto(["recall", "invoice validation rules"], dry_run=True)

    assert "'invoice validation rules'" in output


def test_main_accepts_subcommand_dry_run(capsys):
    """The post subcommand should print dry-run remember commands."""

    status = main([
        "post",
        "--skill",
        "/review",
        "--summary",
        "Decision: keep adapters thin.",
        "--dry-run",
    ])

    captured = capsys.readouterr()
    assert status == 0
    assert "DRY-RUN: memanto remember" in captured.out


def test_main_accepts_mid_session_event_dry_run(capsys):
    """The event subcommand should save one mid-session memory."""

    status = main([
        "event",
        "--skill",
        "/apply",
        "--type",
        "decision",
        "--note",
        "Switched from polling to webhook delivery during implementation.",
        "--dry-run",
    ])

    captured = capsys.readouterr()
    assert status == 0
    assert "DRY-RUN: memanto remember" in captured.out
    assert "Switched from polling to webhook delivery" in captured.out
    assert "--type decision" in captured.out


def test_local_backend_persists_context_across_skill_runs(tmp_path, capsys):
    """A credential-free local demo should persist and recall durable context."""

    store = tmp_path / "skill-memory.jsonl"
    save_status = main([
        "post",
        "--skill",
        "/spec",
        "--summary",
        "Decision: invoices reject negative totals. "
        "Convention: billing tests use domain fixtures.",
        "--backend",
        "local",
        "--store",
        str(store),
    ])
    capsys.readouterr()

    recall_status = main([
        "pre",
        "--task",
        "/tdd add invoice validation",
        "--files",
        "src/billing/invoice.py",
        "--backend",
        "local",
        "--store",
        str(store),
    ])

    captured = capsys.readouterr()
    assert save_status == 0
    assert recall_status == 0
    assert "invoices reject negative totals" in captured.out
    assert "billing tests use domain fixtures" in captured.out


def test_local_recall_ranks_relevant_memories_first(tmp_path):
    """Local recall should prioritize memories sharing terms with the task."""

    store = tmp_path / "skill-memory.jsonl"
    main([
        "post",
        "--skill",
        "/spec",
        "--summary",
        "Decision: invoice validation rejects negative totals. "
        "Decision: profile avatars use WebP.",
        "--backend",
        "local",
        "--store",
        str(store),
    ])

    recalled = recall_local(
        store,
        query="invoice validation",
        agent="developer-skills",
        limit=1,
    )

    assert len(recalled) == 1
    assert recalled[0]["content"] == "invoice validation rejects negative totals"


def test_local_recall_skips_malformed_jsonl_records(tmp_path):
    """A truncated record should not hide valid memories in the same store."""

    store = tmp_path / "skill-memory.jsonl"
    store.write_text(
        '{"agent":"developer-skills","type":"decision",'
        '"title":"Invoice validation","content":"reject negative totals",'
        '"tags":["developer-skills","/tdd"]}\n'
        '{"agent":"developer-skills"',
        encoding="utf-8",
    )

    recalled = recall_local(
        store,
        query="invoice validation",
        agent="developer-skills",
        limit=5,
    )

    assert [record["content"] for record in recalled] == ["reject negative totals"]

