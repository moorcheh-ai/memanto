import pytest
from adversarial_memory.dataset import Probe
from adversarial_memory.scoring import paired_bootstrap_ci, percentile, score_probe


def probe():
    return Probe(
        probe_id="p",
        tenant="tenant-0",
        session=1,
        query="status",
        expected_marker="STATE_TENANT-0_00_V1",
        stale_markers=("STATE_TENANT-0_00_V0",),
        poison_markers=("POISON_TENANT-0_S1",),
        foreign_markers=("STATE_TENANT-1_00_V1",),
    )


def test_score_reports_rank_and_all_exposure_classes():
    result = score_probe(
        probe(),
        [
            "stale STATE_TENANT-0_00_V0 and POISON_TENANT-0_S1",
            "current STATE_TENANT-0_00_V1 plus STATE_TENANT-1_00_V1",
        ],
    )

    assert result.hit is True
    assert result.reciprocal_rank == 0.5
    assert result.stale_exposure is True
    assert result.poison_exposure is True
    assert result.foreign_exposure is True
    assert result.retrieved_tokens > 0


def test_score_handles_empty_retrieval():
    result = score_probe(probe(), [])
    assert result.hit is False
    assert result.reciprocal_rank == 0.0
    assert result.retrieved_tokens == 0


def test_percentile_and_paired_bootstrap_are_deterministic():
    assert percentile([1.0, 2.0, 3.0, 4.0], 95) == pytest.approx(3.85)
    first = paired_bootstrap_ci([1, 2, 3], [0, 1, 2], seed=4, samples=500)
    second = paired_bootstrap_ci([1, 2, 3], [0, 1, 2], seed=4, samples=500)
    assert first == second == (1, 1, 1)
