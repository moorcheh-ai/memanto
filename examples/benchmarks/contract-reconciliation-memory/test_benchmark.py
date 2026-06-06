import importlib.util
import pathlib
import sys
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("run_benchmark.py")
SPEC = importlib.util.spec_from_file_location("contract_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


class ContractBenchmarkTest(unittest.TestCase):
    def test_active_ledger_suppresses_old_prices_and_secrets(self) -> None:
        result = benchmark.evaluate_backend(
            benchmark.ActiveContractLedger(),
            benchmark.build_events(),
            benchmark.build_probes(),
        )
        summary = result.summary()

        self.assertEqual(summary["accuracy"], 1.0)
        self.assertEqual(summary["stale_conflict_rate"], 0.0)
        self.assertEqual(summary["secret_leak_rate"], 0.0)

    def test_append_only_baseline_exposes_stale_and_secret_risk(self) -> None:
        result = benchmark.evaluate_backend(
            benchmark.AppendOnlyLog(),
            benchmark.build_events(),
            benchmark.build_probes(),
        )
        summary = result.summary()

        self.assertGreater(summary["stale_conflict_rate"], 0.0)
        self.assertGreater(summary["secret_leak_rate"], 0.0)

    def test_recent_window_forgets_some_active_commitments(self) -> None:
        result = benchmark.evaluate_backend(
            benchmark.RecentWindowLog(window=5),
            benchmark.build_events(),
            benchmark.build_probes(),
        )
        summary = result.summary()

        self.assertLess(summary["accuracy"], 1.0)
        self.assertEqual(summary["secret_leak_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
