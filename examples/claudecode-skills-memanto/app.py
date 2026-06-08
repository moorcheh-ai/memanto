"""
Streamlit demo — Memanto + Claude Code Skills

Two-tab UI showing cross-session memory persistence:
  Tab 1 (Session 1): Store engineering decisions as a developer
  Tab 2 (Session 2): Fresh context — recalls everything stored in Session 1

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from memanto_skills import MemantoSkillsClient
from memanto_skills.extractor import infer_memory_type

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Memanto + Claude Code Skills",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
.memory-card {
    background: #1e1e2e;
    border-left: 4px solid #7c3aed;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 0.88rem;
}
.memory-card.instruction { border-color: #ef4444; }
.memory-card.decision    { border-color: #3b82f6; }
.memory-card.preference  { border-color: #10b981; }
.memory-card.learning    { border-color: #f59e0b; }
.memory-card.fact        { border-color: #6366f1; }
.type-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 1px 7px;
    border-radius: 999px;
    margin-right: 6px;
    text-transform: uppercase;
}
.badge-instruction { background:#ef444422; color:#ef4444; }
.badge-decision    { background:#3b82f622; color:#3b82f6; }
.badge-preference  { background:#10b98122; color:#10b981; }
.badge-learning    { background:#f59e0b22; color:#f59e0b; }
.badge-fact        { background:#6366f122; color:#6366f1; }
.badge-default     { background:#ffffff22; color:#aaa; }
.session-header {
    font-size: 0.8rem;
    color: #888;
    margin-bottom: 4px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
</style>
""", unsafe_allow_html=True)

# ─── Helpers ─────────────────────────────────────────────────────────────────

BADGE_CLASS = {
    "instruction": "badge-instruction",
    "decision":    "badge-decision",
    "preference":  "badge-preference",
    "learning":    "badge-learning",
    "fact":        "badge-fact",
}

PRESET_DECISIONS = {
    "tdd": [
        ("Always use pytest-asyncio for all async tests. Never use unittest.IsolatedAsyncioTestCase.", "instruction", 0.95),
        ("Test seams are always at the public repository interface — use InMemoryRepository adapters, never mock the DB directly.", "decision", 0.90),
        ("Test naming: test_<action>_<condition>_<expected_outcome>.", "instruction", 0.90),
        ("Prefer integration-style tests. A test that mocks 3+ collaborators is a design smell.", "preference", 0.85),
    ],
    "grill-with-docs": [
        ("'Order' = confirmed purchase with payment captured. 'Cart' = pre-confirmation. Never mix.", "instruction", 0.98),
        ("CQRS for Order domain: reads via QueryService, writes via OrderRepository. Do not mix paths.", "decision", 0.92),
        ("ADR-0003: Postgres = write model, Redis = read model. Never query Postgres from the read path.", "decision", 0.95),
    ],
    "general": [
        ("This project uses Ruff for linting. Never suggest Black or Flake8.", "instruction", 1.0),
        ("Developer prefers explicit over implicit. Avoid magic and deep decorator stacks.", "preference", 0.85),
    ],
}


@st.cache_resource
def get_client(agent_id: str | None = None) -> MemantoSkillsClient:
    """Shared client across reruns — cached by Streamlit."""
    client = MemantoSkillsClient(agent_id=agent_id)
    client.setup()
    return client


def reset_agent() -> str:
    """Rotate to a fresh agent ID and return it."""
    import uuid
    new_id = f"skills-demo-{uuid.uuid4().hex[:8]}"
    from memanto_skills.client import MemantoSkillsClient as _C
    import os
    tmp = _C(agent_id=new_id)
    tmp.setup()
    return new_id


def render_memory_card(mem: dict) -> None:
    mtype = mem.get("type", "memory")
    title = mem.get("title", "").strip()
    content = mem.get("content", "").strip()
    conf = mem.get("confidence", "")
    badge_cls = BADGE_CLASS.get(mtype, "badge-default")
    conf_str = f"{float(conf):.0%}" if conf != "" else ""

    st.markdown(f"""
<div class="memory-card {mtype}">
  <span class="type-badge {badge_cls}">{mtype}</span>
  {"<strong>" + title + "</strong><br>" if title else ""}
  <span style="color:#ccc">{content}</span>
  {"<br><small style='color:#666'>confidence: " + conf_str + "</small>" if conf_str else ""}
</div>
""", unsafe_allow_html=True)


