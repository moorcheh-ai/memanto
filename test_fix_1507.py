from memory import Memory, SUCCESSFUL_UPLOAD_STATUSES


def test_failed_update_raises_memory_error():
    mem = Memory()
    try:
        mem.update(status="failed")
    except MemoryError:
        pass
    else:
        raise AssertionError("MemoryError was not raised for status='failed'")

    try:
        mem.update(status="")
    except MemoryError:
        pass
    else:
        raise AssertionError("MemoryError was not raised for status=''")

    try:
        mem.update(status=None)
    except MemoryError:
        pass
    else:
        raise AssertionError("MemoryError was not raised for status=None")

    valid_status = SUCCESSFUL_UPLOAD_STATUSES[0]
    try:
        mem.update(status=valid_status)
    except MemoryError:
        raise AssertionError(f"MemoryError was raised for valid status='{valid_status}'")

+ Thought: 415ms
