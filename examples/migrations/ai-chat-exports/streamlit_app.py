"""Streamlit showcase UI for the Universal Migration Adapter.

Browser interface on top of the CLI: pick a source, load an export, choose
conversations, generate the OKF bundle, import it into Memanto, export it back
to portable OKF, and query it back with recall/answer.

Run:
    pip install streamlit
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapters  # noqa: F401
import streamlit as st
from core.adapters import ADAPTERS
from core.okf_generator import OKFGenerator
from generate_report import build_report

_NO_AGENT = (
    "No active agent",
    "No active session",
    "Call activate_agent()",
)

# Browser-provided paths must stay inside the migration workspace so a shared
# Streamlit server cannot read or write arbitrary files on the host.
_WORKSPACE = Path(__file__).resolve().parent


def _workspace_path(raw: str, *, for_write: bool = False) -> Path:
    """Resolve *raw* inside the migration workspace.

    Relative paths are resolved against the workspace; absolute paths that
    point outside the workspace are rejected (or reused only when they are
    already inside it) to prevent path traversal / arbitrary file access.
    """
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = _WORKSPACE / path
    path = path.resolve()
    try:
        path.relative_to(_WORKSPACE)
    except ValueError:
        raise ValueError(
            f"Path outside the migration workspace is not allowed: {path}"
        )
    if for_write:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _active_agent_hint() -> str:
    """Return a help string for activating a Memanto agent."""
    return (
        "Memanto needs an active agent for this step.\n"
        "Activate one first, for example:\n"
        "  memanto agent activate claude-migration\n"
        "or pass --agent <id>."
    )


def _is_no_agent(output: str) -> bool:
    """Check whether *output* contains a 'no active agent' signal."""
    return any(token.lower() in output.lower() for token in _NO_AGENT)


def _run_memanto(cmd: list[str]) -> tuple[int, str, str]:
    """Run a ``memanto`` CLI subcommand and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "memanto", *cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _show_cmd_error(cmd_name: str, rc: int, out: str, err: str) -> None:
    """Display a Memanto command error in the Streamlit UI."""
    combined = (out + "\n" + err).strip()
    if _is_no_agent(combined):
        st.warning(f"**{cmd_name}: agent not active.**")
        st.info(_active_agent_hint())
        st.code(combined, language="text")
    else:
        st.error(f"**{cmd_name} failed** (exit {rc})")
        st.code(combined, language="text")


st.set_page_config(page_title="Universal Migration Adapter", layout="wide")
st.title("Universal Migration Adapter")
st.caption("ChatGPT / Claude / Gemini exports → OKF bundles → Memanto → portable OKF")

source = st.sidebar.selectbox("Source", list(ADAPTERS.keys()))
input_path = st.sidebar.text_input("Export path", "./conversations.json")

st.sidebar.markdown("### Options")
use_dry_run = st.sidebar.checkbox("Dry run (preview only)", value=False)
output_dir = st.sidebar.text_input("Output directory", "./okf_output/streamlit")
agent = st.sidebar.text_input("Memanto agent", "claude-migration")

adapter = ADAPTERS[source]()

if st.button("Read export"):
    try:
        resolved_input = _workspace_path(input_path)
        if not resolved_input.is_file():
            raise FileNotFoundError(f"Export file not found: {resolved_input}")
        raw = adapter.load(str(resolved_input))
        st.session_state["raw"] = raw
        st.session_state["conv_list"] = adapter.get_conversation_list(raw)
        st.session_state["bundle"] = None
        st.session_state["_source_key"] = source
        st.success(f"Loaded {len(st.session_state['conv_list'])} conversations.")
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to load: {e}")

if source != st.session_state.get("_source_key"):
    st.session_state.pop("raw", None)
    st.session_state.pop("conv_list", None)
    st.session_state.pop("bundle", None)
    st.session_state.pop("entities", None)
    st.session_state.pop("_source_key", None)
    st.rerun()

