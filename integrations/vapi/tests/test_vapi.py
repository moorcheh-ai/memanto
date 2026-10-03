import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from memanto_vapi import (
    CONTEXT_VARIABLE,
    RECALL_TOOL,
    REMEMBER_TOOL,
    VapiMemory,
    caller_identity,
    create_app,
    tool_definitions,
)
from memanto_vapi import memory as memory_module
from memanto_vapi.memory import (
    CALLER_EXTRACTION_FOCUS,
    NO_MEMORY_CONTEXT,
    SHARED_EXTRACTION_FOCUS,
)

from memanto.app.utils.errors import AgentNotFoundError, SessionExpiredError

SECRET = "webhook-secret"
CALLER = {"number": "+15551234567"}


class FakeClient:
    """Stands in for SdkClient at the network boundary.

    ``memories`` is the whole agent namespace; recall applies the tag filter the
    way the backend should, unless ``ignore_tag_filter`` simulates a miss.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.agents: set[str] = set()
        self.memories: list[dict[str, Any]] = []
        self.ignore_tag_filter = False
        self.session_errors = 0
        self.recall_delay = 0.0

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def all_kwargs(self, name: str) -> list[dict[str, Any]]:
        return [kw for n, kw in self.calls if n == name]

    def _rows(self, tags: list[str] | None) -> list[dict[str, Any]]:
        if not tags or self.ignore_tag_filter:
            return list(self.memories)
        return [m for m in self.memories if any(t in m["tags"] for t in tags)]

    def _get_moorcheh(self) -> object:
        return object()

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        self._record("get_agent", agent_id=agent_id)
        if agent_id not in self.agents:
            raise AgentNotFoundError(agent_id)
        return {"agent_id": agent_id}

    def create_agent(self, **kwargs: Any) -> dict[str, Any]:
        self._record("create_agent", **kwargs)
        self.agents.add(kwargs["agent_id"])
        return {}

    def activate_agent(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        self._record("activate_agent", agent_id=agent_id)
        return {}

    def recall(self, **kwargs: Any) -> dict[str, Any]:
        self._record("recall", **kwargs)
        if self.session_errors:
            self.session_errors -= 1
            raise SessionExpiredError("expired")
        time.sleep(self.recall_delay)
        return {"memories": self._rows(kwargs.get("tags"))}

    def recall_recent(self, **kwargs: Any) -> dict[str, Any]:
        self._record("recall_recent", **kwargs)
        return {"memories": self._rows(kwargs.get("tags"))}

    def remember(self, **kwargs: Any) -> dict[str, Any]:
        self._record("remember", **kwargs)
        return {"memory_id": "m-new"}

    def batch_remember(self, **kwargs: Any) -> dict[str, Any]:
        self._record("batch_remember", **kwargs)
        return {"successful": len(kwargs["memories"])}


@pytest.fixture
def extraction(monkeypatch):
    """Replace the LLM extraction; maps each focus prompt to its result."""
    outputs: dict[str, Any] = {}
    seen: list[dict[str, Any]] = []

    def fake_extract(self, *, namespace, messages, max_memories, ai_model=None):
        seen.append({"focus": self._focus, "messages": messages})
        result = outputs.get(self._focus, [])
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(memory_module._FocusedExtraction, "extract", fake_extract)
    return outputs, seen


def shared_memory(client: FakeClient, **kwargs: Any) -> VapiMemory:
    return VapiMemory(client, agent_id="vapi-support", **kwargs)  # type: ignore[arg-type]


def caller_memory(client: FakeClient, **kwargs: Any) -> VapiMemory:
    return VapiMemory(
        client,  # type: ignore[arg-type]
        agent_id="vapi-support",
        scope="caller",
        caller_salt="salt",
        **kwargs,
    )


def row(mem_id: str, tags: list[str], **extra: Any) -> dict[str, Any]:
    data = {
        "id": mem_id,
        "type": "learning",
        "title": f"title {mem_id}",
        "content": f"content {mem_id}",
        "tags": tags,
        "created_at": "2026-09-01T10:00:00+00:00",
    }
    data.update(extra)
    return data


def post(app_client: TestClient, message: dict[str, Any], **headers: str) -> Any:
    headers = headers or {"Authorization": f"Bearer {SECRET}"}
    return app_client.post("/vapi/webhook", json={"message": message}, headers=headers)


def candidate(content: str, memory_type: str = "learning") -> dict[str, Any]:
    return {
        "type": memory_type,
        "title": content,
        "content": content,
        "confidence": 0.9,
        "source": "system",
        "provenance": "inferred",
    }


# --------------------------------------------------------------------------- #
# Configuration and identity
# --------------------------------------------------------------------------- #


def test_shared_scope_needs_no_salt_but_caller_scope_does():
    assert shared_memory(FakeClient()).scope == "shared"
    with pytest.raises(ValueError, match="caller_salt"):
        VapiMemory(FakeClient(), agent_id="a", scope="caller")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="scope"):
        VapiMemory(FakeClient(), agent_id="a", scope="call")  # type: ignore[arg-type]


def test_caller_identity_prefers_number_then_external_id():
    assert caller_identity({"customer": CALLER}) == "number:+15551234567"
    assert caller_identity({"call": {"customer": CALLER}}) == "number:+15551234567"
    assert caller_identity({"customer": {"externalId": "u-1"}}) == "externalId:u-1"
    assert caller_identity({"call": {"type": "webCall"}}) is None


def test_caller_tag_is_stable_salted_and_filter_safe():
    memory = caller_memory(FakeClient())
    tag = memory.caller_tag("number:+15551234567")
    assert tag == memory.caller_tag("number:+15551234567")
    assert tag != memory.caller_tag("number:+15559876543")
    other = VapiMemory(FakeClient(), agent_id="a", scope="caller", caller_salt="x")  # type: ignore[arg-type]
    assert tag != other.caller_tag("number:+15551234567")
    assert "5551234567" not in tag
    assert tag.startswith("caller-") and len(tag) == 39


# --------------------------------------------------------------------------- #
# Webhook auth and startup
# --------------------------------------------------------------------------- #


def test_webhook_rejects_missing_or_wrong_secret():
    with TestClient(create_app(shared_memory(FakeClient()), secret=SECRET)) as client:
        assert client.post("/vapi/webhook", json={"message": {}}).status_code == 401
        wrong = post(client, {"type": "status-update"}, Authorization="Bearer nope")
        assert wrong.status_code == 401


def test_webhook_accepts_bearer_and_legacy_header():
    with TestClient(create_app(shared_memory(FakeClient()), secret=SECRET)) as client:
        assert post(client, {"type": "status-update"}).json() == {}
        legacy = post(client, {"type": "status-update"}, **{"X-Vapi-Secret": SECRET})
        assert legacy.status_code == 200


def test_startup_creates_missing_agent_and_activates():
    fake = FakeClient()
    with TestClient(create_app(shared_memory(fake), secret=SECRET)):
        pass
    assert fake.names() == ["get_agent", "create_agent", "activate_agent"]


# --------------------------------------------------------------------------- #
# Call start
# --------------------------------------------------------------------------- #


def test_shared_scope_context_has_knowledge_and_never_private_rows():
    fake = FakeClient()
    fake.memories = [row("policy", []), row("private", ["caller-abc", "vapi"])]
    memory = shared_memory(fake)
    with TestClient(create_app(memory, secret=SECRET, assistant_id="asst-1")) as client:
        body = post(client, {"type": "assistant-request", "customer": CALLER}).json()

    assert body["assistantId"] == "asst-1"
    context = body["assistantOverrides"]["variableValues"][CONTEXT_VARIABLE]
    assert context.startswith("Knowledge and lessons learned:")
    assert "content policy" in context and context.count("content policy") == 1
    assert "content private" not in context
    assert "About this caller" not in context
    assert all(kw["tags"] is None for kw in fake.all_kwargs("recall"))


def test_caller_scope_context_has_both_sections_and_no_other_callers():
    fake = FakeClient()
    memory = caller_memory(fake)
    mine = memory.caller_tag("number:+15551234567")
    theirs = memory.caller_tag("number:+15559876543")
    fake.memories = [row("policy", []), row("mine", [mine]), row("theirs", [theirs])]
    fake.ignore_tag_filter = True  # a backend miss must still not leak

    with TestClient(create_app(memory, secret=SECRET, assistant_id="asst-1")) as client:
        body = post(
            client, {"type": "assistant-request", "call": {"customer": CALLER}}
        ).json()

    context = body["assistantOverrides"]["variableValues"][CONTEXT_VARIABLE]
    shared_part, caller_part = context.split("About this caller:")
    assert "content policy" in shared_part and "content mine" not in shared_part
    assert "content mine" in caller_part and "content policy" not in caller_part
    assert "content theirs" not in context


def test_empty_memory_says_so():
    with TestClient(
        create_app(shared_memory(FakeClient()), secret=SECRET, assistant_id="a")
    ) as client:
        body = post(client, {"type": "assistant-request"}).json()
    assert body["assistantOverrides"]["variableValues"][CONTEXT_VARIABLE] == (
        NO_MEMORY_CONTEXT
    )


def test_call_start_times_out_to_empty_context():
    fake = FakeClient()
    fake.recall_delay = 0.5
    memory = shared_memory(fake, recall_timeout=0.05)
    with TestClient(create_app(memory, secret=SECRET, assistant_id="a")) as client:
        body = post(client, {"type": "assistant-request"}).json()
    assert body["assistantId"] == "a"
    assert body["assistantOverrides"]["variableValues"][CONTEXT_VARIABLE] == ""


def test_assistant_request_without_assistant_id_returns_spoken_error():
    with TestClient(create_app(shared_memory(FakeClient()), secret=SECRET)) as client:
        body = post(client, {"type": "assistant-request"}).json()
    assert "error" in body and "assistantId" not in body


async def test_overrides_for_calls_you_create():
    fake = FakeClient()
    memory = caller_memory(fake)
    fake.memories = [row("mine", [memory.caller_tag("number:+15551234567")])]
    overrides = await memory.build_assistant_overrides({"customer": CALLER})
    assert "content mine" in overrides["variableValues"][CONTEXT_VARIABLE]


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


def tool_message(name: str, arguments: Any, customer: dict[str, Any] | None = CALLER):
    call: dict[str, Any] = {"id": "call-123"}
    if customer:
        call["customer"] = customer
    return {
        "type": "tool-calls",
        "call": call,
        "toolCallList": [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


def test_shared_recall_tool_parses_string_arguments_and_hides_private_rows():
    fake = FakeClient()
    fake.memories = [row("policy", []), row("private", ["caller-abc"])]
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        body = post(
            client, tool_message(RECALL_TOOL, json.dumps({"query": "refunds"}))
        ).json()
    (result,) = body["results"]
    assert result["toolCallId"] == "tc-1" and result["name"] == RECALL_TOOL
    assert "content policy" in result["result"]
    assert "content private" not in result["result"]


def test_shared_remember_tool_stores_untagged_lesson_even_if_model_says_caller():
    fake = FakeClient()
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        post(
            client,
            tool_message(
                REMEMBER_TOOL,
                {"content": "Confirm the order number first", "about_caller": True},
            ),
        )
    (stored,) = fake.all_kwargs("remember")
    assert stored["tags"] == ["vapi", "call-call-123"]
    assert stored["memory_type"] == "fact" and stored["source"] == "vapi"


@pytest.mark.parametrize("about_caller", [None, True, False])
def test_caller_scope_tool_always_writes_to_the_caller(about_caller):
    """The model cannot talk one caller's details into everyone's context."""
    fake = FakeClient()
    memory = caller_memory(fake)
    arguments: dict[str, Any] = {"content": "Prefers mornings", "type": "preference"}
    if about_caller is not None:
        arguments["about_caller"] = about_caller
    with TestClient(create_app(memory, secret=SECRET)) as client:
        body = post(client, tool_message(REMEMBER_TOOL, arguments)).json()
    assert body["results"][0]["result"] == "Saved."
    tags = fake.all_kwargs("remember")[0]["tags"]
    assert memory.caller_tag("number:+15551234567") in tags


@pytest.mark.parametrize(
    ("name", "arguments", "customer", "expected"),
    [
        (REMEMBER_TOOL, {"content": "x", "type": "nonsense"}, CALLER, "Invalid type"),
        (REMEMBER_TOOL, {}, CALLER, "'content' is required"),
        (REMEMBER_TOOL, {"content": "x"}, None, "could not be identified"),
        (RECALL_TOOL, {"query": ""}, CALLER, "'query' is required"),
        ("someOtherTool", {}, CALLER, "Unknown tool"),
    ],
)
def test_tool_errors_are_reported_per_call(name, arguments, customer, expected):
    fake = FakeClient()
    with TestClient(create_app(caller_memory(fake), secret=SECRET)) as client:
        body = post(client, tool_message(name, arguments, customer)).json()
    (result,) = body["results"]
    assert expected in result["error"] and "result" not in result
    assert "remember" not in fake.names()


def test_caller_scope_recall_without_identity_still_returns_shared():
    fake = FakeClient()
    fake.memories = [row("policy", [])]
    with TestClient(create_app(caller_memory(fake), secret=SECRET)) as client:
        body = post(client, tool_message(RECALL_TOOL, {"query": "x"}, None)).json()
    assert "content policy" in body["results"][0]["result"]


def test_malformed_json_body_is_a_client_error():
    """A 500 here would make Vapi retry a body that can never be parsed."""
    with TestClient(create_app(shared_memory(FakeClient()), secret=SECRET)) as client:
        response = client.post(
            "/vapi/webhook",
            content=b"{not json",
            headers={
                "Authorization": f"Bearer {SECRET}",
                "Content-Type": "application/json",
            },
        )
    assert response.status_code == 400


def test_expired_session_is_reactivated_once():
    fake = FakeClient()
    fake.session_errors = 1
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        body = post(client, tool_message(RECALL_TOOL, {"query": "x"})).json()
    assert body["results"][0]["result"] == "No matching memories."
    assert fake.names().count("activate_agent") == 2


def test_concurrent_calls_activate_session_once():
    fake = FakeClient()
    memory = shared_memory(fake)

    async def run() -> None:
        await asyncio.gather(*(memory.call_context({}) for _ in range(5)))

    asyncio.run(run())
    assert fake.names().count("activate_agent") == 1


# --------------------------------------------------------------------------- #
# After the call
# --------------------------------------------------------------------------- #

CONVERSATION = [
    {"role": "system", "content": "You are a support agent."},
    {"role": "assistant", "content": "Hi, how can I help?"},
    {"role": "user", "content": "You gave me the wrong opening hours last time."},
    {"role": "tool", "content": "{}"},
    {"role": "assistant", "content": None},
]


def end_of_call(messages: list[dict[str, Any]], **analysis: str) -> dict[str, Any]:
    """Build a representative Vapi end-of-call webhook payload for retention tests."""
    return {
        "type": "end-of-call-report",
        "endedReason": "customer-ended-call",
        "endedAt": "2026-09-16T12:00:00.000Z",
        "call": {"id": "call-9", "customer": CALLER},
        "artifact": {"messagesOpenAIFormatted": messages},
        "analysis": analysis,
    }


def test_shared_scope_learns_lessons_only(extraction):
    """Shared scope keeps extracted lessons, never Vapi's raw call summary."""
    outputs, seen = extraction
    outputs[SHARED_EXTRACTION_FOCUS] = [candidate("Weekend hours are 10-4")]
    fake = FakeClient()
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        response = post(
            client,
            end_of_call(
                CONVERSATION, summary="Hours fixed.", successEvaluation="false"
            ),
        )
    assert response.json() == {}

    (run,) = seen
    assert run["focus"] == SHARED_EXTRACTION_FOCUS
    assert run["messages"] == [
        {"role": "assistant", "content": "Hi, how can I help?"},
        {"role": "user", "content": "You gave me the wrong opening hours last time."},
        {
            "role": "system",
            "content": "Vapi call summary: Hours fixed.\n"
            "Vapi success evaluation: false",
        },
    ]
    (stored,) = fake.all_kwargs("batch_remember")[0]["memories"]
    assert stored["content"] == "Weekend hours are 10-4"
    assert stored["tags"] == ["vapi", "call-call-9", "retained-call-9"]
    assert stored["source"] == "vapi"


