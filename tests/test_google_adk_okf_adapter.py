"""Google ADK SQLite → OKF adapter fidelity and safety tests."""

from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

ADAPTER_PATH = (
    Path(__file__).parents[1] / "examples" / "migrations" / "google-adk" / "adapter.py"
)
EXAMPLE_DIR = ADAPTER_PATH.parent
RUN_DEMO_PATH = EXAMPLE_DIR / "run_demo.py"
ROUNDTRIP_PATH = EXAMPLE_DIR / "run_roundtrip.py"
LONG_DESCRIPTION = (
    "The first staging migration failed because PostgreSQL pg_trgm was missing. "
    "After enabling the extension it succeeded with healthy latency, and the "
    "release runbook now requires a pg_trgm preflight before every migration."
)
SPEC = importlib.util.spec_from_file_location("google_adk_okf_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)

VERIFY_PATH = (
    Path(__file__).parents[1]
    / "examples"
    / "migrations"
    / "google-adk"
    / "verify_artifacts.py"
)
VERIFY_SPEC = importlib.util.spec_from_file_location(
    "google_adk_okf_verifier", VERIFY_PATH
)
assert VERIFY_SPEC and VERIFY_SPEC.loader
verifier = importlib.util.module_from_spec(VERIFY_SPEC)
PREVIOUS_ADAPTER_MODULE = sys.modules.get("adapter")
sys.modules["adapter"] = adapter
try:
    VERIFY_SPEC.loader.exec_module(verifier)
finally:
    if PREVIOUS_ADAPTER_MODULE is None:
        del sys.modules["adapter"]
    else:
        sys.modules["adapter"] = PREVIOUS_ADAPTER_MODULE


def _load_roundtrip_module():
    spec = importlib.util.spec_from_file_location(
        "google_adk_roundtrip_test", ROUNDTRIP_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous_adapter = sys.modules.get("adapter")
    sys.modules["adapter"] = adapter
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(EXAMPLE_DIR))
        if previous_adapter is None:
            del sys.modules["adapter"]
        else:
            sys.modules["adapter"] = previous_adapter
    return module


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
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO app_states VALUES (?, ?, ?)",
            (
                "release-agent",
                json.dumps(
                    {
                        "goal.release_window": "Current window is August 4 at 14:00 UTC.",
                        "decision.cache_ttl": "Approved cache TTL is 6 hours.",
                        "learning.long_description": LONG_DESCRIPTION,
                        "api_key": "do-not-publish",
                        "accessToken": "camel-secret",
                        "tokenizer_config": "keep-me",
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
        connection.commit()
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
    assert "camel-secret" not in serialized
    assert "<redacted>" in serialized
    assert "keep-me" in serialized
    assert snapshot["source"]["redacted_values"] == 2
    assert snapshot["source"]["google_adk_version"] == "2.6.0"


def test_sensitive_key_detection_handles_camelcase_without_false_positives():
    for key in ("accessToken", "refreshToken", "clientSecret", "userPassword"):
        assert adapter._is_sensitive_key(key)
    for key in ("tokenizer_config", "secretary", "passwordless_mode"):
        assert not adapter._is_sensitive_key(key)


def test_mapping_uses_scope_and_key_types_without_importing_temp_state(tmp_path):
    concepts = adapter.build_concepts(_snapshot(_database(tmp_path / "sessions.db")))
    by_key = {item["state_key"]: item for item in concepts}

    assert by_key["goal.release_window"]["type"] == "goal"
    assert by_key["decision.cache_ttl"]["type"] == "decision"
    assert by_key["preference.update_format"]["type"] == "preference"
    assert by_key["context.topic"]["type"] == "context"
    assert by_key["preference.update_format"]["scope"] == "user"
    assert "temp:tool_buffer" not in by_key
    assert "api_key" not in by_key
    assert "accessToken" not in by_key
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
    assert len(rows) == manifest["migration"]["mapped_memories"] == 6
    assert manifest["migration"]["skipped"] == 2
    assert "Approved cache TTL is 6 hours" in joined
    assert "Draft TTL is 24 hours" not in joined
    assert "Draft TTL is 24 hours" in archive
    assert manifest["migration"]["superseded_timelines_archived"] == 1


def test_histories_sort_overlapping_session_updates_chronologically():
    snapshot = {
        "sessions": [
            {
                "app_name": "app",
                "user_id": "user",
                "session_id": "started-first",
                "events": [
                    {
                        "id": "event-z",
                        "timestamp": "2026-07-10T12:00:03Z",
                        "invocation_id": "inv-z",
                        "event_data": {
                            "author": "agent",
                            "actions": {"stateDelta": {"app:goal.release": "stale"}},
                        },
                    }
                ],
            },
            {
                "app_name": "app",
                "user_id": "user",
                "session_id": "started-later",
                "events": [
                    {
                        "id": "event-a",
                        "timestamp": "2026-07-10T12:00:02Z",
                        "invocation_id": "inv-a",
                        "event_data": {
                            "author": "user",
                            "actions": {"stateDelta": {"app:goal.release": "earlier"}},
                        },
                    }
                ],
            },
        ]
    }

    histories = adapter.state_histories(snapshot)
    updates = histories[("app", "app", None, None, "goal.release")]
    assert [item["event_id"] for item in updates] == ["event-a", "event-z"]


def test_bundle_preserves_full_descriptions_and_resolvable_audit_links(tmp_path):
    snapshot = _snapshot(_database(tmp_path / "sessions.db"))
    bundle = tmp_path / "bundle"
    adapter.write_bundle(snapshot, bundle)

    entries = load_okf_bundle(bundle)["memories"]
    learning = next(entry for entry in entries if entry["title"] == "Long description")
    assert learning["description"] == LONG_DESCRIPTION

    links_checked = 0
    for path in (bundle / "memories").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[Audit trail[^]]*\]\(([^)]+)\)", text):
            resolved = (path.parent / target).resolve()
            resolved.relative_to(bundle.resolve())
            assert resolved.is_file()
            links_checked += 1
    assert links_checked == 1


def test_session_transcripts_use_persisted_event_chronology(tmp_path):
    snapshot = _snapshot(_database(tmp_path / "sessions.db"))
    bundle = tmp_path / "bundle"
    adapter.write_bundle(snapshot, bundle)
    transcript = next((bundle / "sessions").glob("session-1-*.md")).read_text(
        encoding="utf-8"
    )

    assert "- First persisted event: `" in transcript
    assert "- Last persisted event: `" in transcript
    assert "- Captured: `2026-07-31T12:00:00Z`" in transcript
    assert "- Created:" not in transcript


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
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE sessions (id TEXT)")
    with pytest.raises(adapter.AdapterError, match="missing table") as exc_info:
        adapter.snapshot_database(path)
    assert "adk migrate session --source_db_url" in str(exc_info.value)


def test_capture_rejects_database_changed_during_read(tmp_path, monkeypatch):
    path = _database(tmp_path / "sessions.db")
    real_sha256_file = adapter.sha256_file
    calls = 0

    def changing_digest(target):
        nonlocal calls
        calls += 1
        digest = real_sha256_file(target)
        return digest if calls == 1 else "0" * 64

    monkeypatch.setattr(adapter, "sha256_file", changing_digest)
    with pytest.raises(adapter.AdapterError, match="changed during capture"):
        adapter.snapshot_database(path)


@pytest.mark.parametrize(
    "flag",
    [
        "--app=release-agent",
        "--user=dana",
        "--captured-at=2026-08-01T00:00:00Z",
        "--source-version=2.6.0",
        "--include-sensitive",
    ],
)
def test_snapshot_replay_rejects_database_capture_options(tmp_path, flag, capsys):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        adapter.canonical_json(_snapshot(_database(tmp_path / "sessions.db"))),
        encoding="utf-8",
    )
    result = adapter.main(
        ["--snapshot", str(snapshot_path), "--output", str(tmp_path / "out"), flag]
    )

    assert result == 2
    assert "apply only to --db captures" in capsys.readouterr().out


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


def test_run_demo_force_refuses_unowned_directory(tmp_path):
    unsafe = tmp_path / "user-files"
    unsafe.mkdir()
    marker = unsafe / "keep.txt"
    marker.write_text("do not delete", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(RUN_DEMO_PATH), "--artifacts", str(unsafe), "--force"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "refusing to delete" in result.stdout
    assert marker.read_text(encoding="utf-8") == "do not delete"


def test_roundtrip_capture_redacts_the_configured_api_key():
    module = _load_roundtrip_module()

    assert (
        module._redact_secret_text(
            "request failed for mk_test_secret", {"MOORCHEH_API_KEY": "mk_test_secret"}
        )
        == "request failed for <redacted>"
    )


def test_roundtrip_clears_only_stale_summaries_for_new_agent(tmp_path):
    module = _load_roundtrip_module()
    stale = tmp_path / "target_2026-08-01_unknown_summary.md"
    keep_agent = tmp_path / "other_2026-08-01_unknown_summary.md"
    keep_non_summary = tmp_path / "target_notes.md"
    for path in (stale, keep_agent, keep_non_summary):
        path.write_text("evidence", encoding="utf-8")

    assert module._clear_stale_session_summaries("target", tmp_path) == 1
    assert not stale.exists()
    assert keep_agent.is_file()
    assert keep_non_summary.is_file()


def test_roundtrip_rejects_duplicate_active_resources(tmp_path):
    module = _load_roundtrip_module()
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    first = sessions / "first_summary.md"
    second = sessions / "second_summary.md"
    first.write_text("- OKF resource: `google-adk://same`\n", encoding="utf-8")
    second.write_text("- OKF resource: `google-adk://same`\n", encoding="utf-8")

    with pytest.raises(adapter.AdapterError, match="Duplicate active OKF resource"):
        module._assert_unique_summary_resources(tmp_path)


def test_roundtrip_maps_every_persisted_event_date_with_create_fallback():
    module = _load_roundtrip_module()
    assert module._source_session_dates(
        {
            "create_time": "2026-07-01T00:00:00Z",
            "events": [
                {"timestamp": "2026-07-03T23:00:00Z"},
                {"timestamp": "2026-07-02T01:00:00Z"},
                {"timestamp": "2026-07-03T01:00:00Z"},
            ],
        }
    ) == ["2026-07-02", "2026-07-03"]
    assert module._source_session_dates(
        {"create_time": "2026-07-01T00:00:00Z", "events": []}
    ) == ["2026-07-01"]


def test_verifier_rejects_manifest_paths_outside_bundle(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    manifest = {
        "schema": adapter.MANIFEST_SCHEMA,
        "files": [
            {
                "path": "../outside.txt",
                "bytes": 0,
                "sha256": "0" * 64,
            }
        ],
        "source": {
            "snapshot_path": "source/snapshot.json",
            "snapshot_sha256": "0" * 64,
        },
        "migration": {"mapped_memories": 0},
    }
    (root / "migration-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(adapter.AdapterError, match="Unsafe manifest file path"):
        verifier.verify_bundle(root)

    with pytest.raises(adapter.AdapterError, match="expected a relative path"):
        verifier._manifest_path(root, "", label="source snapshot path")


def test_verifier_detects_unlisted_memory_files(tmp_path):
    bundle = tmp_path / "bundle"
    adapter.write_bundle(_snapshot(_database(tmp_path / "sessions.db")), bundle)
    extra = bundle / "memories" / "fact" / "unlisted.md"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("# Not in the manifest\n", encoding="utf-8")

    report = verifier.verify_bundle(bundle)

    assert not report["passed"]
    assert "unlisted memory file: memories/fact/unlisted.md" in report["failures"]


def test_verifier_detects_short_meaningful_superseded_values():
    assert verifier._contains_meaningful_value(
        "Current value accidentally says old.", "old"
    )
    assert not verifier._contains_meaningful_value("A normal active memory.", "a")
    assert not verifier._contains_meaningful_value("Marker: <redacted>", "<redacted>")


@pytest.mark.parametrize(
    ("content", "value"),
    [
        (
            'Current value:\n{\n  "mode": "legacy",\n  "retries": 3\n}',
            {"mode": "legacy", "retries": 3},
        ),
        ("Current value: legacy", {"content": "legacy"}),
        ("Current value: [\n  true,\n  7\n]", [True, 7]),
        ("Current value: 42", 42),
        ("Current value: true", True),
    ],
)
def test_verifier_detects_structured_superseded_values(content, value):
    assert verifier._contains_meaningful_value(content, value)


def test_verifier_ignores_superseded_values_in_supporting_data():
    assert not verifier._contains_meaningful_value(
        "Current value is modern.\n[Supporting data]\nOld value: legacy", "legacy"
    )
