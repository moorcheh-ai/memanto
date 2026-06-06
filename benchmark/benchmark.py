import asyncio
import time
from typing import List, Dict
import json
import os
from memanto import Memanto
from memanto.agents.memory_agent import MemoryAgent
from memanto.memories.memory import Memory


class BenchmarkSuite:
    """Benchmark suite for comparing Memanto with other memory frameworks"""
    
    def __init__(self):
        self.memanto_client = None
        self.competitor_client = None
        
    def setup_memanto(self):
        """Initialize Memanto client for benchmarking"""
        # Initialize Memanto
        self.memanto_client = Memanto()
        return self.memanto_client
    
    def setup_competitor(self, framework: str = "mem0"):
        """Initialize competitor memory framework for benchmarking"""
        if framework.lower() == "mem0":
            # Setup for Mem0 comparison
            try:
                from mem0 import Mem0
                self.competitor_client = Mem0()
            except ImportError:
                print("Mem0 not installed. Please install it with: pip install mem0-python")
                return None
        elif framework.lower() == "zep":
            # Setup for Zep/Graphiti comparison
            try:
                from zep import ZepClient
                self.competitor_client = ZepClient()
            except ImportError:
                print("Zep not installed. Please install it with: pip install zep-python")
                return None
        else:
            raise ValueError(f"Unsupported competitor framework: {framework}")
        
        return self.competitor_client
    
    def generate_benchmark_data(self, num_samples: int = 100) -> List[Dict]:
        """Generate synthetic conversation data for benchmarking"""
        # In a real implementation, this would be replaced with actual conversation data
        samples = []
        for i in range(num_samples):
            samples.append({
                "id": f"sample_{i}",
                "user_message": f"This is user message {i}",
                "assistant_message": f"This is assistant response {i}",
                "context": f"Context information for sample {i}"
            })
        return samples
    
    async def benchmark_memory_operations(self, framework_name: str, client, samples: List[Dict]):
        """Run memory operations benchmark"""
        results = {
            "framework": framework_name,
            "total_samples": len(samples),
            "remember_timings": [],
            "recall_timings": [],
            "memory_footprint": [],
            "accuracy_scores": []
        }
        
        for sample in samples:
            # Measure remember operation
            start_time = time.time()
            if hasattr(client, 'remember'):
                await client.remember(sample["user_message"], sample["assistant_message"])
            end_time = time.time()
            results["remember_timings"].append(end_time - start_time)
            
            # Measure recall operation
            start_time = time.time()
            if hasattr(client, 'recall'):
                await client.recall(sample["user_message"])
            end_time = time.time()
            results["recall_timings"].append(end_time - start_time)
            
        return results
    
    def run_benchmark(self, competitor_framework: str = "mem0", num_samples: int = 100):
        """Run the full benchmark suite"""
        print(f"Running benchmark: Memanto vs {competitor_framework}")
        
        # Setup clients
        self.setup_memanto()
        self.setup_competitor(competitor_framework)
        
        # Generate test data
        samples = self.generate_benchmark_data(num_samples)
        
        # Run benchmarks
        memanto_results = asyncio.run(self.benchmark_memory_operations("Memanto", self.memanto_client, samples))
        
        if self.competitor_client:
            competitor_results = asyncio.run(self.benchmark_memory_operations(competitor_framework, self.competitor_client, samples))
        else:
            competitor_results = None
            
        # Compare results
        comparison = {
            "memanto": memanto_results,
            competitor_framework: competitor_results
        }
        
        return comparison
        
    def generate_report(self, results: Dict) -> str:
        """Generate a markdown report from benchmark results"""
        report = "# Memanto Benchmark Report\n\n"
        report += "## Results Summary\n\n"
        
        for framework, data in results.items():
            if data is None:
                continue
                
            report += f"### {framework.upper()} Results\n"
            report += f"- Total Samples: {data['total_samples']}\n"
            report += f"- Average Remember Time: {sum(data['remember_timings'])/len(data['remember_timings']):.4f}s\n"
            report += f"- Average Recall Time: {sum(data['recall_timings'])/len(data['recall_timings']):.4f}s\n"
            report += f"- Memory Footprint: {sum(data['memory_footprint']) if data['memory_footprint'] else 'N/A'}\n"
            report += f"- Accuracy: {sum(data['accuracy_scores'])/len(data['accuracy_scores'])*100:.1f}%\n\n"
        
        return report


if __name__ == "__main__":
    # Example usage
    suite = BenchmarkSuite()
    results = suite.run_benchmark("mem0")
    print(suite.generate_report(results))