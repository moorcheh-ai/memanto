"""
Memanto Migration UI

Streamlit app for migrating AI conversation exports into Memanto.
Covers ZIP providers (ChatGPT, Claude, Gemini) and API-key providers
(Mem0, Letta, Supermemory, Zep, Hindsight).

Run:
    streamlit run examples/migrations/app.py
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import streamlit as st

# Allow running as `streamlit run app.py` from inside examples/migrations/
# as well as `streamlit run examples/migrations/app.py` from the repo root.
_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
for _p in (_HERE, _REPO_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

st.set_page_config(
    page_title="Memanto Migration",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Explicit widget key for the API-key-provider selectbox. Giving it a key
# means we control its value directly through session_state, instead of
# letting Streamlit's default "remembered widget state" silently win over
# our own state changes on rerun (this was the root cause of the "can't
# switch back to a ZIP provider" bug).
API_SOURCE_KEY = "api_source_select"

# ---------------------------------------------------------------------------
# Lazy imports — memanto must be installed (pip install -e .)
# ---------------------------------------------------------------------------

@st.cache_resource
def _load_memanto():
    """
    Load the Memanto migration components required by the application.
    
    Returns:
    	tuple: The mapper registry, migration runner, and SDK client class.
    """
    try:
        from mappers import MAPPERS
        from runner import run_migration
        from memanto.cli.client.sdk_client import SdkClient
        return MAPPERS, run_migration, SdkClient
    except ImportError:
        pass
    try:
        from examples.migrations.mappers import MAPPERS
        from examples.migrations.runner import run_migration
        from memanto.cli.client.sdk_client import SdkClient
        return MAPPERS, run_migration, SdkClient
    except ImportError as exc:
        st.error(f"memanto package not found. Run `pip install -e .` from the repo root.\n\n{exc}")
        st.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_gemini_archive(tmp_path: Path) -> dict[str, Any]:
    """
    Normalize a Google Takeout Gemini archive into a memory export.
    
    Parameters:
    	tmp_path (Path): Directory containing the extracted archive files.
    
    Returns:
    	dict[str, Any]: A dictionary with a `memories` list containing normalized conversation records.
    """
    import re

    json_hits = list(tmp_path.rglob("My Activity.json"))
    html_hits = list(tmp_path.rglob("My Activity.html"))

    if json_hits:
        entries = json.loads(json_hits[0].read_text(encoding="utf-8"))
        memories = []
        for entry in entries or []:
            title = entry.get("title") or ""
            if not title.startswith("Prompted "):
                continue
            prompt = title[len("Prompted "):]
            if not prompt.strip():
                continue
            memories.append({"createdTime": entry.get("time"), "messages": [{"role": "user", "text": prompt}]})
        return {"memories": memories}

    if html_hits:
        # basic extraction from HTML activity
        raw = html_hits[0].read_text(encoding="utf-8", errors="replace")
        entries = re.findall(r'Prompted\s+(.*?)(?=Prompted\s|$)', raw, re.DOTALL)
        memories = []
        for e in entries:
            text = re.sub(r'<[^>]+>', '', e).strip()
            if text:
                memories.append({"messages": [{"role": "user", "text": text[:500]}]})
        return {"memories": memories}

    candidates = [f for f in tmp_path.rglob("*.json") if f.name != "My Activity.json"]
    memories = []
    for f in candidates:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "messages" in item:
                        memories.append(item)
            elif isinstance(data, dict) and "messages" in data:
                memories.append(data)
        except Exception:
            continue
    return {"memories": memories}


def _load_export_from_bytes(file_bytes: bytes, source: str) -> dict[str, Any]:
    """
    Load a provider export ZIP and normalize its contents into a migration-ready structure.
    
    Parameters:
        file_bytes (bytes): The uploaded ZIP archive contents.
        source (str): The provider identifier used to select the archive format.
    
    Returns:
        dict[str, Any]: The normalized export data.
    
    Raises:
        SystemExit: Stops the Streamlit app when the archive is invalid, contains unsafe paths, or lacks the required conversation file.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                for member in zf.infolist():
                    dest = (tmp_path / member.filename).resolve()
                    if not dest.is_relative_to(tmp_path.resolve()):
                        st.error("ZIP archive contains unsafe paths and cannot be extracted.")
                        st.stop()
                zf.extractall(tmp)
        except zipfile.BadZipFile:
            st.error("Could not read the ZIP file. Make sure you uploaded a valid export archive.")
            st.stop()

        if source in ("chatgpt", "claude"):
            json_file = tmp_path / "conversations.json"
            if not json_file.exists():
                candidates = list(tmp_path.rglob("conversations.json"))
                if not candidates:
                    st.error("conversations.json not found in the ZIP. Make sure you exported the right file.")
                    st.stop()
                json_file = candidates[0]
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                st.error(f"conversations.json is not valid JSON: {exc}")
                st.stop()
            return {"memories": raw} if isinstance(raw, list) else raw

        return _parse_gemini_archive(tmp_path)


