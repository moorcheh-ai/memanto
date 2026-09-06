"""OpenAI Agents SDK ``SQLiteSession`` -> OKF migration example.

Covers ``examples/migrations/openai-agents-sqlite-session``:

* the source parser (schema introspection, identifier safety, read-only access,
  and the WAL-consistent read snapshot);
* every Responses item shape the SDK persists — plain-string and structured-block
  messages, assistant output items, tool calls, tool outputs, reasoning traces;
* malformed rows (undecodable JSON, wrong top-level shape, text-free content);
* OKF 0.2 conformance (index frontmatter rules, actor identity, ISO-8601 trust
  data) and deterministic generation; and
* the integrity of the committed sample artifacts, which are re-derived from the
  committed snapshot of the real SDK run and compared byte for byte.

The adapter is standard library only, so none of this needs ``openai-agents``
installed — the committed snapshot is the real run's output.
"""

from __future__ import annotations

import filecmp
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "migrations"
    / "openai-agents-sqlite-session"
)
sys.path.insert(0, str(EXAMPLE_DIR))

import okf_adapter  # noqa: E402
import parity_check  # noqa: E402
from okf_adapter import AdapterError  # noqa: E402

SNAPSHOT_PATH = EXAMPLE_DIR / "sample" / "source" / "session_snapshot.json"
BUNDLE_DIR = EXAMPLE_DIR / "sample" / "okf"
REPORT_PATH = EXAMPLE_DIR / "sample" / "evidence" / "adapter-report.json"
PARITY_EVIDENCE = EXAMPLE_DIR / "sample" / "evidence" / "08-query-parity.json"
SESSION_ID = "workspace-buddy-demo"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return _load_json(SNAPSHOT_PATH)


@pytest.fixture(scope="module")
def committed_report() -> dict[str, Any]:
    return _load_json(REPORT_PATH)


