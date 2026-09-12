# ruff: noqa: E402

import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(EXAMPLE_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from generate_demo import DEMO_THREADS, generate_database  # noqa: E402
from langgraph_checkpoint_to_okf import (
    convert_database,
    extract_records,
    load_latest_checkpoints,
)  # noqa: E402
from validate_roundtrip import validate  # noqa: E402

from memanto.cli.migrate.mappers import map_okf  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402


@pytest.fixture
def workspace(request: pytest.FixtureRequest):
    parent = REPO_ROOT / ".adapter-test-output"
    root = parent / f"{request.node.name}-{uuid4().hex}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)
    try:
        parent.rmdir()
    except OSError:
        pass


def test_actual_langgraph_database_converts_to_importable_okf(workspace: Path):
    database = generate_database(workspace / "source.sqlite")
    output, checkpoints, records = convert_database(
        database,
        workspace / "bundle",
        excluded_channels={"event"},
    )

    assert {item.thread_id for item in checkpoints} == set(DEMO_THREADS)
    assert records
    assert {"event", "fact", "preference", "decision"} <= {
        item.memory_type for item in records
    }

    exported = load_okf_bundle(output)
    mapped = map_okf(exported)
    assert len(mapped) == len(records)
    assert all(row["source"] == "tool" for row in mapped)
    assert all(row["provenance"] == "imported" for row in mapped)
    assert any(
        row["type"] == "preference" and "window" in row["content"] for row in mapped
    )


def test_latest_checkpoint_preserves_corrected_structured_preference(workspace: Path):
    database = generate_database(workspace / "source.sqlite")
    checkpoint = load_latest_checkpoints(database, thread_ids=["mira-travel"])[0]

    assert checkpoint.channel_values["preferences"]["flight_seat"] == "window"
    records = extract_records([checkpoint], excluded_channels={"event", "messages"})
    preference_text = "\n".join(
        record.content for record in records if record.memory_type == "preference"
    )
    assert "window" in preference_text
    assert "aisle" not in preference_text


def test_thread_filter_and_golden_recall_parity(workspace: Path):
    database = generate_database(workspace / "source.sqlite")
    output, checkpoints, _ = convert_database(
        database,
        workspace / "bundle",
        excluded_channels={"event"},
    )

    work_only = load_latest_checkpoints(database, thread_ids=["mira-work"])
    assert [item.thread_id for item in work_only] == ["mira-work"]

    report = validate(database, output)
    assert report["passed"] == report["total"]
    assert report["recall_parity"] == 1.0


def test_nonempty_output_is_never_overwritten(workspace: Path):
    database = generate_database(workspace / "source.sqlite")
    output = workspace / "bundle"
    convert_database(database, output, excluded_channels={"event"})

    try:
        convert_database(database, output, excluded_channels={"event"})
    except FileExistsError as exc:
        assert "never overwritten" in str(exc)
    else:
        raise AssertionError("conversion unexpectedly overwrote an existing bundle")
