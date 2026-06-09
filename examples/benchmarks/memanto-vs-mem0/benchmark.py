import os
import time
import json
import asyncio
from dotenv import load_dotenv
from memanto import MemantoClient # Hypothetical based on repo structure
from mem0 import Memory # Standard Mem0 API
from evaluator import MemoryEvaluator

load_dotenv()

async def run_memanto_test(client, dataset):
    results = []
    total_tokens = 0
    total_latency = 0
    
    for session in dataset:
        start_time = time.time()
        # Simulate session turns
        for turn in session['turns']:
            if 'query' not in session:
                await client.add(turn['content'])
        
        if 'query' in session:
            response = await client.search(session['query'])
            latency = time.time() - start_time
            
            # Mock token counting (usually provided by LLM API)
            tokens = len(response) // 4 
            
            results.append({
                "query": session['query'],
                "expected": session['expected_answer'],
                "actual": response,
                "latency": latency,
                "tokens": tokens
            })
            total_latency += latency
            total_tokens += tokens
            
    return results, total_tokens, total_latency / len(results) if results else 0

async def run_mem0_test(mem0, dataset):
    results = []
    total_tokens = 0
    total_latency = 0
    
    for session in dataset:
        start_time = time.time()
        for turn in session['turns']:
            if 'query' not in session:
                mem0.add(turn['content'])
        
        if 'query' in session:
            response = mem0.search(session['query'])
            latency = time.time() - start_time
            tokens = len(str(response)) // 4
            
            results.append({
                "query": session['query'],
                "expected": session['expected_answer'],
                "actual": response,
                "latency": latency,
                "tokens": tokens
            })
            total_latency += latency
            total_tokens += tokens
            
    return results, total_tokens, total_latency / len(results) if results else 0

async def main():
    with open('dataset.json', 'r') as f:
        dataset = json.load(f)
    
    evaluator = MemoryEvaluator()
    
    # Setup clients
    try:
        memanto = MemantoClient(api_key=os.getenv("MOORCHEH_API_KEY"))
        mem0 = Memory()
        
        print("Running Memanto tests...")
        m_res, m_tokens, m_lat = await run_memanto_test(memanto, dataset)
        
        print("Running Mem0 tests...")
        z_res, z_tokens, z_lat = await run_mem0_test(mem0, dataset)
        
        # Evaluation
        m_score = sum([evaluator.evaluate(r['query'], r['expected'], r['actual'])['score'] for r in m_res]) / len(m_res)
        z_score = sum([evaluator.evaluate(r['query'], r['expected'], r['actual'])['score'] for r in z_res]) / len(z_res)
        
        final_results = {
            "Memanto": {"accuracy": m_score, "avg_latency": m_lat, "total_tokens": m_tokens},
            "Mem0": {"accuracy": z_score, "avg_latency": z_lat, "total_tokens": z_tokens}
        }
        
        with open('results.json', 'w') as f:
            json.dump(final_results, f, indent=2)
            
        print("Benchmark complete. Results saved to results.json")
        
    except Exception as e:
        print(f"Error during benchmark: {e}")
        print("Make sure MOORCHEH_API_KEY is set in .env")

if __name__ == "__main__":
    asyncio.run(main())