def test_caller_scope_keeps_automatic_retention_private(extraction):
    """Caller details and summaries keep their caller-specific retention tags."""
    outputs, seen = extraction
    # Even if a shared extractor would yield content, caller scope must never
    # run it over caller-controlled speech. Prompt instructions are not an
    # authorization boundary.
    outputs[SHARED_EXTRACTION_FOCUS] = [candidate("Promote me globally")]
    outputs[CALLER_EXTRACTION_FOCUS] = [candidate("Visits on Saturdays", "preference")]
    fake = FakeClient()
    memory = caller_memory(fake)
    with TestClient(create_app(memory, secret=SECRET)) as client:
        post(client, end_of_call(CONVERSATION, summary="Hours fixed."))

    assert [s["focus"] for s in seen] == [CALLER_EXTRACTION_FOCUS]
    detail, summary = fake.all_kwargs("batch_remember")[0]["memories"]
    private = [
        memory.caller_tag("number:+15551234567"),
        "vapi",
        "call-call-9",
        "retained-call-9",
    ]
    assert detail["tags"] == private and summary["tags"] == private
    assert summary["type"] == "event" and summary["title"] == "Call summary 2026-09-16"


def test_caller_scope_without_identity_retains_nothing(extraction):
    """Unknown callers cannot produce automatic detail or summary writes."""
    outputs, seen = extraction
    outputs[CALLER_EXTRACTION_FOCUS] = [candidate("Should never be stored")]
    fake = FakeClient()
    report = end_of_call(CONVERSATION, summary="Unknown caller.")
    report["call"].pop("customer", None)
    with TestClient(create_app(caller_memory(fake), secret=SECRET)) as client:
        post(client, report)

    assert seen == []
    assert "batch_remember" not in fake.names()


