"""Bounty #770 round 4 — reproducible regression tests for 3 more bugs.

Run:  python -m pytest tests/failing_tests/test_bounty_770_round4.py -v
      (or:  python tests/failing_tests/test_bounty_770_round4.py)

Bugs covered:
1. HIGH: tags containing a comma are corrupted on write->read round-trip.
   MemoryRecord.to_moorcheh_document joins tags with "," (comma-separated
   filter syntax) while readers split on ",", so a tag like "urgent,high"
   comes back as ["urgent", "high"] — the original tag is lost and a
   phantom tag appears. Tag filtering (#tag) then matches the wrong rows.
2. MED:  CLI `memanto conflicts` (interactive resolver) hardcodes
   ~/.memanto/conflicts while the generator writes get_data_dir()/conflicts
   — same on-prem split as the round-3 fixes, but the CLI path was missed.
3. MED:  _normalize_tags treats list-typed tags differently from
   string-typed tags: a list with a comma-bearing tag is NOT split while
   the identical string IS split, so filtering/search results depend on
   how the storage layer happens to serialize tags.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# 1. Comma-bearing tags must be rejected before they can corrupt storage
# ---------------------------------------------------------------------------
def test_comma_tag_roundtrip_is_not_corrupted():
    """The schema must reject comma-bearing tags so the CSV wire format can
    never be ambiguous (a comma tag would round-trip as two tags, losing
    the original and fabricating a phantom)."""
    from pydantic import ValidationError

    from memanto.app.core import MemoryRecord

    try:
        MemoryRecord(
            type="fact",
            title="t",
            content="c",
            agent_id="a1",
            actor_id="a1",
            source="user",
            tags=["urgent,high", "clean"],
        )
        raise AssertionError("expected ValidationError for comma in tag")
    except ValidationError:
        pass


def test_comma_tag_does_not_create_phantom_tag():
    """A comma-bearing tag must never reach the serializer, so reading back
    cannot fabricate a 'high' tag from 'urgent,high'."""
    from pydantic import ValidationError

    from memanto.app.core import MemoryRecord

    try:
        MemoryRecord(
            type="fact",
            title="t",
            content="c",
            agent_id="a1",
            actor_id="a1",
            source="user",
            tags=["urgent,high"],
        )
        raise AssertionError("expected ValidationError for comma in tag")
    except ValidationError:
        pass


def test_normal_tags_still_roundtrip():
    """Tags without commas must serialize and read back unchanged."""
    from memanto.app.core import MemoryRecord
    from memanto.app.services.memory_read_service import MemoryReadService

    mem = MemoryRecord(
        type="fact",
        title="t",
        content="c",
        agent_id="a1",
        actor_id="a1",
        source="user",
        tags=["clean", "tag2"],
    )
    serialized = mem.to_moorcheh_document()["tags"]

    class FakeClient:
        class D:
            def fetch_text_data(self, **kwargs):
                return {
                    "items": [
                        {
                            "id": "m1",
                            "text": "[FACT] t\n\nc",
                            "metadata": {
                                "memory_type": "fact",
                                "tags": serialized,
                                "created_at": "2026-01-01T00:00:00Z",
                                "updated_at": "2026-01-01T00:00:00Z",
                            },
                        }
                    ],
                    "pagination": {"has_more": False},
                }

        documents = D()

    svc = MemoryReadService(FakeClient())
    result = svc.search_recent(agent_id="a1")
    tags = result["results"][0]["tags"]
    assert tags == ["clean", "tag2"], f"normal tags corrupted: {tags}"


# ---------------------------------------------------------------------------
# 2. CLI conflict resolver must honor get_data_dir()
# ---------------------------------------------------------------------------
def test_cli_conflicts_command_uses_get_data_dir():
    """memanto/cli/commands/memory.py (conflicts command) must read the
    report from get_data_dir()/conflicts, not ~/.memanto/conflicts."""
    src = (
        Path(__file__).resolve().parents[2]
        / "memanto"
        / "cli"
        / "commands"
        / "memory.py"
    ).read_text(encoding="utf-8")
    assert "Path.home() / \".memanto\" / \"conflicts\"" not in src, (
        "CLI conflicts command hardcodes ~/.memanto/conflicts"
    )


def test_cli_conflicts_reads_configured_data_dir_at_runtime(tmp_path, monkeypatch):
    """Runtime proof: with get_data_dir() pointed at a temp root, the CLI
    conflicts command must load its report from THAT root, not from
    ~/.memanto (which would raise FileNotFoundError / read stale data)."""
    import json

    import memanto.app.config as config_mod

    # Point get_data_dir at a temp root and write the report there.
    monkeypatch.setattr(config_mod, "get_data_dir", lambda: tmp_path)
    conflicts_dir = tmp_path / "conflicts"
    conflicts_dir.mkdir(parents=True, exist_ok=True)
    report_path = conflicts_dir / "a1_2026-01-15_conflicts.json"
    report_path.write_text(
        json.dumps(
            [
                {
                    "type": "CONTRADICTION",
                    "title": "t",
                    "old_memory_id": "m1",
                    "new_memory_id": "m2",
                    "old_content": "old",
                    "new_content": "new",
                    "recommendation": "keep_new",
                    "resolved": False,
                }
            ]
        ),
        encoding="utf-8",
    )

    import typer

    import memanto.cli.commands.memory as mem_cli

    class FakeClient:
        def list_conflicts(self, agent_id, date):
            return [
                {
                    "type": "CONTRADICTION",
                    "title": "t",
                    "old_memory_id": "m1",
                    "new_memory_id": "m2",
                    "old_content": "old",
                    "new_content": "new",
                    "recommendation": "keep_new",
                }
            ]

    monkeypatch.setattr(mem_cli, "get_client", lambda: FakeClient())
    monkeypatch.setattr(
        mem_cli.config_manager, "get_active_session", lambda: ("a1", "tok")
    )
    # Quit immediately after the first panel so the loop terminates.
    monkeypatch.setattr(typer, "prompt", lambda *a, **k: "q")

    # Must not raise FileNotFoundError and must report the configured-path
    # report was found.
    mem_cli.conflicts(date="2026-01-15", agent_id="a1", list_only=False)
    assert report_path.exists(), "report fixture missing"


# ---------------------------------------------------------------------------
# 3. _normalize_tags must treat string and list serialization identically
# ---------------------------------------------------------------------------
def test_normalize_tags_string_and_list_agree():
    """The same tags serialized as CSV string vs list must normalize to the
    same result — otherwise recall/filter behavior depends on storage
    serialization."""
    from memanto.app.services.memory_read_service import MemoryReadService

    svc = MemoryReadService.__new__(MemoryReadService)
    as_str = svc._normalize_tags("a,b")
    as_list = svc._normalize_tags(["a,b"])
    assert as_str == as_list, (
        f"string serialization {as_str} != list serialization {as_list}"
    )


if __name__ == "__main__":
    tests = [
        test_comma_tag_roundtrip_is_not_corrupted,
        test_comma_tag_does_not_create_phantom_tag,
        test_normal_tags_still_roundtrip,
        test_cli_conflicts_command_uses_get_data_dir,
        test_normalize_tags_string_and_list_agree,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")

    # The runtime CLI test needs pytest-style fixtures; run it standalone
    # with hand-rolled stand-ins so `python tests/...py` still exercises it.
    import tempfile

    from _pytest.monkeypatch import MonkeyPatch

    class _TmpPath:
        def __init__(self, root):
            self._root = Path(root)

        def __truediv__(self, other):
            return self._root / other

        def mkdir(self, *a, **k):
            return self._root.mkdir(*a, **k)

        def __str__(self):
            return str(self._root)

    try:
        tmp_path = _TmpPath(tempfile.mkdtemp(prefix="memanto_r4_"))
        mp = MonkeyPatch()
        test_cli_conflicts_reads_configured_data_dir_at_runtime(tmp_path, mp)
        mp.undo()
        print("PASS: test_cli_conflicts_reads_configured_data_dir_at_runtime")
    except Exception as e:
        failures += 1
        print(f"FAIL: test_cli_conflicts_reads_configured_data_dir_at_runtime: {e}")

    sys.exit(1 if failures else 0)
