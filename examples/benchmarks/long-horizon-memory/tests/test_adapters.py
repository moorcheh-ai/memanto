from __future__ import annotations

import unittest
from unittest.mock import patch

from long_horizon.adapters import _is_transient_error, _retry_transient, _safe_id


class AdapterTests(unittest.TestCase):
    def test_safe_id_preserves_uniqueness_when_truncated(self) -> None:
        first = _safe_id("long-horizon-" + ("a" * 80) + "-seed-7")
        second = _safe_id("long-horizon-" + ("a" * 80) + "-seed-19")

        self.assertEqual(len(first), 48)
        self.assertEqual(len(second), 48)
        self.assertNotEqual(first, second)

    def test_transient_retry_eventually_succeeds(self) -> None:
        attempts = 0

        def flaky_operation() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("Server disconnected without sending a response")
            return "ok"

        with patch("long_horizon.adapters.time.sleep") as sleep:
            self.assertEqual(
                _retry_transient(flaky_operation, attempts=3),
                "ok",
            )
        self.assertEqual(attempts, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.0, 2.0])

    def test_non_transient_error_is_not_retried(self) -> None:
        attempts = 0

        def invalid_operation() -> None:
            nonlocal attempts
            attempts += 1
            raise ValueError("invalid API key")

        with self.assertRaisesRegex(ValueError, "invalid API key"):
            _retry_transient(invalid_operation)
        self.assertEqual(attempts, 1)

    def test_nested_timeout_is_recognized(self) -> None:
        try:
            try:
                raise TimeoutError("TLS handshake timed out")
            except TimeoutError as exc:
                raise RuntimeError("request failed") from exc
        except RuntimeError as exc:
            self.assertTrue(_is_transient_error(exc))

    def test_certificate_error_is_not_transient(self) -> None:
        error = RuntimeError("Network or request error: certificate verify failed")
        self.assertFalse(_is_transient_error(error))


if __name__ == "__main__":
    unittest.main()
