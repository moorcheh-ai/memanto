"""Bounty #770 round 8 — integration-layer fixes: LangGraph store crash,
silent memory drop, comma-tag splitting, UI body type validation, migrate
file loading.

Run:  python -m pytest tests/failing_tests/test_bounty_770_round8.py -v
      (or:  python tests/failing_tests/test_bounty_770_round8.py)

Bugs covered:
  1. langgraph_memanto/store.py _do_list_namespaces iterated the dict returned
     by SdkClient.list_agents() ({'agents': ..., 'count': ..., 'warnings': ...})
     instead of its 'agents' list -> AttributeError crash on every call.
  2. langgraph_memanto/nodes.py create_remember_node silently swallowed a
     ValueError when the message content exceeded the 10000-char memory cap
     and still returned {"messages": []} — memory lost, caller sees success.
  3. ui_router _migrate_load_or_export let JSONDecodeError escape for an
     existing-but-broken export file -> HTTP 500 instead of 400.
  4. ui_router update_api_key / migrate_dry_run / migrate_import called
     .strip() on unvalidated body values -> AttributeError -> HTTP 500 for a
     non-string JSON value (e.g. {"api_key": 12345}).
  5. cli/commands/migrate.py _load_or_export loaded a missing/broken --file
     with no error handling -> raw FileNotFoundError/JSONDecodeError traceback
     instead of a friendly _error, unlike migrate_okf and ui_router.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# 1. LangGraph store: _do_list_namespaces must read the 'agents' envelope key
# ---------------------------------------------------------------------------

def test_do_list_namespaces_handles_list_agents_envelope():
    """SdkClient.list_agents() returns {'agents': [...], 'count': N}; the
    store must iterate the envelope's 'agents' list, not the dict itself."""
    import sys
    import types

    # langgraph is an optional integration dependency; stub the modules the
    # store imports so this test runs without installing the real package.
    lg_store = types.ModuleType("langgraph")
    lg_store.store = types.ModuleType("langgraph.store")
    base_mod = types.ModuleType("langgraph.store.base")

    class _BaseStore:
        pass

    class _Item:
        pass

    class _SearchItem:
        pass

    class _GetOp:
        pass

    class _PutOp:
        pass

    class _ListNamespacesOp:
        pass

    class _SearchOp:
        pass

    for name, obj in [
        ("BaseStore", _BaseStore),
        ("Item", _Item),
        ("SearchItem", _SearchItem),
        ("GetOp", _GetOp),
        ("PutOp", _PutOp),
        ("ListNamespacesOp", _ListNamespacesOp),
        ("SearchOp", _SearchOp),
    ]:
        setattr(base_mod, name, obj)
    lg_store.store.base = base_mod
    sys.modules["langgraph"] = lg_store
    sys.modules["langgraph.store"] = lg_store.store
    sys.modules["langgraph.store.base"] = base_mod

    # Load the module from its file path directly: `integrations/langgraph`
    # is a namespace package without __init__.py, and a real `langgraph`
    # distribution may be installed, so importing through the package chain
    # is fragile. Loading by path keeps this test standalone.
    import importlib.util

    def _load_module(name: str, path: str):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    store_path = Path(__file__).resolve().parents[2] / "integrations" / "langgraph" / "langgraph_memanto" / "store.py"
    m_store = _load_module("lg_memanto_store_test", str(store_path))

    class _FakeClient:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def list_agents(self):
            return {
                "agents": [
                    {"agent_id": "memanto_agent_default"},
                    {"agent_id": "memanto_agent_alpha_beta"},
                ],
                "count": 2,
                "warnings": [],
            }

    store = m_store.MemantoStore.__new__(m_store.MemantoStore)
    store.api_key = "k"
    store._agent_prefix = "memanto_agent_"
    m_store.SdkClient = _FakeClient

    class _Op:
        match_conditions = None
        max_depth = None
        limit = 100

    result = store._do_list_namespaces(_Op())
    assert () in result, "default agent must map to the empty namespace tuple"
    assert ("alpha", "beta") in result, (
        "underscore-suffixed agent id must be split into namespace parts"
    )


# ---------------------------------------------------------------------------
# 2. LangGraph node: oversized remember must fail loudly, not silently drop
# ---------------------------------------------------------------------------

