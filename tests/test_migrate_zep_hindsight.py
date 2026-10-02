"""Tests for the Zep and Hindsight migrations (exporters, mappers, CLI, UI)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from memanto.app.core import MemoryRecord
from memanto.cli.analyze import hindsight_export, zep_export
from memanto.cli.main import app
from memanto.cli.migrate.mappers import map_hindsight, map_zep
from memanto.cli.migrate.runner import run_migration, source_count

runner = CliRunner()

PAST = "2025-01-01T00:00:00Z"
FUTURE = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
# Mapped-row keys SdkClient.batch_remember passes through to MemoryRecord.
MEMORY_RECORD_KEYS = (
    "type",
    "title",
    "content",
    "confidence",
    "tags",
    "source",
    "provenance",
    "source_ref",
    "created_at",
    "updated_at",
)


def zep_edge(uuid="e1", fact="Alice works at Acme", **extra):
    return {
        "uuid": uuid,
        "name": "WORKS_AT",
        "fact": fact,
        "created_at": "2025-06-01T10:00:00Z",
        "valid_at": "2025-05-01T00:00:00Z",
        "source_node_name": "Alice",
        "target_node_name": "Acme",
        "episodes": ["ep-1", "ep-2"],
        "export_user_id": "alice",
        **extra,
    }


def hindsight_unit(uid="u1", text="Alice prefers dark mode", **extra):
    return {
        "id": uid,
        "text": text,
        "context": "settings chat",
        "fact_type": "world",
        "state": "valid",
        "mentioned_at": "2025-07-01T09:00:00Z",
        "entities": "Alice",
        "tags": ["ui"],
        "proof_count": 3,
        "export_bank_id": "bank-a",
        **extra,
    }


# --------------------------------------------------------------------------
# Mappers
# --------------------------------------------------------------------------


def test_map_zep_keeps_provenance_and_tags_user():
    [row] = map_zep({"memories": [zep_edge()]})

    assert row["source"] == "zep"
    assert row["source_ref"] == "e1"
    assert row["provenance"] == "imported"
    assert row["type"] is None  # auto-classified by the parser
    assert row["tags"] == ["user=alice", "works_at"]
    # valid_at (when the fact became true) beats ingest time.
    assert row["created_at"] == datetime(2025, 5, 1, tzinfo=timezone.utc)
    assert "- From: Alice" in row["content"]
    assert "- Source episodes: 2" in row["content"]


def test_map_zep_skips_superseded_and_ended_facts():
    export = {
        "memories": [
            zep_edge("expired", expired_at=PAST),
            zep_edge("ended", invalid_at=PAST),
            zep_edge("ends-later", invalid_at=FUTURE),
            zep_edge("empty", fact="  "),
            zep_edge("current"),
        ]
    }
    rows = map_zep(export)

    assert [r["source_ref"] for r in rows] == ["ends-later", "current"]
    assert "- Valid until:" in rows[0]["content"]
    assert source_count("zep", export) == 5


def test_map_hindsight_maps_fact_types_and_skips_invalidated():
    export = {
        "memories": [
            hindsight_unit("w", fact_type="world"),
            hindsight_unit("x", fact_type="experience", occurred_start=PAST),
            hindsight_unit("o", fact_type="observation"),
            hindsight_unit("unknown", fact_type="something-new"),
            hindsight_unit("gone", state="invalidated"),
        ]
    }
    rows = map_hindsight(export)

    assert [(r["source_ref"], r["type"]) for r in rows] == [
        ("w", "fact"),
        ("x", "event"),
        ("o", "observation"),
        ("unknown", None),
    ]
    # occurred_start (when it happened) beats mentioned_at.
    assert rows[1]["created_at"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert rows[0]["created_at"] == datetime(2025, 7, 1, 9, tzinfo=timezone.utc)
    assert rows[0]["tags"] == ["bank=bank-a", "ui"]
    # Titles drop Hindsight's " | When: ... | Involving: ..." suffix; content keeps it.
    [row] = map_hindsight(
        {
            "memories": [
                hindsight_unit(
                    text="Alice joined Acme | When: 2025-03-02 | Involving: Alice"
                )
            ]
        }
    )
    assert row["title"] == "Alice joined Acme"
    assert row["content"].startswith("Alice joined Acme | When: 2025-03-02")
    assert "- Times observed: 3" in rows[0]["content"]
    assert "- Context: settings chat" in rows[0]["content"]


def test_run_migration_writes_zep_rows_in_batches():
    client = MagicMock()
    client.batch_remember.side_effect = lambda agent_id, memories: {
        "total_submitted": len(memories),
        "successful": len(memories),
        "failed": 0,
        "rejected": 0,
        "results": [{"id": f"m{i}"} for i in range(len(memories))],
    }
    export = {"memories": [zep_edge(f"e{i}", fact=f"fact {i}") for i in range(150)]}

    summary, _rows = run_migration(
        provider="zep", export=export, client=client, agent_id="a", dry_run=False
    )

    assert (summary.imported, summary.failed, summary.batches) == (150, 0, 2)


def test_unstorable_tags_move_to_footer_instead_of_failing_the_batch():
    # One out-of-bounds tag list fails MemoryRecord validation for the whole
    # write batch, so every mapped row must stay within the tag limits.
    long_tag = "x" * 80
    unit = hindsight_unit(
        tags=["project,billing", long_tag, *(f"t{i}" for i in range(25))]
    )
    edge = zep_edge(export_user_id="u" * 70)

    [h_row] = map_hindsight({"memories": [unit]})
    [z_row] = map_zep({"memories": [edge]})

    assert len(h_row["tags"]) == 20
    assert h_row["tags"][:2] == ["bank=bank-a", "t0"]
    assert "project,billing" not in h_row["tags"] and long_tag not in h_row["tags"]
    assert "- Extra tags: project,billing, " in h_row["content"]
    assert z_row["tags"] == ["works_at"]
    assert f"- Extra tags: user={'u' * 70}" in z_row["content"]

    for row in (h_row, z_row):
        MemoryRecord(
            agent_id="a",
            actor_id="a",
            **{k: row[k] for k in MEMORY_RECORD_KEYS},
        )


# --------------------------------------------------------------------------
# Exporters (HTTP mocked at the transport layer)
# --------------------------------------------------------------------------


def _mock_client(original, handler):
    """Wrap an exporter's ``_client`` so its real auth/base URL hit *handler*."""

    def factory(*args):
        with original(*args) as real:
            return httpx.Client(
                base_url=real.base_url,
                headers=real.headers,
                transport=httpx.MockTransport(handler),
            )

    return factory


