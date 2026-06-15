import os
import uuid
import numpy as np
from rich.console import Console
from rich.table import Table
from dotenv import load_dotenv

from dataset import SHIFTING_PERSONA_DATASET, EXPECTED_STATE
from memory_layers import MemantoLayer, Mem0Layer
from judge import LLMJudge

# Load environment variables
load_dotenv()

def run_evaluation(layer_name: str, layer, dataset: list, expected_state: str, judge: LLMJudge):
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    
    total_ingest_latency = 0.0
    total_tokens_ingested = 0
    
    print(f"[{layer_name}] Starting ingestion...")
    # 1. Ingest Data
    for msg in dataset[:-1]: # All except the last query
        metrics = layer.add_memory(user_id=user_id, content=msg["content"])
        total_ingest_latency += metrics["latency"]
        total_tokens_ingested += metrics["tokens"]
        
    print(f"[{layer_name}] Ingestion complete. Retrieving memory...")
        
    # 2. Retrieve Memory
    query = dataset[-1]["content"]
    retrieved_context, retrieve_metrics = layer.retrieve_memory(user_id=user_id, query=query)
    
    # 3. Judge Accuracy
    print(f"[{layer_name}] Judging retrieval accuracy...")
    evaluation = judge.evaluate(expected_state=expected_state, retrieved_context=retrieved_context)
    
    return {
        "Layer": layer_name,
        "Total Tokens Ingested": total_tokens_ingested,
        "Tokens Retrieved": retrieve_metrics["tokens"],
        "p95 Latency (s)": round(np.percentile([total_ingest_latency, retrieve_metrics["latency"]], 95), 3),
        "Accuracy Score": evaluation.get("score", 0),
        "Judge Reasoning": evaluation.get("reasoning", "N/A"),
        "Context Snippet": retrieved_context[:100] + "..." if len(retrieved_context) > 100 else retrieved_context
    }

def main():
    console = Console()
    console.print("[bold cyan]Starting Memanto vs Mem0 Benchmark (Scenario: Shifting Persona)[/bold cyan]")
    
    judge = LLMJudge()
    
    # Initialize layers
    console.print("Initializing Memory Layers...")
    memanto = MemantoLayer()
    mem0 = Mem0Layer()
    
    results = []
    
    # Run Memanto
    res_memanto = run_evaluation("Memanto", memanto, SHIFTING_PERSONA_DATASET, EXPECTED_STATE, judge)
    results.append(res_memanto)
    
    # Run Mem0
    res_mem0 = run_evaluation("Mem0", mem0, SHIFTING_PERSONA_DATASET, EXPECTED_STATE, judge)
    results.append(res_mem0)
    
    # Output Table
    table = Table(title="Benchmark Results: Accuracy vs. Resource Footprint")
    
    table.add_column("Framework", justify="left", style="cyan", no_wrap=True)
    table.add_column("Total Tokens Ingested", justify="right", style="magenta")
    table.add_column("Tokens Retrieved", justify="right", style="magenta")
    table.add_column("p95 Latency (s)", justify="right", style="green")
    table.add_column("Accuracy Score", justify="right", style="yellow")
    
    for r in results:
        table.add_row(
            r["Layer"],
            str(r["Total Tokens Ingested"]),
            str(r["Tokens Retrieved"]),
            str(r["p95 Latency (s)"]),
            f"{r['Accuracy Score']}/100"
        )
        
    console.print("\n")
    console.print(table)
    
    console.print("\n[bold]Judge Reasoning Notes:[/bold]")
    for r in results:
        console.print(f"- [bold cyan]{r['Layer']}[/bold cyan]: {r['Judge Reasoning']}")
        console.print(f"  [dim]Snippet: {r['Context Snippet']}[/dim]")

if __name__ == "__main__":
    main()
