"""Tests for Moorche agent conflict detection client."""

import json as json_mod
import threading
import time

import httpx
import pytest

from memanto.app.clients.agent_conflict import (
    CANCELLED_MESSAGE,
    conflict_progress_step,
    describe_conflict_progress,
    detect_conflicts_via_agent,
    extract_report_from_run_payload,
    iter_sse_events_from_stream,
    parse_sse_block,
    parse_sse_events,
    summarize_agent_run,
    wait_for_conflict_report_from_run,
)
from memanto.app.services.daily_analysis_service import DailyAnalysisService
from memanto.app.utils.errors import MemoryOperationError


def test_parse_sse_events_extracts_message_payload():
    raw = (
        "event: run_started\n"
        'data: {"run_id":"run_1"}\n\n'
        "event: message\n"
        'data: {"run_id":"run_1","text":"{\\"count\\":1}"}\n\n'
        "event: done\n"
        'data: {"run_id":"run_1","stop_reason":"end_turn"}\n\n'
    )
    events = parse_sse_events(raw)
    summary = summarize_agent_run(events)
    assert summary["message_text"] == '{"count":1}'
    assert summary["stop_reason"] == "end_turn"


def test_parse_sse_block_handles_single_block():
    parsed = parse_sse_block('event: status\ndata: {"phase":"thinking"}\n')
    assert parsed == {"event": "status", "data": {"phase": "thinking"}}


def test_describe_conflict_progress_maps_phases():
    assert "Starting" in describe_conflict_progress("run_started", {})
    assert "Loading session memories" in describe_conflict_progress(
        "status", {"phase": "loading"}
    )
    assert "Analyzing" in describe_conflict_progress(
        "status", {"phase": "analyzing", "count": 42, "memory_type": "fact"}
    )
    assert "similar pairs" in describe_conflict_progress(
        "status", {"phase": "similarity", "done": 3, "total": 10}
    )
    assert "Semantic conflict" in describe_conflict_progress(
        "status", {"phase": "semantic", "done": 1, "total": 5}
    )
    assert "Searching" in describe_conflict_progress(
        "status", {"phase": "searching", "query": "timezone"}
    )
    assert "semantic" in describe_conflict_progress(
        "status", {"phase": "detecting_conflicts"}
    )
    assert "Loading session memories" in describe_conflict_progress(
        "status", {"phase": "listing_memories", "offset": 50}
    )
    assert "3 memory matches" in describe_conflict_progress(
        "search_completed", {"context_count": 3, "query": "votes"}
    )
    assert "2 conflicts" in describe_conflict_progress(
        "conflict_detection_completed", {"count": 2, "memories_scanned": 50}
    )


def test_conflict_progress_step_maps_ui_steps():
    assert conflict_progress_step("run_started") == "start"
    assert conflict_progress_step("status", {"phase": "loading"}) == "search"
    assert conflict_progress_step("status", {"phase": "analyzing"}) == "detect"
    assert conflict_progress_step("status", {"phase": "similarity"}) == "search"
    assert conflict_progress_step("status", {"phase": "semantic"}) == "detect"
    assert conflict_progress_step("status", {"phase": "searching"}) == "search"
    assert (
        conflict_progress_step("conflict_detection_completed", {"count": 1}) == "done"
    )
    assert conflict_progress_step("message") == "done"
    assert conflict_progress_step("status", {"phase": "listing_memories"}) == "search"
    assert conflict_progress_step("done") == "done"


def test_detect_conflicts_via_agent_parses_report(monkeypatch):
    report = {
        "date": "2026-06-28",
        "conflicts": [
            {
                "type": "contradiction",
                "title": "Team changed",
                "old_memory_id": "a",
                "new_memory_id": "b",
                "old_text": "finance",
                "new_text": "marketing",
                "recommendation": "keep_new",
                "conflict": True,
            }
        ],
        "count": 1,
    }

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_text(self):
            import json

            body = (
                "event: run_started\n"
                'data: {"run_id":"run_1"}\n\n'
                "event: status\n"
                'data: {"phase":"detecting_conflicts"}\n\n'
                "event: message\n"
                f'data: {{"text": {json.dumps(json.dumps(report))}}}\n\n'
                "event: done\n"
                'data: {"stop_reason":"end_turn"}\n\n'
            )
            yield body

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.httpx.Client",
        lambda timeout: FakeClient(),
    )

    seen = []

    result = detect_conflicts_via_agent(
        base_url="https://api.moorcheh.ai/v1",
        api_key="test-key",
        namespace="memanto_agent_bot",
        date="2026-06-28",
        on_event=lambda name, data: seen.append(name),
    )
    assert result["count"] == 1
    assert result["conflicts"][0]["title"] == "Team changed"
    assert "run_started" in seen
    assert "status" in seen


