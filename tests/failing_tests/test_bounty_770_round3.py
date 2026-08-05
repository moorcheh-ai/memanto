"""Bounty #770 round 3 — reproducible regression tests for 3 more bugs.

Run:  python -m pytest tests/failing_tests/test_bounty_770_round3.py -v
      (or:  python tests/failing_tests/test_bounty_770_round3.py)

Bugs covered:
1. HIGH: conflict-report read paths hardcode ~/.memanto/conflicts while the
   generator uses get_data_dir()/conflicts (regression introduced by the
   round-2 fix). With MEMANTO_BACKEND=on-prem (data dir
   ~/.memanto/on-prem), list/resolve can never see generated reports.
   Affects DirectClient (2 sites), SdkClient (2 sites), and the UI router
   (1 site).
2. MED:  PATCH /api/ui/config with a non-numeric recall.limit /
   recall.min_similarity raises an uncaught ValueError -> HTTP 500
   instead of a 400, unlike every other config section which maps
   ValueError to 400.
3. MED:  OkfExportService defaults to ~/.memanto/exports while
   MemoryExportService defaults to get_data_dir()/exports; on-prem
   exports land in different directories depending on which exporter is
   used.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# 1. Conflict-report read paths must honor get_data_dir()
# ---------------------------------------------------------------------------
def test_direct_client_conflict_paths_use_get_data_dir():
    """list_conflicts / resolve_conflict must read the same directory the
    generator writes to (get_data_dir()/conflicts), not hardcoded
    ~/.memanto/conflicts."""
    import inspect

    from memanto.cli.client.direct_client import DirectClient

    for method_name in ("list_conflicts", "resolve_conflict"):
        src = inspect.getsource(getattr(DirectClient, method_name))
        assert "Path.home()" not in src, (
            f"DirectClient.{method_name} hardcodes ~/.memanto instead of "
            f"get_data_dir()/conflicts"
        )


def test_sdk_client_conflict_paths_use_get_data_dir():
    """SdkClient mirrors the same contract."""
    import inspect

    from memanto.cli.client.sdk_client import SdkClient

    for method_name in ("list_conflicts", "resolve_conflict"):
        src = inspect.getsource(getattr(SdkClient, method_name))
        assert "Path.home()" not in src, (
            f"SdkClient.{method_name} hardcodes ~/.memanto instead of "
            f"get_data_dir()/conflicts"
        )


def test_ui_conflict_scans_use_get_data_dir():
    """The UI conflict-scan reader must point at the same directory as the
    generator."""
    import inspect

    from memanto.app.ui.routes import ui_router

    src = inspect.getsource(ui_router.list_conflict_scans)
    assert "Path.home()" not in src, (
        "ui_router.list_conflict_scans hardcodes ~/.memanto/conflicts"
    )


# ---------------------------------------------------------------------------
# 2. Non-numeric recall config must be a 400, not an uncaught 500
# ---------------------------------------------------------------------------
def test_update_ui_config_recall_rejects_bad_limit():
    """A non-numeric recall.limit must produce a clean 400 (ValueError
    mapped), not bubble up as an unhandled exception -> 500."""
    import inspect

    from memanto.app.ui.routes import ui_router

    src = inspect.getsource(ui_router.update_ui_config)
    # The recall branch must be wrapped so ValueError -> 400 like every
    # other section (session, schedule_time, answer).
    assert "except ValueError" in src.split('if "recall" in updates')[1], (
        "update_ui_config recall branch does not map ValueError to 400"
    )


def test_update_ui_config_recall_rejects_bad_min_similarity():
    """Same contract for recall.min_similarity."""
    import inspect

    from memanto.app.ui.routes import ui_router

    src = inspect.getsource(ui_router.update_ui_config)
    recall_part = src.split('if "recall" in updates')[1]
    # int(rec["limit"]) / float(rec["min_similarity"]) must be inside the
    # guarded region, not evaluated bare.
    assert "try:" in recall_part and "except ValueError" in recall_part


# ---------------------------------------------------------------------------
# 3. Export services must agree on the data directory
# ---------------------------------------------------------------------------
def test_okf_export_default_dir_matches_memory_export():
    """OkfExportService and MemoryExportService must share the same default
    exports root (get_data_dir()/exports) so on-prem data stays under
    ~/.memanto/on-prem like everything else."""
    import inspect

    from memanto.app.services import memory_export_service, okf_export_service

    mem_src = inspect.getsource(memory_export_service.MemoryExportService.__init__)
    okf_src = inspect.getsource(okf_export_service.OkfExportService.__init__)
    assert "get_data_dir() / \"exports\"" in mem_src
    assert "get_data_dir() / \"exports\"" in okf_src, (
        "OkfExportService defaults to ~/.memanto/exports instead of "
        "get_data_dir()/exports — on-prem exports split across two roots"
    )


if __name__ == "__main__":
    tests = [
        test_direct_client_conflict_paths_use_get_data_dir,
        test_sdk_client_conflict_paths_use_get_data_dir,
        test_ui_conflict_scans_use_get_data_dir,
        test_update_ui_config_recall_rejects_bad_limit,
        test_update_ui_config_recall_rejects_bad_min_similarity,
        test_okf_export_default_dir_matches_memory_export,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")
    sys.exit(1 if failures else 0)
