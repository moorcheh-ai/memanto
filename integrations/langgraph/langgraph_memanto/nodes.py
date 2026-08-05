import logging
import threading
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from memanto.app.utils.errors import SessionError
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


def _extract_text_content(content: Any) -> str:
    """Return plain-text from a LangChain message content value."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)
        return " ".join(text_parts)
    return str(content)


class _PerAgentClientCache:
    """Thread-safe cache of per-agent-id SdkClient instances.

    Each agent_id gets its own SdkClient so that concurrent LangGraph runs for
    different tenants never share session_token / agent_id state.  Without this
    isolation, a concurrent _do_setup("bob") would clobber the shared client's
    session_token while agent "alice" is mid-request, causing cross-tenant auth
    failures or silent data leaks.

    The cache is intentionally unbounded: in a typical LangGraph deployment the
    number of distinct agent IDs active in a single process is naturally bounded
    by the number of concurrent tenants, so unbounded growth is not a concern.
    """

    def __init__(self, template_client: SdkClient) -> None:
        """Initialise cache, extracting the API key from *template_client*."""
        self._api_key = template_client.api_key
        self._clients: dict[str, tuple[SdkClient, threading.Lock]] = {}
        self._lock = threading.Lock()

    def get(self, agent_id: str) -> tuple[SdkClient, threading.Lock]:
        """Return the SdkClient and setup lock for *agent_id*, creating them on first access."""
        with self._lock:
            if agent_id not in self._clients:
                self._clients[agent_id] = (
                    SdkClient(api_key=self._api_key),
                    threading.Lock(),
                )
            return self._clients[agent_id]


def _do_setup(
    agent_client: SdkClient, resolved_agent_id: str, agent_lock: threading.Lock
) -> None:
    """Ensure agent exists and activate a session on *agent_client*.

    Uses the caller-supplied per-agent client, not a shared one, so mutations
    to session_token / agent_id stay scoped to a single tenant. Concurrent
    calls for the same agent_id are serialized, and secondary callers will
    skip setup if the first caller successfully established a session.
    """
    with agent_lock:
        # Check if another thread already activated the session while we waited
        if agent_client.agent_id == resolved_agent_id and agent_client.session_token:
            try:
                agent_client.get_session_info()
                return
            except Exception as exc:
                logger.debug(
                    "Ignoring get_session_info failure during setup for agent_id=%s: %s",
                    resolved_agent_id,
                    exc,
                )

        try:
            agent_client.create_agent(agent_id=resolved_agent_id, pattern="tool")
        except Exception as exc:
            logger.debug(
                "Ignoring create_agent failure during setup for agent_id=%s: %s",
                resolved_agent_id,
                exc,
            )
        try:
            agent_client.activate_agent(resolved_agent_id, duration_hours=6)
        except Exception as exc:
            logger.debug(
                "Ignoring activate_agent failure during setup for agent_id=%s: %s",
                resolved_agent_id,
                exc,
            )


def create_recall_node(
    client: SdkClient,
    agent_id: str | None = None,
    agent_id_from_config: str = "agent_id",
    output_key: str | None = None,
):
    """Create a LangGraph node that recalls memories based on the latest human message.

    This node extracts the query from the most recent human message in the state
    and retrieves relevant memories from Memanto.
    """
    _cache = _PerAgentClientCache(client)

    def recall_node(
        state: dict, config: RunnableConfig | None = None
    ) -> dict[str, Any]:
        resolved_agent_id = agent_id
        if resolved_agent_id is None and config:
            configurable = config.get("configurable", {})
            resolved_agent_id = configurable.get(agent_id_from_config)

        if not resolved_agent_id:
            logger.warning(
                "No agent_id available for recall node, skipping memory injection."
            )
            if output_key:
                return {output_key: None}
            return {"messages": []}

        # Extract query from the latest human message
        query = None
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                query = _extract_text_content(msg.content)
                break

        if not query:
            if output_key:
                return {output_key: None}
            return {"messages": []}

        agent_client, agent_lock = _cache.get(resolved_agent_id)

        try:
            # First try assuming the session is already active (saves an API call)
            result = agent_client.recall(
                agent_id=resolved_agent_id,
                query=query,
            )
        except Exception:
            # If there's an error (e.g. no active session), try to setup and retry
            _do_setup(agent_client, resolved_agent_id, agent_lock)
            try:
                result = agent_client.recall(
                    agent_id=resolved_agent_id,
                    query=query,
                )
            except Exception as inner_e:
                logger.error(f"Recall failed after setup: {inner_e}")
                if output_key:
                    return {output_key: None}
                return {"messages": []}
        if not result:
            if output_key:
                return {output_key: None}
            return {"messages": []}

        memories = result.get("memories", [])
        if not memories:
            if output_key:
                return {output_key: None}
            return {"messages": []}

        try:
            lines = ["Relevant memories:"]
            for i, mem in enumerate(memories, 1):
                title = mem.get("title", "Untitled")
                content = mem.get("content", "")
                mem_type = mem.get("type", "unknown")
                lines.append(f"{i}. [{mem_type}] {title}: {content}")
            memory_text = "\n".join(lines)

            if output_key:
                return {output_key: memory_text}
            return {
                "messages": [
                    SystemMessage(content=memory_text, id="memanto_memory_context")
                ]
            }

        except Exception as e:
            logger.error(f"Recall failed: {e}")
            if output_key:
                return {output_key: None}
            return {"messages": []}

    return recall_node


def create_remember_node(
    client: SdkClient,
    agent_id: str | None = None,
    agent_id_from_config: str = "agent_id",
    remember_human: bool = True,
    remember_ai: bool = False,
):
    """Create a LangGraph node that stores conversation messages as memories.

    This node extracts the latest messages and stores them in Memanto.
    """
    _cache = _PerAgentClientCache(client)

    def remember_node(
        state: dict, config: RunnableConfig | None = None
    ) -> dict[str, Any]:
        resolved_agent_id = agent_id
        if resolved_agent_id is None and config:
            configurable = config.get("configurable", {})
            resolved_agent_id = configurable.get(agent_id_from_config)

        if not resolved_agent_id:
            logger.warning(
                "No agent_id available for remember node, skipping memory storage."
            )
            return {"messages": []}

        # Only retain the latest human and/or AI message
        messages_to_remember = []
        if remember_human:
            for msg in reversed(state.get("messages", [])):
                if isinstance(msg, HumanMessage):
                    text = _extract_text_content(msg.content)
                    if text:
                        messages_to_remember.append(text)
                    break

        if remember_ai:
            for msg in reversed(state.get("messages", [])):
                if isinstance(msg, AIMessage):
                    text = _extract_text_content(msg.content)
                    if text:
                        messages_to_remember.append(text)
                    break

        if not messages_to_remember:
            return {"messages": []}

        content = "\n\n".join(messages_to_remember)
        title = content if len(content) <= 50 else content[:47] + "..."

        agent_client, agent_lock = _cache.get(resolved_agent_id)

        try:
            # First try assuming the session is already active
            agent_client.remember(
                agent_id=resolved_agent_id,
                memory_type=None,
                title=title,
                content=content,
                source="langgraph-node",
                provenance="explicit_statement",
            )
        except SessionError:
            # SessionError is always raised before any write completes, so
            # retrying after _do_setup cannot produce duplicate memories.
            _do_setup(agent_client, resolved_agent_id, agent_lock)
            try:
                agent_client.remember(
                    agent_id=resolved_agent_id,
                    memory_type=None,
                    title=title,
                    content=content,
                    source="langgraph-node",
                    provenance="explicit_statement",
                )
            except Exception as inner_e:
                logger.error(f"Remember failed after setup: {inner_e}")
        except Exception as e:
            # Non-session errors may occur after the write has started; do not
            # retry to avoid storing duplicate memories.
            logger.error(f"Remember failed: {e}")
        return {"messages": []}

    return remember_node