def _fetch_export(source: str, provider_key: str, **kwargs) -> dict | None:
    """
    Fetch and cache an export for an API-based provider.
    
    Parameters:
        source (str): Provider identifier used to select the export handler.
        provider_key (str): Provider API key.
        **kwargs: Optional provider-specific settings, including the Hindsight base URL.
    
    Returns:
        dict | None: The fetched export, or `None` if fetching fails.
    """
    import hashlib
    raw = f"{source}:{provider_key}:{kwargs.get('base_url', '')}"
    cache_key = "export_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    if st.session_state.get(cache_key):
        return st.session_state[cache_key]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if source == "mem0":
                from memanto.cli.analyze.mem0_export import run_mem0_export
                _, export = run_mem0_export(provider_key, tmp_path)
            elif source == "letta":
                from memanto.cli.analyze.letta_export import run_letta_export
                _, export = run_letta_export(provider_key, tmp_path)
            elif source == "supermemory":
                from memanto.cli.analyze.supermemory_export import run_supermemory_export
                _, export = run_supermemory_export(provider_key, tmp_path)
            elif source == "zep":
                try:
                    from exporters.zep_export import run_zep_export
                except ImportError:
                    from examples.migrations.exporters.zep_export import run_zep_export
                _, export = run_zep_export(provider_key, tmp_path)
            elif source == "hindsight":
                try:
                    from exporters.hindsight_export import run_hindsight_export
                except ImportError:
                    from examples.migrations.exporters.hindsight_export import run_hindsight_export
                base_url = kwargs.get("base_url")
                kw = {"base_url": base_url} if base_url else {}
                _, export = run_hindsight_export(provider_key, tmp_path, **kw)
            else:
                raise ValueError(f"Unknown source: {source}")
        st.session_state[cache_key] = export
        return export
    except Exception as exc:
        st.error(str(exc))
        return None


def _run_dry_run(source: str, export: dict[str, Any]) -> tuple[list[dict], dict]:
    """
    Generate a preview of the memories mapped from an export without performing migration.
    
    Parameters:
    	source (str): Provider identifier for the export.
    	export (dict[str, Any]): Normalized provider export to process.
    
    Returns:
    	tuple[list[dict], dict]: Mapped memory rows and a migration summary.
    """
    _, run_migration, _ = _load_memanto()
    summary, rows = run_migration(
        provider=source,
        export=export,
        client=None,
        agent_id="",
        dry_run=True,
        on_progress=lambda msg: None,
    )
    return rows, summary.as_dict()


def _do_migrate(source: str, export: dict[str, Any], agent_id: str, api_key: str) -> dict:
    _, run_migration, SdkClient = _load_memanto()
    client = SdkClient(api_key=api_key)
    client.activate_agent(agent_id, duration_hours=2)
    try:
        summary, _ = run_migration(
            provider=source,
            export=export,
            client=client,
            agent_id=agent_id,
            dry_run=False,
            on_progress=lambda msg: None,
        )
    finally:
        client.deactivate_agent(agent_id)
    return summary.as_dict()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

PROVIDERS = {
    "chatgpt":     "ChatGPT",
    "claude":      "Claude",
    "gemini":      "Gemini",
    "mem0":        "Mem0",
    "letta":       "Letta",
    "supermemory": "Supermemory",
    "zep":         "Zep",
    "hindsight":   "Hindsight",
}

