#!/usr/bin/env python3
import os
import sys
import time
import json
import argparse
import numpy as np
import tiktoken
from openai import OpenAI
from tabulate import tabulate

# Ensure API keys are present
def check_env_vars():
    missing = []
    if not os.environ.get("MOORCHEH_API_KEY"):
        missing.append("MOORCHEH_API_KEY")
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        print("Please set them before running the benchmark.")
        sys.exit(1)

# Token counter
def count_tokens(text, model="gpt-4o-mini"):
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # Fallback simple estimation
        return int(len(text.split()) * 1.3)

# Simple Vector Memory Baseline (Passive Vector DB representation)
class SimpleVectorMemory:
    def __init__(self, openai_client):
        self.client = openai_client
        self.memories = {}  # user_id -> list of dicts with text and embedding

    def _get_embedding(self, text):
        response = self.client.embeddings.create(
            input=[text],
            model="text-embedding-3-small"
        )
        return response.data[0].embedding

    def add(self, text, user_id):
        emb = self._get_embedding(text)
        if user_id not in self.memories:
            self.memories[user_id] = []
        self.memories[user_id].append({"text": text, "embedding": emb})

    def search(self, query, user_id):
        if user_id not in self.memories or not self.memories[user_id]:
            return []
        query_emb = self._get_embedding(query)
        
        results = []
        for mem in self.memories[user_id]:
            emb = mem["embedding"]
            sim = np.dot(query_emb, emb) / (np.linalg.norm(query_emb) * np.linalg.norm(emb))
            results.append((sim, mem["text"]))
        
        results.sort(key=lambda x: x[0], reverse=True)
        # Return top 2 most similar memories
        return [text for sim, text in results[:2]]

# Dataset definition
BENCHMARK_DATASET = {
    "Scenario A: Context-Overhead & Latency Sprint": {
        "description": "Dense technical logs with a specific error detail buried inside.",
        "ingest_steps": [
            {"text": "2026-03-15 08:00:01 INFO [system] Startup sequence initiated.", "user_id": "sys_admin"},
            {"text": "2026-03-15 08:05:23 DEBUG [database] Connection pool size set to 50.", "user_id": "sys_admin"},
            {"text": "2026-03-15 08:12:45 WARN [auth] Failed login attempt from IP 192.168.1.105.", "user_id": "sys_admin"},
            {"text": "2026-03-15 08:15:30 ERROR [payment] Transaction failed for tx_99281. Error: Gateway timeout (code: 504).", "user_id": "sys_admin"},
            {"text": "2026-03-15 08:20:12 INFO [system] Scheduled backup completed successfully.", "user_id": "sys_admin"}
        ],
        "eval_queries": [
            {
                "query": "What was the specific error code and message for the failed payment transaction?",
                "golden_answer": "Error: Gateway timeout (code: 504) for transaction tx_99281.",
                "user_id": "sys_admin"
            }
        ]
    },
    "Scenario B: Shifting Persona & Temporal Tracking": {
        "description": "Evolving user preferences over multiple sessions where preferences mutate or contradict.",
        "ingest_steps": [
            {"text": "Session 1: I am planning a trip to Tokyo. I only want to stay in traditional Ryokans and eat sushi.", "user_id": "traveler_1"},
            {"text": "Session 2: I've decided to change my destination to Paris. Forget Tokyo. I want to stay in a boutique hotel near the Eiffel Tower and eat croissants.", "user_id": "traveler_1"},
            {"text": "Session 3: Actually, I am traveling with my cousin who is extremely allergic to gluten, so we cannot eat croissants or any wheat products. We need gluten-free dining options in Paris.", "user_id": "traveler_1"}
        ],
        "eval_queries": [
            {
                "query": "Where is the user traveling, what type of accommodation do they want, and what are their dietary restrictions?",
                "golden_answer": "The user is traveling to Paris, wants to stay in a boutique hotel near the Eiffel Tower, and has a strict gluten-free dietary restriction (no croissants or wheat products).",
                "user_id": "traveler_1"
            }
        ]
    }
}

