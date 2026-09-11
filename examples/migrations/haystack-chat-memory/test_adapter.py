import pytest
from adapter import FORMAT, reconstruct, render_session, write_bundle
from haystack.dataclasses import ChatMessage
from source_history import SESSION, populate
from validate import validate

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def snapshot_with(text):
    return {
        "format": FORMAT,
        "sessions": {SESSION: [ChatMessage.from_user(text).to_dict()]},
    }


def test_real_store_complete_history_and_scoped_roundtrip(tmp_path):
    store, snapshot = populate()
    assert store.count_messages(SESSION) == 15
    assert snapshot["sessions"][SESSION][0]["role"] == "system"
    assert (
        snapshot["sessions"][SESSION][0]["meta"]["chat_message_id"]
        == snapshot["sessions"]["other-user"][0]["meta"]["chat_message_id"]
    )
    output = tmp_path / "bundle"
    assert write_bundle(snapshot, SESSION, output)["okf_memories"] == 15
    rows = map_okf(load_okf_bundle(output))
    report = validate(snapshot, SESSION, [row["content"] for row in rows])
    assert report["exact_structured_parity"]
    store.delete_messages(SESSION)
    assert store.count_messages(SESSION) == 0
    assert store.count_messages("other-user") == 1
    assert len(rows) == 15
    other = render_session(snapshot, "other-user")
    assert set(other) - {"index.md"} != set(render_session(snapshot, SESSION)) - {
        "index.md"
    }


@pytest.mark.parametrize(
    "text",
    [
        "<!-- okf-entry -->",
        "---\ntype: index\n---",
        "<!-- haystack-source-json -->\n```json\n{}\n```\n<!-- /haystack-source-json -->",
        "```\n````\nこんにちは <tag> café [link](https://example.com)",
    ],
)
def test_literal_delimiters_preserve_single_complete_message(tmp_path, text):
    snapshot = snapshot_with(text)
    write_bundle(snapshot, SESSION, tmp_path / "bundle")
    rows = map_okf(load_okf_bundle(tmp_path / "bundle"))
    assert len(rows) == 1
    assert (
        reconstruct(rows[0]["content"])["message"] == snapshot["sessions"][SESSION][0]
    )


def test_oversize_rejected_before_partial_output(tmp_path):
    snapshot = snapshot_with("small")
    snapshot["sessions"][SESSION].append(ChatMessage.from_user("x" * 9000).to_dict())
    with pytest.raises(ValueError, match="8000-character"):
        write_bundle(snapshot, SESSION, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_existing_evidence_not_overwritten(tmp_path):
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "marker").write_text("keep")
    with pytest.raises(FileExistsError):
        write_bundle(snapshot_with("small"), SESSION, output)
    assert (output / "marker").read_text() == "keep"


def test_mapper_truncation_fails_before_publish(tmp_path, monkeypatch):
    import adapter

    monkeypatch.setattr(adapter, "map_okf", lambda _export: [{"content": "truncated"}])
    with pytest.raises(ValueError, match="intact"):
        write_bundle(snapshot_with("small"), SESSION, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_missing_scope_and_unsupported_content_rejected(tmp_path):
    with pytest.raises(ValueError, match="absent"):
        write_bundle(snapshot_with("small"), "not-selected", tmp_path / "bundle")
    snapshot = snapshot_with("small")
    snapshot["sessions"][SESSION][0]["content"] = [{"unknown_modality": "bad"}]
    with pytest.raises(ValueError, match="supported"):
        write_bundle(snapshot, SESSION, tmp_path / "bundle")


def test_duplicate_and_tampered_destination_detected(tmp_path):
    _, snapshot = populate()
    write_bundle(snapshot, SESSION, tmp_path / "bundle")
    contents = [row["content"] for row in map_okf(load_okf_bundle(tmp_path / "bundle"))]
    with pytest.raises(ValueError, match="positions"):
        validate(snapshot, SESSION, contents + contents[:1])
    damaged = contents.copy()
    damaged[1] = damaged[1].replace("USD", "GBP")
    with pytest.raises(ValueError, match="changed"):
        validate(snapshot, SESSION, damaged)


def test_cli_bootstrap_scopes_home_before_import(tmp_path, monkeypatch):
    """Sentinel module proves the real bootstrap scopes imports and restores home."""
    import os
    import runpy
    import sys
    import types
    from pathlib import Path

    demo = tmp_path / "private"
    original_home = Path.home()
    observed = {}
    fake_main = types.ModuleType("memanto.cli.main")

    def app():
        observed["home"] = Path.home()
        observed["key"] = os.environ["MOORCHEH_API_KEY"]

    fake_main.app = app
    monkeypatch.setitem(sys.modules, "memanto.cli.main", fake_main)
    monkeypatch.setenv("HAYSTACK_MEMANTO_CONFIG", str(demo))
    monkeypatch.setenv("MOORCHEH_API_KEY", "explicit-demo-sentinel")
    runpy.run_path(str(Path(__file__).with_name("cli.py")), run_name="__main__")
    assert observed == {"home": demo, "key": "explicit-demo-sentinel"}
    assert Path.home() == original_home


def test_generated_backend_config_uses_actual_memanto_schema(tmp_path):
    from run_showcase import configure_run

    from memanto.cli.config.manager import ConfigManager

    configure_run(tmp_path, "on-prem", "http://127.0.0.1:18080")
    config = ConfigManager(tmp_path / "private" / ".memanto")
    assert config.get_backend().value == "on-prem"
    assert config.get_onprem_state()["url"] == "http://127.0.0.1:18080"


def test_demo_without_destination_fails_before_writing(tmp_path, monkeypatch):
    import sys

    from run_showcase import main

    output = tmp_path / "should-not-exist"
    monkeypatch.setattr(sys, "argv", ["run_showcase.py", str(output), "--demo"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output.exists()
