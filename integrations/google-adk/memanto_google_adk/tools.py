"""A tool that lets an ADK agent save a memory the moment it hears one.

Reading needs no Memanto-specific tool: ADK's ``load_memory`` and
``preload_memory`` call the configured memory service. This tool writes through
the same service (``tool_context.add_memory``), scoped to the current app and
user by ADK, so the model can never pick whose memory it writes.
"""

from __future__ import annotations

from google.adk.memory.memory_entry import MemoryEntry
from google.adk.tools import FunctionTool, ToolContext
from google.genai import types

from memanto.app.constants import VALID_MEMORY_TYPES


async def memanto_remember(
    content: str, memory_type: str, tool_context: ToolContext
) -> dict[str, str]:
    """Save one durable fact about the user to long-term memory.

    Use this when the user states something worth remembering in future
    conversations: a preference, a goal, a decision, a commitment, a fact
    about themselves. Save one self-contained statement per call. Never save
    passwords, payment details or other secrets.

    Args:
      content: The memory, written as a standalone statement, e.g.
        "User is vegetarian and allergic to peanuts."
      memory_type: One of fact, preference, goal, decision, artifact,
        learning, event, instruction, relationship, context, observation,
        commitment, error.
    """
    content = content.strip()
    memory_type = memory_type.strip().lower()
    if not content:
        return {"status": "error", "error": "content is required"}
    if memory_type not in VALID_MEMORY_TYPES:
        return {
            "status": "error",
            "error": "memory_type must be one of: "
            + ", ".join(sorted(VALID_MEMORY_TYPES)),
        }
    await tool_context.add_memory(
        memories=[
            MemoryEntry(
                content=types.Content(
                    role="user", parts=[types.Part.from_text(text=content)]
                ),
                custom_metadata={"type": memory_type},
            )
        ]
    )
    return {"status": "saved"}


remember_tool = FunctionTool(memanto_remember)
