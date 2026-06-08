# memanto_benchmark.py
# FastAPI service for benchmarking agentic memory backends.
# Provides endpoints to run insert/retrieve benchmarks and report latency & memory usage.

import time
import json
import random
import statistics
import psutil
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.testclient import TestClient
import uvicorn

# Optional Redis import
try:
    import redis
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False

# --------------------------
# Memory Backend Abstraction
# --------------------------

class MemoryBackend(ABC):
    @abstractmethod
    def put(self, key: str, value: Any) -> None:
        pass

    @abstractmethod
    def get(self, key: str) -> Any:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class DictMemory(MemoryBackend):
    def __init__(self):
        self.store: Dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        self.store[key] = value

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def close(self) -> None:
        self.store.clear()


class FileMemory(MemoryBackend):
    def __init__(self, path: str = "benchmark_shelve.db"):
        import shelve
        self.path = path
        self.shelve = shelve.open(path, writeback=True)

    def put(self, key: str, value: Any) -> None:
        self.shelve[key] = value

    def get(self, key: str) -> Any:
        return self.shelve.get(key)

    def close(self) -> None:
        self.shelve.close()
        if os.path.exists(self.path):
            os.remove(self.path)


class RedisMemory(MemoryBackend):
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        if not REDIS_AVAILABLE:
            raise RuntimeError("Redis package not installed")
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def put(self, key: str, value: Any) -> None:
        self.client.set(key, json.dumps(value))

    def get(self, key: str) -> Any:
        raw = self.client.get(key)
        return json.loads(raw) if raw is not None else None

    def close(self) -> None:
        self.client.close()


# --------------------------
# Benchmark Logic
# --------------------------

def run_backend(backend: MemoryBackend, num_items: int, num_queries: int) -> Dict[str, Any]:
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / 1024 / 1024  # MB

    # Insert phase
    insert_latencies = []
    for i in range(num_items):
        key = f"key_{i}"
        value = {"data": f"value_{i}", "idx": i}
        start = time.perf_counter()
        backend.put(key, value)
        insert_latencies.append((time.perf_counter() - start) * 1000)  # ms

    # Query phase (random subset)
    query_latencies = []
    keys = [f"key_{i}" for i in range(num_items)]
    for _ in range(num_queries):
        key = random.choice(keys)
        start = time.perf_counter()
        backend.get(key)
        query_latencies.append((time.perf_counter() - start) * 1000)  # ms

    mem_after = process.memory_info().rss / 1024 / 1024  # MB
    backend.close()

    def stats(latencies: List[float]) -> Dict[str, float]:
        if not latencies:
            return {"min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0}
        sorted_lat = sorted(latencies)
        return {
            "min": sorted_lat[0],
            "max": sorted_lat[-1],
            "mean": statistics.mean(latencies),
            "p50": sorted_lat[int(len(sorted_lat) * 0.5)],
            "p95": sorted_lat[int(len(sorted_lat) * 0.95)],
        }

    return {
        "memory_mb_before": round(mem_before, 2),
        "memory_mb_after": round(mem_after, 2),
        "memory_mb_delta": round(mem_after - mem_before, 2),
        "insert_latency_ms": stats(insert_latencies),
        "query_latency_ms": stats(query_latencies),
        "num_items": num_items,
        "num_queries": num_queries,
    }


# --------------------------
# FastAPI App
# --------------------------

app = FastAPI(title="Memanto Memory Benchmark")


class BenchmarkRequest(BaseModel):
    backend: str  # "dict", "file", or "redis"
    num_items: int = 1000
    num_queries: int = 500
    redis_host: Optional[str] = "localhost"
    redis_port: Optional[int] = 6379
    redis_db: Optional[int] = 0


@app.post("/benchmark")
def benchmark(req: BenchmarkRequest):
    if req.backend == "dict":
        backend = DictMemory()
    elif req.backend == "file":
        backend = FileMemory()
    elif req.backend == "redis":
        if not REDIS_AVAILABLE:
            raise HTTPException(status_code=500, detail="Redis not available")
        backend = RedisMemory(host=req.redis_host, port=req.redis_port, db=req.redis_db)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown backend: {req.backend}")

    try:
        result = run_backend(backend, req.num_items, req.num_queries)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {
        "message": "Memanto Memory Benchmark API. POST /benchmark with JSON config.",
        "example": {
            "backend": "dict",
            "num_items": 1000,
            "num_queries": 500
        }
    }


# --------------------------
# Simple Test / Example Usage
# --------------------------

if __name__ == "__main__":
    # Run a quick in-process benchmark and print results
    print("Running dict backend benchmark (1000 inserts, 500 queries)...")
    b = DictMemory()
    res = run_backend(b, 1000, 500)
    print(json.dumps(res, indent=2))

    # Also start the server if invoked with argument "serve