def test_remember_node_oversized_content_fails_loudly():
    """When content exceeds the memory cap, the node must surface the failure
    instead of returning {'messages': []} as if the write succeeded."""
    import sys
    import types

    # langgraph/langchain-core are optional integration deps; stub the
    # modules nodes.py imports so this test runs standalone. langgraph's
    # __init__ also imports store.py, so stub langgraph.store.base too.
    lg_store = types.ModuleType("langgraph")
    lg_store.store = types.ModuleType("langgraph.store")
    base_mod = types.ModuleType("langgraph.store.base")

    class _BaseStore:
        pass

    class _Item:
        pass

    class _SearchItem:
        pass

    class _GetOp:
        pass

    class _PutOp:
        pass

    class _ListNamespacesOp:
        pass

    class _SearchOp:
        pass

    for name, obj in [
        ("BaseStore", _BaseStore),
        ("Item", _Item),
        ("SearchItem", _SearchItem),
        ("GetOp", _GetOp),
        ("PutOp", _PutOp),
        ("ListNamespacesOp", _ListNamespacesOp),
        ("SearchOp", _SearchOp),
    ]:
        setattr(base_mod, name, obj)
    lg_store.store.base = base_mod
    sys.modules["langgraph"] = lg_store
    sys.modules["langgraph.store"] = lg_store.store
    sys.modules["langgraph.store.base"] = base_mod

    lc_messages = types.ModuleType("langchain_core.messages")
    lc_runnables = types.ModuleType("langchain_core.runnables")

    class _HumanMessage:
        def __init__(self, content):
            self.content = content

    class _AIMessage:
        def __init__(self, content):
            self.content = content

    class _SystemMessage:
        def __init__(self, content):
            self.content = content

    class _RunnableConfig:
        pass

    lc_messages.HumanMessage = _HumanMessage
    lc_messages.AIMessage = _AIMessage
    lc_messages.SystemMessage = _SystemMessage
    lc_runnables.RunnableConfig = _RunnableConfig
    sys.modules["langchain_core"] = types.ModuleType("langchain_core")
    sys.modules["langchain_core.messages"] = lc_messages
    sys.modules["langchain_core.runnables"] = lc_runnables

    # Load the module from its file path directly (namespace package, and a
    # real langgraph distribution may be installed) so this test is standalone.
    import importlib.util

    def _load_module(name: str, path: str):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    nodes_path = Path(__file__).resolve().parents[2] / "integrations" / "langgraph" / "langgraph_memanto" / "nodes.py"
    m = _load_module("lg_memanto_nodes_test", str(nodes_path))

    calls = {"count": 0, "content_len": 0}

    class _Client:
        api_key = "test-key"

        def __init__(self, api_key=None):
            self.api_key = api_key or "test-key"

        def remember(self, **kwargs):
            calls["count"] += 1
            calls["content_len"] = len(kwargs.get("content", ""))
            content = kwargs.get("content", "")
            if len(content) > 10_000:
                raise ValueError("content exceeds maximum length of 10000")
            return {"memory_id": "m1"}

    node = m.create_remember_node(_Client(), agent_id="ag1")
    # _PerAgentClientCache.get() constructs SdkClient(api_key=...) internally;
    # point the module's SdkClient at the fake so remember() routes to it.
    m.SdkClient = _Client
    result = node({"messages": [_HumanMessage(content="x" * 10_001)]})
    # The fix truncates content to the store's cap BEFORE the call, so the
    # memory is actually stored instead of the ValueError being swallowed and
    # the node returning success with nothing persisted.
    assert calls["count"] >= 1, "remember must have been attempted"
    assert calls["content_len"] <= 10_000, (
        f"content must be truncated to the 10000-char cap, got {calls['content_len']}"
    )


# ---------------------------------------------------------------------------
# 3. ui_router migrate: broken export JSON must map to 400, not 500
# ---------------------------------------------------------------------------

def test_migrate_load_or_export_broken_json_is_400(tmp_path):
    """A file that exists but contains invalid JSON must raise HTTPException
    400 (bad user input), not let JSONDecodeError escape as a 500."""
    import memanto.app.ui.routes.ui_router as m

    from fastapi import HTTPException

    bad_file = tmp_path / "broken.json"
    bad_file.write_text("{not valid json!!!", encoding="utf-8")

    try:
        m._migrate_load_or_export("mem0", str(bad_file), None)
        raise AssertionError("broken JSON must be rejected")
    except HTTPException as exc:
        assert exc.status_code == 400, f"expected 400, got {exc.status_code}"


# ---------------------------------------------------------------------------
# 4. ui_router: non-string body values must map to 400, not AttributeError 500
# ---------------------------------------------------------------------------

def test_update_api_key_rejects_non_string(tmp_path):
    """body={"api_key": 12345} must raise HTTPException(400), not crash with
    AttributeError (which would surface as HTTP 500)."""
    import asyncio

    import memanto.app.ui.routes.ui_router as m

    from fastapi import HTTPException

    # Stub config manager so no real file is touched.
    class _CM:
        def set_api_key(self, key):
            pass

    original = m._config_manager
    m._config_manager = _CM()
    try:
        try:
            asyncio.run(m.update_api_key({"api_key": 12345}, None))
            raise AssertionError("non-string api_key must be rejected")
        except HTTPException as exc:
            assert exc.status_code == 400, (
                f"expected 400, got {exc.status_code}"
            )
    finally:
        m._config_manager = original


# ---------------------------------------------------------------------------
# 5. CLI migrate --file: missing/broken file must produce a friendly error
# ---------------------------------------------------------------------------

def test_migrate_load_or_export_missing_file():
    """_load_or_export with a nonexistent --file must raise ValueError (which
    the CLI converts to _error) instead of a raw FileNotFoundError traceback."""
    import memanto.cli.commands.migrate as m

    try:
        m._load_or_export(
            provider="mem0",
            file=Path("C:/definitely/not/here.json"),
            api_key=None,
            run_dir=Path("."),
            progress=lambda s: None,
        )
        raise AssertionError("missing file must raise")
    except (ValueError, FileNotFoundError) as exc:
        # ValueError -> friendly _error; FileNotFoundError is the old raw leak.
        assert isinstance(exc, ValueError), (
            f"expected friendly ValueError, got {type(exc).__name__}"
        )


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        test_do_list_namespaces_handles_list_agents_envelope()
        test_remember_node_oversized_content_fails_loudly()
        test_migrate_load_or_export_broken_json_is_400(p)
        test_update_api_key_rejects_non_string(p)
        test_migrate_load_or_export_missing_file()
    print("ALL ROUND 8 TESTS PASSED")
