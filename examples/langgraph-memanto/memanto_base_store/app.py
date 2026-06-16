"""Streamlit chat UI for the LangGraph + Memanto cross-session memory demo.

Run with:
    streamlit run app.py

Two chat tabs share the same MemantoStore.  Session 1 stores Bob's
preferences; Session 2 opens a brand-new LangGraph thread_id so the
checkpointer has zero history, yet the agent recalls everything from
Session 1 via MemantoStore.  The right-hand memory panel shows exactly
what is stored in Memanto in real time.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import html
import os
import time
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────

# Timeout for LLM calls (seconds). RetryPolicy may sleep 32 s per attempt x 5.
_LLM_TIMEOUT = 300

# Separate pools so memory-panel fetches don't queue behind a slow LLM call.
_LLM_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
_STORE_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)

SUGGESTED_S1 = (
    "Hi! I'm Bob. I'm severely allergic to peanuts (epi-pen level) "
    "and please only contact me by email at bob@example.com, never by phone."
)
SUGGESTED_S2 = "What snacks would you recommend for a long road trip next weekend?"

KIND_COLORS = {
    "preference": "#0e7490",
    "fact": "#1e40af",
    "commitment": "#7c3aed",
    "goal": "#15803d",
    "instruction": "#b45309",
    "observation": "#475569",
    "relationship": "#9f1239",
    "context": "#374151",
    "decision": "#92400e",
}


# ── Async helpers ─────────────────────────────────────────────────────────────


def _run(
    coro, *, pool: concurrent.futures.ThreadPoolExecutor, timeout: float = _LLM_TIMEOUT
):
    """Run *coro* in *pool*, block with *timeout* seconds. Raises on error."""
    future = pool.submit(asyncio.run, coro)
    return future.result(timeout=timeout)


async def _invoke(graph, thread_id: str, user_msg: str, user_id: str) -> str:
    """Run one turn of the graph and return the assistant's reply as text."""
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=user_msg)]},
        config={"configurable": {"thread_id": thread_id, "user_id": user_id}},
    )
    for m in reversed(result["messages"]):
        if isinstance(m, AIMessage):
            c = m.content
            return (
                c
                if isinstance(c, str)
                else "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in c
                )
            )
    return "(no reply)"


async def _fetch_memories(store, user_id: str, target_namespace: str = "memories"):
    """Return up to 20 memories under ``(user_id, "memories")`` for the panel."""
    return await store.asearch((user_id, target_namespace), query="*", limit=20)


async def _poll_for_memories(
    store, user_id: str, prev_count: int, max_wait_s: float = 12.0
):
    """Wait for newly-stored memories to become searchable.

    Memanto's aput returns as soon as the write is acknowledged; the
    search index catches up asynchronously, taking up to several seconds.
    We poll sparingly (every 3 s, up to 12 s) so we don't burn through
    Memanto's Community-plan recall rate-limit budget. The MemantoStore
    caches results internally, so a poll after the first non-zero result
    is essentially free.
    """
    deadline = time.time() + max_wait_s
    memories = await _fetch_memories(store, user_id)
    while time.time() < deadline and len(memories) <= prev_count:
        await asyncio.sleep(3.0)
        memories = await _fetch_memories(store, user_id)
    return memories


# ── Cached resources ──────────────────────────────────────────────────────────
# Cache key is a hash of graph.py so Streamlit's file-watcher auto-reload
# does NOT silently keep the old compiled graph in memory. Whenever graph.py
# changes the hash changes, _load() is called with a new argument, and
# @st.cache_resource builds a fresh graph with the updated code.


def _graph_hash() -> str:
    """Short MD5 of graph.py. Changes here bust the @st.cache_resource."""
    try:
        src = (Path(__file__).parent / "graph.py").read_bytes()
        return hashlib.md5(src).hexdigest()[:12]
    except Exception:
        return "0"


@st.cache_resource(show_spinner=False)
def _load(_graph_version: str = ""):
    """Set up Memanto + compile the graph once per ``_graph_version`` value.

    ``_graph_version`` is a hash of ``graph.py``; changing it busts the
    cache so edits to graph.py take effect on the next Streamlit rerun
    without a manual server restart.
    """
    from langgraph_memanto import MemantoStore
    from memanto_base_store.graph import build_support_graph

    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    graph = build_support_graph(api_key)
    store = MemantoStore(api_key)
    return graph, store


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="LangGraph + Memanto",
    page_icon="🧠",
    layout="wide",
)

# ── API key guard ─────────────────────────────────────────────────────────────

missing = [k for k in ("MOORCHEH_API_KEY",) if not os.environ.get(k)]
if not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
    missing.append("OPENROUTER_API_KEY or OPENAI_API_KEY")