def fetch_memories(client: MemantoSkillsClient, skill: str, hint: str = "") -> list[dict]:
    try:
        profile = client.recall_for_skill(skill_name=skill, task_hint=hint)
        return profile.memories
    except Exception:
        return []


def fetch_all_memories(client: MemantoSkillsClient) -> list[dict]:
    """Use recall_recent (not semantic search) so sidebar reflects true stored state."""
    try:
        result = client._sdk.recall_recent(agent_id=client.agent_id, limit=50)
        return result.get("memories", [])
    except Exception:
        return []


# ─── Sidebar — memory panel ───────────────────────────────────────────────────

def render_sidebar(client: MemantoSkillsClient) -> None:
    st.sidebar.title("🧠 Engineering Profile")
    st.sidebar.caption("Live view of memories stored in Memanto")

    col_r, col_ref = st.sidebar.columns(2)
    with col_r:
        if st.button("🗑 Reset demo", key="reset", help="Wipe all memories — start fresh"):
            with st.spinner("Resetting..."):
                new_id = reset_agent()
                st.session_state["agent_id"] = new_id
                st.cache_resource.clear()
            st.success("Reset! Profile is now empty.")
            time.sleep(0.5)
            st.rerun()
    with col_ref:
        if st.button("🔄 Refresh", key="refresh"):
            st.rerun()

    memories = fetch_all_memories(client)

    if not memories:
        st.sidebar.info("No memories stored yet. Use Session 1 to store some!")
        return

    st.sidebar.markdown(f"**{len(memories)} memories stored**")
    st.sidebar.markdown("---")

    for mem in memories:
        render_memory_card(mem)
        st.sidebar.markdown("")  # spacing


# ─── Session 1 tab ───────────────────────────────────────────────────────────

def render_session_1(client: MemantoSkillsClient) -> None:
    st.markdown('<div class="session-header">Session 1 · Storing decisions</div>', unsafe_allow_html=True)
    st.subheader("Store engineering decisions")
    st.caption("Simulate a developer finishing a /tdd or /grill-with-docs session and capturing what was decided.")

    col1, col2 = st.columns([2, 1])

    with col1:
        skill = st.selectbox(
            "Skill that produced this insight",
            ["tdd", "grill-with-docs", "general", "diagnose", "handoff"],
            key="s1_skill",
        )

        summary = st.text_area(
            "Engineering insight to store",
            placeholder="e.g. Always use pytest-asyncio for async tests in this project.",
            height=100,
            key="s1_summary",
        )

        auto_type = infer_memory_type(summary) if summary else "learning"
        mtype = st.selectbox(
            "Memory type",
            ["instruction", "decision", "preference", "learning", "fact", "goal", "artifact", "context"],
            index=["instruction", "decision", "preference", "learning", "fact", "goal", "artifact", "context"].index(auto_type),
            key="s1_type",
        )
        confidence = st.slider("Confidence", 0.0, 1.0, 0.85, 0.05, key="s1_conf")

        if st.button("💾 Store memory", type="primary", key="s1_store"):
            if not summary.strip():
                st.warning("Enter an insight to store.")
            else:
                with st.spinner("Storing..."):
                    mid = client.store_from_skill(
                        skill_name=skill,
                        summary=summary,
                        memory_type=mtype,
                        confidence=confidence,
                    )
                if mid:
                    st.success(f"Stored ✓  `{mid}`")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Failed to store. Check your API key.")

    with col2:
        st.markdown("**Quick load presets**")
        st.caption("Load a batch of realistic decisions")
        for preset_skill, entries in PRESET_DECISIONS.items():
            if st.button(f"Load /{preset_skill}", key=f"preset_{preset_skill}"):
                with st.spinner(f"Storing {len(entries)} memories from /{preset_skill}..."):
                    ids = client.batch_store_from_skill(
                        preset_skill,
                        [{"summary": s, "memory_type": t, "confidence": c} for s, t, c in entries],
                    )
                stored = len([i for i in ids if i])
                st.success(f"Stored {stored}/{len(entries)} memories")
                time.sleep(0.5)
                st.rerun()

    # Show recent memories for this skill
    st.markdown("---")
    st.markdown(f"**Recent memories for `/{skill}`**")
    mems = fetch_memories(client, skill, "")
    if mems:
        for m in mems[:5]:
            render_memory_card(m)
    else:
        st.caption("No memories yet for this skill.")


