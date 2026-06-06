"""
The Great Agentic Memory Showdown: Shifting Persona & Temporal Tracking Test
=============================================================================

Benchmarks Memanto against Mem0 and a raw-API baseline on the core challenge
of agentic memory in 2026: correctly tracking user preferences that evolve and
contradict across sessions, while minimising token overhead.

Scenario: "The Evolving Entertainment Curator"
    An agent serves as a personal entertainment curator. The user's preferences
    shift and contradict across four distinct sessions. A capable memory system
    must surface the CURRENT preferences and suppress outdated ones.

Metrics (per framework):
    accuracy            : LLM-judge score 0–3 per probe (0=wrong, 3=perfect)
    mean_accuracy       : Mean accuracy across all 4 probe questions (max 3.0)
    context_tokens      : Tokens of memory context injected per LLM call
    total_tokens        : Total tokens consumed per LLM call (prompt + completion)
    memory_write_p50_ms : Median latency of a single memory write (ms)
    memory_write_p95_ms : 95th-percentile write latency (ms)
    memory_read_p50_ms  : Median retrieval latency (ms)
    memory_read_p95_ms  : 95th-percentile retrieval latency (ms)

Frameworks:
    raw_api   : No memory. Fresh context each probe. Baseline.
    mem0      : Mem0 local memory layer.
    memanto   : Memanto SDK (requires MOORCHEH_API_KEY — free at moorcheh.ai).
    cathedral : Cathedral API (requires CATHEDRAL_API_KEY, optional).

LLM backends supported (set LLM_PROVIDER env var):
    openai (default) : requires OPENAI_API_KEY — uses gpt-4o-mini
    groq             : requires GROQ_API_KEY   — uses llama-3.3-70b-versatile

Embedder backends (set EMBEDDER env var):
    openai (default) : requires OPENAI_API_KEY — text-embedding-3-small
    local            : sentence-transformers/all-MiniLM-L6-v2 (no API key needed)

Setup:
    pip install -r requirements.txt

    # Option A: OpenAI (recommended for reproducibility)
    export OPENAI_API_KEY=sk-...
    export MOORCHEH_API_KEY=...     # free at moorcheh.ai

    # Option B: Groq + local embeddings (no OpenAI key needed)
    export GROQ_API_KEY=gsk-...
    export LLM_PROVIDER=groq
    export EMBEDDER=local
    export MOORCHEH_API_KEY=...

Run:
    python benchmark.py                          # run all available frameworks
    python benchmark.py --framework mem0 memanto # run specific frameworks
    python benchmark.py --results                # print results table
    python benchmark.py --plot                   # generate bar chart
"""

import os
import json
import time
import argparse
import statistics
import numpy as np
from pathlib import Path
from datetime import datetime

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
EMBEDDER     = os.environ.get("EMBEDDER", "openai").lower()

# ── LLM client factory ────────────────────────────────────────────────────────

def make_llm_client():
    if LLM_PROVIDER == "groq":
        from groq import Groq
        return Groq(api_key=os.environ["GROQ_API_KEY"])
    from openai import OpenAI
    return OpenAI()

LLM_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant") if LLM_PROVIDER == "groq" else "gpt-4o-mini"
JUDGE_MODEL = LLM_MODEL

# ── Embedding factory ─────────────────────────────────────────────────────────

_st_model = None

def embed_texts(texts: list[str]) -> np.ndarray:
    if EMBEDDER == "local":
        global _st_model
        if _st_model is None:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        vecs = _st_model.encode(texts, normalize_embeddings=True)
        return np.array(vecs)
    # openai
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return np.array([d.embedding for d in resp.data])

# ── Scenario: The Evolving Entertainment Curator ──────────────────────────────

