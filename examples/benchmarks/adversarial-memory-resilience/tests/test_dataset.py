from adversarial_memory.dataset import generate_scenario, marker


def test_scenario_is_deterministic_and_balanced():
    first = generate_scenario(seed=7, tenants=3, incidents=2, revisions=3)
    second = generate_scenario(seed=7, tenants=3, incidents=2, revisions=3)

    assert first == second
    assert len(first.events) == 3 * 3 * (2 + 1 + 2)
    assert len(first.probes) == 3 * 3 * 2


def test_final_probe_tracks_current_stale_poison_and_foreign_markers():
    scenario = generate_scenario(seed=1, tenants=2, incidents=1, revisions=2)
    probe = scenario.probes[-1]

    assert probe.expected_marker == marker("tenant-1", 0, 1)
    assert probe.stale_markers == (marker("tenant-1", 0, 0),)
    assert len(probe.poison_markers) == 2
    assert marker("tenant-0", 0, 1) in probe.foreign_markers
    assert "POISON_TENANT-0_S1" in probe.foreign_markers


def test_scenario_rejects_invalid_dimensions():
    for kwargs in (
        {"tenants": 1},
        {"incidents": 0},
        {"revisions": 1},
        {"revisions": 5},
    ):
        try:
            generate_scenario(seed=0, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {kwargs}")