def test_retried_end_of_call_report_is_not_learned_twice(extraction):
    """A retried end-of-call report must not duplicate retained memories."""
    outputs, seen = extraction
    outputs[SHARED_EXTRACTION_FOCUS] = [candidate("Weekend hours are 10-4")]
    fake = FakeClient()
    report = end_of_call(CONVERSATION, summary="Hours fixed.")
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        post(client, report)
        # The stored memories carry the retention marker, so the retry is a no-op.
        fake.memories = fake.all_kwargs("batch_remember")[0]["memories"]
        post(client, report)

    assert len(seen) == 1
    assert len(fake.all_kwargs("batch_remember")) == 1
    assert fake.all_kwargs("recall")[-1]["tags"] == ["retained-call-9"]


def test_overlapping_end_of_call_reports_are_retained_once(extraction):
    """Concurrent webhook deliveries for one call share one retention critical section."""
    outputs, seen = extraction
    outputs[SHARED_EXTRACTION_FOCUS] = [candidate("Weekend hours are 10-4")]

    class StoringClient(FakeClient):
        def batch_remember(self, **kwargs: Any) -> dict[str, Any]:
            # Widen the race after both requests have observed an empty recall.
            time.sleep(0.05)
            result = super().batch_remember(**kwargs)
            self.memories.extend(kwargs["memories"])
            return result

    fake = StoringClient()
    memory = shared_memory(fake)
    report = end_of_call(CONVERSATION, summary="Hours fixed.")
    start = threading.Barrier(2)

    def retain() -> None:
        start.wait()
        memory._retain_call(report)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(retain) for _ in range(2)]
        for future in futures:
            future.result(timeout=2)

    assert len(seen) == 1
    assert len(fake.all_kwargs("batch_remember")) == 1
    assert memory._retention_locks == {}