_ICO_DIR = Path(__file__).parent / "ico"

PROVIDER_LOGOS = {
    "chatgpt":     str(_ICO_DIR / "chatgpt.svg"),
    "claude":      str(_ICO_DIR / "claude.svg"),
    "gemini":      str(_ICO_DIR / "gemini.svg"),
    "mem0":        str(_ICO_DIR / "mem0.svg"),
    "letta":       str(_ICO_DIR / "letta.svg"),
    "supermemory": str(_ICO_DIR / "supermemory.svg"),
    "zep":         str(_ICO_DIR / "zep.svg"),
    "hindsight":   str(_ICO_DIR / "hindsight.svg"),
}

API_KEY_PROVIDERS = {
    "mem0":        "MEM0_API_KEY",
    "letta":       "LETTA_API_KEY",
    "supermemory": "SUPERMEMORY_API_KEY",
    "zep":         "ZEP_API_KEY",
    "hindsight":   "HINDSIGHT_API_KEY",
}


def _render_api_key_panel(source: str, agent_id: str, api_key: str) -> None:
    """
    Render API-key-based export controls, migration actions, and their results.
    
    Parameters:
        source (str): Provider identifier used to select the required API key and export workflow.
        agent_id (str): Target namespace identifier for migration.
        api_key (str): Moorcheh API key from the sidebar.
    """
    env_var = API_KEY_PROVIDERS[source]
    key = st.text_input(env_var, type="password", value=os.environ.get(env_var, ""))

    base_url = ""
    if source == "hindsight":
        base_url = st.text_input(
            "HINDSIGHT_BASE_URL",
            value="https://api.hindsight.vectorize.io",
        )

    uploaded = st.file_uploader(
        "Optional: pre-exported JSON (skips live API call)",
        type=["json"],
        key=f"upload_{source}",
    )
    export: dict | None = None
    if uploaded:
        try:
            export = json.loads(uploaded.read())
        except Exception as exc:
            st.error(str(exc))
            return

    col_dry, col_migrate = st.columns(2)

    with col_dry:
        if st.button("🔍 Dry run", use_container_width=True):
            if not key.strip():
                st.warning(f"{env_var} is required.")
            elif source == "hindsight" and not base_url.strip():
                st.warning("HINDSIGHT_BASE_URL is required.")
            else:
                live = export
                if live is None:
                    with st.spinner("Fetching export..."):
                        live = _fetch_export(source, key.strip(), base_url=base_url.strip())
                if live is not None:
                    with st.spinner("Mapping records..."):
                        rows, summary = _run_dry_run(source, live)
                    st.session_state[f"dry_run_rows_{source}"] = rows
                    st.session_state[f"dry_run_summary_{source}"] = summary
                    st.session_state.pop(f"migrate_result_{source}", None)

    with col_migrate:
        if st.button("🚀 Migrate", type="primary", use_container_width=True):
            if not key.strip():
                st.warning(f"{env_var} is required.")
            elif not agent_id:
                st.warning("Select or create a target namespace in the sidebar.")
            elif source == "hindsight" and not base_url.strip():
                st.warning("HINDSIGHT_BASE_URL is required.")
            elif not api_key:
                st.warning("Enter your Moorcheh API Key in the sidebar first.")
            else:
                live = export
                if live is None:
                    with st.spinner("Fetching export..."):
                        live = _fetch_export(source, key.strip(), base_url=base_url.strip())
                if live is not None:
                    with st.spinner("Migrating..."):
                        result = _do_migrate(source, live, agent_id, api_key)
                    st.session_state[f"migrate_result_{source}"] = result

    summary = st.session_state.get(f"dry_run_summary_{source}")
    rows = st.session_state.get(f"dry_run_rows_{source}")
    migrate_result = st.session_state.get(f"migrate_result_{source}")

    if migrate_result:
        imported = migrate_result["imported"]
        failed = migrate_result["failed"]
        if failed == 0:
            st.success(f"Migration complete! {imported} memories imported into `{agent_id}`.")
        else:
            st.warning(f"Done with errors. Imported: {imported}, Failed: {failed}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Imported", imported)
        m2.metric("Failed", failed)
        m3.metric("Batches", migrate_result["batches"])
        if migrate_result.get("errors"):
            with st.expander("Errors", expanded=False):
                for err in migrate_result["errors"]:
                    st.code(err)

    if summary:
        st.divider()
        st.markdown("### Preview")
        m1, m2, m3 = st.columns(3)
        m1.metric("Source records", summary["source_count"])
        m2.metric("Mapped memories", summary["mapped_count"])
        m3.metric("Skipped (empty)", summary["skipped"])
        if summary.get("type_counts"):
            st.markdown("**Type breakdown**")
            st.json(summary["type_counts"])
        if rows:
            st.markdown("**Sample memories**")
            for row in rows[:5]:
                with st.expander(row.get("title", "Memory")[:80], expanded=False):
                    st.markdown(f"**Content:**\n\n{row.get('content', '')[:600]}")
                    st.markdown(f"**Type:** `{row.get('type') or 'auto'}`  |  **Source:** `{row.get('source')}`  |  **Provenance:** `{row.get('provenance')}`")
            if len(rows) > 5:
                st.caption(f"...and {len(rows) - 5} more memories")

