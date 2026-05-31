from skill_memory_hook import extract_memories, normalize_spaces


def test_normalize_spaces_collapses_whitespace():
    assert normalize_spaces("  one\n two\t three  ") == "one two three"


def test_extract_memories_classifies_typed_summary():
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
    memories = extract_memories("Ran the command. Decision: keep adapters thin. Done.")

    assert len(memories) == 1
    assert memories[0].memory_type == "decision"
    assert memories[0].content == "keep adapters thin"


def test_main_accepts_subcommand_dry_run(capsys):
    from skill_memory_hook import main

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
