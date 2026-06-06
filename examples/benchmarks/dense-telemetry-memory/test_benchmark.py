import unittest

from .run_benchmark import (
    ActiveTelemetryDigest,
    AppendOnlyLog,
    EVENTS,
    QUERIES,
    SESSION_ORDER,
    degradation_curve,
    events_through_session,
    run,
)


class DenseTelemetryMemoryBenchmarkTests(unittest.TestCase):
    def test_active_digest_beats_append_only_accuracy(self) -> None:
        report = run()
        results = {item["backend"]: item for item in report["results"]}

        self.assertGreater(
            results["active_telemetry_digest"]["accuracy"],
            results["append_only_log"]["accuracy"],
        )
        self.assertEqual(results["active_telemetry_digest"]["stale_conflict_rate"], 0)
        self.assertGreater(
            results["active_telemetry_digest"]["signal_noise_ratio"],
            results["append_only_log"]["signal_noise_ratio"],
        )

    def test_active_digest_suppresses_contraindicated_antibiotic(self) -> None:
        backend = ActiveTelemetryDigest(EVENTS)
        context = backend.retrieve(
            "What antibiotic regimen is currently active and safe given documented allergies?"
        )

        self.assertIn("levofloxacin", context.lower())
        self.assertNotIn("ceftriaxone", context.lower())

    def test_active_digest_retains_durable_allergy(self) -> None:
        late_events = events_through_session("shift-07")
        backend = ActiveTelemetryDigest(late_events)
        context = backend.retrieve(
            "What is the patient's severe allergy and what must be avoided?"
        )

        self.assertIn("penicillin", context.lower())
        self.assertIn("anaphylaxis", context.lower())

    def test_windowed_log_forgets_early_allergy_at_mid_course(self) -> None:
        """Recent-window memory misses admission allergy before discharge re-states it."""
        from .run_benchmark import WindowedRecentLog

        mid_events = events_through_session("shift-04")
        backend = WindowedRecentLog(mid_events, window_size=4)
        context = backend.retrieve(
            "What is the patient's severe allergy and what must be avoided?"
        )

        self.assertNotIn("penicillin", context.lower())
        self.assertNotIn("anaphylaxis", context.lower())

    def test_cross_session_degradation_curve_length(self) -> None:
        curve = degradation_curve(ActiveTelemetryDigest, QUERIES)
        self.assertEqual(len(curve), len(SESSION_ORDER))

    def test_all_queries_have_expected_answers(self) -> None:
        for query in QUERIES:
            self.assertTrue(query.must_have, query.question)


if __name__ == "__main__":
    unittest.main()