def _restore(snapshot: dict[str, Any], db_path: Path) -> Path:
    """Rebuild the SDK's database from the committed snapshot."""
    conn = sqlite3.connect(str(db_path))
    try:
        for sql in snapshot["schema"].values():
            conn.execute(sql)
        conn.executemany(
            "INSERT INTO agent_sessions (session_id, created_at, updated_at) "
            "VALUES (:session_id, :created_at, :updated_at)",
            snapshot["agent_sessions"],
        )
        conn.executemany(
            "INSERT INTO agent_messages (id, session_id, message_data, created_at) "
            "VALUES (:id, :session_id, :message_data, :created_at)",
            snapshot["agent_messages"],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def source_db(snapshot: dict[str, Any], tmp_path: Path) -> Path:
    return _restore(snapshot, tmp_path / "agent_sessions.db")


def _synthetic_db(
    tmp_path: Path, items: list[dict[str, Any]], session_id: str = "s1"
) -> Path:
    """Build a database with the SDK's real schema and hand-picked item rows.

    ``items`` entries are ``{"data": <str|obj>, "created_at": <str>}``; ``data``
    is stored verbatim when it is a string, so malformed rows can be exercised.
    """
    schema = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))["schema"]
    db_path = tmp_path / "synthetic.db"
    conn = sqlite3.connect(str(db_path))
    try:
        for sql in schema.values():
            conn.execute(sql)
        conn.execute(
            "INSERT INTO agent_sessions (session_id, created_at, updated_at) "
            "VALUES (?, ?, ?)",
            (session_id, "2026-01-01 00:00:00", "2026-01-01 00:00:10"),
        )
        for index, item in enumerate(items, start=1):
            data = item["data"]
            conn.execute(
                "INSERT INTO agent_messages (id, session_id, message_data, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    index,
                    session_id,
                    data if isinstance(data, str) else json.dumps(data),
                    item.get("created_at", "2026-01-01 00:00:00"),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


# ---------------------------------------------------------------------------
# Source parser: schema introspection, identifier safety, read-only access
# ---------------------------------------------------------------------------


def test_source_snapshot_is_a_real_sdk_capture(snapshot: dict[str, Any]) -> None:
    """The committed source is a verbatim dump of the SDK's own schema and rows,
    produced by the pinned ``openai-agents`` release."""
    assert "CREATE TABLE agent_messages" in snapshot["schema"]["agent_messages"]
    assert "message_data TEXT NOT NULL" in snapshot["schema"]["agent_messages"]
    assert "session_id TEXT PRIMARY KEY" in snapshot["schema"]["agent_sessions"]

    pinned = re.search(
        r"^openai-agents==(\S+)$",
        (EXAMPLE_DIR / "requirements.txt").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert pinned, "requirements.txt must pin openai-agents"
    assert snapshot["source"]["package_version"] == pinned.group(1)

    # Every row is a JSON Responses item, and the shapes the adapter branches on
    # are all present in the real capture.
    kinds = set()
    for row in snapshot["agent_messages"]:
        payload = json.loads(row["message_data"])
        kinds.add(payload.get("type") or f"role:{payload.get('role')}")
    assert {
        "role:user",
        "message",
        "function_call",
        "function_call_output",
        "reasoning",
    } <= kinds


def test_list_sessions_reports_both_sessions(source_db: Path) -> None:
    sessions = {s.session_id: s for s in okf_adapter.list_sessions(source_db)}
    assert set(sessions) == {SESSION_ID, "sandbox-smoke-test"}
    assert sessions[SESSION_ID].item_count == 19
    assert sessions["sandbox-smoke-test"].item_count == 2
    assert sessions[SESSION_ID].updated_at


def test_read_rows_is_scoped_and_ordered(source_db: Path) -> None:
    rows = okf_adapter.read_rows(source_db, SESSION_ID)
    assert [r.row_id for r in rows] == sorted(r.row_id for r in rows)
    assert {r.session_id for r in rows} == {SESSION_ID}
    assert len(rows) == 19


def test_unknown_session_raises(source_db: Path) -> None:
    with pytest.raises(AdapterError, match="No items found"):
        okf_adapter.read_rows(source_db, "does-not-exist")


@pytest.mark.parametrize(
    "table",
    ["agent messages", "agent_messages; DROP TABLE agent_sessions", "1bad", ""],
)
def test_table_names_must_be_plain_identifiers(source_db: Path, table: str) -> None:
    """Table names are never interpolated blind — they must match the identifier
    pattern before any SQL is built."""
    with pytest.raises(AdapterError, match="Invalid messages table"):
        okf_adapter.read_rows(source_db, SESSION_ID, messages_table=table)


def test_missing_table_is_reported_with_available_tables(source_db: Path) -> None:
    with pytest.raises(AdapterError, match="not found in the database"):
        okf_adapter.read_rows(source_db, SESSION_ID, messages_table="nope")


def test_table_without_expected_columns_is_rejected(source_db: Path) -> None:
    conn = sqlite3.connect(str(source_db))
    conn.execute("CREATE TABLE decoy (id INTEGER PRIMARY KEY, note TEXT)")
    conn.commit()
    conn.close()
    with pytest.raises(AdapterError, match="missing expected column"):
        okf_adapter.read_rows(source_db, SESSION_ID, messages_table="decoy")


def test_missing_database_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="not found"):
        okf_adapter.read_rows(tmp_path / "absent.db", SESSION_ID)


def test_database_path_with_uri_metacharacters(
    snapshot: dict[str, Any], tmp_path: Path
) -> None:
    """A filename containing '?' or '#' must not be mangled into a URI query or
    fragment by the read-only connection."""
    awkward = tmp_path / "who? what# sessions.db"
    _restore(snapshot, awkward)

    rows = okf_adapter.read_rows(awkward, SESSION_ID)
    assert len(rows) == 19
    assert okf_adapter.read_session_meta(awkward, SESSION_ID)["created_at"]
    assert {s.session_id for s in okf_adapter.list_sessions(awkward)} == {
        SESSION_ID,
        "sandbox-smoke-test",
    }

    # Still genuinely read-only.
    conn = okf_adapter.connect_readonly(awkward)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM agent_messages")
    finally:
        conn.close()


def test_wal_only_writes_are_read_and_hashed(tmp_path: Path) -> None:
    """``SQLiteSession`` runs in WAL mode, where committed rows can live only in
    the ``-wal`` sidecar. The main ``.db`` file is then byte-identical for two
    different logical states, so the migration must read *and* hash a consistent
    snapshot that includes WAL content."""
    db = _synthetic_db(tmp_path, [{"data": {"role": "user", "content": "First."}}])

    writer = sqlite3.connect(str(db))
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.commit()
        main_hash_before = _sha256(db)

        first = okf_adapter.migrate(
            db_path=db, session_id="s1", out_dir=tmp_path / "okf-1"
        )

        # Commit a row that stays in the WAL (no checkpoint at this size).
        writer.execute(
            "INSERT INTO agent_messages (id, session_id, message_data, created_at) "
            "VALUES (2, 's1', ?, '2026-01-01 00:00:05')",
            (json.dumps({"role": "user", "content": "Second, WAL-only."}),),
        )
        writer.commit()
        assert (tmp_path / f"{db.name}-wal").exists()
        # The defect this guards against: main file unchanged, data changed.
        assert _sha256(db) == main_hash_before

        second = okf_adapter.migrate(
            db_path=db, session_id="s1", out_dir=tmp_path / "okf-2"
        )
    finally:
        writer.close()

    # The latest logical rows are migrated...
    assert first["counts"]["mapped_documents"] == 1
    assert second["counts"]["mapped_documents"] == 2
    assert "Second, WAL-only." in (
        tmp_path / "okf-2" / second["mapped"][1]["okf_document"]
    ).read_text(encoding="utf-8")

    # ...and the recorded hash tracks the logical state, unlike the main file.
    assert (
        first["source"]["read_snapshot_sha256"]
        != second["source"]["read_snapshot_sha256"]
    )
    # The human-facing report names the user's database, never a temp path.
    assert second["source"]["db_file"] == db.name
    assert tempfile.gettempdir() not in json.dumps(second["source"])


def test_consistent_snapshot_is_isolated_and_always_cleaned_up(
    source_db: Path,
) -> None:
    """The snapshot is a private copy that is removed even when the body raises."""
    with okf_adapter.consistent_snapshot(source_db) as snapshot_path:
        assert snapshot_path.is_file() and snapshot_path != source_db
        assert not snapshot_path.with_name(snapshot_path.name + "-wal").exists()
        captured = snapshot_path
    assert not captured.exists() and not captured.parent.exists()

    with pytest.raises(RuntimeError):
        with okf_adapter.consistent_snapshot(source_db) as snapshot_path:
            failed = snapshot_path
            raise RuntimeError("boom")
    assert not failed.exists() and not failed.parent.exists()


def test_missing_session_error_names_the_users_database(source_db: Path) -> None:
    """The temporary snapshot path must never surface in a user-facing error."""
    with pytest.raises(AdapterError) as excinfo:
        okf_adapter.migrate(
            db_path=source_db, session_id="nope", out_dir=source_db.parent / "okf"
        )
    assert str(source_db) in str(excinfo.value)
    assert "okf-adapter-snapshot" not in str(excinfo.value)


def test_sessions_table_without_optional_timestamp_columns(tmp_path: Path) -> None:
    """A custom sessions table may carry only ``session_id``; the optional
    metadata columns must degrade to None instead of raising OperationalError."""
    db = tmp_path / "minimal.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE agent_sessions (session_id TEXT PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE agent_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "session_id TEXT NOT NULL, message_data TEXT NOT NULL, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute("INSERT INTO agent_sessions (session_id) VALUES ('s1')")
    conn.execute(
        "INSERT INTO agent_messages (session_id, message_data, created_at) "
        "VALUES ('s1', ?, '2026-01-01 00:00:00')",
        (json.dumps({"role": "user", "content": "Hello."}),),
    )
    conn.commit()
    conn.close()

    (info,) = okf_adapter.list_sessions(db)
    assert (info.session_id, info.item_count) == ("s1", 1)
    assert info.created_at is None and info.updated_at is None
    assert okf_adapter.read_session_meta(db, "s1") == {
        "created_at": None,
        "updated_at": None,
    }

    # And a full migration still succeeds over that schema.
    report = okf_adapter.migrate(
        db_path=db, session_id="s1", out_dir=tmp_path / "okf", generated_at="fixed"
    )
    assert report["counts"]["mapped_documents"] == 1
    assert report["source"]["session_created_at"] is None


def test_migration_never_writes_to_the_source_database(
    source_db: Path, tmp_path: Path
) -> None:
    before = _sha256(source_db)
    okf_adapter.migrate(
        db_path=source_db, session_id=SESSION_ID, out_dir=tmp_path / "okf"
    )
    assert _sha256(source_db) == before
    assert not (source_db.parent / f"{source_db.name}-wal").exists()


# ---------------------------------------------------------------------------
# Role and content variants
# ---------------------------------------------------------------------------


def test_role_and_content_variants(tmp_path: Path) -> None:
    """Plain-string content, structured input blocks, assistant output items and
    system messages all map, each keeping its role."""
    db = _synthetic_db(
        tmp_path,
        [
            {"data": {"role": "user", "content": "Plain string content."}},
            {
                "data": {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Structured block."}],
                }
            },
            {
                "data": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "First part.",
                            "annotations": [],
                        },
                        {
                            "type": "output_text",
                            "text": "Second part.",
                            "annotations": [],
                        },
                    ],
                }
            },
            {"data": {"role": "system", "content": "Standing system rule."}},
        ],
    )
    result = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1")

    assert not result.skipped
    kinds = [r.kind for r in result.records]
    assert kinds == [
        "user-message",
        "user-message",
        "assistant-message",
        "system-message",
    ]
    assert [r.role for r in result.records] == ["user", "user", "assistant", "system"]
    assert "Plain string content." in result.records[0].body
    assert "Structured block." in result.records[1].body
    # Multiple text blocks are joined, not dropped.
    assert "First part." in result.records[2].body
    assert "Second part." in result.records[2].body
    # Turn numbering advances on user messages only.
    assert [r.turn for r in result.records] == [1, 2, 2, 2]