def _svg_data_uri(path: str) -> str:
    """Convert an SVG file to a base64-encoded data URI.
    
    Parameters:
    	path (str): Path to the SVG file.
    
    Returns:
    	str: Data URI containing the encoded SVG content.
    """
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:image/svg+xml;base64,{b64}"

EXPORT_INSTRUCTIONS = {
    "chatgpt": "**ChatGPT:** Settings → Data controls → Export data → confirm email → download ZIP",
    "claude": "**Claude:** claude.ai → Account settings → Privacy → Export data → download ZIP",
    "gemini": "**Gemini:** [takeout.google.com](https://takeout.google.com) → Deselect all → My Activity → Gemini Apps → JSON → Create export → download ZIP",
}


def _fetch_agents(api_key: str) -> tuple[list[str], str | None]:
    try:
        _, _, SdkClient = _load_memanto()
        client = SdkClient(api_key=api_key)
        result = client.list_agents()
        return [a["agent_id"] for a in (result.get("agents") or []) if a.get("agent_id")], None
    except Exception as exc:
        return [], str(exc)


def _create_agent(api_key: str, agent_id: str) -> tuple[bool, str]:
    from memanto.app.utils.errors import AgentAlreadyExistsError

    try:
        _, _, SdkClient = _load_memanto()
        client = SdkClient(api_key=api_key)
        client.create_agent(agent_id=agent_id, pattern="tool")
        return True, f"Namespace '{agent_id}' created."
    except AgentAlreadyExistsError:
        return True, f"Namespace '{agent_id}' already exists — using it."
    except Exception as exc:
        return False, str(exc)


