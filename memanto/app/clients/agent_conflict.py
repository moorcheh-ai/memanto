"""Call Moorche agent/run for memory conflict detection (cloud backend)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from memanto.app.utils.errors import MemoryOperationError

DEFAULT_AGENT_CONFLICT_TIMEOUT = 300.0
POLL_INTERVAL_S = 3.0
CANCELLED_MESSAGE = "Conflict detection cancelled"

ConflictProgressCallback = Callable[[str, dict[str, Any]], None]


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise MemoryOperationError(CANCELLED_MESSAGE)


def _sleep_or_cancel(
    seconds: float, cancel_event: threading.Event | None = None
) -> None:
    if cancel_event is None:
        time.sleep(seconds)
        return
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _raise_if_cancelled(cancel_event)
        time.sleep(min(0.25, deadline - time.monotonic()))


def parse_sse_block(block: str) -> dict[str, Any] | None:
    """Parse one SSE block into {event, data}."""
    block = block.strip()
    if not block:
        return None
    event_name = "message"
    data_parts: list[str] = []
    for line in block.split("\n"):
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_parts.append(line[5:].strip())
    if not data_parts:
        return None
    raw_data = "".join(data_parts)
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        payload = {"raw": raw_data}
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    return {"event": event_name, "data": payload}


def parse_sse_events(text: str) -> list[dict[str, Any]]:
    """Parse Server-Sent Events from a Moorche agent/run response body."""
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        parsed = parse_sse_block(block)
        if parsed:
            events.append(parsed)
    return events


def iter_sse_events_from_stream(
    response: httpx.Response,
    cancel_event: threading.Event | None = None,
) -> Iterator[dict[str, Any]]:
    """Incrementally parse SSE events from an httpx streaming response."""
    stop_watcher = threading.Event()

    def _close_on_cancel() -> None:
        while not stop_watcher.wait(0.25):
            if cancel_event is not None and cancel_event.is_set():
                response.close()
                return

    watcher: threading.Thread | None = None
    if cancel_event is not None:
        watcher = threading.Thread(target=_close_on_cancel, daemon=True)
        watcher.start()

    buffer = ""
    try:
        for chunk in response.iter_text():
            _raise_if_cancelled(cancel_event)
            if not chunk:
                continue
            buffer += chunk
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                parsed = parse_sse_block(block)
                if parsed:
                    yield parsed
    except httpx.StreamClosed:
        _raise_if_cancelled(cancel_event)
        raise
    finally:
        stop_watcher.set()
        if watcher is not None:
            watcher.join(timeout=1.0)

    _raise_if_cancelled(cancel_event)
    tail = buffer.strip()
    if tail:
        parsed = parse_sse_block(tail)
        if parsed:
            yield parsed


def describe_conflict_progress(
    event_name: str, data: dict[str, Any] | None = None
) -> str | None:
    """Map Moorche agent/run SSE events to user-facing status text."""
    data = data or {}
    if event_name == "run_started":
        run_id = str(data.get("run_id") or "").strip()
        if run_id:
            return f"Starting conflict detection (run {run_id})…"
        return "Starting conflict detection…"
    if event_name == "status":
        phase = str(data.get("phase") or "")
        if phase == "waiting":
            run_id = str(data.get("run_id") or "").strip()
            run_status = str(data.get("run_status") or "processing").strip()
            if run_id:
                return f"Waiting for Moorche run {run_id} ({run_status})…"
            return "Waiting for Moorche conflict detection to finish…"
        if phase == "loading":
            return "Loading session memories…"
        if phase == "analyzing":
            count = data.get("count")
            memory_type = str(data.get("memory_type") or "").strip()
            if isinstance(count, int) and memory_type:
                return f"Analyzing {count} {memory_type} memories…"
            if isinstance(count, int):
                return f"Analyzing {count} memories…"
            return "Running holistic conflict analysis…"
        if phase == "similarity":
            done = data.get("done")
            total = data.get("total")
            if isinstance(done, int) and isinstance(total, int) and total > 0:
                return f"Finding similar pairs ({done}/{total})…"
            return "Finding similar memory pairs…"
        if phase == "semantic":
            done = data.get("done")
            total = data.get("total")
            if isinstance(done, int) and isinstance(total, int) and total > 0:
                return f"Semantic conflict check ({done}/{total})…"
            return "Running semantic conflict analysis…"
        if phase == "thinking":
            return "Agent reviewing memory catalog…"
        if phase == "searching":
            query = str(data.get("query") or "").strip()
            return f"Searching memories{f': {query}' if query else ''}…"
        if phase == "detecting_conflicts":
            return "Running semantic conflict analysis…"
        if phase == "listing_memories":
            offset = data.get("offset")
            if isinstance(offset, int):
                return f"Loading session memories (offset {offset})…"
            return "Loading session memories…"
        return None
    if event_name == "search_completed":
        count = data.get("context_count")
        query = str(data.get("query") or "").strip()
        if isinstance(count, int):
            base = f"Loaded {count} memory match{'es' if count != 1 else ''}"
            return f"{base}{f' for “{query}”' if query else ''}"
        return "Memory search complete"
    if event_name == "conflict_detection_completed":
        count = data.get("count")
        scanned = data.get("memories_scanned")
        source = str(data.get("detect_source") or "").strip()
        parts: list[str] = []
        if isinstance(count, int):
            parts.append(
                f"Found {count} conflict{'s' if count != 1 else ''}"
                if count
                else "No conflicts found"
            )
        else:
            parts.append("Conflict scan complete")
        if isinstance(scanned, int):
            parts.append(f"{scanned} memories scanned")
        if source:
            parts.append(f"via {source}")
        return " · ".join(parts)
    if event_name == "error":
        return str(
            data.get("message") or data.get("code") or "Conflict detection error"
        )
    return None


def conflict_progress_step(
    event_name: str, data: dict[str, Any] | None = None
) -> str | None:
    """Map SSE events to coarse UI step ids: start | search | detect | done."""
    data = data or {}
    if event_name in {"run_started"}:
        return "start"
    if event_name == "status":
        phase = str(data.get("phase") or "")
        if phase in {"loading", "listing_memories", "searching", "similarity"}:
            return "search"
        if phase in {"analyzing", "semantic", "detecting_conflicts", "waiting"}:
            return "detect"
        if phase == "thinking":
            return "start"
    if event_name == "search_completed":
        return "search"
    if event_name == "conflict_detection_completed":
        return "done"
    if event_name == "message":
        return "done"
    if event_name == "done":
        return "done"
    if event_name == "error":
        return "done"
    return None


def summarize_agent_run(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the final message text and error state from SSE events."""
    message_text: str | None = None
    stop_reason: str | None = None
    error_message: str | None = None
    conflict_count: int | None = None
    run_id: str | None = None

    for event in events:
        name = event.get("event")
        data = event.get("data") or {}
        if name == "run_started" and isinstance(data.get("run_id"), str):
            run_id = data["run_id"]
        if name == "message" and isinstance(data.get("text"), str):
            message_text = data["text"]
        if name == "conflict_detection_completed":
            conflict_count = data.get("count")
        if name == "done":
            stop_reason = data.get("stop_reason")
        if name == "error":
            error_message = data.get("message") or data.get("code")

    return {
        "message_text": message_text,
        "stop_reason": stop_reason,
        "error_message": error_message,
        "conflict_count": conflict_count,
        "run_id": run_id,
    }


