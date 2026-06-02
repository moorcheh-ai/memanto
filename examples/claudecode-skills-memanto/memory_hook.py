"""
Memanto Skills Hook for Claude Code (and similar developer skills).

Implements a global memory hook to eliminate context fragmentation across
different command executions. It manages active extraction on skill completion
and dynamic injection on skill startup.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


class MemantoSkillsHook:
    """
    Hook to integrate Memanto memory into developer skills execution lifecycles.
    """

    def __init__(self, api_key: str, agent_id: str = "claudecode-skills") -> None:
        """
        Initialize the hook.

        Args:
            api_key: Moorcheh API key.
            agent_id: Unique identifier for the developer skills memory agent.
        """
        self.api_key = api_key
        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        self.initialized = False

    def initialize(self) -> None:
        """
        Ensure the agent exists and activate the session.
        """
        if self.initialized:
            return

        try:
            # Try to create the agent
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="tool",
                description="Global active memory agent for developer skills integration",
            )
            logger.info("Created Memanto skills agent '%s'", self.agent_id)
        except AgentAlreadyExistsError:
            logger.info("Memanto skills agent '%s' already exists, reusing", self.agent_id)
        except Exception as e:
            logger.error("Failed to create agent '%s': %s", self.agent_id, e)
            raise

        # Activate the session (6 hours default duration)
        self.client.activate_agent(self.agent_id, duration_hours=6)
        self.initialized = True
        logger.info("Activated session for skills agent '%s'", self.agent_id)

    def pre_skill_execute(
        self, skill_name: str, file_path: str | Path | None = None, task_description: str | None = None
    ) -> str | None:
        """
        Query Memanto for relevant memories and format them as system constraints.

        Args:
            skill_name: Name of the skill being executed (e.g. "/grill-with-docs", "/tdd").
            file_path: Path of the file(s) being operated on.
            task_description: The prompt or objective of the skill.

        Returns:
            A formatted prompt block to inject into the LLM context, or None if no memories found.
        """
        if not self.initialized:
            self.initialize()

        # Build a search query combining task description and file path info
        query_parts = []
        if task_description:
            query_parts.append(task_description)
        if file_path:
            p = Path(file_path)
            query_parts.append(f"file: {p.name}")
            if p.suffix:
                query_parts.append(f"extension: {p.suffix}")

        search_query = " ".join(query_parts) if query_parts else f"developer skill {skill_name}"

        try:
            # Query Memanto memory
            result = self.client.recall(
                agent_id=self.agent_id,
                query=search_query,
                limit=5,
                min_similarity=0.45,  # Moderate threshold for semantic match
            )

            memories = result.get("memories", [])
            if not memories:
                return None

            # Format the output block
            prompt_lines = [
                "\n==================================================",
                "💡 [Memanto Persistent Developer Memory Context]",
                "The following relevant engineering choices, preferences,",
                "and codebase quirks were recalled for this context:",
            ]

            for i, mem in enumerate(memories, 1):
                mem_type = mem.get("type", "fact")
                title = mem.get("title", "Untitled")
                content = mem.get("content", "")
                prompt_lines.append(f"  {i}. [{mem_type.upper()}] {title}: {content}")

            prompt_lines.append("Please align your actions strictly with these constraints.")
            prompt_lines.append("==================================================\n")

            return "\n".join(prompt_lines)

        except Exception as e:
            logger.warning("Failed to recall memories in pre_skill_execute: %s", e)
            return None

    def post_skill_execute(
        self, skill_name: str, file_path: str | Path | None, input_text: str, output_text: str
    ) -> dict[str, Any] | None:
        """
        Analyze the skill execution output, extract new engineering context/decisions,
        and save them to Memanto.

        Args:
            skill_name: Name of the executed skill.
            file_path: File path operated on.
            input_text: Input prompt or task.
            output_text: Generated response/outcome of the skill.

        Returns:
            Stored memory information dict, or None if no meaningful memory was extracted.
        """
        if not self.initialized:
            self.initialize()

        # Heuristic-based active extraction:
        # Detect key engineering choices, preference declarations, or architectural decisions
        # in the input/output interaction.
        extracted_type = None
        title = None
        content = None
        tags = ["developer-skill", skill_name.strip("/")]

        # Look for explicit rules, configuration, or preferences
        lower_input = input_text.lower()
        lower_output = output_text.lower()

        # 1. Architectural Decisions / Choices
        if any(w in lower_output for w in ["decided to", "we should use", "using package", "architecture choice"]):
            extracted_type = "decision"
            title = f"Architecture Decision in {skill_name}"
            # Extract a concise sentence containing the choice
            content = self._extract_snippet(output_text, ["use", "using", "decided", "implement"])
        # 2. Preferences
        elif any(w in lower_input for w in ["prefer", "always use", "never use", "style guide", "strict rule"]):
            extracted_type = "preference"
            title = f"Developer Preference via {skill_name}"
            content = input_text.strip()
        # 3. Codebase quirks/learnings (e.g. fixes or errors resolved)
        elif any(w in lower_output for w in ["fixed bug", "error occurred because", "resolved issue"]):
            extracted_type = "learning"
            title = f"Bug Resolve Learning in {skill_name}"
            content = self._extract_snippet(output_text, ["fix", "error", "because", "resolve"])
        # 4. Fallback: Generic instruction if explicit instruction detected
        elif "instruction" in lower_input or "tutorial" in lower_input:
            extracted_type = "instruction"
            title = f"Skill Directive for {skill_name}"
            content = output_text[:300] + "..." if len(output_text) > 300 else output_text

        if file_path:
            tags.append(Path(file_path).name)

        if not extracted_type or not content:
            # Nothing highly structured to extract
            return None

        # Format title & content guidelines
        title = title[:100]
        content = content[:500]  # Keep memories atomic and concise

        try:
            # Store memory in Memanto
            result = self.client.remember(
                agent_id=self.agent_id,
                memory_type=extracted_type,
                title=title,
                content=content,
                confidence=0.9,
                tags=tags,
                source="claudecode-skills",
            )
            return {
                "memory_id": result["memory_id"],
                "type": extracted_type,
                "title": title,
                "content": content,
            }
        except Exception as e:
            logger.warning("Failed to store memory in post_skill_execute: %s", e)
            return None

    def close(self) -> None:
        """
        Deactivate session and clean up.
        """
        if self.initialized:
            try:
                self.client.deactivate_agent(self.agent_id)
                logger.info("Deactivated session for skills agent '%s'", self.agent_id)
            except Exception as e:
                logger.warning("Failed to deactivate agent session during close: %s", e)
            finally:
                self.initialized = False

    def _extract_snippet(self, text: str, keywords: list[str]) -> str:
        """Helper to extract a relevant sentence/paragraph containing keywords."""
        sentences = text.split(".")
        for sentence in sentences:
            s_lower = sentence.lower()
            if any(kw in s_lower for kw in keywords):
                return sentence.strip() + "."
        # Fallback: first 150 characters
        return text[:150].strip() + "..."
