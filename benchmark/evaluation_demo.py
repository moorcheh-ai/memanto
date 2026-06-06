"""
Evaluation demo showing Memanto vs other frameworks in action.
This demonstrates the core tension of 2026 agent infrastructure: 
Accuracy vs. Resource Footprint.
"""

import time
from memanto import MemantoClient


def main():
    # Initialize frameworks
    memanto = MemantoClient()
    
    # Simulate memory operations
    test_data = [
        {"id": 1, "content": "User's favorite color is blue", "query": "What is the user's favorite color?"},
        {"id": 2, "content": "User lives in San Francisco", "query": "Where does the user live?"},
        # Add more test data as needed
    ]
    
    # Run evaluation
    results = {}
    
    # Example for Memanto
    print("Evaluating Memanto...")
    start_time = time.time()
    for data in test_data:
        memanto.remember(data["content"])
    remember_time = time.time() - start_time
    
    # Simulate recall evaluation
    queries = [data["query"] for data in test_data]
    answers = []
    start_time = time.time()
    for query in queries:
        answer = memanto.recall(query)
        answers.append(answer)
    recall_time = time.time() - start_time
    
    results['memanto'] = {
        'remember_time': remember_time,
        'recall_time': recall_time,
        'answers': answers
    }
    
    # Here you would repeat for other frameworks (Mem0, Zep, etc.)
    # ...
    
    # Print results
    print("Benchmark Results:")
    for framework, data in results.items():
        print(f"{framework}: {data}")


if __name__ == "__main__":
    main()