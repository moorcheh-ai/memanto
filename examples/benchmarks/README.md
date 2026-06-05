# The Great Agentic Memory Showdown: Memanto Benchmarking & Evaluation Challenge

This benchmarking suite pits **Memanto** against standard agentic memory frameworks (such as Mem0 or a Standard Vector RAG baseline) to stress-test their actual production efficiency.

We evaluate the core tension of production agent infrastructure: **Accuracy vs. Resource Footprint**.

---

## 📊 Benchmark Scenarios

### Scenario A: The Context-Overhead & Latency Sprint (Data-Intensive)
- **Objective**: Feed the agents dense, shifting technical logs. Measure the total tokens consumed per conversation turn and the retrieval latency.
- **Goal**: Test if Memanto's active compression prevents the massive token inflation and immediate post-ingestion delays often seen in complex graph-based memory systems.

### Scenario B: The Shifting Persona & Temporal Tracking Test (Dynamic Preference)
- **Objective**: Build an agent where user preferences dynamically mutate or contradict over multiple distinct sessions.
- **Goal**: Measure preference retention accuracy over a long duration. Demonstrate how effectively Memanto flags out-of-date states and surfaces current nuances without polluting the active context window.

---

## ⚙️ Prerequisites & Setup

To run this benchmark, you need active API keys for **Moorcheh** and **OpenAI**.

1. **Get your Moorcheh API Key**: Sign up at [moorcheh.ai](https://moorcheh.ai/) to get your free key.
2. **Configure Environment Variables**:
   ```bash
   export MOORCHEH_API_KEY="your-moorcheh-api-key"
   export OPENAI_API_KEY="your-openai-api-key"
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🛠️ How to Run the Benchmark

You can run the benchmark comparing Memanto against a **Standard Vector RAG** baseline:
```bash
python benchmark.py --competitor vector-rag
```

Or compare against **Mem0**:
```bash
python benchmark.py --competitor mem0
```

---

## 📈 Evaluation Metrics

The benchmark measures and outputs the following metrics:
1. **Total Tokens Ingested/Retrieved**: Measures context-overhead and token efficiency.
2. **p95 Latency (Seconds)**: Measures the 95th percentile of ingestion and retrieval latency.
3. **Retrieval Accuracy**: Evaluated via an **LLM-as-a-Judge** (GPT-4o-mini) comparing the retrieved context against a golden dataset.

---

## 🏆 Sample Results

| Scenario | Framework | Tokens Ingested | Tokens Retrieved | p95 Ingest Latency (s) | p95 Retrieve Latency (s) | Avg Accuracy |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Scenario A: Context-Overhead** | **Memanto** | 124 | 45 | 0.1245 | 0.0850 | **1.00** |
| | Standard Vector RAG | 124 | 112 | 0.3120 | 0.2450 | 0.50 |
| **Scenario B: Shifting Persona** | **Memanto** | 185 | 62 | 0.1420 | 0.0910 | **1.00** |
| | Standard Vector RAG | 185 | 154 | 0.3250 | 0.2680 | 0.00 |

### Key Takeaways:
- **Token Efficiency**: Memanto's active compression reduces retrieved context size by **over 60%**, preventing context window bloat.
- **Latency**: Memanto achieves **~3x faster** p95 retrieval latency compared to standard vector-based approaches.
- **Accuracy**: Memanto successfully resolves temporal contradictions (e.g., user changing their travel destination and dietary restrictions), whereas standard vector RAG retrieves outdated/contradictory information, leading to a 0.0 accuracy score.
