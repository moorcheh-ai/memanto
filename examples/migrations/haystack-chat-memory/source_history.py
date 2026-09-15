"""Populate and snapshot an actual Haystack in-memory store (synthetic demo inputs)."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

from adapter import FORMAT
from haystack.dataclasses import ChatMessage, ChatRole, TextContent, ToolCall
from haystack_experimental.chat_message_stores.in_memory import InMemoryChatMessageStore

SESSION = "procurement-demo"
GOLDEN = {
    "currency": "EUR",
    "response_window": "48 hours",
    "channel": "email",
    "approver": "Maya",
}


def answer(messages: list[dict], key: str) -> str | None:
    """Small deterministic demo agent: the latest explicit user setting wins."""
    result = None
    prefix = f"Set {key} = "
    for message in messages:
        if message["role"] != "user":
            continue
        for part in message["content"]:
            for line in part.get("text", "").splitlines():
                if line.startswith(prefix):
                    result = line[len(prefix) :].strip()
    return result


def populate() -> tuple[InMemoryChatMessageStore, dict]:
    # Both options are essential: defaults omit the system message and truncate history.
    store = InMemoryChatMessageStore(skip_system_messages=False, last_k=None)
    call = ToolCall(
        tool_name="lookup_purchase_order", arguments={"id": "PO-42"}, id="call-42"
    )
    messages = [
        ChatMessage.from_system(
            "Keep procurement context and explicit corrections; never authorize payments."
        ),
        ChatMessage.from_user("Set currency = USD"),
        ChatMessage.from_assistant("Recorded the initial currency."),
        ChatMessage.from_user("Set response_window = 24 hours"),
        ChatMessage.from_user("Set channel = email"),
        ChatMessage.from_assistant(tool_calls=[call]),
        ChatMessage.from_tool(
            "PO-42: 12 approved items; receiving confirmation pending", origin=call
        ),
        ChatMessage.from_assistant(
            "The purchase order still needs receiving confirmation."
        ),
        ChatMessage.from_user("Set approver = Maya"),
        ChatMessage.from_user("Correction for our EU branch:\nSet currency = EUR"),
        ChatMessage.from_assistant("EUR supersedes the earlier USD preference."),
        ChatMessage.from_user(
            "Set response_window = 48 hours",
            meta={
                "ticket": {
                    "notes": "Review context. " * 30,
                    "labels": ["EU", "corrected"],
                }
            },
        ),
        ChatMessage(
            _role=ChatRole.USER,
            _content=[
                TextContent("Two source text blocks, both retained."),
                TextContent(
                    "Unicode: café, 東京. Literal delimiter: <!-- okf-entry -->"
                ),
            ],
        ),
        ChatMessage.from_assistant(
            'A quoted wrapper is source data:\n<!-- haystack-source-json -->\n```json\n{"example":true}\n```\n<!-- /haystack-source-json -->'
        ),
        ChatMessage.from_tool("Temporary lookup failure", origin=call, error=True),
    ]
    written = store.write_messages(SESSION, messages)
    store.write_messages("other-user", [ChatMessage.from_user("Set currency = GBP")])
    # to_dict() on the store only describes its constructor, not its messages.
    sessions = {
        key: [message.to_dict() for message in store.retrieve_messages(key)]
        for key in (SESSION, "other-user")
    }
    assert len(sessions[SESSION]) == written == len(messages)
    return store, {
        "format": FORMAT,
        "source": "haystack_experimental.InMemoryChatMessageStore",
        "data_kind": "synthetic procurement conversation written and retrieved through the real source API",
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("haystack-ai", "haystack-experimental", "memanto")
        },
        "store_options": {"skip_system_messages": False, "last_k": None},
        "sessions": sessions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    _, snapshot = populate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        f"Haystack wrote and retrieved {len(snapshot['sessions'][SESSION])} selected messages; second session excluded by adapter scope."
    )


if __name__ == "__main__":
    main()