def test_normalize_agent_conflicts_keeps_contradictions_only():
    service = DailyAnalysisService.__new__(DailyAnalysisService)
    report = {
        "conflicts": [
            {
                "type": "contradiction",
                "title": "Team changed",
                "old_memory_id": "a",
                "new_memory_id": "b",
                "old_text": "finance",
                "new_text": "marketing",
                "conflict": True,
            },
            {
                "type": "duplicate",
                "title": "Same fact",
                "old_memory_id": "c",
                "new_memory_id": "d",
                "conflict": True,
            },
            {
                "type": "compatible",
                "title": "Related",
                "old_memory_id": "e",
                "new_memory_id": "f",
                "conflict": False,
            },
            {
                "type": "update",
                "title": "Superseded",
                "old_memory_id": "g",
                "new_memory_id": "h",
                "conflict": False,
            },
        ]
    }
    normalized = service._normalize_agent_conflicts(report)
    assert len(normalized) == 1
    assert normalized[0]["type"] == "contradiction"
    assert normalized[0]["old_memory_id"] == "a"


def test_extract_report_from_run_payload_reads_assistant_message():
    report = extract_report_from_run_payload(
        {
            "status": "completed",
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"text": '{"conflicts":[],"count":0}'}],
                }
            ],
        }
    )
    assert report["count"] == 0


def test_wait_for_conflict_report_from_run_polls_until_completed(monkeypatch):
    import json as json_mod

    report = {"conflicts": [], "count": 0}
    calls = {"n": 0}

    class FakeResponse:
        def __init__(self, status):
            self.status_code = 200
            self._status = status

        def json(self):
            if self._status == "processing":
                return {"status": "processing", "messages": []}
            return {
                "status": "completed",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"text": json_mod.dumps(report)}],
                    }
                ],
            }

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        status = "processing" if calls["n"] < 3 else "completed"
        return FakeResponse(status)

    monkeypatch.setattr("memanto.app.clients.agent_conflict.httpx.get", fake_get)
    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.time.sleep", lambda _s: None
    )

    seen = []

    result = wait_for_conflict_report_from_run(
        base_url="https://api.moorcheh.ai/v1",
        api_key="test-key",
        run_id="run_poll",
        poll_interval=0.01,
        timeout=5.0,
        on_event=lambda name, data: seen.append((name, data)),
    )
    assert result["count"] == 0
    assert calls["n"] >= 3
    assert any(data.get("phase") == "waiting" for _name, data in seen)


def test_detect_conflicts_via_agent_falls_back_to_run_fetch(monkeypatch):
    report = {
        "date": "2026-09-08",
        "conflicts": [{"type": "contradiction", "conflict": True}],
        "count": 1,
    }

    class FakeStreamResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_text(self):
            yield (
                "event: run_started\n"
                'data: {"run_id":"run_fallback"}\n\n'
                "event: status\n"
                'data: {"phase":"analyzing"}\n\n'
            )
            raise httpx.RemoteProtocolError(
                "peer closed connection without sending complete message body"
            )

    class FakeStreamClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return FakeStreamResponse()

    class FakeGetResponse:
        status_code = 200

        def json(self):
            return {
                "status": "completed",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"text": __import__("json").dumps(report)}],
                    }
                ],
            }

    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.httpx.Client",
        lambda timeout: FakeStreamClient(),
    )
    poll_calls = {"n": 0}

    class PollingGetResponse:
        status_code = 200

        def json(self):
            poll_calls["n"] += 1
            if poll_calls["n"] < 2:
                return {"status": "processing", "messages": []}
            return {
                "status": "completed",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"text": __import__("json").dumps(report)}],
                    }
                ],
            }

    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.httpx.get",
        lambda *args, **kwargs: PollingGetResponse(),
    )
    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.time.sleep", lambda _s: None
    )

    result = detect_conflicts_via_agent(
        base_url="https://api.moorcheh.ai/v1",
        api_key="test-key",
        namespace="memanto_agent_bot",
        date="2026-09-08",
    )
    assert result["count"] == 1