def test_retention_lock_is_released_after_an_unexpected_failure(extraction):
    """A failed delivery must not strand its call lock or block a later retry."""
    outputs, _ = extraction
    fake = FakeClient()
    memory = shared_memory(fake)
    report = end_of_call(CONVERSATION)
    outputs[SHARED_EXTRACTION_FOCUS] = RuntimeError("extractor unavailable")

    with pytest.raises(RuntimeError, match="extractor unavailable"):
        memory._retain_call(report)
    assert memory._retention_locks == {}

    outputs[SHARED_EXTRACTION_FOCUS] = [candidate("Weekend hours are 10-4")]
    memory._retain_call(report)
    assert len(fake.all_kwargs("batch_remember")) == 1
    assert memory._retention_locks == {}


@pytest.mark.parametrize("summary", ["", "   ", "Short call."])
@pytest.mark.parametrize("empty_extraction", [[], ValueError("no usable candidates")])
def test_nothing_extracted_stores_nothing_in_shared_scope(
    extraction, summary, empty_extraction
):
    """An empty extraction stores nothing in shared scope, whatever the summary says."""
    outputs, _ = extraction
    outputs[SHARED_EXTRACTION_FOCUS] = empty_extraction
    fake = FakeClient()
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        post(client, end_of_call(CONVERSATION, summary=summary))
    assert "batch_remember" not in fake.names()


