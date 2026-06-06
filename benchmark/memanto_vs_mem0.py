"""
Benchmarking suite for Memanto vs Mem0
"""

import time
import asyncio
import numpy as np
from memanto import Memanto
from mem0 import Memory
import openai
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration for Mem0
config = {
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o",
            "temperature": 0,
        }
    },
    "vector_db": {
        "provider": "qdrant",
        "config": {
            "host": "localhost",
            "port": 6333,
        }
    },
    "embedding": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small"
        }
    }
}


class BenchmarkRunner:
    def __init__(self):
        self.memanto_client = Memanto()
        self.mem0_client = Memory.from_config(config)
        
    def benchmark_memanto(self, data):
        """Benchmark Memanto performance"""
        # Memory storage test
        start_time = time.time()
        self.memanto_client.remember(data)
        store_time = time.time() - start_time
        
        # Recall test
        start_time = time.time()
        memories = self.memanto_client.recall()
        recall_time = time.time() - start_time
        
        # Answer test
        start_time = time.time()
        answer = self.memanto_client.answer("What are the key points from the memories?")
        answer_time = time.time() - start_time
        
        return {
            "store_time": store_time,
            "recall_time": recall_time,
            "answer": answer,
            "answer_time": answer_time
        }
    
    def benchmark_mem0(self, data):
        """Benchmark Mem0 performance"""
        # Add memory test
        start_time = time.time()
        self.mem0_client.add(data)
        store_time = time.time() - start_time
        
        # Get memory test
        start_time = time.time()
        memories = self.mem0_client.get_all()
        recall_time = time.time() - start_time
        
        # Search test
        start_time = time.time()
        search_result = self.mem0_client.search("What are the key points from the memories?")
        search_time = time.time() - start_time
        
        return {
            "store_time": store_time,
            "recall_time": recall_time,
            "search_result": search_result,
            "search_time": search_time
        }
    
    def run_comparison(self, test_data):
        """Run comparison between Memanto and Mem0"""
        print("Running benchmark comparison...")
        
        # Benchmark Memanto
        memanto_results = self.benchmark_memanto(test_data)
        
        # Benchmark Mem0
        mem0_results = self.benchmark_mem0(test_data)
        
        # Print results
        print("\n=== BENCHMARK RESULTS ===")
        print("\nMemanto Results:")
        print(f"Store time: {memanto_results['store_time']:.4f}s")
        print(f"Recall time: {memanto_results['recall_time']:.4f}s")
        print(f"Answer time: {memanto_results['answer_time']:.4f}s")
        print(f"Answer: {memanto_results['answer']}")
        
        print("\nMem0 Results:")
        print(f"Store time: {mem0_results['store_time']:.4f}s")
        print(f"Recall time: {mem0_results['recall_time']:.4f}s")
        print(f"Search time: {mem0_results['search_time']:.4f}s")
        print(f"Search result: {mem0_results['search_result']}")
        
        return {
            "memanto": memanto_results,
            "mem0": mem0_results
        }


if __name__ == "__main__":
    # Sample test data
    test_data = """
    Project Management
    1. Project Initiation: The project started on January 1st, 2024. The main goal is to develop a new AI assistant.
    2. Team Formation: The team consists of 5 members: 2 developers, 1 designer, 1 product manager, and 1 QA engineer.
    3. Technology Stack: The application will be built using Python, FastAPI, and React.
    4. Milestone 1: Complete initial design by February 15th, 2024.
    5. Milestone 2: Complete development by April 1st, 2024.
    6. Milestone 3: Launch beta version by May 1st, 2024.
    7. Budget: Total budget is $100,000 with the following allocation:
       - Development: $50,000
       - Design: $20,000
       - Marketing: $15,000
       - Misc: $15,000
    8. Risks: Potential delays in development due to team member unavailability.
    9. Communication: Weekly standups every Monday at 10 AM.
    10. Success metrics: User satisfaction score above 4.5/5.
    """
    
    runner = BenchmarkRunner()
    results = runner.run_comparison(test_data)