WRITE_SESSIONS = [
    {
        "id": 1,
        "label": "Baseline — action + classic rock",
        "memories": [
            ("preference", "Film genre",   "User loves big-budget action blockbusters. Favourites: Mad Max, John Wick, Mission Impossible."),
            ("preference", "Music taste",  "User is a classic rock devotee: Led Zeppelin, AC/DC, Black Sabbath."),
            ("preference", "Film dislike", "User actively dislikes romance films and musicals. Finds them unwatchable."),
        ],
    },
    {
        "id": 2,
        "label": "Discovery — arthouse cinema emerges",
        "memories": [
            ("learning",   "Taste shift",         "User watched Parasite and their worldview shifted. Now fascinated by slow, deliberate world cinema."),
            ("preference", "New film preference",  "User increasingly prefers arthouse and indie films with layered storytelling over blockbusters."),
        ],
    },
    {
        "id": 3,
        "label": "Reversal — action fatigue sets in",
        "memories": [
            ("preference", "Action reversal",    "User is now burned out on action films. Finds them hollow and repetitive. Do NOT suggest them."),
            ("preference", "Thriller obsession", "Current obsession: slow-burn psychological thrillers — Fincher, Park Chan-wook, Villeneuve."),
            ("preference", "Music pivot",        "User has pivoted fully to jazz: Coltrane, Miles Davis, Bill Evans. Classic rock now feels 'too aggressive'."),
        ],
    },
    {
        "id": 4,
        "label": "Final constraint — foreign language only",
        "memories": [
            ("preference", "Language constraint", "User will ONLY watch foreign-language films with subtitles. English-language films feel shallow now."),
            ("preference", "Favourite directors", "Must-watch directors: Park Chan-wook (Korean), Hirokazu Kore-eda (Japanese), Céline Sciamma (French)."),
        ],
    },
]

PROBE_QUESTIONS = [
    "What film should I watch tonight? Give me one specific recommendation.",
    "I want something to listen to while I work. What would you suggest?",
    "A friend says I'd love the latest Marvel blockbuster. Should I watch it?",
    "Recommend a director whose entire filmography I should explore.",
]

GROUND_TRUTH = (
    "Current preferences: ONLY foreign-language psychological thrillers (Park Chan-wook, "
    "Kore-eda, Sciamma). Jazz music only (Coltrane, Miles Davis). "
    "MUST NOT suggest: action films (burned out), English-language films, classic rock, romance."
)

SYSTEM_PROMPT = "You are a personal entertainment curator. Recommend based on the user's stored preferences."

# ── Helpers ───────────────────────────────────────────────────────────────────

def percentile(data: list, p: float) -> float:
    return float(np.percentile(data, p)) if data else 0.0


def count_tokens(text: str) -> int:
    """Rough token estimate (4 chars ≈ 1 token) when usage object unavailable."""
    return len(text) // 4


def llm_judge(question: str, response: str, client) -> int:
    """Score 0–3: how accurately does the response reflect current preferences?"""
    prompt = f"""You are evaluating an AI agent's response for preference accuracy.

Current user preferences (ground truth):
{GROUND_TRUTH}

Question asked: {question}
Agent response: {response}

Score 0–3:
0 = Contradicts preferences (e.g. recommends action when user is burned out on it)
1 = Ignores preferences (generic, non-committal answer)
2 = Partially correct (some preferences honoured, some missed or outdated ones included)
3 = Fully correct (accurately reflects ALL current preferences, avoids outdated ones)

Reply with ONLY the single digit (0, 1, 2, or 3)."""

    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=5,
    )
    try:
        return int(resp.choices[0].message.content.strip()[0])
    except Exception:
        return 1


def llm_call(client, system: str, user: str):
    """Unified LLM call; returns (answer, prompt_tokens, total_tokens)."""
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.3,
    )
    answer = resp.choices[0].message.content
    usage  = resp.usage
    return answer, usage.prompt_tokens, usage.total_tokens


def save_result(framework: str, data: dict):
    path = RESULTS_DIR / f"{framework}.json"
    path.write_text(json.dumps(data, indent=2))
    print(f"  Saved → {path}")


def build_result(framework: str, probe_rows: list,
                 write_latencies: list, read_latencies: list) -> dict:
    accuracies     = [r["accuracy"]       for r in probe_rows]
    context_tokens = [r["context_tokens"] for r in probe_rows]
    total_tokens   = [r["total_tokens"]   for r in probe_rows]
    return {
        "framework":            framework,
        "timestamp":            datetime.utcnow().isoformat(),
        "llm_model":            LLM_MODEL,
        "embedder":             EMBEDDER,
        "ground_truth":         GROUND_TRUTH,
        "mean_accuracy":        round(statistics.mean(accuracies), 2),
        "max_accuracy":         max(accuracies),
        "mean_context_tokens":  round(statistics.mean(context_tokens), 1),
        "mean_total_tokens":    round(statistics.mean(total_tokens), 1),
        "memory_write_p50_ms":  round(percentile(write_latencies, 50), 1),
        "memory_write_p95_ms":  round(percentile(write_latencies, 95), 1),
        "memory_read_p50_ms":   round(percentile(read_latencies, 50), 1),
        "memory_read_p95_ms":   round(percentile(read_latencies, 95), 1),
        "n_writes":             len(write_latencies),
        "n_probes":             len(probe_rows),
        "probe_details":        probe_rows,
    }

