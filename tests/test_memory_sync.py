from pathlib import Path


def test_direct_sync_refreshes_cached_export_before_copy(tmp_path, monkeypatch):
    from memanto.cli.client.direct_client import DirectClient

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cache_dir = tmp_path / ".memanto" / "exports"
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / "agent-1_memory.md"
    cache_path.write_text("# MEMORY\n\n### stale memory\n", encoding="utf-8")

    client = DirectClient.__new__(DirectClient)
    export_calls = []

    def fresh_export(*, agent_id, limit_per_type):
        export_calls.append((agent_id, limit_per_type))
        cache_path.write_text(
            "# MEMORY\n\n### current memory\n\n### newer memory\n",
            encoding="utf-8",
        )
        return {
            "output_path": str(cache_path),
            "total_memories": 2,
            "per_type_counts": {"learning": 2},
        }

    monkeypatch.setattr(client, "export_memory_md", fresh_export)

    project_dir = tmp_path / "project"
    result = client.sync_memory_to_project(
        agent_id="agent-1",
        project_dir=str(project_dir),
        limit_per_type=7,
    )

    target = project_dir / "MEMORY.md"
    assert export_calls == [("agent-1", 7)]
    assert target.read_text(encoding="utf-8") == cache_path.read_text(encoding="utf-8")
    assert "current memory" in target.read_text(encoding="utf-8")
    assert "stale memory" not in target.read_text(encoding="utf-8")
    assert result == {
        "output_path": str(target.resolve()),
        "total_memories": 2,
        "source": "fresh",
    }


def test_sdk_sync_reports_fresh_source_after_refresh(tmp_path, monkeypatch):
    from memanto.cli.client.sdk_client import SdkClient

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cache_dir = tmp_path / ".memanto" / "exports"
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / "agent-1_memory.md"

    client = SdkClient.__new__(SdkClient)

    def fresh_export(*, agent_id, limit_per_type):
        assert agent_id == "agent-1"
        assert limit_per_type == 3
        cache_path.write_text(
            "# MEMORY\n\n### current memory\n\n### formatting heading\n",
            encoding="utf-8",
        )
        return {"output_path": str(cache_path), "total_memories": 1}

    monkeypatch.setattr(client, "export_memory_md", fresh_export)

    result = client.sync_memory_to_project(
        agent_id="agent-1",
        project_dir=str(tmp_path / "project"),
        limit_per_type=3,
    )

    assert result["source"] == "fresh"
    assert result["total_memories"] == 1
    assert (tmp_path / "project" / "MEMORY.md").exists()