conv_list = st.session_state.get("conv_list")
if conv_list is not None:
    st.subheader("Conversations")
    options = [
        f"[{i + 1}] {c['title']} ({c['message_count']} msgs)"
        for i, c in enumerate(conv_list)
    ]
    selected = st.multiselect(
        "Select conversations", options, default=[], key="conv_select"
    )
    selected_ids = [
        conv_list[i]["id"] for i, label in enumerate(options) if label in selected
    ]

    if st.button("Generate OKF bundle"):
        raw = st.session_state["raw"]
        filters = {}
        if selected_ids:
            filters["chat_ids"] = selected_ids
        entities = adapter.extract(raw, filters)
        if not entities:
            st.warning("No entities matched. Check filters / input.")
        else:
            if use_dry_run:
                st.subheader("Dry-run preview")
                for i, e in enumerate(entities[:10]):
                    st.markdown(f"**[{i + 1}]** [{e.source_type.value}] {e.title[:60]}")
                    st.caption(f"Tags: {', '.join(e.tags)}")
                if len(entities) > 10:
                    st.caption(f"... and {len(entities) - 10} more")
                st.info("Dry run — no files written.")
            else:
                bundle_base = _workspace_path(output_dir, for_write=True)
                path = OKFGenerator(str(bundle_base)).generate_bundle(entities)
                st.session_state["bundle"] = path
                st.session_state["entities"] = entities
                selected_count = len(selected_ids) if selected_ids else len(conv_list)
                st.session_state["conv_count"] = selected_count
                st.session_state["input_path"] = input_path
                st.session_state["report"] = None
                st.success(
                    f"Generated OKF bundle with {len(entities)} memories at `{path}`"
                )

bundle_path = st.session_state.get("bundle")
if bundle_path is not None:
    st.subheader("Generated bundle")
    md_files = sorted(Path(bundle_path).rglob("*.md"))
    preview_file = st.selectbox(
        "Preview file", [str(p.relative_to(bundle_path)) for p in md_files]
    )
    if preview_file:
        content = (Path(bundle_path) / preview_file).read_text(encoding="utf-8")
        st.code(content, language="markdown")

    st.markdown("#### Memanto import")
    if st.button("Import into Memanto (dry run)"):
        rc, out, err = _run_memanto(
            ["migrate", "okf", str(bundle_path), "--dry-run", "--agent", agent]
        )
        if rc == 0:
            st.success("Dry run OK — import preview:")
            st.code((out + err).strip(), language="text")
        else:
            _show_cmd_error("Import (dry run)", rc, out, err)

    if st.button("Import into Memanto (real)"):
        rc, out, err = _run_memanto(
            ["migrate", "okf", str(bundle_path), "--agent", agent]
        )
        if rc == 0:
            st.success("Imported into Memanto.")
            st.code((out + err).strip(), language="text")
        else:
            _show_cmd_error("Import", rc, out, err)

    st.markdown("#### Report")
    report_path_input = st.text_input(
        "Report file path", "./REPORT.md", key="report_path"
    )
    if st.button("Generate report"):
        entities = st.session_state.get("entities") or []
        if not entities:
            st.warning("Generate the OKF bundle first.")
        else:
            report_target = _workspace_path(report_path_input, for_write=True)
            report_text = build_report(
                source=source,
                input_path=st.session_state.get("input_path", input_path),
                output_dir=str(bundle_path),
                entities=entities,
                conv_count=st.session_state.get("conv_count", 0),
                export_dir=None,
            )
            report_target.write_text(report_text, encoding="utf-8")
            st.session_state["report"] = report_text
            st.session_state["report_file"] = str(report_target.resolve())
            st.success(f"Report written to `{report_target}`")

if st.session_state.get("report_file") is not None:
    st.markdown("### Generated report")
    st.caption(st.session_state["report_file"])
    report_md = st.session_state.get("report")
    if report_md:
        with st.expander("View REPORT.md"):
            st.code(report_md, language="markdown")

st.sidebar.markdown("### Export / Query")
export_dir = st.sidebar.text_input(
    "Export dir", str(_WORKSPACE / "okf_export")
)

if st.button("Export OKF bundle from Memanto"):
    try:
        export_target = str(_workspace_path(export_dir, for_write=True))
    except ValueError as e:
        st.error(str(e))
        export_target = None
    if export_target:
        rc, out, err = _run_memanto(
            ["memory", "export", "--agent", agent, "--okf", "-o", export_target]
        )
        if rc == 0:
            st.session_state["export_bundle"] = export_target
            st.success(f"Exported OKF bundle to `{export_target}`")
            st.code((out + err).strip(), language="text")
        else:
            _show_cmd_error("Export", rc, out, err)

export_bundle = st.session_state.get("export_bundle")
if export_bundle is not None:
    st.subheader("Exported bundle")
    md_files = sorted(Path(export_bundle).rglob("*.md"))
    preview_file = st.selectbox(
        "Preview exported file", [str(p.relative_to(export_bundle)) for p in md_files]
    )
    if preview_file:
        content = (Path(export_bundle) / preview_file).read_text(encoding="utf-8")
        st.code(content, language="markdown")

question = st.text_input(
    "Question to query the migrated memory", value="What database should we use?"
)

if st.button("Answer from Memanto"):
    rc, out, err = _run_memanto(["answer", question])
    if rc == 0:
        st.success("Answer:")
        st.write(out.strip())
        if err.strip():
            st.code(err.strip(), language="text")
    else:
        _show_cmd_error("Answer", rc, out, err)