# ─── Session 2 tab ───────────────────────────────────────────────────────────

def render_session_2(client: MemantoSkillsClient) -> None:
    st.markdown('<div class="session-header">Session 2 · FRESH context · Cross-session recall</div>', unsafe_allow_html=True)
    st.subheader("Recall engineering context")
    st.caption(
        "This simulates a brand-new terminal session. No shared Python state with Session 1. "
        "The agent recalls everything from Memanto automatically before running the skill."
    )

    col1, col2 = st.columns([3, 2])

    with col1:
        skill = st.selectbox(
            "Skill about to run",
            ["tdd", "grill-with-docs", "diagnose", "general", "handoff"],
            key="s2_skill",
        )
        task_hint = st.text_input(
            "Task hint (what are you working on?)",
            placeholder="e.g. writing tests for the checkout module",
            key="s2_hint",
        )

        if st.button("🔍 Recall context", type="primary", key="s2_recall"):
            with st.spinner("Querying Memanto..."):
                profile = client.recall_for_skill(skill_name=skill, task_hint=task_hint)

            if profile.is_empty:
                st.warning("No memories found. Store some in Session 1 first.")
            else:
                st.success(f"Found {profile.count} memories — injecting into skill context")
                st.markdown("---")
                st.markdown("**Context block that would be injected into the skill:**")
                st.markdown(
                    "<div style='background:#0d0d1a;padding:16px;border-radius:8px;font-size:0.85rem'>"
                    + profile.format_context_block().replace("\n", "<br>")
                    + "</div>",
                    unsafe_allow_html=True,
                )

    with col2:
        st.markdown("**What this means**")
        st.markdown("""
The agent running `/{skill}` would see all your past decisions
*before* it starts asking questions.

- `instruction` memories → **hard rules** it must follow
- `decision` memories → **chosen patterns** it won't re-litigate  
- `preference` memories → **style choices** it respects

**Zero repeated instructions. Zero re-prompting.**
""".format(skill=skill if "skill" in dir() else "tdd"))

        st.markdown("---")
        st.markdown("**Memory types recalled**")
        mems = fetch_memories(client, skill, task_hint if "task_hint" in dir() else "")
        if mems:
            from collections import Counter
            counts = Counter(m.get("type", "unknown") for m in mems)
            for mtype, count in sorted(counts.items()):
                badge_cls = BADGE_CLASS.get(mtype, "badge-default")
                st.markdown(
                    f'<span class="type-badge {badge_cls}">{mtype}</span> {count}',
                    unsafe_allow_html=True,
                )


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    st.title("🧠 Memanto + Claude Code Skills")
    st.caption(
        "Cross-session engineering memory for `mattpocock/skills`. "
        "Decisions stored in Session 1 are automatically recalled in Session 2 — "
        "zero re-prompting across terminals, sessions, or machines."
    )

    try:
        agent_id = st.session_state.get("agent_id", None)
        client = get_client(agent_id)
    except ValueError as e:
        st.error(str(e))
        st.code("export MOORCHEH_API_KEY=your_key_here")
        st.stop()
        return

    # Sidebar
    render_sidebar(client)

    # Main tabs
    tab1, tab2 = st.tabs(["📝 Session 1 — Store decisions", "🔍 Session 2 — Recall context"])

    with tab1:
        render_session_1(client)

    with tab2:
        render_session_2(client)


if __name__ == "__main__":
    main()
