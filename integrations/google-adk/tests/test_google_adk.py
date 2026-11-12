import logging
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from google.adk.agents import LlmAgent
from google.adk.events.event import Event
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import preload_memory
from google.genai import types
from memanto_google_adk import (
    MemantoMemoryService,
    default_agent_id,
    remember_tool,
    user_tag,
)
from memanto_google_adk import memory as memory_module

from memanto.app.utils.errors import AgentNotFoundError, SessionExpiredError

APP = "travel-app"
AGENT = "adk-travel-app"


class FakeBackend:
    """Stands in for Memanto at the SdkClient boundary.

    ``memories`` holds every agent's rows; recall applies the tag filter the way
    the backend should, unless ``ignore_tag_filter`` simulates a miss.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.agents: set[str] = set()
        self.memories: list[dict[str, Any]] = []
        self.ignore_tag_filter = False
        self.session_errors = 0
        self.reject_content: str | None = None
        self.extractions: list[list[dict[str, str]]] = []
        self.extracted: list[dict[str, Any]] = [
            {
                "type": "preference",
                "title": "Window seat",
                "content": "User prefers window seats.",
                "confidence": 0.9,
                "provenance": "explicit_statement",
            }
        ]

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def rows(self, agent_id: str, tags: list[str] | None) -> list[dict[str, Any]]:
        rows = [m for m in self.memories if m["agent_id"] == agent_id]
        if tags and not self.ignore_tag_filter:
            rows = [m for m in rows if any(t in m["tags"] for t in tags)]
        return rows


class FakeClient:
    def __init__(self, backend: FakeBackend, api_key: str) -> None:
        self.backend = backend

    def _record(self, name: str, **kwargs: Any) -> None:
        self.backend.calls.append((name, kwargs))

    def _check_session(self) -> None:
        if self.backend.session_errors:
            self.backend.session_errors -= 1
            raise SessionExpiredError("expired")

    def _get_moorcheh(self) -> object:
        return object()

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        self._record("get_agent", agent_id=agent_id)
        if agent_id not in self.backend.agents:
            raise AgentNotFoundError(agent_id)
        return {"agent_id": agent_id}

    def create_agent(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        self._record("create_agent", agent_id=agent_id, **kwargs)
        self.backend.agents.add(agent_id)
        return {"agent_id": agent_id}

    def activate_agent(self, agent_id: str) -> dict[str, Any]:
        self._record("activate_agent", agent_id=agent_id)
        return {"agent_id": agent_id}

    def batch_remember(
        self, agent_id: str, memories: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self._check_session()
        if len(memories) > 100:
            raise ValueError("Batch size exceeds maximum of 100")
        self._record("batch_remember", agent_id=agent_id, memories=memories)
        results = []
        for memory in memories:
            if memory["content"] == self.backend.reject_content:
                results.append({"status": "failed", "error": "rejected by backend"})
                continue
            self.backend.memories.append(
                {
                    **memory,
                    "id": f"m{len(self.backend.memories)}",
                    "agent_id": agent_id,
                    "created_at": "2026-09-25T10:00:00Z",
                }
            )
            results.append({"status": "stored"})
        return {"successful": len(memories), "results": results}

    def recall(self, agent_id: str, query: str, **kwargs: Any) -> dict[str, Any]:
        self._check_session()
        self._record("recall", agent_id=agent_id, query=query, **kwargs)
        return {"memories": self.backend.rows(agent_id, kwargs.get("tags"))}

    def recall_recent(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        self._check_session()
        self._record("recall_recent", agent_id=agent_id, **kwargs)
        rows = self.backend.rows(agent_id, kwargs.get("tags"))
        return {"memories": list(reversed(rows))[: kwargs.get("limit")]}


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> FakeBackend:
    backend = FakeBackend()
    monkeypatch.setattr(
        memory_module, "SdkClient", lambda api_key: FakeClient(backend, api_key)
    )

    def extract(self: Any, *, namespace: str, messages: list, max_memories: int):
        backend.extractions.append(messages)
        if not backend.extracted:
            raise ValueError("nothing worth keeping")
        return [dict(m) for m in backend.extracted]

    monkeypatch.setattr(
        memory_module.ConversationMemoryExtractionService, "extract", extract
    )
    return backend


@pytest.fixture
def service(backend: FakeBackend) -> MemantoMemoryService:
    return MemantoMemoryService(api_key="test-key")


def _event(author: str, text: str, **kwargs: Any) -> Event:
    role = "user" if author == "user" else "model"
    return Event(
        author=author,
        content=types.Content(role=role, parts=[types.Part.from_text(text=text)]),
        **kwargs,
    )


async def _session(user_id: str = "alice", *events: Event):
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name=APP, user_id=user_id)
    for event in events:
        await sessions.append_event(session, event)
    return sessions, session


# ---------------------------------------------------------------------- #
# Identity and setup
# ---------------------------------------------------------------------- #


def test_default_agent_id_is_a_valid_memanto_id() -> None:
    assert default_agent_id("travel app") == AGENT
    assert default_agent_id("a/b::c") == "adk-a-b--c"
    assert default_agent_id("!!!") == "adk-app"


def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOORCHEH_API_KEY", raising=False)
    with pytest.raises(ValueError, match="api_key"):
        MemantoMemoryService()


def test_from_uri_reads_agent_id(
    backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOORCHEH_API_KEY", "env-key")
    assert (
        MemantoMemoryService.from_uri("memanto://shared-mem")._agent_id == "shared-mem"
    )
    assert MemantoMemoryService.from_uri("memanto://", agents_dir="x")._agent_id is None


async def test_creates_agent_once_and_reactivates_on_session_error(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    await service.search_memory(app_name=APP, user_id="alice", query="seats")
    await service.search_memory(app_name=APP, user_id="alice", query="seats")
    assert backend.names().count("create_agent") == 1
    assert backend.names().count("activate_agent") == 1

    backend.session_errors = 1
    await service.search_memory(app_name=APP, user_id="alice", query="seats")
    assert backend.names().count("activate_agent") == 2


# ---------------------------------------------------------------------- #
# Search
# ---------------------------------------------------------------------- #


async def test_search_returns_only_this_users_memories(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    backend.agents.add(AGENT)
    backend.memories = [
        {
            "id": "a1",
            "agent_id": AGENT,
            "type": "preference",
            "title": "Window seat",
            "content": "Prefers window seats.",
            "confidence": 0.9,
            "tags": [user_tag("alice")],
            "created_at": "2026-09-01T00:00:00Z",
        },
        {
            "id": "b1",
            "agent_id": AGENT,
            "title": "Bob",
            "content": "Bob's passport number.",
            "tags": [user_tag("bob")],
        },
    ]
    backend.ignore_tag_filter = True  # a backend miss must not leak Bob's row

    result = await service.search_memory(app_name=APP, user_id="alice", query="seat")

    assert [m.id for m in result.memories] == ["a1"]
    entry = result.memories[0]
    assert (
        entry.content.parts[0].text == "[preference] Window seat: Prefers window seats."
    )
    assert entry.timestamp == "2026-09-01T00:00:00Z"
    assert entry.custom_metadata["confidence"] == 0.9
    recall = dict(backend.calls)["recall"]
    assert recall["tags"] == [user_tag("alice")]
    assert recall["status"] == "active"


async def test_explicit_agent_id_is_shared_across_apps(backend: FakeBackend) -> None:
    service = MemantoMemoryService(api_key="k", agent_id="one-memory")
    await service.search_memory(app_name="app-a", user_id="alice", query="q")
    await service.search_memory(app_name="app-b", user_id="alice", query="q")
    assert {kw["agent_id"] for n, kw in backend.calls if n == "recall"} == {
        "one-memory"
    }


# ---------------------------------------------------------------------- #
# Session ingestion
# ---------------------------------------------------------------------- #


async def test_add_session_extracts_new_events_only(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    sessions, session = await _session(
        "alice",
        _event("user", "I always want a window seat."),
        _event("travel_agent", "Noted, window seats from now on."),
    )

    await service.add_session_to_memory(session)
    assert backend.extractions == [
        [
            {"role": "user", "content": "I always want a window seat."},
            {"role": "assistant", "content": "Noted, window seats from now on."},
        ]
    ]
    stored = backend.memories[0]
    assert stored["tags"][0] == user_tag("alice")
    assert stored["source"] == "google-adk"

    # ADK may add the same session again: nothing new, nothing extracted.
    await service.add_session_to_memory(session)
    assert len(backend.extractions) == 1

    await sessions.append_event(session, _event("user", "Book me to Lisbon."))
    await sessions.append_event(session, _event("travel_agent", "Booked."))
    await service.add_session_to_memory(session)
    assert backend.extractions[1] == [
        {"role": "user", "content": "Book me to Lisbon."},
        {"role": "assistant", "content": "Booked."},
    ]


async def test_add_session_resumes_across_service_instances(
    backend: FakeBackend,
) -> None:
    _, session = await _session("alice", _event("user", "I prefer aisle seats."))
    await MemantoMemoryService(api_key="k").add_session_to_memory(session)
    # A fresh process has no local state; the markers in Memanto are enough.
    await MemantoMemoryService(api_key="k").add_session_to_memory(session)
    assert len(backend.extractions) == 1


async def test_add_session_skips_partial_tool_and_agent_only_events(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    call = Event(
        author="travel_agent",
        content=types.Content(
            role="model",
            parts=[types.Part.from_function_call(name="search", args={"q": "x"})],
        ),
    )
    _, session = await _session(
        "alice",
        _event("travel_agent", "Welcome!"),
        call,
        _event("travel_agent", "Wel", partial=True),
    )
    await service.add_session_to_memory(session)
    assert backend.extractions == []  # no user speech: nothing to learn


async def test_turn_with_nothing_to_keep_stores_nothing(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    backend.extracted = []
    _, session = await _session("alice", _event("user", "hi"))
    await service.add_session_to_memory(session)
    assert "batch_remember" not in backend.names()


async def test_add_events_is_idempotent_on_retry(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    events = [_event("user", "My budget is 2000 EUR."), _event("bot", "Got it.")]
    for _ in range(2):
        await service.add_events_to_memory(
            app_name=APP, user_id="alice", events=events, session_id="s1"
        )
    assert len(backend.extractions) == 1
    assert len(backend.memories) == 1


# ---------------------------------------------------------------------- #
# Explicit memories
# ---------------------------------------------------------------------- #


async def test_add_memory_stores_typed_entries(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    await service.add_memory(
        app_name=APP,
        user_id="alice",
        memories=[
            MemoryEntry(
                content=types.Content(parts=[types.Part.from_text(text="Vegetarian.")]),
                custom_metadata={"type": "preference"},
            )
        ],
    )
    (stored,) = backend.memories
    assert stored["type"] == "preference"
    assert stored["content"] == "Vegetarian."
    assert stored["tags"] == [user_tag("alice"), "google-adk"]
    assert backend.extractions == []

    with pytest.raises(ValueError, match="Invalid memory type"):
        await service.add_memory(
            app_name=APP,
            user_id="alice",
            memories=[
                MemoryEntry(
                    content=types.Content(parts=[types.Part.from_text(text="x")]),
                    custom_metadata={"type": "gossip"},
                )
            ],
        )


async def test_long_backlog_is_chunked_not_truncated(
    backend: FakeBackend, service: MemantoMemoryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    limits = memory_module.ConversationMemoryExtractionService
    monkeypatch.setattr(limits, "MAX_CONTENT_CHARS", 60)
    events = [_event("user", f"fact number {i} " + "x" * 20) for i in range(6)]
    _, session = await _session("alice", *events)

    await service.add_session_to_memory(session)

    # Every message reached the extractor, none past its character budget.
    extracted = [m["content"] for chunk in backend.extractions for m in chunk]
    assert extracted == [e.content.parts[0].text for e in events]
    assert all(
        sum(len(m["role"]) + len(m["content"]) + 3 for m in chunk) <= 60
        for chunk in backend.extractions
    )
    assert len(backend.extractions) > 1
    # Nothing is re-extracted on the next save.
    count = len(backend.extractions)
    await service.add_session_to_memory(session)
    assert len(backend.extractions) == count


async def test_chunk_failure_resumes_from_last_stored_chunk(
    backend: FakeBackend, service: MemantoMemoryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    limits = memory_module.ConversationMemoryExtractionService
    monkeypatch.setattr(limits, "MAX_MESSAGES", 2)
    events = [_event("user", f"turn {i}") for i in range(4)]
    _, session = await _session("alice", *events)

    calls = 0

    def flaky_store(self: Any, agent: Any, items: list) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionError("network down")
        original_store(self, agent, items)

    original_store = MemantoMemoryService._store
    monkeypatch.setattr(MemantoMemoryService, "_store", flaky_store)
    with pytest.raises(ConnectionError):
        await service.add_session_to_memory(session)

    monkeypatch.setattr(MemantoMemoryService, "_store", original_store)
    backend.extractions.clear()
    await service.add_session_to_memory(session)
    assert backend.extractions == [
        [{"role": "user", "content": "turn 2"}, {"role": "user", "content": "turn 3"}]
    ]


async def test_add_memory_slices_large_batches(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    entries = [
        MemoryEntry(content=types.Content(parts=[types.Part.from_text(text=f"n{i}")]))
        for i in range(250)
    ]
    await service.add_memory(app_name=APP, user_id="alice", memories=entries)
    sizes = [len(kw["memories"]) for n, kw in backend.calls if n == "batch_remember"]
    assert sizes == [100, 100, 50]
    assert len(backend.memories) == 250


async def test_rejected_items_are_logged(
    backend: FakeBackend,
    service: MemantoMemoryService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend.reject_content = "bad"
    await service.add_memory(
        app_name=APP,
        user_id="alice",
        memories=[
            MemoryEntry(content=types.Content(parts=[types.Part.from_text(text="bad")]))
        ],
    )
    assert "rejected by backend" in caplog.text


async def test_empty_query_returns_nothing_without_calling_memanto(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    result = await service.search_memory(app_name=APP, user_id="alice", query="  ")
    assert result.memories == []
    assert backend.calls == []


def test_rejects_out_of_range_settings() -> None:
    with pytest.raises(ValueError, match="recall_limit"):
        MemantoMemoryService(api_key="k", recall_limit=0)
    with pytest.raises(ValueError, match="extract_max_memories"):
        MemantoMemoryService(api_key="k", extract_max_memories=101)


# ---------------------------------------------------------------------- #
# End to end through a real ADK Runner
# ---------------------------------------------------------------------- #


class ScriptedLlm(BaseLlm):
    """Replays fixed responses and records every request it receives."""

    model: str = "scripted"
    script: list[types.Content] = []
    requests: list[LlmRequest] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        yield LlmResponse(content=self.script.pop(0))


def _model_says(*parts: types.Part) -> types.Content:
    return types.Content(role="model", parts=list(parts))


async def _run(runner: Runner, user_id: str, session_id: str, text: str) -> None:
    message = types.Content(role="user", parts=[types.Part.from_text(text=text)])
    async for _ in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        pass


async def test_runner_remembers_then_preloads_in_a_new_session(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    llm = ScriptedLlm(
        script=[
            _model_says(
                types.Part.from_function_call(
                    name="memanto_remember",
                    args={
                        "content": "User is vegetarian.",
                        "memory_type": "preference",
                    },
                )
            ),
            _model_says(types.Part.from_text(text="I'll remember that.")),
            _model_says(types.Part.from_text(text="Here are vegetarian options.")),
        ],
        requests=[],
    )
    agent = LlmAgent(
        name="travel_agent", model=llm, tools=[remember_tool, preload_memory]
    )
    sessions = InMemorySessionService()
    runner = Runner(
        app_name=APP,
        agent=agent,
        session_service=sessions,
        memory_service=service,
    )

    first = await sessions.create_session(app_name=APP, user_id="alice")
    await _run(runner, "alice", first.id, "I'm vegetarian.")
    (stored,) = backend.memories
    assert stored["content"] == "User is vegetarian."
    assert stored["tags"][0] == user_tag("alice")

    second = await sessions.create_session(app_name=APP, user_id="alice")
    await _run(runner, "alice", second.id, "Find me a vegetarian dinner.")
    # ADK 2.0 puts preloaded memory in the system instruction; later versions
    # add it to the contents.
    request = llm.requests[-1]
    prompt = str(request.config.system_instruction or "") + " ".join(
        part.text or "" for content in request.contents for part in content.parts or []
    )
    assert "User is vegetarian." in prompt

    # Another user of the same app sees none of it.
    result = await service.search_memory(app_name=APP, user_id="bob", query="diet")
    assert result.memories == []


async def test_readme_callback_survives_outage_and_catches_up(
    backend: FakeBackend, service: MemantoMemoryService
) -> None:
    """The after_agent_callback exactly as the README shows it."""

    async def save_to_memory(callback_context):
        try:
            await callback_context.add_session_to_memory()
        except Exception:
            logging.exception("Saving to Memanto failed")

    llm = ScriptedLlm(
        script=[
            _model_says(types.Part.from_text(text="Window seat, noted.")),
            _model_says(types.Part.from_text(text="Lisbon it is.")),
        ],
        requests=[],
    )
    agent = LlmAgent(
        name="travel_agent",
        model=llm,
        tools=[preload_memory],
        after_agent_callback=save_to_memory,
    )
    sessions = InMemorySessionService()
    runner = Runner(
        app_name=APP, agent=agent, session_service=sessions, memory_service=service
    )
    session = await sessions.create_session(app_name=APP, user_id="alice")

    # Memanto is down for the first turn: the user still gets their answer.
    backend.session_errors = 99
    await _run(runner, "alice", session.id, "I always want a window seat.")
    assert backend.extractions == []
    # Back up: the second save also covers the turn the first one missed.
    backend.session_errors = 0
    await _run(runner, "alice", session.id, "Book me to Lisbon.")

    assert backend.extractions == [
        [
            {"role": "user", "content": "I always want a window seat."},
            {"role": "assistant", "content": "Window seat, noted."},
            {"role": "user", "content": "Book me to Lisbon."},
            {"role": "assistant", "content": "Lisbon it is."},
        ],
    ]
    # And nothing twice on the next save.
    await service.add_session_to_memory(
        await sessions.get_session(app_name=APP, user_id="alice", session_id=session.id)
    )
    assert len(backend.extractions) == 1