def evaluate_accuracy(query, retrieved_context, golden_answer, openai_client):
    prompt = f"""
You are an expert scientific judge evaluating the retrieval accuracy of an AI agent's memory system.
Compare the retrieved memory context against the golden answer for the given query.

Query: {query}
Retrieved Context: {retrieved_context}
Golden Answer: {golden_answer}

Rate the retrieval accuracy on a scale from 0.0 to 1.0:
- 1.0: The retrieved context contains all the correct and up-to-date information needed to answer the query, matching the golden answer perfectly.
- 0.5: The retrieved context contains some relevant information, but misses key details or contains outdated/contradictory information.
- 0.0: The retrieved context is completely irrelevant, empty, or contains only outdated/incorrect information.

Provide your response in the following JSON format:
{{
    "score": <float between 0.0 and 1.0>,
    "reasoning": "<brief explanation of the score>"
}}
Do not include any other text or markdown formatting outside the JSON.
"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        result = json.loads(response.choices[0].message.content)
        return float(result.get("score", 0.0)), result.get("reasoning", "")
    except Exception as e:
        print(f"Error in LLM-as-a-Judge evaluation: {e}")
        return 0.0, str(e)

def run_benchmark():
    parser = argparse.ArgumentParser(description="Memanto Benchmarking & Evaluation Challenge")
    parser.add_argument("--competitor", choices=["vector-rag", "mem0"], default="vector-rag", help="Competitor memory framework to compare against")
    args = parser.parse_args()

    check_env_vars()

    openai_client = OpenAI()

    # Initialize Memanto
    print("Initializing Memanto...")
    try:
        from memanto import Memanto
        memanto = Memanto(api_key=os.environ.get("MOORCHEH_API_KEY"))
    except Exception as e:
        print(f"Failed to initialize Memanto: {e}")
        sys.exit(1)

    # Initialize Competitor
    competitor_name = ""
    competitor_instance = None
    if args.competitor == "vector-rag":
        print("Initializing Standard Vector RAG Baseline...")
        competitor_instance = SimpleVectorMemory(openai_client)
        competitor_name = "Standard Vector RAG"
    elif args.competitor == "mem0":
        print("Initializing Mem0...")
        try:
            from mem0 import Memory
            competitor_instance = Memory()
            competitor_name = "Mem0"
        except ImportError:
            print("Error: mem0-ai package is not installed. Please install it or use --competitor vector-rag")
            sys.exit(1)

    results = []

    for scenario_name, scenario_data in BENCHMARK_DATASET.items():
        print(f"\n=========================================")
        print(f"Running {scenario_name}")
        print(f"Description: {scenario_data['description']}")
        print(f"=========================================")

        # Metrics tracking
        metrics = {
            "memanto": {
                "ingest_latencies": [],
                "retrieve_latencies": [],
                "tokens_ingested": 0,
                "tokens_retrieved": 0,
                "accuracy_scores": [],
                "reasons": []
            },
            "competitor": {
                "ingest_latencies": [],
                "retrieve_latencies": [],
                "tokens_ingested": 0,
                "tokens_retrieved": 0,
                "accuracy_scores": [],
                "reasons": []
            }
        }

        # 1. Ingestion Phase
        print("\n--- Ingestion Phase ---")
        for step in scenario_data["ingest_steps"]:
            text = step["text"]
            user_id = step["user_id"]
            tokens = count_tokens(text)

            # Memanto Ingestion
            start_time = time.perf_counter()
            memanto.add(text=text, user_id=user_id)
            latency = time.perf_counter() - start_time
            metrics["memanto"]["ingest_latencies"].append(latency)
            metrics["memanto"]["tokens_ingested"] += tokens
            print(f"[Memanto] Ingested: '{text[:50]}...' in {latency:.4f}s ({tokens} tokens)")

            # Competitor Ingestion
            start_time = time.perf_counter()
            competitor_instance.add(text, user_id=user_id)
            latency = time.perf_counter() - start_time
            metrics["competitor"]["ingest_latencies"].append(latency)
            metrics["competitor"]["tokens_ingested"] += tokens
            print(f"[{competitor_name}] Ingested: '{text[:50]}...' in {latency:.4f}s ({tokens} tokens)")

        # 2. Retrieval & Evaluation Phase
        print("\n--- Retrieval & Evaluation Phase ---")
        for eval_case in scenario_data["eval_queries"]:
            query = eval_case["query"]
            golden_answer = eval_case["golden_answer"]
            user_id = eval_case["user_id"]

            # Memanto Retrieval
            start_time = time.perf_counter()
            memanto_retrieved = memanto.retrieve(query=query, user_id=user_id)
            latency = time.perf_counter() - start_time
            metrics["memanto"]["retrieve_latencies"].append(latency)
            
            # Format retrieved context
            if isinstance(memanto_retrieved, list):
                memanto_context = "\n".join([str(item) for item in memanto_retrieved])
            else:
                memanto_context = str(memanto_retrieved)
            
            retrieved_tokens = count_tokens(memanto_context)
            metrics["memanto"]["tokens_retrieved"] += retrieved_tokens

            # Evaluate Memanto Accuracy
            score, reason = evaluate_accuracy(query, memanto_context, golden_answer, openai_client)
            metrics["memanto"]["accuracy_scores"].append(score)
            metrics["memanto"]["reasons"].append(reason)

            print(f"[Memanto] Retrieved context in {latency:.4f}s ({retrieved_tokens} tokens). Accuracy Score: {score}")

            # Competitor Retrieval
            start_time = time.perf_counter()
            if args.competitor == "vector-rag":
                comp_retrieved = competitor_instance.search(query, user_id=user_id)
            else:
                comp_retrieved = competitor_instance.search(query, user_id=user_id)
            latency = time.perf_counter() - start_time
            metrics["competitor"]["retrieve_latencies"].append(latency)

            # Format retrieved context
            if isinstance(comp_retrieved, list):
                comp_context = "\n".join([str(item) for item in comp_retrieved])
            else:
                comp_context = str(comp_retrieved)

            retrieved_tokens = count_tokens(comp_context)
            metrics["competitor"]["tokens_retrieved"] += retrieved_tokens

            # Evaluate Competitor Accuracy
            score, reason = evaluate_accuracy(query, comp_context, golden_answer, openai_client)
            metrics["competitor"]["accuracy_scores"].append(score)
            metrics["competitor"]["reasons"].append(reason)

            print(f"[{competitor_name}] Retrieved context in {latency:.4f}s ({retrieved_tokens} tokens). Accuracy Score: {score}")

        # Calculate summary statistics
        def get_p95(latencies):
            return np.percentile(latencies, 95) if latencies else 0.0

        memanto_p95_ingest = get_p95(metrics["memanto"]["ingest_latencies"])
        memanto_p95_retrieve = get_p95(metrics["memanto"]["retrieve_latencies"])
        comp_p95_ingest = get_p95(metrics["competitor"]["ingest_latencies"])
        comp_p95_retrieve = get_p95(metrics["competitor"]["retrieve_latencies"])

        memanto_avg_acc = np.mean(metrics["memanto"]["accuracy_scores"]) if metrics["memanto"]["accuracy_scores"] else 0.0
        comp_avg_acc = np.mean(metrics["competitor"]["accuracy_scores"]) if metrics["competitor"]["accuracy_scores"] else 0.0

        results.append({
            "Scenario": scenario_name,
            "Framework": "Memanto",
            "Tokens Ingested": metrics["memanto"]["tokens_ingested"],
            "Tokens Retrieved": metrics["memanto"]["tokens_retrieved"],
            "p95 Ingest Latency (s)": f"{memanto_p95_ingest:.4f}",
            "p95 Retrieve Latency (s)": f"{memanto_p95_retrieve:.4f}",
            "Avg Accuracy": f"{memanto_avg_acc:.2f}"
        })

        results.append({
            "Scenario": scenario_name,
            "Framework": competitor_name,
            "Tokens Ingested": metrics["competitor"]["tokens_ingested"],
            "Tokens Retrieved": metrics["competitor"]["tokens_retrieved"],
            "p95 Ingest Latency (s)": f"{comp_p95_ingest:.4f}",
            "p95 Retrieve Latency (s)": f"{comp_p95_retrieve:.4f}",
            "Avg Accuracy": f"{comp_avg_acc:.2f}"
        })

    # Print final summary table
    print("\n=========================================")
    print("FINAL BENCHMARK RESULTS")
    print("=========================================")
    print(tabulate(results, headers="keys", tablefmt="grid"))

if __name__ == "__main__":
    run_benchmark()