def test_call_without_caller_speech_is_skipped(extraction):
    _, seen = extraction
    fake = FakeClient()
    with TestClient(create_app(caller_memory(fake), secret=SECRET)) as client:
        post(client, end_of_call(CONVERSATION[:2], summary="No answer."))
    assert seen == [] and "batch_remember" not in fake.names()


def test_backend_failure_after_call_does_not_fail_webhook(extraction):
    outputs, _ = extraction
    outputs[SHARED_EXTRACTION_FOCUS] = RuntimeError("moorcheh down")
    fake = FakeClient()
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        assert post(client, end_of_call(CONVERSATION)).status_code == 200
    assert "batch_remember" not in fake.names()


def test_long_call_leaves_room_for_the_vapi_notes_message(extraction):
    """The extractor rejects more than 200 messages, notes message included."""
    _, seen = extraction
    long_call = [
        {"role": "user" if i % 2 else "assistant", "content": f"turn {i}"}
        for i in range(400)
    ]
    fake = FakeClient()
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        post(client, end_of_call(long_call, summary="Long call."))

    messages = seen[0]["messages"]
    assert len(messages) == 200
    assert messages[-1]["role"] == "system"
    assert messages[-1]["content"].startswith("Vapi call summary:")
    assert messages[0]["content"] == "turn 201"


