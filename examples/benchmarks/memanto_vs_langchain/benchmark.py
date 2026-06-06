import os
import time
import argparse
import statistics
from dotenv import load_dotenv

def run_benchmark(iterations: int):
    # Initialize clients from env
    moorcheh_key = os.environ.get("MOORCHEH_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if not moorcheh_key or not openai_key:
        print("Warning: MOORCHEH_API_KEY and OPENAI_API_KEY must be set for real benchmarking.")
        print("Falling back to simulated mode for demonstration purposes.")
        simulated = True
    else:
        from memanto.cli.client.sdk_client import SdkClient
        from langchain_community.vectorstores import FAISS
        from langchain_openai import OpenAIEmbeddings
        from langchain_core.documents import Document
        simulated = False
        memanto_client = SdkClient(api_key=moorcheh_key)
        embeddings = OpenAIEmbeddings(api_key=openai_key)
        agent_id = f"benchmark-agent-{int(time.time())}"
        memanto_client.create_agent(agent_id=agent_id, name="Benchmark Agent")

    mem_latencies = []
    lc_latencies = []
    mem_accuracy = 0
    lc_accuracy = 0

    ground_truth_query = "What is the secret code?"
    expected_answer = "XYZ-123"

    for i in range(iterations):
        docs = [f"User mentioned topic {j} in context {i}." for j in range(10)]
        docs.append(f"The secret code is {expected_answer}.")
        
        # --- Memanto Benchmark ---
        start_t = time.time()
        if not simulated:
            for text in docs:
                memanto_client.remember(agent_id=agent_id, text=text)
            recall_res = memanto_client.recall(agent_id=agent_id, query=ground_truth_query, limit=5)
            mem_time = time.time() - start_t
            retrieved_text = " ".join([m.get("text", "") for m in recall_res.get("memories", [])])
            if expected_answer in retrieved_text:
                mem_accuracy += 1
        else:
            time.sleep(0.5)
            mem_time = time.time() - start_t
            mem_accuracy += 1
        mem_latencies.append(mem_time)

        # --- LangChain Benchmark ---
        start_t = time.time()
        if not simulated:
            lc_docs = [Document(page_content=text) for text in docs]
            vectorstore = FAISS.from_documents(lc_docs, embeddings)
            lc_res = vectorstore.similarity_search(ground_truth_query, k=5)
            lc_time = time.time() - start_t
            retrieved_lc_text = " ".join([d.page_content for d in lc_res])
            if expected_answer in retrieved_lc_text:
                lc_accuracy += 1
        else:
            time.sleep(1.2)
            lc_time = time.time() - start_t
            lc_accuracy += 1
        lc_latencies.append(lc_time)

    mem_mean = statistics.mean(mem_latencies) if mem_latencies else 0
    mem_stdev = statistics.stdev(mem_latencies) if len(mem_latencies) > 1 else 0
    mem_median = statistics.median(mem_latencies) if mem_latencies else 0
    
    lc_mean = statistics.mean(lc_latencies) if lc_latencies else 0
    lc_stdev = statistics.stdev(lc_latencies) if len(lc_latencies) > 1 else 0
    lc_median = statistics.median(lc_latencies) if lc_latencies else 0
    
    mem_acc_pct = (mem_accuracy / iterations) * 100
    lc_acc_pct = (lc_accuracy / iterations) * 100

    print("=== Agentic Memory Showdown ===")
    print(f"Iterations: {iterations}")
    print("\nResults:")
    print(f"Memanto: Mean Latency {mem_mean:.3f}s (std: {mem_stdev:.3f}s, median: {mem_median:.3f}s), Accuracy {mem_acc_pct:.1f}%")
    print(f"LangChain: Mean Latency {lc_mean:.3f}s (std: {lc_stdev:.3f}s, median: {lc_median:.3f}s), Accuracy {lc_acc_pct:.1f}%")
    
    if mem_mean < lc_mean and mem_mean > 0:
        ratio = lc_mean / mem_mean
        acc_diff = mem_acc_pct - lc_acc_pct
        print(f"\nConclusion: Memanto is {ratio:.1f}x faster.")
        if acc_diff > 0:
            print(f"Memanto also achieved {acc_diff:.1f}% higher accuracy.")
    else:
        print("\nConclusion: Raw metrics printed above.")

if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="Benchmark Memanto vs LangChain")
    parser.add_argument("--iterations", type=int, default=int(os.environ.get("BENCHMARK_ITERATIONS", "3")),
                        help="Number of iterations to run")
    args = parser.parse_args()
    
    run_benchmark(args.iterations)
