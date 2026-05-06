"""
MemantoAgentMemory - Drop-in memory provider for CrewAI using MEMANTO.

This module provides a MemantoAgentMemory class that implements
CrewAI's memory interface using MEMANTO's persistent memory layer.

Usage:
    from memanto_memory import MemantoAgentMemory

    memory = MemantoAgentMemory(agent_id="my-agent")
    memory.remember("User prefers dark mode", memory_type="preference")
    results = memory.recall("dark mode preferences")
"""

import subprocess
import json
import os
import time
from typing import Optional, List, Dict, Any


class MemantoAgentMemory:
    """
    MEMANTO-based memory for AI agents.

    Provides remember, recall, and answer operations using MEMANTO's
    typed semantic memory with zero ingestion latency.
    """

    def __init__(
        self,
        agent_id: str = "crewai-memanto-agent",
        api_key: Optional[str] = None,
        auto_activate: bool = True,
    ):
        """
        Initialize MEMANTO memory.

        Args:
            agent_id: Unique identifier for this agent's memory namespace
            api_key: Moorcheh API key (falls back to MOORCHEH_API_KEY env var)
            auto_activate: Whether to auto-activate the agent on init
        """
        self.agent_id = agent_id
        self._api_key = api_key or os.getenv("MOORCHEH_API_KEY")
        self._stats = {"stored": 0, "recalled": 0, "errors": 0}

        if not self._api_key:
            print("[MEMANTO] Warning: MOORCHEH_API_KEY not set. "
                  "Set it in .env or pass api_key parameter.")

        if auto_activate:
            self._ensure_agent_active()

    def _ensure_agent_active(self) -> bool:
        """Activate the MEMANTO agent session."""
        try:
            result = subprocess.run(
                ["memanto", "agent", "activate", self.agent_id],
                check=True, capture_output=True, text=True, timeout=15
            )
            if "activated" in result.stdout.lower() or "created" in result.stdout.lower():
                print(f"[MEMANTO] Agent '{self.agent_id}' activated.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[MEMANTO] Warning: Could not activate agent: {e.stderr}")
            return False
        except FileNotFoundError:
            print("[MEMANTO] Error: 'memanto' CLI not found. Install with: pip install memanto")
            self._stats["errors"] += 1
            return False
        except Exception as e:
            print(f"[MEMANTO] Warning: {e}")
            return False

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        tags: Optional[str] = None,
        confidence: float = 0.9,
        provenance: str = "agent_observation",
    ) -> bool:
        """
        Store a memory in MEMANTO.

        Args:
            content: The memory content to store
            memory_type: Type of memory (fact, preference, goal, instruction,
                        decision, relationship, etc.)
            tags: Comma-separated tags for categorization
            confidence: Confidence score (0.0 to 1.0)
            provenance: Source of the memory

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            cmd = [
                "memanto", "remember", content,
                "--type", memory_type,
                "--confidence", str(min(max(confidence, 0.0), 1.0)),
                "--provenance", provenance,
                "--source", self.agent_id,
            ]
            if tags:
                cmd.extend(["--tags", tags])

            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            self._stats["stored"] += 1
            return True

        except subprocess.CalledProcessError as e:
            print(f"[MEMANTO] Error remembering: {e.stderr.decode() if e.stderr else str(e)}")
            self._stats["errors"] += 1
            return False
        except Exception as e:
            print(f"[MEMANTO] Error: {e}")
            self._stats["errors"] += 1
            return False

    def recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search memories using semantic similarity.

        Args:
            query: Natural language search query
            limit: Maximum number of results to return

        Returns:
            List of matching memory objects with content, type, confidence, etc.
        """
        try:
            result = subprocess.run(
                ["memanto", "recall", query, "--limit", str(limit), "--json"],
                check=True, capture_output=True, text=True, timeout=15
            )

            self._stats["recalled"] += 1

            if result.stdout.strip():
                parsed = json.loads(result.stdout)
                # MEMANTO may return a list directly or wrapped in a structure
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict) and "results" in parsed:
                    return parsed["results"]
                elif isinstance(parsed, dict) and "memories" in parsed:
                    return parsed["memories"]
                return [parsed]

            return []

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"[MEMANTO] Error recalling: {e}")
            self._stats["errors"] += 1
            return []
        except Exception as e:
            print(f"[MEMANTO] Error: {e}")
            self._stats["errors"] += 1
            return []

    def answer(self, question: str) -> str:
        """
        Ask a question answered from memory (RAG).

        Args:
            question: Natural language question

        Returns:
            Answer generated from relevant memories
        """
        try:
            result = subprocess.run(
                ["memanto", "answer", question],
                check=True, capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode() if e.stderr else str(e)
            return f"[MEMANTO] Error: {err}"
        except Exception as e:
            return f"[MEMANTO] Error: {e}"

    def get_stats(self) -> Dict[str, int]:
        """Get memory operation statistics."""
        return dict(self._stats)

    def clear(self) -> bool:
        """Clear all memories for this agent (use with caution)."""
        try:
            subprocess.run(
                ["memanto", "memory", "clear", "--agent", self.agent_id, "--force"],
                check=True, capture_output=True, timeout=15
            )
            self._stats["stored"] = 0
            return True
        except Exception as e:
            print(f"[MEMANTO] Error clearing memories: {e}")
            return False


# Convenience functions for quick use

def create_memory(agent_id: str = "crewai-agent") -> MemantoAgentMemory:
    """Create and return a MEMANTO memory instance."""
    return MemantoAgentMemory(agent_id=agent_id)


def quick_remember(content: str, agent_id: str = "crewai-agent", **kwargs) -> bool:
    """One-shot remember."""
    mem = MemantoAgentMemory(agent_id=agent_id)
    return mem.remember(content, **kwargs)


def quick_recall(query: str, agent_id: str = "crewai-agent", **kwargs) -> list:
    """One-shot recall."""
    mem = MemantoAgentMemory(agent_id=agent_id)
    return mem.recall(query, **kwargs)