# ── Framework runners ─────────────────────────────────────────────────────────

def run_raw_api(client) -> dict:
    """No memory. Every probe starts cold. Establishes the accuracy floor."""
    print(f"\n[raw_api] Running ({LLM_MODEL}, no memory — baseline)...")
    probe_rows = []

    for q in PROBE_QUESTIONS:
        answer, prompt_tok, total_tok = llm_call(client, SYSTEM_PROMPT, q)
        score = llm_judge(q, answer, client)
        probe_rows.append({
            "question":       q,
            "answer":         answer,
            "accuracy":       score,
            "context_tokens": 0,
            "total_tokens":   total_tok,
            "memory_read_ms": 0,
        })
        print(f"  [{score}/3] {q[:55]}...")
        time.sleep(0.3)

    return build_result("raw_api", probe_rows, write_latencies=[], read_latencies=[])


def run_mem0(client) -> dict:
    """Mem0 local memory — accumulates all sessions, retrieves relevant ones per probe."""
    from mem0 import Memory

    print(f"\n[mem0] Running ({LLM_MODEL}, embedder={EMBEDDER})...")

    if EMBEDDER == "local":
        config = {
            "llm": {
                "provider": "groq" if LLM_PROVIDER == "groq" else "openai",
                "config": {
                    "model": LLM_MODEL,
                    **({"api_key": os.environ["GROQ_API_KEY"]} if LLM_PROVIDER == "groq" else {}),
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {"model": "sentence-transformers/all-MiniLM-L6-v2"},
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "showdown_mem0_v2",
                    "embedding_model_dims": 384,
                    "on_disk": False,
                },
            },
        }
    else:
        config = {
            "llm":     {"provider": "openai", "config": {"model": LLM_MODEL}},
            "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
        }

    m       = Memory.from_config(config)
    user_id = "showdown_curator_mem0"
    write_latencies, read_latencies, probe_rows = [], [], []

    for sess in WRITE_SESSIONS:
        print(f"  Writing session {sess['id']}: {sess['label']}")
        for mem_type, title, content in sess["memories"]:
            t0 = time.perf_counter()
            m.add(f"[{title}] {content}", user_id=user_id)
            write_latencies.append((time.perf_counter() - t0) * 1000)
            time.sleep(0.2)

    # mem0 v2: user_id moved to filters param
    _search_kwargs = {"filters": {"user_id": user_id}, "limit": 8}

    for q in PROBE_QUESTIONS:
        t0   = time.perf_counter()
        hits = m.search(q, **_search_kwargs)
        read_latencies.append((time.perf_counter() - t0) * 1000)

        # mem0 v2 returns strings directly; v1 returned dicts with 'memory' key
        memory_text = "\n".join(
            f"- {h['memory']}" if isinstance(h, dict) else f"- {h}" for h in hits
        )
        system      = f"{SYSTEM_PROMPT}\n\nUser memory:\n{memory_text}"

        answer, prompt_tok, total_tok = llm_call(client, system, q)
        score = llm_judge(q, answer, client)

        probe_rows.append({
            "question":       q,
            "answer":         answer,
            "accuracy":       score,
            "context_tokens": prompt_tok,
            "total_tokens":   total_tok,
            "memory_read_ms": read_latencies[-1],
        })
        print(f"  [{score}/3] {q[:55]}... (read {read_latencies[-1]:.0f}ms)")
        time.sleep(0.3)

    return build_result("mem0", probe_rows, write_latencies, read_latencies)


