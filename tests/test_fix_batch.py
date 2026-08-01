""" Unit tests for bug fix batch: memory validation & constants. """

from memanto.app.utils.ids import generate_id, generate_memory_id, is_valid_memory_id


def test_is_valid_memory_id_accepts_valid_ids():
    assert is_valid_memory_id("mem_abc123") is True
    assert is_valid_memory_id("mem_1") is True  # 6 chars, has underscore
    assert is_valid_memory_id("user-pref_fact") is True
    assert is_valid_memory_id("a_b_c_d") is True  # 7 chars with underscores


def test_is_valid_memory_id_rejects_too_short():
    assert is_valid_memory_id("a_b") is False    # only 3 chars
    assert is_valid_memory_id("ab_c") is False    # 4 chars


def test_is_valid_memory_id_rejects_no_underscore():
    assert is_valid_memory_id("abcde") is False   # 5 chars, no underscore


def test_is_valid_memory_id_rejects_path_traversal():
    """The old validation accepted this pattern - new one must reject."""
    assert is_valid_memory_id("../../../etc/passwd") is False
    assert is_valid_memory_id("..%2F..%2Fetc") is False


def test_is_valid_memory_id_rejects_empty_and_none():
    assert is_valid_memory_id("") is False
    assert is_valid_memory_id(None) is False  # type: ignore


def test_is_valid_memory_id_rejects_special_chars():
    assert is_valid_memory_id("mem@123") is False
    assert is_valid_memory_id("mem 123") is False
    assert is_valid_memory_id("mem.123") is False
    assert is_valid_memory_id("mem/123") is False
    assert is_valid_memory_id("mem\\123") is False


def test_is_valid_memory_id_rejects_unicode():
    assert is_valid_memory_id("mem_测试") is False


def test_generate_id_length():
    """Just ensure gen functions still work."""
    i = generate_id()
    assert len(i) == 12
    assert isinstance(i, str)


def test_generate_memory_id_has_underscore():
    mid = generate_memory_id()
    assert "_" in mid
    assert is_valid_memory_id(mid) is True