def test_non_text_blocks_are_reported_not_stringified(tmp_path: Path) -> None:
    """An image block alongside text is flagged in a note; its raw dict never
    reaches the memory body."""
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Look at this."},
                        {
                            "type": "input_image",
                            "image_url": "https://example.com/x.png",
                        },
                    ],
                }
            }
        ],
    )
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records
    assert "Look at this." in record.body
    assert "input_image" in " ".join(record.notes)
    assert "image_url" not in record.body
    assert "example.com" not in record.body


def test_items_without_usable_text_are_skipped(tmp_path: Path) -> None:
    """A refusal-only message and an empty message carry no text to remember."""
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "refusal", "refusal": "I can't help."}],
                }
            },
            {"data": {"role": "user", "content": ""}},
            {"data": {"role": "user", "content": {"unexpected": "dict"}}},
        ],
    )
    result = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1")
    assert not result.records
    assert [s.reason for s in result.skipped] == ["no_text_content"] * 3


def test_message_status_is_surfaced(tmp_path: Path) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "status": "incomplete",
                    "content": [
                        {"type": "output_text", "text": "Partial.", "annotations": []}
                    ],
                }
            }
        ],
    )
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records
    assert "incomplete" in " ".join(record.notes)


# ---------------------------------------------------------------------------
# Tool calls
# ---------------------------------------------------------------------------


def test_tool_call_and_output_merge_into_one_record(tmp_path: Path) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {"data": {"role": "user", "content": "Check the calendar."}},
            {
                "data": {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "lookup_team_calendar",
                    "arguments": '{"team": "platform"}',
                }
            },
            {
                "data": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": '{"deploy_window": "Thu 09:00 UTC"}',
                }
            },
        ],
    )
    result = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1")
    tool = [r for r in result.records if r.kind == "tool-call"]
    assert len(tool) == 1
    (record,) = tool
    # Both source rows are preserved on the one record.
    assert record.row_ids == [2, 3]
    assert record.memanto_type == "artifact"
    assert '"team": "platform"' in record.body
    assert '"deploy_window": "Thu 09:00 UTC"' in record.body
    assert not any(n.startswith("Result item missing") for n in record.notes)


def _tool_pair(call_at: str, output_at: str) -> list[dict[str, Any]]:
    return [
        {
            "data": {
                "type": "function_call",
                "call_id": "c1",
                "name": "lookup_team_calendar",
                "arguments": "{}",
            },
            "created_at": call_at,
        },
        {
            "data": {
                "type": "function_call_output",
                "call_id": "c1",
                "output": '{"ok": true}',
            },
            "created_at": output_at,
        },
    ]


def test_merged_tool_record_uses_the_result_timestamp(tmp_path: Path) -> None:
    """The merged concept ends with the result, so ``generated.at`` — the last
    meaningful content change (§5.2) — must be the result row's timestamp, not
    the earlier call's."""
    yaml = pytest.importorskip("yaml")
    db = _synthetic_db(
        tmp_path, _tool_pair("2026-01-01 00:00:00", "2026-01-01 00:00:09")
    )
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records

    assert record.row_ids == [1, 2]
    assert record.timestamp == "2026-01-01T00:00:09+00:00"
    assert not record.notes or all("No usable" not in n for n in record.notes)

    front = yaml.safe_load(
        okf_adapter.render_document(record, "s1", "agent_messages").split("---\n")[1]
    )
    assert front["timestamp"] == "2026-01-01T00:00:09+00:00"
    assert front["generated"]["at"] == "2026-01-01T00:00:09+00:00"


@pytest.mark.parametrize("output_at", ["not-a-date", ""])
def test_merged_tool_record_drops_timestamp_when_result_has_none(
    tmp_path: Path, output_at: str
) -> None:
    """A valid call timestamp must not be passed off as the timestamp of content
    that grew after it — the merged record keeps none, and says so."""
    yaml = pytest.importorskip("yaml")
    db = _synthetic_db(tmp_path, _tool_pair("2026-01-01 00:00:00", output_at))
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records

    assert record.row_ids == [1, 2]
    assert record.timestamp is None
    assert any(n.startswith("No usable source timestamp") for n in record.notes)

    front = yaml.safe_load(
        okf_adapter.render_document(record, "s1", "agent_messages").split("---\n")[1]
    )
    assert "timestamp" not in front and "generated" not in front


def test_merged_tool_record_clears_a_stale_timestamp_caveat(tmp_path: Path) -> None:
    """Call timestamp invalid, result timestamp valid: the merged record gains a
    timestamp and must not keep the caveat saying it has none."""
    db = _synthetic_db(tmp_path, _tool_pair("whenever", "2026-01-01 00:00:09"))
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records

    assert record.timestamp == "2026-01-01T00:00:09+00:00"
    assert not any(n.startswith("No usable source timestamp") for n in record.notes)