if missing:
    st.error(
        f"Missing env vars: {', '.join(f'`{k}`' for k in missing)}. "
        "Copy `.env.example` to `.env` and fill them in, then restart."
    )
    st.stop()

graph, store = _load(_graph_version=_graph_hash())

# ── Session state ─────────────────────────────────────────────────────────────


def _init_session(ts: str | None = None) -> None:
    """Initialise (or reset) all demo-scoped session state.

    A fresh suffix (timestamp + 4-char uuid) is used on every call so
    each Streamlit browser session and every explicit reset starts with
    a clean memory namespace. The uuid component guarantees two rapid
    "Reset demo" clicks within the same second still get distinct
    namespaces. Cross-session recall is proven within the same running
    Streamlit session (Session 1 tab -> Session 2 tab), not across app
    restarts.
    """
    suffix = ts or f"{int(time.time())}-{uuid.uuid4().hex[:4]}"
    st.session_state.user_id = f"bob-{suffix}"
    st.session_state.s1_thread = f"streamlit-s1-{suffix}"
    st.session_state.s2_thread = f"streamlit-s2-{suffix}"
    st.session_state.s1 = []
    st.session_state.s2 = []


if "user_id" not in st.session_state:
    _init_session()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🧠 LangGraph + Memanto")
    st.markdown(
        "Demonstrates **cross-session memory recall** using "
        "[Memanto](https://memanto.ai) as a LangGraph `BaseStore`."
    )
    st.divider()
    st.markdown("**How it works**")
    st.markdown(
        "**Session 1** runs inside a LangGraph thread. When you send a message, "
        "the `extract_and_store` node pulls atomic facts from what you said and "
        "writes them to **MemantoStore**, backed by Memanto's cloud.\n\n"
        "**Session 2** starts with a completely fresh `thread_id` and an empty "
        "checkpointer. The `recall_context` node queries MemantoStore and injects "
        "any matching memories as system context, so the agent knows your "
        "preferences without seeing any prior conversation.\n\n"
        "The memory panel on the right shows everything currently stored in "
        "Memanto for this user, updated after each message."
    )
    st.divider()
    st.caption(f"User: `{st.session_state.user_id}`")
    st.caption(f"S1 thread: `{st.session_state.s1_thread}`")
    st.caption(f"S2 thread: `{st.session_state.s2_thread}`")
    st.divider()
    if st.button("🗑️ Clear chat history", use_container_width=True):
        st.session_state.s1 = []
        st.session_state.s2 = []
    st.caption("Clears the chat UI only. Stored memories persist.")
    if st.button("♻️ Reset demo (fresh memory namespace)", use_container_width=True):
        # Pass None so _init_session generates a fresh timestamp+uuid suffix;
        # passing a fixed timestamp here would let two rapid clicks collide.
        _init_session()
        st.rerun()
    st.caption(
        "Switches to a new user namespace so the next run starts with zero memories. "
        "Previous memories remain in Memanto under the old user ID."
    )

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    "### 🧠 LangGraph + Memanto: Cross-Session Memory Demo  "
    "<span style='color:#22c55e;font-size:0.8rem'>● Connected</span>",
    unsafe_allow_html=True,
)
st.caption(
    "**Session 1** stores Bob's preferences in **MemantoStore**. "
    "**Session 2** opens a *completely fresh* `thread_id` with an empty checkpointer, "
    "yet the agent recalls everything Bob said in Session 1."
)
st.divider()

# ── Layout ────────────────────────────────────────────────────────────────────

chat_col, mem_col = st.columns([3, 1], gap="large")

# ── Memory panel ──────────────────────────────────────────────────────────────

