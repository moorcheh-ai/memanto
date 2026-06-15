"""Shared LangGraph state for the customer-support demo."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class SupportState(TypedDict):
    """The graph state for a customer support conversation.

    Only ``messages`` actually flows through the graph - everything else
    we care about (user preferences, prior facts) lives in the
    cross-thread ``MemantoStore``, not in this state.

    Note that ``user_id`` is intentionally NOT here. We read it from the
    LangGraph config (``config["configurable"]["user_id"]``) so it isn't
    part of the checkpointed state.
    """

    messages: Annotated[list, add_messages]
