import os
import time
import uuid
import logging
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Try importing SDKs
try:
    from memanto.cli.client.sdk_client import SdkClient
    MEMANTO_AVAILABLE = True
except ImportError:
    MEMANTO_AVAILABLE = False
    logger.warning("Memanto SDK not found. Please install memanto.")

try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    logger.warning("Mem0 SDK not found. Please run: pip install mem0ai")

class BenchmarkResult:
    def __init__(self, name: str):
        self.name = name
        self.write_latencies: List[float] = []
        self.read_latencies: List[float] = []
        self.tokens_used: int = 0
        self.retrieved_facts: List[str] = []

    def add_write(self, latency: float):
        self.write_latencies.append(latency)

    def add_read(self, latency: float):
        self.read_latencies.append(latency)

    def print_summary(self):
        avg_write = sum(self.write_latencies) / len(self.write_latencies) if self.write_latencies else 0
        avg_read = sum(self.read_latencies) / len(self.read_latencies) if self.read_latencies else 0
        print(f"--- {self.name} Benchmark Summary ---")
        print(f"Total Writes: {len(self.write_latencies)}")
        print(f"Avg Write Latency: {avg_write:.4f}s")
        print(f"Total Reads: {len(self.read_latencies)}")
        print(f"Avg Read Latency: {avg_read:.4f}s")
        print(f"Final Retrieved Preferences:")
        for fact in self.retrieved_facts:
            print(f"  - {fact}")
        print("--------------------------------------\n")


def run_memanto_benchmark(preferences: List[str], query: str, user_id: str) -> BenchmarkResult:
    result = BenchmarkResult("Memanto")
    if not MEMANTO_AVAILABLE:
        logger.error("Skipping Memanto. SDK unavailable.")
        return result

    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        logger.error("Skipping Memanto. MOORCHEH_API_KEY not set.")
        return result

    client = SdkClient(api_key=api_key)
    agent_id = f"bench-memanto-{user_id}"

    # Setup Agent and Session
    try:
        client.create_agent(agent_id=agent_id, pattern="tool", description="Benchmarking Agent")
        client.activate_agent(agent_id=agent_id)
    except Exception as e:
        logger.error(f"Memanto setup error: {e}")
        return result

    # Writes
    for idx, pref in enumerate(preferences):
        start_t = time.time()
        try:
            client.memorize(
                agent_id=agent_id,
                content=pref,
                type="preference",
                title=f"Preference Update {idx}",
                confidence=0.9,
                source="user"
            )
            result.add_write(time.time() - start_t)
        except Exception as e:
            logger.error(f"Memanto Write Error: {e}")
        time.sleep(1) # simulate real user gap

    # Reads
    start_t = time.time()
    try:
        memories = client.recall(agent_id=agent_id, query=query, limit=5, type=["preference"])
        result.add_read(time.time() - start_t)
        
        # SdkClient returns a dict with 'memories'
        facts = [m.get("content", str(m)) for m in memories.get("memories", [])]
        result.retrieved_facts = facts
    except Exception as e:
        logger.error(f"Memanto Read Error: {e}")

    # Cleanup
    try:
        client.delete_agent(agent_id=agent_id)
    except Exception as e:
        logger.warning(f"Failed to cleanup Memanto agent: {e}")

    return result

def run_mem0_benchmark(preferences: List[str], query: str, user_id: str) -> BenchmarkResult:
    result = BenchmarkResult("Mem0")
    if not MEM0_AVAILABLE:
        logger.error("Skipping Mem0. SDK unavailable.")
        return result
    
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("Skipping Mem0. OPENAI_API_KEY not set.")
        return result

    m = Memory()

    # Writes
    for pref in preferences:
        start_t = time.time()
        try:
            m.add(pref, user_id=user_id)
            result.add_write(time.time() - start_t)
        except Exception as e:
            logger.error(f"Mem0 Write Error: {e}")
        time.sleep(1)

    # Reads
    start_t = time.time()
    try:
        memories = m.search(query, user_id=user_id)
        result.add_read(time.time() - start_t)
        
        # Mem0 returns a dict with 'results' or similar
        facts = [mem.get("memory", str(mem)) for mem in memories] if isinstance(memories, list) else []
        result.retrieved_facts = facts
    except Exception as e:
        logger.error(f"Mem0 Read Error: {e}")

    # Cleanup
    try:
        m.delete_all(user_id=user_id)
    except Exception:
        pass

    return result


def main():
    print("=========================================================")
    print("🐜 The Great Agentic Memory Showdown: Memanto vs. Mem0")
    print("Scenario: The Shifting Persona & Temporal Tracking Test")
    print("=========================================================\n")

    # Sequence of shifting preferences
    preferences = [
        "I absolutely love Italian food, especially Pasta.",
        "Actually, I've been eating too much carbs. I prefer Mexican food now.",
        "I'm on a strict Keto diet currently. No carbs at all. I love Steak and Salad."
    ]
    query = "What food does the user like right now?"
    user_id = f"user-{uuid.uuid4().hex[:6]}"

    print(f"Sequence of inputs over time:")
    for p in preferences:
        print(f" - {p}")
    print(f"\nQuerying: '{query}'\n")

    # Run benchmarks
    res_memanto = run_memanto_benchmark(preferences, query, user_id)
    res_mem0 = run_mem0_benchmark(preferences, query, user_id)

    # Output summaries
    res_memanto.print_summary()
    res_mem0.print_summary()

if __name__ == "__main__":
    main()