def test_tool_call_without_output_keeps_a_caveat(tmp_path: Path) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup_team_calendar",
                    "arguments": "{}",
                }
            }
        ],
    )
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records
    assert record.row_ids == [1]
    assert any(n.startswith("Result item missing") for n in record.notes)


def test_orphan_tool_output_is_kept_and_labelled(tmp_path: Path) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {
                    "type": "function_call_output",
                    "call_id": "call_99",
                    "output": "raw text result",
                }
            }
        ],
    )
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records
    assert record.kind == "tool-output"
    assert "raw text result" in record.body
    assert "call_99" in " ".join(record.notes)


def test_non_json_tool_payloads_are_kept_verbatim(tmp_path: Path) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "run_report",
                    "arguments": "not json at all",
                }
            },
            {
                "data": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "plain text output",
                }
            },
        ],
    )
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records
    assert "not json at all" in record.body
    assert "plain text output" in record.body
    # Raw strings must not be fenced as JSON — the fence tag has to be honest.
    assert "```json" not in record.body
    assert record.body.count("```text") == 2


def test_json_tool_payloads_are_fenced_as_json(tmp_path: Path) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "run_report",
                    "arguments": '{"scope": "weekly"}',
                }
            },
            {
                "data": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": '{"rows": 12}',
                }
            },
        ],
    )
    (record,) = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records
    assert record.body.count("```json") == 2
    assert "```text" not in record.body


def test_reasoning_and_unsupported_items_are_skipped_with_reasons(
    tmp_path: Path,
) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {"data": {"id": "rs_1", "type": "reasoning", "summary": []}},
            {"data": {"type": "file_search_call", "id": "fs_1", "queries": ["x"]}},
            {"data": {"type": "function_call", "call_id": "c", "arguments": "{}"}},
        ],
    )
    result = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1")
    assert not result.records
    assert [s.reason for s in result.skipped] == [
        "reasoning_trace",
        "unsupported_item_type",
        "malformed_tool_call",
    ]
    assert result.skipped[1].detail == "file_search_call"


# ---------------------------------------------------------------------------
# Malformed rows
# ---------------------------------------------------------------------------


def test_malformed_rows_are_skipped_not_fatal(tmp_path: Path) -> None:
    """A corrupt row must not abort the migration — it is counted and explained."""
    db = _synthetic_db(
        tmp_path,
        [
            {"data": "{not valid json"},
            {"data": "[1, 2, 3]"},
            {"data": '"just a string"'},
            {"data": {"role": "user", "content": "Survivor."}},
        ],
    )
    result = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1")
    assert [r.body.splitlines()[-1] for r in result.records] == ["Survivor."]
    assert [s.reason for s in result.skipped] == [
        "undecodable_row",
        "unexpected_item_shape",
        "unexpected_item_shape",
    ]
    assert "invalid JSON" in result.skipped[0].detail


def test_non_text_message_data_column_is_skipped(tmp_path: Path) -> None:
    """A BLOB/NULL in ``message_data`` is reported rather than crashing."""
    db = _synthetic_db(tmp_path, [{"data": {"role": "user", "content": "ok"}}])
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO agent_messages (id, session_id, message_data, created_at) "
        "VALUES (2, 's1', X'00FF', '2026-01-01 00:00:00')"
    )
    conn.commit()
    conn.close()

    result = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1")
    assert len(result.records) == 1
    assert result.skipped[0].reason == "undecodable_row"
    assert "expected TEXT" in result.skipped[0].detail


@pytest.mark.parametrize("raw_timestamp", ["whenever", ""])
def test_invalid_timestamp_emits_no_timestamp_or_trust_block(
    tmp_path: Path, raw_timestamp: str
) -> None:
    """OKF requires ISO 8601 for ``timestamp`` and ``generated.at`` (§5.2), so an
    unparseable source value drops both fields rather than emitting garbage — and
    no timestamp is invented to replace it."""
    yaml = pytest.importorskip("yaml")
    db = _synthetic_db(
        tmp_path,
        [{"data": {"role": "user", "content": "Hi."}, "created_at": raw_timestamp}],
    )
    result = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1")
    (record,) = result.records
    assert record.timestamp is None
    # The loss is explicit in the document body.
    assert any("timestamp" in note for note in record.notes)
    if raw_timestamp:
        assert any(raw_timestamp in note for note in record.notes)

    document = okf_adapter.render_document(record, "s1", "agent_messages")
    front = yaml.safe_load(document.split("---\n")[1])
    assert "timestamp" not in front
    assert "generated" not in front
    if raw_timestamp:
        assert raw_timestamp not in str(front)

    report = okf_adapter.migrate(
        db_path=db, session_id="s1", out_dir=tmp_path / "okf", generated_at="fixed"
    )
    assert report["counts"]["mapped_without_timestamp"] == 1
    assert report["mapped"][0]["timestamp"] is None


def test_valid_timestamps_are_normalised_to_utc(tmp_path: Path) -> None:
    db = _synthetic_db(
        tmp_path,
        [
            {
                "data": {"role": "user", "content": "A."},
                "created_at": "2026-03-01 08:30:00",
            },
            {
                "data": {"role": "user", "content": "B."},
                "created_at": "2026-03-01T09:30:00Z",
            },
        ],
    )
    records = okf_adapter.transform(okf_adapter.read_rows(db, "s1"), "s1").records
    assert [r.timestamp for r in records] == [
        "2026-03-01T08:30:00+00:00",
        "2026-03-01T09:30:00+00:00",
    ]
    assert all(not r.notes for r in records)


# ---------------------------------------------------------------------------
# Output shape, determinism and the output-directory guard
# ---------------------------------------------------------------------------