def sidebar():
    """
    Render the sidebar configuration and return the selected API key and namespace.
    
    Returns:
        tuple[str, str]: The Moorcheh API key and selected namespace identifier.
    """
    with st.sidebar:
        st.image("https://raw.githubusercontent.com/moorcheh-ai/memanto/main/assets/memanto-logo.svg", width=140)
        st.markdown("## Memanto Migration")
        st.markdown("Liberate the memory your AI assistant has built about you.")
        st.divider()
        st.markdown("### Configuration")

        api_key = st.text_input(
            "Moorcheh API Key",
            type="password",
            value=os.environ.get("MOORCHEH_API_KEY", ""),
            help="Get yours at moorcheh.ai",
        )

        agent_id = ""

        if api_key:
            prev_key = st.session_state.get("_loaded_api_key")
            if prev_key != api_key:
                with st.spinner("Loading namespaces..."):
                    agents, agents_err = _fetch_agents(api_key)
                    st.session_state["agents"] = agents
                    st.session_state["_agents_error"] = agents_err
                st.session_state["_loaded_api_key"] = api_key
                # a new key means any previously selected namespace no longer applies
                st.session_state.pop("agent_id", None)

            agents: list[str] = st.session_state.get("agents", [])
            agents_err: str | None = st.session_state.get("_agents_error")
            CREATE_OPT = "+ Create new namespace"

            if agents_err:
                st.error(agents_err)

            if not agents:
                # Brand new key, or a key with no namespaces yet — skip straight
                # to the creation form instead of showing a dropdown with a
                # single "+ Create new namespace" option in it.
                st.caption("No namespaces found for this key yet — create one to get started.")
                choice = CREATE_OPT
            else:
                options = agents + [CREATE_OPT]
                if st.session_state.get("agent_id") in agents:
                    default_idx = options.index(st.session_state["agent_id"])
                else:
                    default_idx = 0
                choice = st.selectbox("Target namespace", options, index=default_idx)

            if choice == CREATE_OPT:
                new_id = st.text_input("New namespace ID", placeholder="e.g. my-memory-namespace")
                create_clicked = st.button(
                    "Create namespace",
                    use_container_width=True,
                    disabled=not new_id.strip(),
                )
                if create_clicked:
                    ok, msg = _create_agent(api_key, new_id.strip())
                    if ok:
                        st.success(msg)
                        fetched, _ = _fetch_agents(api_key)
                        if new_id.strip() not in fetched:
                            fetched.append(new_id.strip())
                        st.session_state["agents"] = fetched
                        st.session_state["_agents_error"] = None
                        st.session_state["agent_id"] = new_id.strip()
                        st.rerun()
                    else:
                        st.error(msg)
                agent_id = st.session_state.get("agent_id", "")
            else:
                agent_id = choice
                st.session_state["agent_id"] = agent_id

            if agent_id:
                st.caption(f"Selected: `{agent_id}`")
        else:
            st.caption("Enter your API key to load your namespaces.")

        st.divider()
        st.markdown("**Supported providers:**")
        for provider, name in PROVIDERS.items():
            st.markdown(
                f'<img src="{_svg_data_uri(PROVIDER_LOGOS[provider])}" height="16" style="vertical-align:middle;margin-right:6px">{name}',
                unsafe_allow_html=True,
            )
        st.divider()
        st.markdown("[GitHub](https://github.com/moorcheh-ai/memanto) · [Docs](https://docs.memanto.ai)")
    return api_key, agent_id


