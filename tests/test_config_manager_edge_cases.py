"""Tests for CLI config manager edge cases."""

import pytest
from memanto.cli.config.manager import _normalize_duplicated_api_key


class TestNormalizeDuplicatedApiKey:
    """Tests for _normalize_duplicated_api_key key-deduplication logic."""

    def test_genuinely_doubled_long_key_is_halved(self):
        """A 64-char key that repeats its first 32 chars is correctly halved."""
        half = "sk-abc123def456ghi789jkl012mno34"
        doubled = half + half  # 64 chars
        assert _normalize_duplicated_api_key(doubled) == half

    def test_short_key_repeated_half_not_halved(self):
        """A key shorter than 64 chars is never halved, even if its halves match."""
        # 32-char key that happens to have identical halves — must be preserved
        key = "ab" * 16  # 32 chars, both halves are "ab"*8
        assert _normalize_duplicated_api_key(key) == key

    def test_typical_openai_style_key_not_halved(self):
        """A real-world-length key (51 chars) is preserved as-is."""
        key = "sk-proj-" + "a" * 43  # 51 chars total
        assert _normalize_duplicated_api_key(key) == key

    def test_odd_length_key_not_halved(self):
        """An odd-length key is never considered for deduplication."""
        key = "x" * 65  # 65 chars, odd length
        assert _normalize_duplicated_api_key(key) == key

    def test_short_duplicated_key_preserved(self):
        """A 16-char key that looks duplicated must not be halved."""
        key = "deadbeefdeadbeef"  # 16 chars, halves match
        assert _normalize_duplicated_api_key(key) == key

    def test_stripped_whitespace(self):
        """Leading/trailing whitespace is stripped before any check."""
        half = "k" * 32
        doubled = f"  {half}{half}\t"
        assert _normalize_duplicated_api_key(doubled) == half

    def test_minimum_threshold_64_chars(self):
        """Keys at exactly 64 chars are eligible for deduplication."""
        # 62 chars: just below threshold, preserved
        key62 = "a" * 62
        assert _normalize_duplicated_api_key(key62) == key62
        # 64 chars: threshold, eligible for dedup
        half32 = "b" * 32
        key64 = half32 + half32
        assert _normalize_duplicated_api_key(key64) == half32