def run_memanto(client) -> dict:
    """Memanto SDK — remember/recall pattern with Moorcheh retrieval backend."""
    from memanto.cli.client.sdk_client import SdkClient

    sdk      = SdkClient(api_key=os.environ["MOORCHEH_API_KEY"])
    agent_id = "showdown-curator-001"

    print(f"\n[memanto] Running ({LLM_MODEL})...")

    try:
        sdk.create_agent(agent_id=agent_id, pattern="tool",
                         description="Benchmark: Shifting Persona & Temporal Tracking")
    except Exception:
        pass  # already exists

    sdk.activate_agent(agent_id, duration_hours=2)
    write_latencies, read_latencies, probe_rows = [], [], []

    for sess in WRITE_SESSIONS:
        print(f"  Writing session {sess['id']}: {sess['label']}")
        for mem_type, title, content in sess["memories"]:
            t0 = time.perf_counter()
            sdk.remember(
                agent_id=agent_id,
                memory_type=mem_type,
                title=title,
                content=content,
                confidence=0.9,
            )
            write_latencies.append((time.perf_counter() - t0) * 1000)
            time.sleep(0.3)

    for q in PROBE_QUESTIONS:
        t0     = time.perf_counter()
        result = sdk.recall(agent_id=agent_id, query=q, limit=8)
        read_latencies.append((time.perf_counter() - t0) * 1000)

        memories    = result.get("memories", [])
        memory_text = "\n".join(
            f"- [{m.get('type','')}] {m.get('title','')}: {m.get('content','')}"
            for m in memories
        )
        system = f"{SYSTEM_PROMPT}\n\nMemanto context:\n{memory_text}"

        answer, prompt_tok, total_tok = llm_call(client, system, q)
        score = llm_judge(q, answer, client)

        probe_rows.append({
            "question":       q,
            "answer":         answer,
            "accuracy":       score,
            "context_tokens": prompt_tok,
            "total_tokens":   total_tok,
            "memory_read_ms": read_latencies[-1],
        })
        print(f"  [{score}/3] {q[:55]}... (read {read_latencies[-1]:.0f}ms)")
        time.sleep(0.3)

    try:
        sdk.deactivate_agent(agent_id)
    except Exception:
        pass
    return build_result("memanto", probe_rows, write_latencies, read_latencies)


def run_cathedral(client) -> dict:
    """Cathedral API — persistent memories with semantic search retrieval."""
    import httpx

    api_key = os.environ["CATHEDRAL_API_KEY"]
    base    = os.environ.get("CATHEDRAL_BASE_URL", "https://cathedral-ai.com")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print(f"\n[cathedral] Running ({LLM_MODEL})...")
    write_latencies, read_latencies, probe_rows = [], [], []

    for sess in WRITE_SESSIONS:
        print(f"  Writing session {sess['id']}: {sess['label']}")
        for mem_type, title, content in sess["memories"]:
            t0 = time.perf_counter()
            httpx.post(f"{base}/memories", headers=headers, json={
                "content":    f"[{title}] {content}",
                "category":   "preference",
                "importance": 0.85,
            }, timeout=15)
            write_latencies.append((time.perf_counter() - t0) * 1000)
            time.sleep(0.2)

    for q in PROBE_QUESTIONS:
        t0 = time.perf_counter()
        r  = httpx.get(f"{base}/memories", headers=headers,
                       params={"search": q, "limit": 8}, timeout=15)
        memories = r.json().get("memories", []) if r.status_code == 200 else []
        read_latencies.append((time.perf_counter() - t0) * 1000)

        memory_text = "\n".join(f"- {m.get('content','')}" for m in memories)
        system      = f"{SYSTEM_PROMPT}\n\nPersistent memory:\n{memory_text}"

        answer, prompt_tok, total_tok = llm_call(client, system, q)
        score = llm_judge(q, answer, client)

        probe_rows.append({
            "question":       q,
            "answer":         answer,
            "accuracy":       score,
            "context_tokens": prompt_tok,
            "total_tokens":   total_tok,
            "memory_read_ms": read_latencies[-1],
        })
        print(f"  [{score}/3] {q[:55]}... (read {read_latencies[-1]:.0f}ms)")
        time.sleep(0.3)

    return build_result("cathedral", probe_rows, write_latencies, read_latencies)

# ── Results table ─────────────────────────────────────────────────────────────

FRAMEWORKS = ["raw_api", "mem0", "memanto", "cathedral"]


def print_table():
    print()
    print("The Great Agentic Memory Showdown — Results")
    print("Scenario: Shifting Persona & Temporal Tracking (4 sessions → 4 probe questions)")
    print()
    cols = [20, 10, 14, 14, 16, 16, 16, 16]
    hdrs = ["Framework", "Accuracy", "Context Tok", "Total Tok",
            "Write p50 ms", "Write p95 ms", "Read p50 ms", "Read p95 ms"]
    div  = "-" * sum(cols)
    fmt  = "".join(f"{{:<{n}}}" for n in cols)

    print(fmt.format(*hdrs))
    print(div)
    for name in FRAMEWORKS:
        path = RESULTS_DIR / f"{name}.json"
        if not path.exists():
            print(fmt.format(name, "(not run)", *["—"] * 6))
            continue
        r   = json.loads(path.read_text())
        acc = f"{r['mean_accuracy']:.2f}/3.0"
        print(fmt.format(
            name, acc,
            f"{r['mean_context_tokens']:.0f}",
            f"{r['mean_total_tokens']:.0f}",
            f"{r['memory_write_p50_ms']:.0f}",
            f"{r['memory_write_p95_ms']:.0f}",
            f"{r['memory_read_p50_ms']:.0f}",
            f"{r['memory_read_p95_ms']:.0f}",
        ))
    print(div)
    print("Accuracy: LLM-as-judge 0–3 (0=wrong prefs served, 3=fully current).")
    print("Context Tok: prompt tokens from injected memory context.")
    print("Latency: wall-clock ms for memory write / semantic retrieval.")
    print()