def main():
    """
    Run the Streamlit application for selecting an export provider, previewing mapped memories, and migrating them into Memanto.
    
    The interface supports ZIP-based conversation exports and API-key-based providers, and displays migration results when available.
    """
    api_key, agent_id = sidebar()

    st.title("🧠 Memanto Migration")
    st.markdown("Upload your AI conversation export and migrate your memories into Memanto.")

    ZIP_PROVIDERS = ["chatgpt", "claude", "gemini"]
    col1, col2, col3 = st.columns(3)
    for col, provider in zip((col1, col2, col3), ZIP_PROVIDERS):
        with col:
            icon_uri = _svg_data_uri(PROVIDER_LOGOS[provider])
            if st.button(f"![]({icon_uri}) {PROVIDERS[provider]}", use_container_width=True):
                st.session_state["source"] = provider
                # Reset the API-key selectbox's own widget state *before* it
                # renders below. Without this, the selectbox would still be
                # holding whatever API-key provider was previously chosen,
                # and the block underneath would immediately overwrite
                # "source" back to that stale value on this same rerun —
                # this was the reason the ZIP buttons appeared "stuck".
                st.session_state[API_SOURCE_KEY] = "—"

    st.divider()
    st.subheader("API-key providers")

    current_source = st.session_state.get("source")
    api_options = ["—"] + list(API_KEY_PROVIDERS.keys())

    if API_SOURCE_KEY not in st.session_state:
        st.session_state[API_SOURCE_KEY] = current_source if current_source in API_KEY_PROVIDERS else "—"

    api_source = st.selectbox(
        "Select provider",
        api_options,
        format_func=lambda k: PROVIDERS.get(k, k),
        key=API_SOURCE_KEY,
    )

    if api_source != "—":
        st.session_state["source"] = api_source
    elif current_source in API_KEY_PROVIDERS:
        # Dropdown was explicitly reset to "—" while an API provider was
        # active — clear the selected source rather than leaving a stale
        # provider active with no visible selection anywhere.
        st.session_state["source"] = None

    source = st.session_state.get("source")

    if not source:
        st.info("Select a provider above to get started.")
        st.divider()
        st.markdown("### How it works")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**1. Export**\nDownload your conversation history from ChatGPT, Claude or Gemini.")
        with c2:
            st.markdown("**2. Upload**\nDrop the ZIP file here. Nothing leaves your machine until you click Migrate.")
        with c3:
            st.markdown("**3. Own it**\nYour memories land in Memanto and export as portable OKF markdown.")
        return

    st.markdown(f"### {PROVIDERS[source]} Migration")
    st.markdown(
        f'<img src="{_svg_data_uri(PROVIDER_LOGOS[source])}" height="32" style="vertical-align:middle;margin-right:8px">',
        unsafe_allow_html=True,
    )

    if source in API_KEY_PROVIDERS:
        _render_api_key_panel(source, agent_id, api_key)
        return

    st.info(EXPORT_INSTRUCTIONS[source])

    uploaded = st.file_uploader(
        f"Upload your {PROVIDERS[source]} export ZIP",
        type=["zip"],
        key=f"upload_{source}",
    )

    if not uploaded:
        return

    file_bytes = uploaded.read()

    with st.spinner("Parsing export..."):
        export = _load_export_from_bytes(file_bytes, source)

    memory_count = len(export.get("memories", []))
    st.success(f"Loaded {memory_count} conversation records from the export.")

    if st.button("🔍 Preview mapped memories (dry run)", use_container_width=True):
        with st.spinner("Mapping records..."):
            rows, summary = _run_dry_run(source, export)
        # Namespaced per-source so switching ChatGPT -> Claude -> Gemini
        # (or back) can never show a stale preview left over from a
        # different provider.
        st.session_state[f"preview_rows_{source}"] = rows
        st.session_state[f"preview_summary_{source}"] = summary

    if st.session_state.get(f"preview_rows_{source}"):
        rows = st.session_state[f"preview_rows_{source}"]
        summary = st.session_state[f"preview_summary_{source}"]

        st.divider()
        st.markdown("### Preview")
        m1, m2, m3 = st.columns(3)
        m1.metric("Source records", summary["source_count"])
        m2.metric("Mapped memories", summary["mapped_count"])
        m3.metric("Skipped (empty)", summary["skipped"])

        if summary.get("type_counts"):
            st.markdown("**Type breakdown**")
            st.json(summary["type_counts"])

        st.markdown("**Sample memories**")
        for row in rows[:5]:
            with st.expander(row.get("title", "Memory")[:80], expanded=False):
                st.markdown(f"**Content:**\n\n{row.get('content', '')[:600]}")
                st.markdown(f"**Type:** `{row.get('type') or 'auto'}`  |  **Source:** `{row.get('source')}`  |  **Provenance:** `{row.get('provenance')}`")

        if len(rows) > 5:
            st.caption(f"...and {len(rows) - 5} more memories")

        st.divider()

        if not agent_id:
            st.warning("Select or create a target namespace in the sidebar to migrate.")
        elif not api_key:
            st.warning("Enter your Moorcheh API Key in the sidebar to migrate.")
        else:
            if st.button(f"🚀 Migrate {summary['mapped_count']} memories into {agent_id}", type="primary", use_container_width=True):
                with st.spinner(f"Migrating {summary['mapped_count']} memories..."):
                    result = _do_migrate(source, export, agent_id, api_key)

                if result["failed"] == 0:
                    st.success(f"Migration complete! {result['imported']} memories imported into agent `{agent_id}`.")
                else:
                    st.warning(f"Done with errors. Imported: {result['imported']}, Failed: {result['failed']}")

                st.markdown("**Migration summary**")
                st.json(result)

                st.divider()
                st.markdown("### Export to OKF")
                st.code(f"memanto memory export --okf --output okf_bundle/ --agent {agent_id}", language="bash")
                st.caption("Run the above command in your terminal to export your memories as portable markdown.")


if __name__ == "__main__":
    main()