def test_iter_sse_events_from_stream_parses_incrementally():
    class FakeResponse:
        def iter_text(self):
            yield "event: run_started\n"
            yield 'data: {"run_id":"run_1"}\n\n'
            yield "event: done\n"
            yield 'data: {"stop_reason":"end_turn"}\n\n'

    events = list(iter_sse_events_from_stream(FakeResponse()))
    assert [e["event"] for e in events] == ["run_started", "done"]


def test_iter_sse_events_from_stream_handles_multibyte_text_across_chunks():
    body = 'event: message\ndata: {"message":"café — résumé"}\n\n'
    encoded = body.encode("utf-8")
    split_at = encoded.index(b"caf") + 4
    assert split_at < len(encoded)
    try:
        encoded[:split_at].decode("utf-8")
        pytest.fail("expected UTF-8 split to fall inside a multibyte character")
    except UnicodeDecodeError:
        pass

    class ChunkStream(httpx.SyncByteStream):
        def __init__(self, chunks: list[bytes]):
            self._chunks = chunks

        def __iter__(self):
            yield from self._chunks

    request = httpx.Request("POST", "https://example.com/v1/agent/run")
    response = httpx.Response(
        200,
        request=request,
        stream=ChunkStream([encoded[:split_at], encoded[split_at:]]),
    )

    events = list(iter_sse_events_from_stream(response))
    assert events[0]["event"] == "message"
    assert events[0]["data"]["message"] == "café — résumé"


def test_wait_for_conflict_report_from_run_does_not_return_completed_after_cancel(
    monkeypatch,
):
    cancel_event = threading.Event()
    report = {"conflicts": [], "count": 0}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "completed",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"text": json_mod.dumps(report)}],
                    }
                ],
            }

    def fake_get(*args, **kwargs):
        cancel_event.set()
        return FakeResponse()

    monkeypatch.setattr("memanto.app.clients.agent_conflict.httpx.get", fake_get)

    with pytest.raises(MemoryOperationError, match=CANCELLED_MESSAGE):
        wait_for_conflict_report_from_run(
            base_url="https://api.moorcheh.ai/v1",
            api_key="test-key",
            run_id="run_cancel_completed",
            poll_interval=0.01,
            timeout=5.0,
            cancel_event=cancel_event,
        )


def test_wait_for_conflict_report_from_run_respects_cancel_event(monkeypatch):
    cancel_event = threading.Event()

    def fake_get(*args, **kwargs):
        cancel_event.set()
        return type(
            "FakeResponse",
            (),
            {
                "status_code": 200,
                "json": lambda self: {"status": "processing", "messages": []},
            },
        )()

    monkeypatch.setattr("memanto.app.clients.agent_conflict.httpx.get", fake_get)
    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.time.sleep", lambda _s: None
    )

    with pytest.raises(MemoryOperationError, match=CANCELLED_MESSAGE):
        wait_for_conflict_report_from_run(
            base_url="https://api.moorcheh.ai/v1",
            api_key="test-key",
            run_id="run_cancel",
            poll_interval=0.01,
            timeout=5.0,
            cancel_event=cancel_event,
        )


def test_detect_conflicts_via_agent_cancels_during_blocking_stream_read(monkeypatch):
    cancel_event = threading.Event()

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def close(self):
            self._closed = True

        def iter_text(self):
            self._closed = False
            while not self._closed:
                time.sleep(0.01)
            yield from ()

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.httpx.Client",
        lambda timeout: FakeClient(),
    )

    def cancel_soon() -> None:
        time.sleep(0.05)
        cancel_event.set()

    threading.Thread(target=cancel_soon, daemon=True).start()
    start = time.monotonic()
    with pytest.raises(MemoryOperationError, match=CANCELLED_MESSAGE):
        detect_conflicts_via_agent(
            base_url="https://api.moorcheh.ai/v1",
            api_key="test-key",
            namespace="memanto_agent_bot",
            date="2026-09-08",
            cancel_event=cancel_event,
        )
    assert time.monotonic() - start < 2.0


def test_detect_conflicts_via_agent_respects_cancel_event(monkeypatch):
    cancel_event = threading.Event()

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_text(self):
            cancel_event.set()
            yield "event: run_started\n"
            yield 'data: {"run_id":"run_cancel"}\n\n'

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "memanto.app.clients.agent_conflict.httpx.Client",
        lambda timeout: FakeClient(),
    )

    with pytest.raises(MemoryOperationError, match=CANCELLED_MESSAGE):
        detect_conflicts_via_agent(
            base_url="https://api.moorcheh.ai/v1",
            api_key="test-key",
            namespace="memanto_agent_bot",
            date="2026-09-08",
            cancel_event=cancel_event,
        )