def test_zep_export_paginates_with_next_cursor_header(tmp_path, monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Api-Key z_test"
        if request.url.path == "/api/v2/users-ordered":
            return httpx.Response(
                200, json={"users": [{"user_id": "alice"}], "total_count": 1}
            )
        body = json.loads(request.content)
        seen.append(body)
        if "cursor" not in body:
            return httpx.Response(
                200, json=[zep_edge("e1")], headers={"Zep-Next-Cursor": "c2"}
            )
        return httpx.Response(200, json=[zep_edge("e2")])

    monkeypatch.setattr(
        zep_export,
        "_client",
        _mock_client(zep_export._client, handler),
    )
    path, export = zep_export.run_zep_export("z_test", tmp_path)

    assert seen[1]["cursor"] == "c2"
    assert [e["uuid"] for e in export["memories"]] == ["e1", "e2"]
    assert all(e["export_user_id"] == "alice" for e in export["memories"])
    assert json.loads(path.read_text(encoding="utf-8"))["summary"]["edge_count"] == 2


def test_hindsight_export_uses_bearer_and_self_hosted_url(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer hsk_test"
        assert request.url.host == "localhost" and request.url.port == 8888
        if request.url.path == "/v1/default/banks":
            return httpx.Response(200, json={"banks": [{"bank_id": "b 1"}], "total": 1})
        assert request.url.raw_path.startswith(
            b"/v1/default/banks/b%201/memories/list?"
        )
        offset = int(request.url.params["offset"])
        page = [
            hindsight_unit(f"u{offset + i}")
            for i in range(hindsight_export.PAGE_SIZE if offset == 0 else 3)
        ]
        return httpx.Response(200, json={"items": page, "total": 103})

    monkeypatch.setattr(
        hindsight_export,
        "_client",
        _mock_client(hindsight_export._client, handler),
    )
    _path, export = hindsight_export.run_hindsight_export(
        "hsk_test", tmp_path, base_url="localhost:8888"
    )

    assert export["api_base"] == "http://localhost:8888"
    assert len(export["memories"]) == 103
    assert export["memories"][0]["export_bank_id"] == "b 1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "https://api.hindsight.vectorize.io"),
        ("", "https://api.hindsight.vectorize.io"),
        ("hindsight.example.com/", "https://hindsight.example.com"),
        ("127.0.0.1:8888", "http://127.0.0.1:8888"),
        ("http://box:8888", "http://box:8888"),
    ],
)
def test_hindsight_base_url_normalization(raw, expected):
    assert hindsight_export.normalize_base_url(raw) == expected


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "export"),
    [
        ("zep", {"memories": [zep_edge(), zep_edge("old", invalid_at=PAST)]}),
        (
            "hindsight",
            {"memories": [hindsight_unit(), hindsight_unit("x", state="invalidated")]},
        ),
    ],
)
def test_cli_dry_run_from_file(tmp_path, provider, export):
    export_file = tmp_path / f"{provider}_export.json"
    export_file.write_text(json.dumps(export), encoding="utf-8")

    with patch("memanto.cli.commands.migrate.config_manager") as cfg:
        cfg.get_migrate_dir.return_value = tmp_path
        cfg.get_hindsight_base_url.return_value = None
        result = runner.invoke(
            app, ["migrate", provider, "--file", str(export_file), "--dry-run"]
        )

    assert result.exit_code == 0, result.stdout
    assert "Dry run complete" in result.stdout
    assert "skipped 1" in result.stdout
    # No savings baseline for these providers, so no report is rendered.
    assert not list(tmp_path.glob("*/migrate-report.md"))
    [preview] = list(tmp_path.glob("*/mapped_preview.json"))
    assert len(json.loads(preview.read_text(encoding="utf-8"))) == 1