def test_documents_carry_okf_and_memanto_metadata(
    source_db: Path, tmp_path: Path
) -> None:
    yaml = pytest.importorskip("yaml")
    okf_adapter.migrate(
        db_path=source_db, session_id=SESSION_ID, out_dir=tmp_path / "okf"
    )
    # Documents are named after their source row, so the calendar call is 0007.
    doc = next((tmp_path / "okf" / "memories" / "tool-call").glob("0007-*.md"))
    front = yaml.safe_load(doc.read_text(encoding="utf-8").split("---\n")[1])

    assert front["type"] == "openai-agents.tool-call"
    assert front["resource"].startswith(f"openai-agents-sqlite://{SESSION_ID}/")
    assert front["timestamp"].endswith("+00:00")
    assert front["generated"]["at"] == front["timestamp"]
    assert front["generated"]["by"] == okf_adapter.GENERATED_BY
    assert [s["id"] for s in front["sources"]] == [
        "agent_messages:7",
        "agent_messages:8",
    ]
    assert front["x_memanto"]["source"] == okf_adapter.SOURCE_LABEL
    assert front["x_memanto"]["type"] == "artifact"
    assert f"session:{SESSION_ID}" in front["tags"]

    # Conversation messages are left for Memanto's classifier.
    message = next((tmp_path / "okf" / "memories" / "user-message").glob("0001-*.md"))
    message_front = yaml.safe_load(
        message.read_text(encoding="utf-8").split("---\n")[1]
    )
    assert "type" not in message_front["x_memanto"]
    assert "role:user" in message_front["tags"]


def test_generation_is_deterministic(source_db: Path, tmp_path: Path) -> None:
    stamp = "2026-01-01T00:00:00+00:00"
    first = okf_adapter.migrate(
        db_path=source_db,
        session_id=SESSION_ID,
        out_dir=tmp_path / "a" / "okf",
        generated_at=stamp,
    )
    second = okf_adapter.migrate(
        db_path=source_db,
        session_id=SESSION_ID,
        out_dir=tmp_path / "b" / "okf",
        generated_at=stamp,
    )
    assert first == second

    left, right = tmp_path / "a" / "okf", tmp_path / "b" / "okf"
    assert _files(left) == _files(right)
    for name in _files(left):
        assert filecmp.cmp(left / name, right / name, shallow=False), name


def test_output_directory_guard(source_db: Path, tmp_path: Path) -> None:
    """The adapter replaces only bundles it wrote, and only with --force."""
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "important.txt").write_text("do not delete", encoding="utf-8")
    with pytest.raises(AdapterError, match="Refusing to write"):
        okf_adapter.migrate(db_path=source_db, session_id=SESSION_ID, out_dir=foreign)
    assert (foreign / "important.txt").exists()

    bundle = tmp_path / "okf"
    okf_adapter.migrate(db_path=source_db, session_id=SESSION_ID, out_dir=bundle)
    with pytest.raises(AdapterError, match="--force"):
        okf_adapter.migrate(db_path=source_db, session_id=SESSION_ID, out_dir=bundle)

    stale = bundle / "memories" / "user-message" / "9999-stale.md"
    stale.write_text("stale", encoding="utf-8")
    okf_adapter.migrate(
        db_path=source_db, session_id=SESSION_ID, out_dir=bundle, force=True
    )
    assert not stale.exists()