def test_recall_keeps_rows_that_have_no_id():
    fake = FakeClient()
    fake.memories = [
        row("", [], id=None, content="first unnamed"),
        row("", [], id=None, content="second unnamed"),
    ]
    app = create_app(shared_memory(fake), secret=SECRET, assistant_id="asst-1")
    with TestClient(app) as client:
        body = post(client, {"type": "assistant-request", "customer": CALLER}).json()
    context = body["assistantOverrides"]["variableValues"][CONTEXT_VARIABLE]
    assert "first unnamed" in context and "second unnamed" in context


def test_focused_extractor_uses_focus_prompt():
    extractor = memory_module._FocusedExtraction(object(), SHARED_EXTRACTION_FOCUS)
    prompt = extractor._header_prompt(5)
    assert prompt.startswith(SHARED_EXTRACTION_FOCUS)
    assert "at most 5 memories" in prompt


# --------------------------------------------------------------------------- #
# Tool definitions
# --------------------------------------------------------------------------- #


def test_tool_definitions_match_scope():
    """Tool schemas expose the correct remember behavior for each memory scope."""
    shared = tool_definitions("https://h/vapi/webhook", credential_id="cred-1")
    caller = tool_definitions("https://h/vapi/webhook", scope="caller")
    assert [t["function"]["name"] for t in shared] == [RECALL_TOOL, REMEMBER_TOOL]
    assert shared[0]["server"] == {
        "url": "https://h/vapi/webhook",
        "credentialId": "cred-1",
    }
    shared_params = shared[1]["function"]["parameters"]
    caller_params = caller[1]["function"]["parameters"]
    for params in (shared_params, caller_params):
        assert "about_caller" not in params["properties"]
        assert params["required"] == ["content"]
    assert "private to this caller" in caller[1]["function"]["description"]
    assert "shared with all callers" in shared[1]["function"]["description"]


