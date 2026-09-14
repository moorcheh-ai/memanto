"""
Tests for the ChatGPT -> OKF migration adapter example
(examples/migrations/chatgpt/chatgpt_to_okf.py).

The adapter is a standalone stdlib-only script, so it is loaded via
importlib rather than a package import. The round-trip tests prove the
generated bundle is consumed by the *shipped* Memanto OKF pipeline
(``load_okf_bundle`` + ``map_okf``) — the same code path
``memanto migrate okf`` runs.
"""

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

_EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "migrations" / "chatgpt"


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, _EXAMPLE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass annotation resolution can find it.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load_module("chatgpt_to_okf")
sample = _load_module("make_sample_export")


@pytest.fixture(scope="module")
def conversations():
    return sample.build_conversations()


@pytest.fixture(scope="module")
def extracted(conversations):
    return adapter.extract_memories(conversations)


class TestExtraction:
    def test_extracts_bio_writes_and_skips_tool_acks(self, extracted):
        memories, stats = extracted

        assert stats.bio_writes == 9
        texts = [m.text for m in memories]
        assert not any("Model set context updated" in t for t in texts)
        assert any("Meridian Robotics" in t for t in texts)

    def test_deduplicates_snapshot_against_bio_writes(self, extracted):
        memories, stats = extracted

        # 9 bio + 6 snapshot + 4 custom-instruction blocks = 19 raw sightings;
        # 4 snapshot repeats + 2 repeated custom-instruction blocks collapse.
        assert stats.duplicates_skipped == 6
        assert len(memories) == 13
        normalized = [adapter._normalize(m.text) for m in memories]
        assert len(normalized) == len(set(normalized))

    def test_snapshot_only_entries_survive(self, extracted):
        memories, _ = extracted
        texts = [m.text for m in memories]

        assert any("shellfish" in t for t in texts)
        assert any("Clint Yeastwood" in t for t in texts)

    def test_custom_instructions_become_instruction_memories(self, extracted):
        memories, stats = extracted

        instructions = [m for m in memories if m.kind == "custom_instructions"]
        assert stats.custom_instruction_blocks == 4  # repeated in 2 conversations
        assert len(instructions) == 2  # deduplicated to one about-user + one style
        assert all(m.memory_type == "instruction" for m in instructions)

    def test_bio_write_beats_snapshot_echo_on_duplicates(self, extracted):
        memories, _ = extracted

        # The espresso memory appears both as an original bio write (exact
        # timestamp, source conversation) and as a day-granular snapshot echo.
        # The higher-fidelity bio version must win.
        espresso = next(m for m in memories if "espresso" in m.text)
        assert espresso.kind == "bio"
        assert espresso.created_at == "2026-04-08T08:10:30+00:00"
        assert espresso.conversation_id == "conv-007"

    def test_timestamps_are_iso_utc(self, extracted):
        memories, _ = extracted

        meridian = next(m for m in memories if "Meridian" in m.text)
        assert meridian.created_at == "2025-11-04T09:12:45+00:00"

    def test_type_inference_heuristics(self):
        infer = adapter.infer_memory_type

        assert infer("User prefers dark roast coffee.") == "preference"
        assert infer("User is training for the Chicago Marathon.") == "goal"
        assert infer("User's partner is named Sam.") == "relationship"
        assert infer("User decided to port drivers to Rust.") == "decision"
        assert infer("User moved to Seattle in March.") == "event"
        assert infer("User is allergic to shellfish.") == "fact"


class TestInputFormats:
    def test_zip_and_directory_inputs_are_equivalent(self, tmp_path, conversations):
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        payload = json.dumps(conversations)
        (export_dir / "conversations.json").write_text(payload, encoding="utf-8")

        zip_path = tmp_path / "chatgpt-export.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("nested/conversations.json", payload)

        from_dir = adapter.load_conversations(export_dir)
        from_zip = adapter.load_conversations(zip_path)
        assert from_dir == from_zip

    def test_missing_conversations_json_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            adapter.load_conversations(tmp_path)

    def test_non_array_export_raises(self, tmp_path):
        bad = tmp_path / "conversations.json"
        bad.write_text('{"not": "an array"}', encoding="utf-8")
        with pytest.raises(ValueError):
            adapter.load_conversations(bad)


class TestOkfRoundTrip:
    """The generated bundle must be consumable by the shipped CLI pipeline."""

    @pytest.fixture(scope="class")
    def bundle(self, tmp_path_factory):
        conversations = sample.build_conversations()
        memories, _ = adapter.extract_memories(conversations)
        out = tmp_path_factory.mktemp("okf") / "bundle"
        adapter.write_okf_bundle(memories, out)
        return out, memories

    def test_loader_reads_every_memory(self, bundle):
        out, memories = bundle
        export = load_okf_bundle(out)
        assert len(export["memories"]) == len(memories) == 13

    def test_mapper_produces_import_ready_rows(self, bundle):
        out, memories = bundle
        rows = map_okf(load_okf_bundle(out))

        assert len(rows) == 13
        assert all(row["source"] == "chatgpt" for row in rows)
        assert all(row["provenance"] == "imported" for row in rows)
        expected_types = sorted(m.memory_type for m in memories)
        assert sorted(row["type"] for row in rows) == expected_types

    def test_source_refs_and_timestamps_survive_round_trip(self, bundle):
        out, _ = bundle
        rows = map_okf(load_okf_bundle(out))

        meridian = next(r for r in rows if "Meridian" in r["content"])
        assert meridian["source_ref"] == "chatgpt:conv-001:m-001c"
        assert meridian["created_at"].isoformat() == "2025-11-04T09:12:45+00:00"

    def test_conversation_title_preserved_in_supporting_data(self, bundle):
        out, _ = bundle
        rows = map_okf(load_okf_bundle(out))

        meridian = next(r for r in rows if "Meridian" in r["content"])
        assert "[Supporting data]" in meridian["content"]
        assert "Debugging an I2C driver" in meridian["content"]

    def test_stacked_split_mode_round_trips(self, tmp_path):
        conversations = sample.build_conversations()
        memories, _ = adapter.extract_memories(conversations)
        out = tmp_path / "stacked"
        adapter.write_okf_bundle(memories, out, split="type")

        rows = map_okf(load_okf_bundle(out))
        assert len(rows) == 13

    def test_index_files_are_skipped_on_import(self, bundle):
        out, _ = bundle
        index_files = list(out.rglob("index.md"))
        assert index_files  # bundle is navigable...
        rows = map_okf(load_okf_bundle(out))
        assert len(rows) == 13  # ...but indexes never become memories


class TestCommittedSampleArtifacts:
    """The committed sample bundle must stay in sync with the generator."""

    def test_committed_sample_bundle_is_valid(self):
        bundle_dir = _EXAMPLE_DIR / "sample_output" / "okf-bundle"
        rows = map_okf(load_okf_bundle(bundle_dir))
        assert len(rows) == 13

    def test_committed_sample_export_matches_generator(self):
        committed = json.loads(
            (
                _EXAMPLE_DIR
                / "sample_data"
                / "chatgpt-export-sample"
                / "conversations.json"
            ).read_text(encoding="utf-8")
        )
        assert committed == sample.build_conversations()