def test_cli_writes_bundle_and_report(
    source_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = okf_adapter.main(
        [
            "--db",
            str(source_db),
            "--session",
            SESSION_ID,
            "--out",
            str(tmp_path / "okf"),
            "--report",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Source items : 19" in out
    assert "Skipped items: 1" in out

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["counts"]["mapped_documents"] == 16
    assert report["adapter"]["okf_version"] == "0.2"


def test_cli_requires_session_and_out(
    source_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert okf_adapter.main(["--db", str(source_db)]) == 2
    assert "--session and --out are required" in capsys.readouterr().err


def test_cli_lists_sessions(
    source_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert okf_adapter.main(["--db", str(source_db), "--list-sessions"]) == 0
    out = capsys.readouterr().out
    assert SESSION_ID in out and "sandbox-smoke-test" in out


# ---------------------------------------------------------------------------
# OKF 0.2 spec conformance
# ---------------------------------------------------------------------------

#: OKF 0.2 §7 actor identity: "<producer>/<version>", "human:<id>", "process:<id>".
_OKF_ACTOR_RE = re.compile(r"^(?:[^\s:/]+/\S+|human:\S+|process:\S+)$")


def _frontmatter(path: Path) -> Any:
    import yaml  # type: ignore[import-untyped]

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    return yaml.safe_load(text.split("---\n")[1])


def _concept_docs(bundle: Path) -> list[Path]:
    return sorted(p for p in bundle.rglob("*.md") if p.name != "index.md")


def _check_index_rules(bundle: Path) -> None:
    """OKF 0.2 §8: ``index.md`` carries no frontmatter — the sole exception is a
    bundle-root ``index.md``, which may carry an ``okf_version`` key."""
    indexes = sorted(bundle.rglob("index.md"))
    assert len(indexes) >= 3
    for path in indexes:
        text = path.read_text(encoding="utf-8")
        if path.parent == bundle:
            assert text.startswith("---\n"), f"{path} should declare okf_version"
            assert _frontmatter(path) == {"okf_version": "0.2"}, path
        else:
            assert not text.lstrip().startswith("---"), (
                f"{path} must not carry frontmatter"
            )


def test_index_files_follow_okf_index_rules(source_db: Path, tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    _check_index_rules(BUNDLE_DIR)

    okf_adapter.migrate(
        db_path=source_db, session_id=SESSION_ID, out_dir=tmp_path / "okf"
    )
    _check_index_rules(tmp_path / "okf")


def test_generated_by_is_a_valid_okf_actor(source_db: Path, tmp_path: Path) -> None:
    """A bare conversation role is neither a valid actor identity (§7) nor
    truthful about who authored the document — the adapter did."""
    pytest.importorskip("yaml")
    okf_adapter.migrate(
        db_path=source_db, session_id=SESSION_ID, out_dir=tmp_path / "okf"
    )

    for bundle in (BUNDLE_DIR, tmp_path / "okf"):
        docs = _concept_docs(bundle)
        assert docs
        for path in docs:
            front = _frontmatter(path)
            actor = front["generated"]["by"]
            assert _OKF_ACTOR_RE.match(actor), f"{path}: invalid actor {actor!r}"
            assert actor == okf_adapter.GENERATED_BY
            assert actor not in ("user", "assistant", "system", "tool")
            # The source role is still preserved — just not as an actor.
            assert "role `" in path.read_text(encoding="utf-8")
            if front["type"].endswith("-message"):
                assert any(t.startswith("role:") for t in front["tags"]), path


def test_session_id_is_percent_encoded_in_identifiers(tmp_path: Path) -> None:
    """A session id is arbitrary user data. Reserved characters must not be able
    to restructure the resource URI (or the colon-delimited x_memanto id)."""
    yaml = pytest.importorskip("yaml")
    session_id = "a b/c?d#e%f café\ttab"
    db = _synthetic_db(
        tmp_path,
        [{"data": {"role": "user", "content": "Hello."}}],
        session_id=session_id,
    )

    uri = okf_adapter.source_uri(session_id, "agent_messages", 7)
    parts = urlsplit(uri)
    # The whole id stays in one component; nothing leaks into path/query/fragment.
    assert parts.path == "/agent_messages/7"
    assert parts.query == "" and parts.fragment == ""
    assert unquote(parts.netloc) == session_id
    assert not any(c in parts.netloc for c in " /?#\t")

    okf_adapter.migrate(
        db_path=db, session_id=session_id, out_dir=tmp_path / "okf", generated_at="x"
    )
    (doc,) = _concept_docs(tmp_path / "okf" / "memories" / "user-message")
    front = yaml.safe_load(doc.read_text(encoding="utf-8").split("---\n")[1])

    assert unquote(urlsplit(front["resource"]).netloc) == session_id
    assert front["sources"][0]["resource"] == front["resource"]
    prefix, encoded, row = front["x_memanto"]["id"].rsplit(":", 2)
    assert prefix == okf_adapter.SOURCE_LABEL
    assert unquote(encoded) == session_id and row == "1"
    # The human-readable tag and body keep the id verbatim.
    assert f"session:{session_id}" in front["tags"]


@pytest.mark.parametrize("session_id", ["workspace-buddy-demo", "sandbox-smoke-test"])
def test_plain_session_ids_are_not_rewritten(session_id: str) -> None:
    """Encoding must be a no-op for ordinary ids, so existing bundles are stable."""
    assert okf_adapter.source_uri(session_id, "agent_messages", 3) == (
        f"openai-agents-sqlite://{session_id}/agent_messages/3"
    )


def test_generated_by_carries_the_adapter_version() -> None:
    assert okf_adapter.GENERATED_BY == (
        f"{okf_adapter.ADAPTER_NAME}/{okf_adapter.ADAPTER_VERSION}"
    )


# ---------------------------------------------------------------------------
# One-command runner
# ---------------------------------------------------------------------------

RUN_DEMO = EXAMPLE_DIR / "run_demo.sh"


def test_run_demo_is_executable_and_valid_shell() -> None:
    """Static checks only — the script itself is exercised by hand (and in the
    README's evidence), because a full SDK run would make this suite slow."""
    assert RUN_DEMO.is_file()
    assert RUN_DEMO.stat().st_mode & 0o100, "run_demo.sh must be executable"

    script = RUN_DEMO.read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in script  # fail fast
    assert "trap cleanup EXIT" in script  # workspace always removed

    syntax = subprocess.run(
        ["bash", "-n", str(RUN_DEMO)], capture_output=True, text=True
    )
    assert syntax.returncode == 0, syntax.stderr


def test_run_demo_never_writes_into_the_committed_sample() -> None:
    """Every generated path must live in the temp workspace, so a demo run can
    never mutate the committed artifacts."""
    script = RUN_DEMO.read_text(encoding="utf-8")
    for flag in ("--db", "--snapshot", "--out", "--report"):
        targets = re.findall(rf"{flag} +(\S+)", script)
        assert targets, f"{flag} not found in run_demo.sh"
        for target in targets:
            assert target.startswith('"$WORK'), f"{flag} {target} escapes the workspace"
    # And it runs the four documented stages.
    for stage in (
        "generate_session.py",
        "okf_adapter.py",
        "migrate okf",
        "verify_artifacts.py",
    ):
        assert stage in script


# ---------------------------------------------------------------------------
# Before/after query parity (offline — not live recall)
# ---------------------------------------------------------------------------


def test_every_query_keeps_its_answer(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    """Every question must still be answerable after the migration — all of them,
    not a majority. Deterministic lexical retrieval over both corpora; no model,
    no network, no Moorcheh call."""
    pytest.importorskip("memanto")
    parity = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )

    assert parity["questions"] == len(parity_check.QUERIES)
    assert parity["threshold"] == 1.0
    assert parity["parity"] == 1.0, [
        r["question"] for r in parity["results"] if not r["passed"]
    ]
    assert parity["meets_threshold"]

    # The corpora are the real ones, minus the question-only rows.
    assert (
        parity["corpus_sizes"]["after_memories"]
        < committed_report["counts"]["mapped_documents"]
    )
    # Labelled honestly.
    assert "not live" in parity["_comment"].lower()
    assert parity["not_measured"] == "live Moorcheh recall quality"


def test_query_only_rows_cannot_answer_anything(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    """A user turn that only asks something is excluded from both corpora, so a
    query can never 'pass' by retrieving its own question back."""
    pytest.importorskip("memanto")
    excluded = parity_check.question_rows(snapshot, SESSION_ID)
    assert excluded, "the scenario contains a question-only user turn"

    for row_id in excluded:
        payload = json.loads(
            next(
                r["message_data"]
                for r in snapshot["agent_messages"]
                if int(r["id"]) == row_id
            )
        )
        assert payload["role"] == "user"
        assert parity_check._raw_text(payload).strip().endswith("?")

    before = dict(parity_check.before_corpus(snapshot, SESSION_ID, excluded))
    after = dict(parity_check.after_corpus(BUNDLE_DIR, excluded))
    assert not (excluded & before.keys())
    assert not (excluded & after.keys())

    parity = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )
    assert parity["excluded_question_rows"] == [
        f"agent_messages:{row}" for row in sorted(excluded)
    ]
    retrieved = {
        item["source_item"]
        for result in parity["results"]
        for side in ("before", "after")
        for item in result[side]["retrieved"]
    }
    assert not (retrieved & set(parity["excluded_question_rows"]))


def test_query_parity_passes_are_earned(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    """A pass needs answer-bearing evidence on both sides, >=80% expected-fact
    coverage each, corrections beating stale evidence, and a shared concept."""
    pytest.importorskip("memanto")
    parity = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )
    assert parity["fact_coverage_threshold"] == 0.80

    for result in parity["results"]:
        assert result["passed"], result["question"]
        for side in ("before", "after"):
            evidence = result[side]
            assert evidence["fact_coverage"] >= 0.80
            assert evidence["meets_coverage"]
            assert evidence["answer_items"], f"{result['question']}: no evidence"
            assert evidence["correction_wins"]
            assert set(evidence["facts_found"]) <= set(result["expected_facts"])
        # Equivalent concepts are allowed; identical row ids are not required.
        assert result["shared_answer_concepts"]


def test_recall_stays_bounded_and_separates_the_two_similarities(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    """Migrated memories share a ``[Supporting data]`` footer, which inflates
    document-to-document similarity. Unbounded, the revision step drags in most
    of the corpus and coverage stops meaning anything, so recall is capped and a
    revision must still be relevant to the question."""
    pytest.importorskip("memanto")
    parity = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )
    cap = parity_check.TOP_K * (1 + parity_check.MAX_REVISIONS_PER_HIT)

    for result in parity["results"]:
        for side in ("before", "after"):
            evidence = result[side]
            assert evidence["retrieved_count"] == len(evidence["retrieved"])
            assert evidence["retrieved_count"] <= cap, result["question"]
            # Never a majority of the corpus — that would prove only that the
            # fact exists somewhere, not that the query reaches it.
            assert evidence["retrieved_count"] < evidence["corpus_size"] / 2

            revisions = 0
            for hit in evidence["retrieved"]:
                # Query relevance is reported for every hit, and separately from
                # the document-to-document revision similarity.
                assert hit["query_score"] >= parity_check.MIN_SCORE
                if hit["revises"] is None:
                    assert hit["revision_similarity"] is None
                else:
                    revisions += 1
                    assert (
                        hit["revision_similarity"] >= parity_check.SUPERSEDE_SIMILARITY
                    )
                    assert hit["revises"] != hit["source_item"]
            assert revisions <= parity_check.TOP_K * parity_check.MAX_REVISIONS_PER_HIT


def test_correction_supersedes_the_stale_answer(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    """The deploy window was corrected mid-session. Both sides must answer with
    the Thursday correction, not the Tuesday the calendar tool returned."""
    pytest.importorskip("memanto")
    parity = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )
    deploy = parity["results"][0]
    assert deploy["superseded_facts"] == ["Tuesday 14:00-16:00"]

    for side in ("before", "after"):
        evidence = deploy[side]
        # The stale evidence is retrieved — and beaten by newer evidence.
        assert evidence["superseded_items"]
        newest_answer = max(int(i.split(":")[1]) for i in evidence["answer_items"])
        newest_stale = max(int(i.split(":")[1]) for i in evidence["superseded_items"])
        assert newest_answer > newest_stale
        assert evidence["facts_found"] == ["Thursday", "09:00 UTC"]


def test_parity_fails_when_only_the_correction_is_lost(
    snapshot: dict[str, Any], committed_report: dict[str, Any], tmp_path: Path
) -> None:
    """Losing just the correction — leaving the stale answer in place — must fail
    the affected query, not be absorbed by an aggregate score."""
    pytest.importorskip("memanto")
    stripped = tmp_path / "okf"
    shutil.copytree(BUNDLE_DIR, stripped)
    for doc in stripped.rglob("*.md"):
        if "Thursday 09:00 UTC" in doc.read_text(encoding="utf-8"):
            doc.unlink()

    parity = parity_check.run_parity(
        snapshot=snapshot, bundle=stripped, report=committed_report
    )
    deploy = parity["results"][0]
    assert not deploy["passed"]
    assert deploy["after"]["fact_coverage"] == 0.0
    assert not parity["meets_threshold"]


def test_query_parity_is_deterministic(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    pytest.importorskip("memanto")
    first = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )
    second = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )
    assert first == second


def test_query_parity_detects_a_broken_migration(
    snapshot: dict[str, Any], committed_report: dict[str, Any], tmp_path: Path
) -> None:
    """The gate has teeth: gut the migrated corpus and parity must collapse."""
    pytest.importorskip("memanto")
    gutted = tmp_path / "okf"
    shutil.copytree(BUNDLE_DIR, gutted)
    for doc in gutted.rglob("*.md"):
        if doc.name == "index.md":
            continue
        # Keep the document structurally importable — type and resource, so it
        # still maps to a memory — but strip every trace of what it said. Title
        # and description carry the text too, so body-only redaction is not
        # enough to prove the check is measuring content.
        front = dict(
            line.split(": ", 1)
            for line in doc.read_text(encoding="utf-8").split("---\n")[1].splitlines()
            if line.startswith(("type: ", "resource: "))
        )
        doc.write_text(
            "---\n"
            f"type: {front['type']}\n"
            f"resource: {front['resource']}\n"
            'title: "redacted"\n'
            "---\n\nredacted\n",
            encoding="utf-8",
        )

    parity = parity_check.run_parity(
        snapshot=snapshot, bundle=gutted, report=committed_report
    )
    assert not parity["meets_threshold"]
    # Not zero: a few facts survive in the document slugs the adapter derives
    # from titles (``0007-lookup-team-calendar.md``), which is itself real
    # preservation. The point is that the gate fails.
    assert parity["parity"] < 0.5
    assert [r["question"] for r in parity["results"] if not r["passed"]]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda s, r: s.update(agent_messages="not a list"), "agent_messages"),
        (
            lambda s, r: s["agent_messages"].append(
                {"id": 99, "session_id": SESSION_ID, "message_data": "{not json"}
            ),
            "not valid JSON",
        ),
        (
            lambda s, r: s["agent_messages"].append(
                {"id": 98, "session_id": SESSION_ID, "message_data": 17}
            ),
            "expected a JSON string",
        ),
        (lambda s, r: r.update(mapped="not a list"), "'mapped' entries"),
        (lambda s, r: r["mapped"].append({"okf_document": "x"}), "source_items"),
        (
            lambda s, r: r["mapped"].append(
                {"okf_document": "x", "source_items": ["agent_messages:not-an-id"]}
            ),
            "unreadable source item",
        ),
    ],
)
def test_malformed_inputs_raise_parity_error(
    snapshot: dict[str, Any],
    committed_report: dict[str, Any],
    mutate: Any,
    match: str,
) -> None:
    """Bad snapshots, source_refs and reports must surface as ParityError so the
    CLI exits cleanly instead of dumping a traceback."""
    pytest.importorskip("memanto")
    broken_snapshot = json.loads(json.dumps(snapshot))
    broken_report = json.loads(json.dumps(committed_report))
    mutate(broken_snapshot, broken_report)

    with pytest.raises(parity_check.ParityError, match=match):
        parity_check.run_parity(
            snapshot=broken_snapshot, bundle=BUNDLE_DIR, report=broken_report
        )


def test_cli_reports_malformed_input_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "snapshot.json"
    bad.write_text("{not json", encoding="utf-8")
    assert parity_check.main(["--snapshot", str(bad)]) == 1
    assert "not valid JSON" in capsys.readouterr().err

    missing = tmp_path / "absent.json"
    assert parity_check.main(["--report", str(missing)]) == 1
    assert "not found" in capsys.readouterr().err


def test_parity_session_id_is_threaded_through(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    """``--session`` / the verifier's session id reaches ``run_parity``."""
    pytest.importorskip("memanto")
    parity = parity_check.load_parity_report(
        SNAPSHOT_PATH, BUNDLE_DIR, REPORT_PATH, SESSION_ID
    )
    assert parity["session_id"] == SESSION_ID

    with pytest.raises(parity_check.ParityError, match="no rows for session"):
        parity_check.run_parity(
            snapshot=snapshot,
            bundle=BUNDLE_DIR,
            report=committed_report,
            session_id="sandbox-smoke-test-not-here",
        )


def test_committed_parity_evidence_matches_a_fresh_run(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    """The committed parity evidence is what the checker produces today."""
    pytest.importorskip("memanto")
    committed = _load_json(PARITY_EVIDENCE)
    fresh = parity_check.run_parity(
        snapshot=snapshot, bundle=BUNDLE_DIR, report=committed_report
    )
    assert committed == fresh


# ---------------------------------------------------------------------------
# Committed artifact integrity
# ---------------------------------------------------------------------------


def test_committed_bundle_is_reproduced_byte_for_byte(
    snapshot: dict[str, Any], committed_report: dict[str, Any], tmp_path: Path
) -> None:
    """The committed OKF bundle is exactly what the adapter produces from the
    committed snapshot of the real SDK run."""
    db = _restore(snapshot, tmp_path / snapshot["source"]["db_file"])
    report = okf_adapter.migrate(
        db_path=db,
        session_id=SESSION_ID,
        out_dir=tmp_path / "out" / BUNDLE_DIR.name,
        source_package_version=snapshot["source"]["package_version"],
        generated_at=committed_report["generated_at"],
    )
    regenerated = tmp_path / "out" / BUNDLE_DIR.name

    assert _files(BUNDLE_DIR) == _files(regenerated)
    for name in sorted(_files(BUNDLE_DIR)):
        assert filecmp.cmp(BUNDLE_DIR / name, regenerated / name, shallow=False), name

    # The rebuilt database is logically identical but physically a different
    # file, so its read-snapshot hash legitimately differs.
    volatile = {"read_snapshot_sha256", "db_file"}
    assert {k: v for k, v in report["source"].items() if k not in volatile} == {
        k: v for k, v in committed_report["source"].items() if k not in volatile
    }
    for section in ("counts", "mapped", "skipped", "output", "adapter"):
        assert report[section] == committed_report[section], section


def test_committed_report_is_consistent_with_the_snapshot(
    snapshot: dict[str, Any], committed_report: dict[str, Any]
) -> None:
    rows = [r for r in snapshot["agent_messages"] if r["session_id"] == SESSION_ID]
    counts = committed_report["counts"]

    # The report and the committed capture describe the same logical database.
    assert (
        committed_report["source"]["read_snapshot_sha256"]
        == snapshot["source"]["read_snapshot_sha256"]
    )
    assert "db_sha256" not in committed_report["source"]  # renamed, not ambiguous
    assert counts["source_items"] == len(rows)
    # Nothing is silently lost: every source row is either mapped or skipped.
    assert counts["source_items_consumed"] == len(rows)
    assert counts["mapped_documents"] == 16
    assert counts["skipped_items"] == 1
    assert counts["skipped_by_reason"] == {"reasoning_trace": 1}

    mapped_rows = {
        int(i.split(":")[1])
        for m in committed_report["mapped"]
        for i in m["source_items"]
    }
    skipped_rows = {
        int(s["source_item"].split(":")[1]) for s in committed_report["skipped"]
    }
    assert mapped_rows | skipped_rows == {r["id"] for r in rows}
    assert not mapped_rows & skipped_rows


def test_committed_bundle_imports_through_memanto() -> None:
    """The committed bundle survives Memanto's real OKF import path."""
    from memanto.cli.migrate.mappers import map_okf, type_breakdown
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    export = load_okf_bundle(BUNDLE_DIR)
    rows = map_okf(export)

    assert len(export["memories"]) == len(rows) == 16
    assert type_breakdown(rows) == {"auto": 14, "artifact": 2}

    for row in rows:
        assert row["source"] == okf_adapter.SOURCE_LABEL
        assert row["source_ref"].startswith("openai-agents-sqlite://")
        assert row["created_at"] is not None
        assert row["provenance"] == "imported"
        assert f"session:{SESSION_ID}" in row["tags"]

    # The tool record keeps its arguments, its result and both source row ids.
    tool = [r for r in rows if r["type"] == "artifact"]
    assert len(tool) == 2
    calendar = next(r for r in tool if "lookup_team_calendar" in r["content"])
    assert '"deploy_window": "Tuesday 14:00-16:00 UTC"' in calendar["content"]
    assert "agent_messages:7" in calendar["content"]
    assert "agent_messages:8" in calendar["content"]

    # The user's correction keeps its text verbatim and its provenance footer,
    # distinct from the assistant reply that echoes the same fact.
    correction = next(
        r for r in rows if r["content"].startswith("User message from turn 4")
    )
    assert "The Tuesday slot is retired" in correction["content"]
    assert "role `user`" in correction["content"]
    assert "[Supporting data]" in correction["content"]


def test_committed_artifacts_contain_no_local_paths(
    committed_report: dict[str, Any],
) -> None:
    """Nothing environment-specific (home dirs, absolute paths) is published."""
    for path in sorted(BUNDLE_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "/home/" not in text and "/Users/" not in text, path
    assert "/" not in committed_report["source"]["db_file"]