def extract_report_from_run_payload(run_payload: dict[str, Any]) -> dict[str, Any]:
    """Parse the conflict JSON report from a completed agent run."""
    messages = run_payload.get("messages") or []
    if not isinstance(messages, list):
        raise MemoryOperationError("Agent run messages must be a list")

    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if not isinstance(text, str) or not text.strip().startswith("{"):
                continue
            try:
                report = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(report, dict) and "conflicts" in report:
                return report

    raise MemoryOperationError("Agent run has no conflict report message")


def _get_agent_run_payload(
    *,
    base_url: str,
    api_key: str,
    run_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/agent/runs/{run_id}"
    response = httpx.get(
        url,
        params={"include": "messages"},
        headers={"x-api-key": api_key},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise MemoryOperationError(
            f"Failed to fetch agent run {run_id} ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise MemoryOperationError("Agent run payload must be a JSON object")
    return payload


def wait_for_conflict_report_from_run(
    *,
    base_url: str,
    api_key: str,
    run_id: str,
    poll_interval: float = POLL_INTERVAL_S,
    timeout: float = DEFAULT_AGENT_CONFLICT_TIMEOUT,
    on_event: ConflictProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Poll GET /agent/runs/{runId} until the conflict report is available."""
    deadline = time.monotonic() + timeout
    request_timeout = httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0)

    while time.monotonic() < deadline:
        _raise_if_cancelled(cancel_event)
        payload = _get_agent_run_payload(
            base_url=base_url,
            api_key=api_key,
            run_id=run_id,
            timeout=request_timeout.read or 30.0,
        )
        _raise_if_cancelled(cancel_event)
        status = str(payload.get("status") or "")

        if status == "completed":
            return extract_report_from_run_payload(payload)
        if status == "failed":
            err = payload.get("error") or "unknown error"
            raise MemoryOperationError(f"Agent run {run_id} failed: {err}")

        _emit_progress(
            on_event,
            "status",
            {
                "phase": "waiting",
                "run_id": run_id,
                "run_status": status or "processing",
            },
        )
        _sleep_or_cancel(poll_interval, cancel_event)

    raise MemoryOperationError(
        f"Timed out waiting for agent run {run_id} to complete after {timeout:.0f}s"
    )


def fetch_conflict_report_from_run(
    *,
    base_url: str,
    api_key: str,
    run_id: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Fetch a completed conflict report when the SSE stream closed early."""
    payload = _get_agent_run_payload(
        base_url=base_url,
        api_key=api_key,
        run_id=run_id,
        timeout=timeout,
    )
    status = str(payload.get("status") or "")
    if status != "completed":
        raise MemoryOperationError(
            f"Agent run {run_id} is not completed (status={status})"
        )
    return extract_report_from_run_payload(payload)


def _finalize_agent_conflict_run(
    events: list[dict[str, Any]],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    on_event: ConflictProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = DEFAULT_AGENT_CONFLICT_TIMEOUT,
) -> dict[str, Any]:
    _raise_if_cancelled(cancel_event)
    summary = summarize_agent_run(events)
    if summary["error_message"]:
        raise MemoryOperationError(
            f"Agent conflict detection error: {summary['error_message']}"
        )
    if summary["stop_reason"] == "error":
        raise MemoryOperationError(
            "Agent conflict detection ended with stop_reason=error"
        )

    message_text = summary.get("message_text")
    if not message_text:
        run_id = summary.get("run_id")
        if run_id and base_url and api_key:
            return wait_for_conflict_report_from_run(
                base_url=base_url,
                api_key=api_key,
                run_id=run_id,
                timeout=timeout,
                on_event=on_event,
                cancel_event=cancel_event,
            )
        raise MemoryOperationError(
            "Agent conflict detection returned no message payload"
        )

    try:
        report = json.loads(message_text)
    except json.JSONDecodeError as exc:
        raise MemoryOperationError(
            f"Agent conflict detection returned invalid JSON: {message_text[:500]}"
        ) from exc

    if not isinstance(report, dict):
        raise MemoryOperationError(
            "Agent conflict detection message must be a JSON object"
        )

    return report


def _emit_progress(
    on_event: ConflictProgressCallback | None,
    event_name: str,
    data: dict[str, Any],
) -> None:
    if not on_event:
        return
    on_event(event_name, data)


def detect_conflicts_via_agent(
    *,
    base_url: str,
    api_key: str,
    namespace: str,
    date: str,
    ai_model: str | None = None,
    memory_type: str | None = None,
    memory_types: list[str] | None = None,
    similarity_threshold: float | None = None,
    conflict_mode: str = "semantic",
    timeout: float = DEFAULT_AGENT_CONFLICT_TIMEOUT,
    on_event: ConflictProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run Moorche ``POST /agent/run`` with ``task=detect_conflicts``.

    Returns the parsed conflict report JSON from the final SSE ``message`` event.
    Optional ``on_event`` receives each raw SSE event as ``(event_name, data)``.
    Pass ``cancel_event`` to stop streaming or polling when the caller disconnects.
    """
    _raise_if_cancelled(cancel_event)
    url = f"{base_url.rstrip('/')}/agent/run"
    body: dict[str, Any] = {
        "namespace": namespace,
        "task": "detect_conflicts",
        "date": date,
        "conflict_mode": conflict_mode,
    }
    if ai_model:
        body["ai_model"] = ai_model
    if memory_types:
        body["memory_types"] = memory_types
    elif memory_type:
        body["memory_type"] = memory_type
    else:
        body["memory_types"] = ["fact", "preference"]
    if similarity_threshold is not None:
        body["similarity_threshold"] = similarity_threshold

    events: list[dict[str, Any]] = []
    run_id: str | None = None
    stream_error: Exception | None = None
    read_timeout = httpx.Timeout(connect=30.0, read=timeout, write=30.0, pool=30.0)

    try:
        with httpx.Client(timeout=read_timeout) as client:
            with client.stream(
                "POST",
                url,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=body,
            ) as response:
                if response.status_code >= 400:
                    detail = response.read().decode("utf-8", errors="replace")
                    raise MemoryOperationError(
                        f"Agent conflict detection failed ({response.status_code}): {detail}"
                    )
                for event in iter_sse_events_from_stream(
                    response, cancel_event=cancel_event
                ):
                    _raise_if_cancelled(cancel_event)
                    events.append(event)
                    data = event.get("data") or {}
                    if event.get("event") == "run_started" and isinstance(
                        data.get("run_id"), str
                    ):
                        run_id = data["run_id"]
                    _emit_progress(on_event, event["event"], data)
    except MemoryOperationError:
        raise
    except httpx.HTTPError as exc:
        _raise_if_cancelled(cancel_event)
        stream_error = exc

    _raise_if_cancelled(cancel_event)

    if stream_error is not None:
        fallback_run_id = run_id or summarize_agent_run(events).get("run_id")
        if fallback_run_id:
            try:
                return wait_for_conflict_report_from_run(
                    base_url=base_url,
                    api_key=api_key,
                    run_id=fallback_run_id,
                    timeout=timeout,
                    on_event=on_event,
                    cancel_event=cancel_event,
                )
            except MemoryOperationError:
                raise
            except Exception as poll_err:
                raise MemoryOperationError(
                    f"Agent conflict detection stream failed and run {fallback_run_id} "
                    f"could not be recovered: {poll_err}"
                ) from stream_error
        raise MemoryOperationError(
            f"Agent conflict detection request failed: {stream_error}"
        ) from stream_error

    return _finalize_agent_conflict_run(
        events,
        base_url=base_url,
        api_key=api_key,
        on_event=on_event,
        cancel_event=cancel_event,
        timeout=timeout,
    )