def test_cli_hindsight_live_export_passes_base_url(tmp_path):
    with (
        patch("memanto.cli.commands.migrate.config_manager") as cfg,
        patch(
            "memanto.cli.commands.migrate._PROVIDER_BUNDLES",
            {"hindsight": {"label": "Hindsight", "exporter": MagicMock()}},
        ) as bundles,
    ):
        cfg.get_migrate_dir.return_value = tmp_path
        cfg.get_hindsight_api_key.return_value = "hsk_saved"
        exporter = bundles["hindsight"]["exporter"]
        exporter.return_value = (tmp_path / "x.json", {"memories": [hindsight_unit()]})

        result = runner.invoke(
            app,
            ["migrate", "hindsight", "--base-url", "localhost:8888", "--dry-run"],
        )

    assert result.exit_code == 0, result.stdout
    assert exporter.call_args.args[0] == "hsk_saved"
    assert exporter.call_args.kwargs["base_url"] == "http://localhost:8888"
    cfg.set_hindsight_base_url.assert_called_once_with("http://localhost:8888")


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------


@pytest.fixture
def ui(tmp_path, monkeypatch):
    from memanto.app.ui.routes import ui_router as mod

    monkeypatch.setattr(mod._config_manager, "get_migrate_dir", lambda p: tmp_path)
    api = FastAPI()
    api.include_router(mod.router)
    api.dependency_overrides[mod._require_local] = lambda: None
    return TestClient(api)


@pytest.mark.parametrize(
    ("provider", "export"),
    [
        ("zep", {"memories": [zep_edge(), zep_edge("old", expired_at=PAST)]}),
        ("hindsight", {"memories": [hindsight_unit()]}),
    ],
)
def test_ui_dry_run_from_file(ui, tmp_path, provider, export):
    export_file = tmp_path / f"{provider}_export.json"
    export_file.write_text(json.dumps(export), encoding="utf-8")

    res = ui.post(
        "/api/ui/migrate/dry-run", json={"provider": provider, "file": str(export_file)}
    )

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["mapped_count"] == 1
    assert data["skipped"] == len(export["memories"]) - 1
    assert data["savings"] == {}


def test_ui_hindsight_live_export_forwards_host(ui, tmp_path):
    exporter = MagicMock(return_value=(tmp_path / "x.json", {"memories": []}))
    with patch("memanto.cli.analyze.hindsight_export.run_hindsight_export", exporter):
        res = ui.post(
            "/api/ui/migrate/dry-run",
            json={
                "provider": "hindsight",
                "api_key": "hsk_test",
                "host": "http://localhost:8888",
            },
        )

    assert res.status_code == 200, res.text
    assert exporter.call_args.kwargs["base_url"] == "http://localhost:8888"
