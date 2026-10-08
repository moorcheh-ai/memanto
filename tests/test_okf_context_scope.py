"""OKF exports must not copy another agent's local context documents."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from memanto.app.config import get_data_dir
from memanto.app.core import MemoryRecord
from memanto.app.services.session_service import SessionService
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


@pytest.mark.parametrize("client_type", [DirectClient, SdkClient])
@pytest.mark.parametrize("agent_id", ["team", "team_2026-10-03"])
def test_export_keeps_only_its_agents_context(
    tmp_path, monkeypatch, client_type, agent_id
):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    data_dir = get_data_dir()
    session_service = SessionService(
        secret_key="context-scope-test-signing-key-0000",
        sessions_dir=data_dir / "sessions",
    )
    active = session_service.create_session(agent_id)
    summaries_dir = data_dir / "summaries"
    summaries_dir.mkdir()
    date_str = "2026-10-03"
    own_session_ids = [active.session_id, "legacy_2026-10-03_session"]

    # Agent ids are allowed to contain underscores and dates. A date-shaped
    # suffix defeats a fix that only anchors the start of the filename date.
    for owner in [agent_id, f"{agent_id}_private", f"{agent_id}_{date_str}"]:
        marker = "OWN_CONTEXT" if owner == agent_id else "OTHER_AGENT_CONTEXT"
        (summaries_dir / f"{owner}_{date_str}.md").write_text(
            f"# Daily Summary for {owner} - {date_str}\n{marker}\n",
            encoding="utf-8",
        )
        record = MemoryRecord(
            agent_id=owner,
            actor_id=owner,
            title="Local context fixture",
            content=marker,
            source="user",
            type="fact",
            created_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        )
        session_ids = (
            own_session_ids
            if owner == agent_id
            else [session_service.create_session(owner).session_id]
        )
        for session_id in session_ids:
            session_service.log_memory_to_session_summary(owner, session_id, record)

    # A prefix alone does not establish ownership for an arbitrary context file.
    (summaries_dir / f"{agent_id}_notes.md").write_text(
        "UNSCOPED_CONTEXT", encoding="utf-8"
    )
    (data_dir / "sessions" / f"{agent_id}_{date_str}_unknown_summary.md").write_text(
        "# An unrelated context document\nUNSCOPED_CONTEXT", encoding="utf-8"
    )

    client = client_type(api_key="synthetic-context-scope-key")
    client.agent_id = agent_id
    client.session_token = active.session_token
    client._session_service = session_service
    # Keep real session validation, recall, gathering, rendering and file copy;
    # only the remote search boundary has a controlled empty result.
    client._read_service = SimpleNamespace(
        search_memories=lambda **kwargs: {"results": [], "total_found": 0}
    )
    result = client.export_okf_bundle(agent_id)
    bundle = Path(result["output_path"])

    for path in bundle.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        assert "OTHER_AGENT_CONTEXT" not in content, path.relative_to(bundle)
        assert "UNSCOPED_CONTEXT" not in content, path.relative_to(bundle)

    assert {
        path.name
        for path in (bundle / "daily-summaries").glob("*.md")
        if path.name != "index.md"
    } == {f"{agent_id}_{date_str}.md"}
    assert {
        path.name
        for path in (bundle / "sessions").glob("*.md")
        if path.name != "index.md"
    } == {
        f"{agent_id}_{date_str}_{session_id}_summary.md"
        for session_id in own_session_ids
    }
