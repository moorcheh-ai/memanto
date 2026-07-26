"""Tests for memanto.app.utils.ids (Finding 2 in #1438).

The canonical `is_valid_memory_id` is now the single source of truth.
Safe-deletion paths must use the same check as everywhere else, so a
memory ID can't pass one gate and fail another.
"""

import pytest

from memanto.app.utils.ids import generate_memory_id, is_valid_memory_id


class TestIsValidMemoryId:
    def test_generated_ids_are_valid(self):
        # The ID generator should always produce IDs that pass validation.
        for _ in range(50):
            mid = generate_memory_id()
            assert is_valid_memory_id(mid), f"generated id {mid!r} failed validation"

    def test_ids_with_underscore_are_valid(self):
        assert is_valid_memory_id("mem_abc123")
        assert is_valid_memory_id("any_thing_here")

    def test_ids_without_underscore_are_invalid(self):
        # `abc-123` previously passed deletion validation but failed the
        # general check. After the fix both reject it.
        assert not is_valid_memory_id("abc-123")
        assert not is_valid_memory_id("abcdef")

    def test_short_ids_are_invalid(self):
        assert not is_valid_memory_id("a_b")
        assert not is_valid_memory_id("")
        assert not is_valid_memory_id(None)  # type: ignore[arg-type]


class TestSafeDeletionUsesCanonicalValidator:
    """The legacy safe_deletion module previously had its own private
    `_is_valid_memory_id` whose rules diverged from the canonical one.
    After the fix it must import from `memanto.app.utils.ids`, so the
    two paths cannot disagree."""

    def test_safe_deletion_imports_canonical(self):
        import memanto.app.legacy.safe_deletion as sd
        # `is_valid_memory_id` should be re-exported from the ids module
        # rather than defined locally.
        from memanto.app.utils.ids import is_valid_memory_id as canonical
        assert sd.is_valid_memory_id is canonical

    def test_safe_deletion_no_longer_defines_private_validator(self):
        import memanto.app.legacy.safe_deletion as sd
        assert not hasattr(sd.SafeDeletion, "_is_valid_memory_id")
