import time
import asyncio
from typing import Dict, List, Tuple
from memanto import MemantoClient

# Mock clients for other memory frameworks
class Mem0Client:
    def __init__(self):
        pass
    
    async def add(self, data: str) -> None:
        # Simulate adding memory with some latency
        await asyncio.sleep(0.01)
    
    async def search(self, query: str) -> List[Dict]:
        # Simulate search with some latency
        await asyncio.sleep(0.05)
        return [{"id": "mem0_result_1", "content": "Mock memory from Mem0", "relevance": 0.9}]

class ZepClient:
    def __init__(self):
        pass
    
    async def add(self, data: str) -> None:
        # Simulate adding memory with some latency
        await asyncio.sleep(0.02)
    
    async def search(self, query: str) -> List[Dict]:
        # Simulate search with some latency
        await asyncio.sleep(0.03)
        return [{"id": "zep_result_1", "content": "Mock memory from Zep", "relevance": 0.85}]

# Benchmarking suite
class MemoryBenchmark:
    def __init__(self):
        self.memanto = MemantoClient()
        self.mem0 = Mem0Client()
        self.zep = ZepClient()
        self.test_data = [
            "User is interested in AI research and machine learning",
            "User prefers Python for data science projects",
            "User has a meeting scheduled for tomorrow at 3 PM",
            "User's favorite programming language is Rust",
0.05)
        ]
    
    async def benchmark_memory_storage(self, client, data: List[str]) -> Dict:
        """Benchmark memory storage performance"""
        start_time = time.time()
        token_count = 0
        
        for item in data:
            await client.add(item)
            token_count += len(item.split())
        
        end_time = time.time()
        latency = end_time - start_time
        
        return {
            "latency": latency,
            "tokens_stored": token_count,
            "throughput": token_count / latency if latency > 0 else 0
        }
    
    async def benchmark_memory_retrieval(self, client, queries: List[str]) -> Dict:
        """Benchmark memory retrieval performance"""
        start_time = time.time()
        results = []
        total_relevance = 0
        
        for query in queries:
            search_results = await client.search(query)
            results.extend(search_results)
            total_relevance += sum(result.get("relevance", 0) for result in search_results)
        
        end_time = time.time()
        latency = end_time - start_time
        avg_relevance = total_relevance / len(results) if results else 0
        
        return {
            "latency": latency,
            "avg_relevance": avg_relevance,
            "results_count": len(results)
        }
    
    async def run_benchmark(self) -> Dict:
        """Run comprehensive benchmark suite"""
        print("Starting Memanto vs Others Benchmark...")
        
        # Test queries for retrieval
        test_queries = [
            "What programming languages does the user prefer?",
            "What are the user's interests?",
            "Does the user have any upcoming meetings?"
        ]
        
        # Benchmark Memanto
        print("\nBenchmarking Memanto...")
        memanto_storage_metrics = await self.benchmark_memory_storage(self.memanto, self.test_data)
        memanto_retrieval_metrics = await self.benchmark_memory_retrieval(self.memanto, test_queries)
        
        # Benchmark Mem0
        print("\nBenchmarking Mem0...")
        mem0_storage_metrics = await self.benchmark_memory_storage(self.mem0, self.test_data)
        mem0_retrieval_metrics = await self.benchmark_memory_retrieval(self.mem0, test_queries)
        
        # Benchmark Zep
        print("\nBenchmarking Zep...")
        zep_storage_metrics = await self.benchmark_memory_storage(self.zep, self.test_data)
        zep_retrieval_metrics = await self.benchmark_retrieval(self.zep, test_queries)
        
        # Compile results
        results = {
            "memanto": {
                "storage": memanto_storage_metrics,
                "retrieval": memanto_retrieval_metrics
            },
            "mem0": {
                "storage": mem0_storage_metrics,
                "retrieval": mem0_retrieval_metrics
            },
            "zep": {
                "storage": zep_storage_metrics,
                "retrieval": zep_retrieval_metrics
            }
        }
        
        return results
    
    def print_results(self, results: Dict) -> None:
        """Print benchmark results in a formatted way"""
        print("\n" + "="*60)
        print("BENCHMARK RESULTS")
        print("="*60)
        
        frameworks = ["memanto", "mem0", "zep"]
        metrics = ["storage", "retrieval"]
        
        for framework in frameworks:
            print(f"\n{framework.upper()} RESULTS:")
            print("-" * 30)
            for metric in metrics:
                data = results[framework][metric]
                print(f"{metric.capitalize()} Metrics:")
                for key, value in data.items():
                    print(f"  {key}: {value}")
        
        print("\n" + "="*60)

# Run the benchmark
if __name__ == "__main__":
    benchmark = MemoryBenchmark()
    results = asyncio.run(benchmark.run_benchmark())
    benchmark.print_results(results)