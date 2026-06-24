import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


def _extract_text_content(content: Any) -> str:
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

    def _do_setup(resolved_agent_id: str):
        try:
            client.create_agent(agent_id=resolved_agent_id, pattern="tool")
        except Exception:
            pass
        try:
            result = client.activate_agent(resolved_agent_id, duration_hours=6)
            client.session_token = result.get("session_token")
        except Exception:
            pass

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

        try:
            # First try assuming the session is already active (saves an API call)
            result = client.recall(
                agent_id=resolved_agent_id,
                query=query,
            )
        except Exception:
            # If there's an error (e.g. no active session), try to setup and retry
            _do_setup(resolved_agent_id)
            try:
                result = client.recall(
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

    def _do_setup(resolved_agent_id: str):
        try:
            client.create_agent(agent_id=resolved_agent_id, pattern="tool")
        except Exception:
            pass
        try:
            result = client.activate_agent(resolved_agent_id, duration_hours=6)
            client.session_token = result.get("session_token")
        except Exception:
            pass

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

        try:
            # First try assuming the session is already active
            client.remember(
                agent_id=resolved_agent_id,
                memory_type=None,
                title=title,
                content=content,
                source="langgraph-node",
                provenance="explicit_statement",
            )
        except Exception:
            # If there's an error, try to setup and retry
            _do_setup(resolved_agent_id)
            try:
                client.remember(
                    agent_id=resolved_agent_id,
                    memory_type=None,
                    title=title,
                    content=content,
                    source="langgraph-node",
                    provenance="explicit_statement",
                )
            except Exception as inner_e:
                logger.error(f"Remember failed after setup: {inner_e}")
        return {"messages": []}

    return remember_node
