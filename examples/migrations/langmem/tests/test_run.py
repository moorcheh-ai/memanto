from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from langgraph.store.memory import InMemoryStore
from langmem import create_manage_memory_tool

SPEC = importlib.util.spec_from_file_location(
    "langmem_run", Path(__file__).parents[1] / "run.py"
)
assert SPEC and SPEC.loader
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


def test_pagination_and_overlapping_namespaces() -> None:
    store = InMemoryStore()
    for number in range(1001):
        store.put(("parent", "child"), str(number), {"content": f"record {number}"})
    exported = run.export_records(store, [("parent",), ("parent", "child")])
    assert exported["count"] == 1001
    assert len({run.identity(row) for row in exported["memories"]}) == 1001


def test_namespace_identity_and_exact_snapshot_survive_mapping(tmp_path: Path) -> None:
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    records = [
        {
            "namespace": ns,
            "key": "same",
            "value": {
                "content": "Unicode हिन्दी café ✓ <!-- okf-entry -->\n" + run.MARKER,
                "metadata": {"nested": [False, None, "x" * 240]},
            },
        }
        for ns in (["a/b", "c"], ["a", "b/c"])
    ]
    run.to_okf({"memories": records}, tmp_path / "bundle")
    rows = map_okf(load_okf_bundle(tmp_path / "bundle"))
    assert len({row["source_ref"] for row in rows}) == 2
    assert sorted(run.decode_snapshots(rows), key=run.identity) == sorted(
        records, key=run.identity
    )
    rows[0]["content"] = rows[0]["content"].split(run.MARKER)[0]
    with pytest.raises(ValueError, match="snapshot"):
        run.decode_snapshots(rows)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"memories": "wrong"},
        {"memories": [None]},
        {"memories": [{"namespace": [], "key": "k", "value": {}}]},
        {"memories": [{"namespace": ["a"], "key": "k", "value": {"x": float("nan")}}]},
        {"memories": [], "count": 1},
    ],
)
def test_malformed_export_is_rejected(value: object, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run.to_okf(value, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_duplicate_and_oversized_records_are_rejected(tmp_path: Path) -> None:
    record = {"namespace": ["a"], "key": "k", "value": {"content": "x"}}
    with pytest.raises(ValueError, match="duplicate"):
        run.to_okf({"memories": [record, record]}, tmp_path / "duplicate")
    record["value"]["content"] = "x" * 9000
    with pytest.raises(ValueError, match="size"):
        run.to_okf({"memories": [record]}, tmp_path / "large")
    assert list(tmp_path.iterdir()) == []


def test_file_import_does_not_generate_unrelated_source_or_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "memories": [
                    {
                        "namespace": ["external"],
                        "key": "id",
                        "value": {"content": "Real export"},
                    }
                ]
            }
        )
    )

    def no_source() -> None:
        raise AssertionError("file input must not construct synthetic memories")

    monkeypatch.setattr(run, "build_source", no_source)
    output = tmp_path / "run"
    monkeypatch.setattr(
        run.sys,
        "argv",
        ["run", "--source-export", str(source), "--output", str(output)],
    )
    run.main()
    report = json.loads((output / "run-report.json").read_text())
    assert report["source_retrieval"] == []
    assert report["summary"]["source_count"] == 1
    assert (
        report["summary"]["source_bytes"]
        == (output / "langmem_export.json").stat().st_size
    )
    before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):
        run.main()
    assert before == {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}


def test_export_preserves_namespaces_and_update_history() -> None:
    store = InMemoryStore()
    ns = ("memories", "synthetic/team")
    tool = create_manage_memory_tool(namespace=ns, store=store)
    created = tool.invoke({"content": "Unicode café preference", "action": "create"})
    key = created.rsplit(" ", 1)[-1]
    tool.invoke({"content": "Unicode café preference ✓", "action": "update", "id": key})
    exported = run.export_records(store, [ns])
    assert exported["count"] == 1
    assert exported["memories"][0]["namespace"] == list(ns)
    assert exported["memories"][0]["value"]["content"].endswith("✓")


def test_source_scenario_deletes_record() -> None:
    store, scopes = run.build_source()
    exported = run.export_records(store, scopes)
    assert exported["count"] == 4
    assert all("UTF-8 JSONL" not in r["value"]["content"] for r in exported["memories"])


def test_okf_round_trip_keeps_source_snapshot_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    store = InMemoryStore()
    ns = ("memories", "synthetic-user")
    create_manage_memory_tool(namespace=ns, store=store).invoke(
        {"content": "Delimiter <!-- okf-entry --> remains text", "action": "create"}
    )
    export = run.export_records(store, [ns])
    bundle = tmp_path / "bundle"
    result = run.to_okf(export, bundle)
    assert result["mapped_count"] == 1
    docs = [p for p in (bundle / "memories/fact").glob("*.md") if p.name != "index.md"]
    assert len(docs) == 1
    assert "[LangMem source record base64]" in docs[0].read_text()
    try:
        run.to_okf(export, bundle)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing output must not be overwritten")


def test_live_snapshot_comparison_reports_exact_differences() -> None:
    live_spec = importlib.util.spec_from_file_location(
        "langmem_live_workflow", Path(__file__).parents[1] / "live_workflow.py"
    )
    assert live_spec and live_spec.loader
    live = importlib.util.module_from_spec(live_spec)
    live_spec.loader.exec_module(live)
    source = [
        {"namespace": ["n"], "key": "same", "value": {"content": "one"}},
        {"namespace": ["n"], "key": "missing", "value": {"content": "two"}},
    ]
    target = [
        {"namespace": ["n"], "key": "same", "value": {"content": "changed"}},
        {"namespace": ["n"], "key": "extra", "value": {"content": "three"}},
    ]
    result = live.compare_records(source, target)
    assert result["exact_match"] is False
    assert result["missing"] == [run.identity(source[1])]
    assert result["unexpected"] == [run.identity(target[1])]
    assert result["changed"] == [run.identity(source[0])]
    with pytest.raises(ValueError, match="duplicate"):
        live.compare_records(source, source + [source[0]])
    client = type("Client", (), {})()
    live.bind_client_session(client, "demo", "token", "demo")
    assert client.agent_id == "demo"
    assert client.session_token == "token"
    with pytest.raises(RuntimeError, match="active agent"):
        live.bind_client_session(client, "other", "token", "demo")


def test_live_reads_actual_shipped_okf_bundle(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "langmem_live_workflow", Path(__file__).parents[1] / "live_workflow.py"
    )
    assert spec and spec.loader
    live = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(live)
    records = [{"namespace": ["n"], "key": "one", "value": {"content": "fact"}}]
    run.to_okf({"memories": records}, tmp_path / "bundle")
    actual = live.decode_snapshots(
        live.map_okf(live.load_okf_bundle(tmp_path / "bundle"))
    )
    assert live.compare_records(records, actual)["exact_match"]


def test_default_output_does_not_collide_with_committed_sample(
    tmp_path: Path, monkeypatch
) -> None:
    sample = tmp_path / "artifacts" / "sample-run"
    sample.mkdir(parents=True)
    marker = sample / "preserve.txt"
    marker.write_text("existing sample")
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "memories": [
                    {"namespace": ["n"], "key": "k", "value": {"content": "fact"}}
                ]
            }
        )
    )
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run.sys, "argv", ["run.py", "--source-export", str(source)])
    run.main()
    assert marker.read_text() == "existing sample"
    generated = list((tmp_path / "artifacts").glob("run-*"))
    assert len(generated) == 1
    assert (generated[0] / "cli-dry-run.txt").is_file()
