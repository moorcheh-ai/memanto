"""Google ADK SQLite → OKF adapter fidelity and safety tests."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

ADAPTER_PATH = (
    Path(__file__).parents[1] / "examples" / "migrations" / "google-adk" / "adapter.py"
)
SPEC = importlib.util.spec_from_file_location("google_adk_okf_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


SCHEMA = """
CREATE TABLE app_states (
    app_name TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    update_time REAL NOT NULL
);
CREATE TABLE user_states (
    app_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    state TEXT NOT NULL,
    update_time REAL NOT NULL,
    PRIMARY KEY (app_name, user_id)
);
CREATE TABLE sessions (
    app_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    id TEXT NOT NULL,
    state TEXT NOT NULL,
    create_time REAL NOT NULL,
    update_time REAL NOT NULL,
    PRIMARY KEY (app_name, user_id, id)
);
CREATE TABLE events (
    id TEXT NOT NULL,
    app_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    invocation_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    event_data TEXT NOT NULL,
    PRIMARY KEY (app_name, user_id, session_id, id),
    FOREIGN KEY (app_name, user_id, session_id)
      REFERENCES sessions(app_name, user_id, id) ON DELETE CASCADE
);
"""


def _event(
    event_id: str,
    *,
    author: str,
    text: str | None = None,
    state_delta: dict | None = None,
    timestamp: float,
):
    data = {
        "id": event_id,
        "invocationId": "inv-1",
        "author": author,
        "timestamp": timestamp,
        "actions": {"stateDelta": state_delta or {}},
    }
    if text is not None:
        data["content"] = {"role": author, "parts": [{"text": text}]}
    return data


def _database(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO app_states VALUES (?, ?, ?)",
            (
                "release-agent",
                json.dumps(
                    {
                        "goal.release_window": "Current window is August 4 at 14:00 UTC.",
                        "decision.cache_ttl": "Approved cache TTL is 6 hours.",
                        "api_key": "do-not-publish",
                    }
                ),
                1785500000.0,
            ),
        )
        connection.execute(
            "INSERT INTO app_states VALUES (?, ?, ?)",
            ("other-app", json.dumps({"fact.hidden": "exclude"}), 1.0),
        )
        connection.execute(
            "INSERT INTO user_states VALUES (?, ?, ?, ?)",
            (
                "release-agent",
                "dana",
                json.dumps(
                    {
                        "preference.update_format": "Use Markdown and no tables.",
                    }
                ),
                1785500000.0,
            ),
        )
        connection.execute(
            "INSERT INTO user_states VALUES (?, ?, ?, ?)",
            ("other-app", "other-user", json.dumps({"fact.hidden": "exclude"}), 1.0),
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            (
                "release-agent",
                "dana",
                "session-1",
                json.dumps({"context.topic": "Beacon rollout"}),
                1785400000.0,
                1785500000.0,
            ),
        )
        events = (
            _event(
                "event-1",
                author="release_copilot",
                text="Draft TTL recorded.",
                state_delta={"app:decision.cache_ttl": "Draft TTL is 24 hours."},
                timestamp=1785400001.0,
            ),
            _event(
                "event-2",
                author="user",
                text="Correct it to six hours.",
                timestamp=1785450001.0,
            ),
            _event(
                "event-3",
                author="release_copilot",
                text=None,
                state_delta={
                    "app:decision.cache_ttl": "Approved cache TTL is 6 hours.",
                    "temp:tool_buffer": "must-not-persist",
                },
                timestamp=1785500001.0,
            ),
        )
        for event in events:
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event["id"],
                    "release-agent",
                    "dana",
                    "session-1",
                    event["invocationId"],
                    event["timestamp"],
                    json.dumps(event),
                ),
            )
    return path


def _snapshot(database: Path):
    return adapter.snapshot_database(
        database,
        app_filter="release-agent",
        user_filter="dana",
        captured_at="2026-07-31T12:00:00Z",
        source_version="2.6.0",
    )


def test_readonly_capture_filters_scope_and_redacts_credentials(tmp_path):
    snapshot = _snapshot(_database(tmp_path / "sessions.db"))

    assert snapshot["schema"] == adapter.SNAPSHOT_SCHEMA
    assert len(snapshot["app_states"]) == 1
    assert len(snapshot["user_states"]) == 1
    assert len(snapshot["sessions"]) == 1
    serialized = adapter.canonical_json(snapshot)
    assert "do-not-publish" not in serialized
    assert "<redacted sha256:" in serialized
    assert snapshot["source"]["redacted_values"] == 1
    assert snapshot["source"]["google_adk_version"] == "2.6.0"


def test_mapping_uses_scope_and_key_types_without_importing_temp_state(tmp_path):
    concepts = adapter.build_concepts(_snapshot(_database(tmp_path / "sessions.db")))
    by_key = {item["state_key"]: item for item in concepts}

    assert by_key["goal.release_window"]["type"] == "goal"
    assert by_key["decision.cache_ttl"]["type"] == "decision"
    assert by_key["preference.update_format"]["type"] == "preference"
    assert by_key["context.topic"]["type"] == "context"
    assert by_key["preference.update_format"]["scope"] == "user"
    assert "temp:tool_buffer" not in by_key
    assert by_key["decision.cache_ttl"]["distinct_values"] == 2


def test_current_truth_import_excludes_superseded_history(tmp_path):
    snapshot = _snapshot(_database(tmp_path / "sessions.db"))
    bundle = tmp_path / "bundle"
    manifest = adapter.write_bundle(snapshot, bundle)

    rows = map_okf(load_okf_bundle(bundle))
    joined = "\n".join(row["content"] for row in rows)
    archive = "\n".join(
        path.read_text(encoding="utf-8") for path in (bundle / "archive").rglob("*.md")
    )
    assert len(rows) == manifest["migration"]["mapped_memories"] == 5
    assert "Approved cache TTL is 6 hours" in joined
    assert "Draft TTL is 24 hours" not in joined
    assert "Draft TTL is 24 hours" in archive
    assert manifest["migration"]["superseded_timelines_archived"] == 1


def test_snapshot_replay_is_byte_deterministic(tmp_path):
    snapshot = _snapshot(_database(tmp_path / "sessions.db"))
    first = tmp_path / "first"
    second = tmp_path / "second"
    adapter.write_bundle(snapshot, first)
    snapshot_file = first / "source" / "google-adk-sqlite-snapshot.json"
    adapter.write_bundle(adapter.load_snapshot(snapshot_file), second)

    first_files = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_non_text_event_remains_in_snapshot_and_transcript(tmp_path):
    snapshot = _snapshot(_database(tmp_path / "sessions.db"))
    bundle = tmp_path / "bundle"
    adapter.write_bundle(snapshot, bundle)

    source_json = (bundle / "source" / "google-adk-sqlite-snapshot.json").read_text(
        encoding="utf-8"
    )
    transcripts = "\n".join(
        path.read_text(encoding="utf-8") for path in (bundle / "sessions").glob("*.md")
    )
    assert '"id": "event-3"' in source_json
    assert "non-text event retained in the source snapshot" in transcripts
    assert "`app:decision.cache_ttl`" in transcripts


def test_refuses_unknown_schema(tmp_path):
    path = tmp_path / "wrong.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sessions (id TEXT)")
    with pytest.raises(adapter.AdapterError, match="missing table"):
        adapter.snapshot_database(path)


def test_output_requires_force_and_force_replaces_exact_target(tmp_path):
    snapshot = _snapshot(_database(tmp_path / "sessions.db"))
    bundle = tmp_path / "bundle"
    adapter.write_bundle(snapshot, bundle)
    marker = bundle / "user-marker.txt"
    marker.write_text("old", encoding="utf-8")

    with pytest.raises(adapter.AdapterError, match="--force"):
        adapter.write_bundle(snapshot, bundle)
    adapter.write_bundle(snapshot, bundle, force=True)
    assert not marker.exists()
    assert (bundle / "migration-manifest.json").is_file()