def plot_results():
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — pip install matplotlib")
        return

    data = {n: json.loads((RESULTS_DIR / f"{n}.json").read_text())
            for n in FRAMEWORKS if (RESULTS_DIR / f"{n}.json").exists()}
    if not data:
        print("No results found. Run the benchmark first.")
        return

    names  = list(data.keys())
    colors = {"raw_api": "#555", "mem0": "#2196F3", "memanto": "#FF9800", "cathedral": "#9C27B0"}

    fig, axes = plt.subplots(1, 3, figsize=(14, 5), facecolor="#1a1a2e")
    fig.suptitle("The Great Agentic Memory Showdown\nShifting Persona & Temporal Tracking Test",
                 color="white", fontsize=12)

    def bar(ax, vals, title, ylabel, ylim=None):
        for ax_ in [ax]:
            ax_.set_facecolor("#16213e")
            ax_.tick_params(colors="white")
            ax_.spines[:].set_color("#444")
        clrs = [colors.get(n, "#aaa") for n in names]
        bs   = ax.bar(names, vals, color=clrs, width=0.5)
        ax.set_title(title, color="white", fontsize=9)
        ax.set_ylabel(ylabel, color="#aaa", fontsize=8)
        if ylim:
            ax.set_ylim(*ylim)
        ax.set_xticklabels(names, rotation=15, ha="right", color="white", fontsize=8)
        ax.set_yticklabels([str(t) for t in ax.get_yticks()], color="white", fontsize=8)
        top = ylim[1] if ylim else max(vals) * 1.15
        for b, v in zip(bs, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + top * 0.02,
                    f"{v:.1f}", ha="center", va="bottom", color="white", fontsize=9)

    bar(axes[0], [data[n]["mean_accuracy"]       for n in names],
        "Preference Accuracy\n(LLM judge 0–3, ↑ better)", "Score", (0, 3.5))
    bar(axes[1], [data[n]["mean_context_tokens"]  for n in names],
        "Context Token Overhead\n(memory injected per call, ↓ better)", "Tokens")
    bar(axes[2], [data[n]["memory_read_p95_ms"]   for n in names],
        "Retrieval Latency p95\n(semantic search ms, ↓ better)", "ms")

    plt.tight_layout()
    out = RESULTS_DIR / "showdown_chart.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="#1a1a2e")
    print(f"Chart saved → {out}")

# ── Main ──────────────────────────────────────────────────────────────────────

AVAILABLE = {
    "raw_api":   lambda: True,
    "mem0":      lambda: True,
    "memanto":   lambda: bool(os.environ.get("MOORCHEH_API_KEY")),
    "cathedral": lambda: bool(os.environ.get("CATHEDRAL_API_KEY")),
}

RUNNERS = {
    "raw_api":   run_raw_api,
    "mem0":      run_mem0,
    "memanto":   run_memanto,
    "cathedral": run_cathedral,
}


def main():
    parser = argparse.ArgumentParser(description="Agentic Memory Showdown Benchmark")
    parser.add_argument("--framework", nargs="+", default=["all"],
                        help=f"Frameworks: {', '.join(FRAMEWORKS)}, or all")
    parser.add_argument("--results", action="store_true", help="Print results table")
    parser.add_argument("--plot",    action="store_true", help="Generate chart")
    args = parser.parse_args()

    if args.results:
        print_table()
        return

    if args.plot:
        plot_results()
        return

    targets = FRAMEWORKS if "all" in args.framework else args.framework
    llm     = make_llm_client()

    for name in targets:
        if not AVAILABLE[name]():
            print(f"\n[{name}] Skipping — required API key not set.")
            continue
        result = RUNNERS[name](llm)
        save_result(name, result)

    print_table()


if __name__ == "__main__":
    main()
