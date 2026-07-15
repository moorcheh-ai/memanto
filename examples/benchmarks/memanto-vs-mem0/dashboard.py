"""
Streamlit dashboard for benchmark results.

Run with:
    streamlit run dashboard.py

If a results JSON file exists in results/, it will be loaded automatically.
Otherwise you can run the benchmark live from the UI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

RESULTS_DIR = Path(__file__).parent / "results"

st.set_page_config(
    page_title="Memanto vs Mem0 Benchmark",
    page_icon="⚖️",
    layout="wide",
)

st.markdown(
    """
<style>
.metric-card {
    background: #1e1e2e;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.winner-badge {
    background: linear-gradient(135deg, #7c3aed, #2563eb);
    color: white;
    padding: 4px 14px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 0.85rem;
    display: inline-block;
}
</style>
""",
    unsafe_allow_html=True,
)


# ── helpers ───────────────────────────────────────────────────────────────


def load_latest_result() -> dict | None:
    files = sorted(RESULTS_DIR.glob("benchmark_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0]) as f:
        return json.load(f)


def fmt(v: float, unit: str = "") -> str:
    return f"{v:.3f}{unit}"


# ── sidebar ───────────────────────────────────────────────────────────────

st.sidebar.title("⚖️ Benchmark Controls")
st.sidebar.caption("Memanto vs Mem0 — Executive Shadow")

run_mode = st.sidebar.radio("Mode", ["Load saved results", "Run benchmark now"])

result_data: dict | None = None

if run_mode == "Load saved results":
    result_data = load_latest_result()
    if result_data is None:
        st.sidebar.warning("No results found. Run the benchmark first.")
    else:
        st.sidebar.success(f"Loaded: {result_data['run_timestamp']}")

else:
    skip_judge = st.sidebar.checkbox("Skip LLM judge (metrics only)", value=False)
    judge_model = st.sidebar.text_input(
        "Judge model",
        value="anthropic/claude-3-5-haiku",
        help="Any OpenRouter-compatible model ID",
    )
    if st.sidebar.button("▶ Run benchmark", type="primary"):
        from harness import run_benchmark
        from reporter import save_results

        with st.spinner("Running benchmark — this takes ~2–5 minutes..."):
            try:
                result = run_benchmark(
                    skip_judge=skip_judge,
                    judge_model=judge_model if not skip_judge else None,
                )
                path = save_results(result)
                st.sidebar.success(f"Done! Saved to {path.name}")
                result_data = json.loads(path.read_text())
            except Exception as exc:
                st.sidebar.error(f"Benchmark failed: {exc}")

# ── main content ──────────────────────────────────────────────────────────

st.title("⚖️ Memanto vs Mem0 — Executive Shadow Benchmark")
st.caption(
    "6-month startup founder simulation · 46 conversation turns · "
    "8 evaluation queries · 3 metrics: tokens, latency, accuracy"
)

if result_data is None:
    st.info(
        "No results loaded. Use the sidebar to run the benchmark or load a saved result."
    )
    st.stop()

systems = result_data["systems"]
sys_names = list(systems.keys())
colors = {"Memanto": "#7c3aed", "Mem0": "#2563eb"}

# ── headline metrics ──────────────────────────────────────────────────────
st.markdown("## Summary")
cols = st.columns(len(sys_names))
for i, name in enumerate(sys_names):
    m = systems[name]["metrics"]
    with cols[i]:
        score = m.get("total_eval_score", 0)
        max_s = m.get("max_possible_eval_score", 1)
        pct = m.get("eval_score_pct", 0)
        st.metric(
            label=f"{name} — Eval Score", value=f"{score}/{max_s}", delta=f"{pct:.0f}%"
        )

# winner (only when judge scores actually exist)
has_eval_scores = all(len(systems[n].get("eval_scores", [])) > 0 for n in sys_names)
if has_eval_scores:
    winner = max(sys_names, key=lambda n: systems[n]["metrics"]["eval_score_pct"])
    st.markdown(
        f'<span class="winner-badge">🏆 Winner: {winner}</span>',
        unsafe_allow_html=True,
    )

st.divider()

# ── token comparison ──────────────────────────────────────────────────────
st.markdown("## Token Efficiency")

token_data = {
    "Metric": ["Tokens Ingested", "Tokens Recalled", "Total Tokens"],
}
for name in sys_names:
    m = systems[name]["metrics"]
    token_data[name] = [
        m["total_tokens_ingested"],
        m["total_tokens_recalled"],
        m["total_tokens"],
    ]
df_tokens = pd.DataFrame(token_data).set_index("Metric")

c1, c2 = st.columns([2, 1])
with c1:
    st.bar_chart(df_tokens, color=[colors.get(n, "#888") for n in sys_names])
with c2:
    st.dataframe(df_tokens, use_container_width=True)

st.divider()

# ── latency comparison ────────────────────────────────────────────────────
st.markdown("## Latency (seconds)")

lat_data = {
    "Metric": ["p95 Ingest", "p95 Recall", "Mean Recall"],
}
for name in sys_names:
    m = systems[name]["metrics"]
    lat_data[name] = [
        m["p95_ingest_latency_s"],
        m["p95_recall_latency_s"],
        m["mean_recall_latency_s"],
    ]
df_lat = pd.DataFrame(lat_data).set_index("Metric")

c1, c2 = st.columns([2, 1])
with c1:
    st.bar_chart(df_lat, color=[colors.get(n, "#888") for n in sys_names])
with c2:
    st.dataframe(df_lat.map(lambda x: f"{x:.3f}s"), use_container_width=True)

st.divider()

# ── per-query accuracy breakdown ──────────────────────────────────────────

# Check if eval scores exist
has_scores = any(len(systems[n].get("eval_scores", [])) > 0 for n in sys_names)

if has_scores:
    st.markdown("## Retrieval Accuracy — Per Query (LLM Judge)")
    st.caption(
        "Each query scored 0–15 (accuracy + staleness avoidance + precision). Max = 15."
    )

    # Load query metadata
    data_path = Path(__file__).parent / "data" / "executive_shadow.json"
    with open(data_path) as f:
        scenario = json.load(f)
    qmeta = {eq["id"]: eq for eq in scenario["evaluation_queries"]}

    # Build scores table
    rows = []
    for qid, qm in qmeta.items():
        row = {
            "Query": qm["query"][:55],
            "Type": qm["tests"],
            "Domain": qm["domain"],
        }
        for name in sys_names:
            sc_list = [
                s for s in systems[name].get("eval_scores", []) if s["query_id"] == qid
            ]
            if sc_list:
                sc = sc_list[0]
                row[f"{name} (acc/stale/prec)"] = (
                    f"{sc['accuracy']}/{sc['staleness_avoidance']}/{sc['precision']} = {sc['total']}"
                )
                row[f"{name}_total"] = sc["total"]
            else:
                row[f"{name} (acc/stale/prec)"] = "—"
                row[f"{name}_total"] = 0
        rows.append(row)

    df_scores = pd.DataFrame(rows)
    display_cols = ["Query", "Type", "Domain"] + [
        f"{n} (acc/stale/prec)" for n in sys_names
    ]
    st.dataframe(df_scores[display_cols], use_container_width=True, hide_index=True)

    # Score totals chart
    total_row = {"Query": "TOTAL", "Type": "", "Domain": ""}
    for name in sys_names:
        total = sum(r.get(f"{name}_total", 0) for r in rows)
        max_s = len(rows) * 15
        total_row[f"{name} (acc/stale/prec)"] = (
            f"{total}/{max_s} ({total / max_s * 100:.0f}%)"
        )

    st.divider()
    st.markdown("## Score Breakdown by Dimension")
    dim_data: dict = {"Dimension": ["Accuracy", "Staleness Avoidance", "Precision"]}
    for name in sys_names:
        scores = systems[name].get("eval_scores", [])
        dim_data[name] = [
            sum(s["accuracy"] for s in scores),
            sum(s["staleness_avoidance"] for s in scores),
            sum(s["precision"] for s in scores),
        ]
    df_dim = pd.DataFrame(dim_data).set_index("Dimension")
    st.bar_chart(df_dim, color=[colors.get(n, "#888") for n in sys_names])

    st.divider()

    # Per-query deep dive
    st.markdown("## Query Deep Dive")
    selected_qid = st.selectbox(
        "Select a query to inspect",
        options=list(qmeta.keys()),
        format_func=lambda qid: f"{qid} — {qmeta[qid]['query'][:60]}",
    )
    if selected_qid:
        qm = qmeta[selected_qid]
        st.markdown(f"**Query:** {qm['query']}")
        st.markdown(f"**Golden answer:** {qm['golden_answer']}")
        st.markdown(f"**Test type:** `{qm['tests']}` | **Domain:** `{qm['domain']}`")
        st.markdown(f"**Stale signals to avoid:** `{', '.join(qm['stale_signals'])}`")
        st.markdown(
            f"**Current signals expected:** `{', '.join(qm['current_signals'])}`"
        )

        cols = st.columns(len(sys_names))
        for i, name in enumerate(sys_names):
            with cols[i]:
                sc_list = [
                    s
                    for s in systems[name].get("eval_scores", [])
                    if s["query_id"] == selected_qid
                ]
                if sc_list:
                    sc = sc_list[0]
                    st.markdown(f"**{name}** — Score: {sc['total']}/15")
                    st.markdown(
                        f"`acc={sc['accuracy']} stale={sc['staleness_avoidance']} prec={sc['precision']}`"
                    )
                    st.caption(f"Reasoning: {sc['reasoning']}")
                    with st.expander("Recalled answer"):
                        st.text(sc["recalled_answer"])
                else:
                    st.markdown(f"**{name}** — no score data")

else:
    st.info(
        "No LLM judge scores in this result. Re-run without `--skip-judge` to see accuracy metrics."
    )

st.divider()
st.caption(
    f"Scenario: {result_data['scenario_title']} · "
    f"Judge: {result_data['judge_model']} · "
    f"Run: {result_data['run_timestamp']}"
)
