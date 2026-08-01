import concurrent.futures
import time
from memanto.app.legacy.idempotency import IdempotencyStore

def test_idempotency_store_concurrency():
    store = IdempotencyStore()
    key = "idem_test_concurrency_key"
    
    def worker(worker_id):
        record = store.get_record(key)
        if record is None:
            time.sleep(0.001)
            store.store_record(key, f"mem_{worker_id}", {"status": "ok", "worker": worker_id})
            return f"stored_{worker_id}"
        return "already_exists"

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(worker, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    stats = store.get_stats()
    assert stats["total_records"] == 1
    assert store.get_record(key) is not None