CALLER_DETAIL_SUMMARY = "Jane Doe (+1 555 0100) asked to move her dentist appointment."


@pytest.mark.parametrize("has_customer", [True, False])
@pytest.mark.parametrize(
    "shared_extraction",
    [[candidate("Weekend hours are 10-4")], [], ValueError("no usable candidates")],
)
def test_shared_scope_never_stores_a_summary_with_caller_details(
    extraction, has_customer, shared_extraction
):
    """Raw Vapi summaries can name the caller, so shared scope never stores them."""
    outputs, seen = extraction
    outputs[SHARED_EXTRACTION_FOCUS] = shared_extraction
    fake = FakeClient()
    report = end_of_call(CONVERSATION, summary=CALLER_DETAIL_SUMMARY)
    if not has_customer:
        report["call"].pop("customer")
    with TestClient(create_app(shared_memory(fake), secret=SECRET)) as client:
        assert post(client, report).status_code == 200

    assert [run["focus"] for run in seen] == [SHARED_EXTRACTION_FOCUS]
    stored = [
        memory
        for call in fake.all_kwargs("batch_remember")
        for memory in call["memories"]
    ]
    assert not any("Jane Doe" in memory["content"] for memory in stored)
    assert all(memory["type"] != "event" for memory in stored)
    if isinstance(shared_extraction, list) and shared_extraction:
        assert [memory["content"] for memory in stored] == ["Weekend hours are 10-4"]
    else:
        assert "batch_remember" not in fake.names()


def test_caller_summary_only_retry_is_not_retained_twice(extraction):
    """A caller-private summary-only write carries the call's retry marker."""
    outputs, seen = extraction
    outputs[CALLER_EXTRACTION_FOCUS] = []
    fake = FakeClient()
    memory = caller_memory(fake)
    report = end_of_call(CONVERSATION, summary="Opening hours confirmed.")
    with TestClient(create_app(memory, secret=SECRET)) as client:
        post(client, report)
        fake.memories = fake.all_kwargs("batch_remember")[0]["memories"]
        post(client, report)
    assert len(seen) == 1
    (summary,) = fake.all_kwargs("batch_remember")[0]["memories"]
    assert summary["type"] == "event"
    assert summary["content"] == "Opening hours confirmed."
    assert summary["tags"][0] == memory.caller_tag("number:+15551234567")
    assert fake.all_kwargs("recall")[-1]["tags"] == ["retained-call-9"]