with mem_col:
    _mem_error: str | None = None
    try:
        mems = _run(
            _fetch_memories(store, st.session_state.user_id, "memories"),
            pool=_STORE_POOL,
            timeout=15,
        )
    except Exception as _e:
        mems = []
        _mem_error = str(_e)

    count = len(mems)
    st.markdown(f"#### 📦 Stored Memories &nbsp; `{count}`")
    st.caption(f"`('{st.session_state.user_id}', 'memories')` namespace")

    if st.button("🔄 Refresh memories", use_container_width=True):
        st.rerun()

    if _mem_error:
        st.warning(f"Could not fetch memories: {_mem_error}")
    elif not mems:
        st.info("No memories yet.\nSend a message in Session 1 to populate this panel.")
    else:
        for m in mems:
            raw_kind = m.value.get("kind", "fact")
            kind = raw_kind if raw_kind in KIND_COLORS else "fact"
            title = str(m.value.get("title", ""))
            content = str(m.value.get("content", ""))
            conf = m.value.get("confidence")
            color = KIND_COLORS[kind]

            with st.expander(f"**{title or content[:40]}**", expanded=False):
                st.markdown(
                    f"<span style='background:{html.escape(color)};color:white;"
                    f"padding:2px 8px;border-radius:4px;font-size:0.75rem'>"
                    f"{html.escape(kind)}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"> {content}")
                if conf is not None:
                    # Clamp + try/except: Memanto could in principle return a
                    # confidence outside [0, 1] or a non-numeric value; st.progress
                    # throws on either, which would break the whole memory panel
                    # render. Defensive coercion keeps the UI alive.
                    try:
                        clamped = max(0.0, min(1.0, float(conf)))
                        st.progress(clamped, text=f"confidence {clamped:.0%}")
                    except (TypeError, ValueError):
                        pass

# ── Chat ──────────────────────────────────────────────────────────────────────

with chat_col:
    tab1, tab2 = st.tabs(
        [
            "💬 Session 1: Store Preferences",
            "🆕 Session 2: Fresh Thread (Recall)",
        ]
    )

    def _render_history(msgs: list) -> None:
        """Render a list of ``(role, text)`` tuples as Streamlit chat bubbles."""
        for role, text in msgs:
            with st.chat_message(role):
                st.markdown(text)

    def _send(session_key: str, thread_id: str, prompt: str) -> None:
        """Append user message, invoke graph, append reply."""
        user_id = st.session_state.user_id
        # Snapshot the current memory count so the poller knows how many
        # new memories to wait for after this send.
        try:
            prev_mems = _run(
                _fetch_memories(store, user_id), pool=_STORE_POOL, timeout=15
            )
            prev_count = len(prev_mems)
        except Exception:
            prev_count = 0

        st.session_state[session_key].append(("user", prompt))
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking... (LLM may retry on rate-limit, please wait)"):
                try:
                    reply = _run(
                        _invoke(graph, thread_id, prompt, user_id),
                        pool=_LLM_POOL,
                        timeout=_LLM_TIMEOUT,
                    )
                except concurrent.futures.TimeoutError:
                    reply = "Request timed out. The LLM may be rate-limited; try again in a moment."
                except Exception as exc:
                    reply = f"Error: {exc}"
            st.markdown(reply)
        st.session_state[session_key].append(("assistant", reply))

        # Wait for Memanto to index all new memories. aput returns as soon as
        # the write is acknowledged but the search index catches up async,
        # so a single fixed sleep would miss memories that take longer than
        # the sleep window. Polling waits until the count grows past prev_count
        # and stays stable for two ticks (or until a 12 s timeout).
        with st.spinner("Indexing new memories..."):
            try:
                _run(
                    _poll_for_memories(store, user_id, prev_count=prev_count),
                    pool=_STORE_POOL,
                    timeout=30,
                )
            except Exception:
                pass  # fall through to rerun even if polling fails
        st.rerun()  # refresh memory panel

    # ── Tab 1 ─────────────────────────────────────────────────────────────────

    with tab1:
        col_info, col_clear = st.columns([4, 1])
        with col_info:
            st.caption(
                f"`thread_id = {st.session_state.s1_thread!r}`: "
                "Bob shares facts; the graph extracts and stores them in Memanto."
            )
        with col_clear:
            if st.button("Clear", key="clear_s1"):
                st.session_state.s1 = []

        _render_history(st.session_state.s1)

        if not st.session_state.s1:
            st.markdown(
                "<div style='opacity:0.6;font-size:0.85rem'>💡 Try the suggested prompt below</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                f'📋 Use suggested: *"{SUGGESTED_S1[:60]}..."*',
                use_container_width=True,
            ):
                _send("s1", st.session_state.s1_thread, SUGGESTED_S1)

        if prompt1 := st.chat_input(
            "Tell the agent something about Bob...",
            key="s1_input",
        ):
            _send("s1", st.session_state.s1_thread, prompt1)

    # ── Tab 2 ─────────────────────────────────────────────────────────────────

    with tab2:
        col_info2, col_clear2 = st.columns([4, 1])
        with col_info2:
            st.caption(
                f"`thread_id = {st.session_state.s2_thread!r}`: "
                "Checkpointer is **empty**. What the agent knows came from MemantoStore only."
            )
        with col_clear2:
            if st.button("Clear", key="clear_s2"):
                st.session_state.s2 = []

        _render_history(st.session_state.s2)

        if not st.session_state.s2:
            st.markdown(
                "<div style='opacity:0.6;font-size:0.85rem'>"
                "💡 First send a message in <b>Session 1</b>, then ask something here. "
                "The agent will recall Bob's preferences with no prior chat history."
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                f'📋 Use suggested: *"{SUGGESTED_S2}"*', use_container_width=True
            ):
                _send("s2", st.session_state.s2_thread, SUGGESTED_S2)

        if prompt2 := st.chat_input(
            "Ask the agent something... (e.g. snack recommendations)",
            key="s2_input",
        ):
            _send("s2", st.session_state.s2_thread, prompt2)
