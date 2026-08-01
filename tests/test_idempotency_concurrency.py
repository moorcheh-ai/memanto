import concurrent.futures
import threading

from memanto.app.legacy.idempotency import IdempotencyStore


def test_idempotency_store_concurrency():
    """Verify that exactly one of 50 concurrent workers wins the reservation."""
    store = IdempotencyStore()
    key = "idem_test_concurrency_key"
    barrier = threading.Barrier(50)

    def worker(worker_id):
        barrier.wait()  # Synchronize all workers to maximise race window
        is_owner, record = store.reserve_or_get(
            key, f"mem_{worker_id}", {"status": "ok", "worker": worker_id}
        )
        return is_owner

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(worker, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Exactly 1 worker must obtain exclusive ownership (True)
    owners_count = sum(1 for is_owner in results if is_owner)
    assert owners_count == 1

    stats = store.get_stats()
    assert stats["total_records"] == 1
    assert store.get_record(key) is not None
