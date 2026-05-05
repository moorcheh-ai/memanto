"""
Daily Summary Service

Aggregates session MD files for a specific day and generates an AI summary.
"""

import json
from pathlib import Path
from typing import Any, cast

from moorcheh_sdk import MoorchehClient

from memanto.app.config import settings
from memanto.app.core import create_memory_scope
from memanto.app.services.session_service import get_session_service
from memanto.app.utils.errors import MemoryError
from memanto.app.utils.temporal_helpers import (
    format_current_local_time,
    format_local_time,
)


class DailySummaryService:
    """Service for generating daily summaries from session MD files"""

    def __init__(
        self,
        api_key: str,
        sessions_dir: Path | None = None,
        summaries_dir: Path | None = None,
    ):
        """
        Initialize the daily summary service

        Args:
            api_key: Moorcheh API key (passed from DirectClient config)
            sessions_dir: Directory where session MD files are stored
            summaries_dir: Directory where generated summaries will be saved
        """
        self.api_key = api_key
        self.session_service = get_session_service()
        self.sessions_dir = sessions_dir or self.session_service.sessions_dir
        self.summaries_dir = summaries_dir or Path.home() / ".memanto" / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)

    def generate_summary(
        self, agent_id: str, date: str, output_path: str | None = None
    ) -> dict[str, Any]:
        """
        Generate a daily natural language summary for an agent and date.
        """
        # Find all relevant session MD files
        pattern = f"{agent_id}_{date}_*_summary.md"
        session_files = list(self.sessions_dir.glob(pattern))

        if not session_files:
            return {"status": "no_sessions"}

        combined_content = []
        for file_path in session_files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    combined_content.append(f.read())
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

        if not combined_content:
            return {"status": "empty_sessions"}

        full_text = "\n\n---\n\n".join(combined_content)

        client = MoorchehClient(api_key=self.api_key)
        scope = create_memory_scope("agent", agent_id)
        namespace = scope.to_namespace()

        summary_prompt = f"""
Summarize the following session memories from {date} into a concise natural language daily summary.
Focus on key themes, accomplishments, and high-level activities.

Sessions Content:
{full_text}

Format the output as a Markdown report:
# Daily Summary for {agent_id} - {date}
**Generated at:** {format_current_local_time()}

## Executive Summary
...
## Key Themes & Activities
...
"""
        try:
            result = client.answer.generate(
                namespace=namespace,
                query=summary_prompt,
                ai_model=settings.SUMMARY_MODEL,
                top_k=50,
            )
            summary_text = result.get("answer", "Failed to generate summary.")
        except Exception as e:
            raise MemoryError(f"AI summarization failed: {str(e)}")

        if output_path:
            summary_path = Path(output_path)
            # Ensure parent directories exist
            summary_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            summary_path = self.summaries_dir / f"{agent_id}_{date}.md"

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_text)

        # Append visual insights (timeline, type distribution, confidence)
        try:
            from memanto.app.services.summary_visualization_service import (
                SummaryVisualizationService,
            )

            viz_service = SummaryVisualizationService()
            viz_service.append_visualizations_to_summary(
                agent_id=agent_id,
                date=date,
                summary_path=summary_path,
                sessions_dir=self.sessions_dir,
            )
        except Exception as e:
            print(f"Warning: Failed to append visualizations: {e}")

        return {
            "status": "success",
            "summary_path": str(summary_path),
            "sessions_count": len(session_files),
            "agent_id": agent_id,
            "date": date,
        }

    def generate_conflict_report(self, agent_id: str, date: str) -> dict[str, Any]:
        """
        Generate a structured conflict report (Contradictions, Conflicts, Updates, Duplicates).
        """

        conflicts_dir = Path.home() / ".memanto" / "conflicts"
        conflicts_dir.mkdir(parents=True, exist_ok=True)

        pattern = f"{agent_id}_{date}_*_summary.md"
        session_files = list(self.sessions_dir.glob(pattern))

        if not session_files:
            return {"status": "no_sessions"}

        combined_content = []
        for file_path in session_files:
            with open(file_path, encoding="utf-8") as f:
                combined_content.append(f.read())

        full_text = "\n\n---\n\n".join(combined_content)

        client = MoorchehClient(api_key=self.api_key)
        scope = create_memory_scope("agent", agent_id)
        namespace = scope.to_namespace()

        conflict_prompt = f"""
Analyze the following session memories from {date} against historical knowledge for this agent.

CRITICAL INSTRUCTIONS:
1. ONLY report conflicts, contradictions, updates, or duplicates that involve AT LEAST ONE of the memories from the "Recent Sessions Content" provided below.
2. DO NOT report conflicts that exist solely between two or more historical memories (Old vs Old). We are only interested in how the NEW data interacts with existing knowledge.
3. If a new memory replaces an old one, clearly identify which is which.
4. NEVER report a conflict where the old_memory_id and new_memory_id are THE SAME. If both IDs match, that is the same memory retrieved from the knowledge base — skip it entirely.

Identify:
1. Contradictions: New info contradicting old facts.
2. Updates: Improvements or changes to existing knowledge provided by new memories.
3. Duplicates: New memories that are redundant with historical ones.
4. Conflicts: Semantic disagreements between new and historical memories.

Recent Sessions Content:
{full_text}

You MUST respond with ONLY a valid JSON array. No markdown, no explanation, no code fences.
Each element must be an object with these exact keys:
- "type": one of "contradiction", "update", "duplicate", "conflict"
- "title": short description of the issue
- "old_memory_id": the ID of the historical/old memory (or null if unknown)
- "old_content": a brief summary of what the old memory says
- "new_memory_id": the ID of the new/recent memory (or null if unknown)
- "new_content": a brief summary of what the new memory says
- "description": detailed explanation of the conflict
- "recommendation": one of "keep_new", "keep_old", "merge", "remove_both"

If there are NO conflicts, return an empty array: []

Example response format:
[{{"type": "contradiction", "title": "Database preference changed", "old_memory_id": "abc-123", "old_content": "We use PostgreSQL", "new_memory_id": "def-456", "new_content": "We migrated to MongoDB", "description": "New memory contradicts old database preference", "recommendation": "keep_new"}}]
"""
        try:
            result = client.answer.generate(
                namespace=namespace,
                query=conflict_prompt,
                ai_model=settings.SUMMARY_MODEL,
                top_k=50,
            )
            conflict_text = result.get("answer", "[]")
        except Exception as e:
            raise MemoryError(f"Conflict detection failed: {str(e)}")

        # Parse JSON from the AI response
        conflicts_data = []
        try:
            # Strip markdown code fences if the model wraps the JSON
            clean_text = conflict_text.strip()
            if clean_text.startswith("```"):
                # Remove opening fence (```json or ```)
                clean_text = (
                    clean_text.split("\n", 1)[1]
                    if "\n" in clean_text
                    else clean_text[3:]
                )
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3].strip()

            parsed = json.loads(clean_text)
            if isinstance(parsed, list):
                # Filter out self-referencing conflicts (same ID on both sides)
                parsed = [
                    item
                    for item in parsed
                    if not (
                        item.get("old_memory_id")
                        and item.get("new_memory_id")
                        and item["old_memory_id"] == item["new_memory_id"]
                    )
                ]
                # Add resolved=False, resolution, and timestamps to each conflict
                for item in parsed:
                    item.setdefault("resolved", False)
                    item.setdefault("resolution", None)

                    # Fetch timestamps and source
                    for prefix in ["old", "new"]:
                        mem_id = item.get(f"{prefix}_memory_id")
                        # Default values
                        item[f"{prefix}_created_at"] = None
                        item[f"{prefix}_source"] = "unknown"

                        if mem_id:
                            try:
                                doc_result = client.documents.get(
                                    namespace_name=namespace, ids=[mem_id]
                                )
                                # Note: Moorcheh SDK documents.get returns the list under "items", not "documents" contrary to its typed response model
                                doc_dict = cast(dict[str, Any], doc_result)
                                if doc_dict and doc_dict.get("items"):
                                    doc = doc_dict["items"][0]
                                    metadata = doc.get("metadata") or {}

                                    # Fallback to flat fields if metadata object is empty
                                    created_at = metadata.get("created_at") or doc.get(
                                        "created_at"
                                    )
                                    source = (
                                        metadata.get("source")
                                        or doc.get("source")
                                        or "unknown"
                                    )

                                    item[f"{prefix}_created_at"] = format_local_time(
                                        created_at
                                    )
                                    item[f"{prefix}_source"] = source
                            except Exception as e:
                                print(
                                    f"Note: Could not fetch metadata for memory {mem_id}: {e}"
                                )

                conflicts_data = parsed
        except (json.JSONDecodeError, ValueError):
            # If AI didn't return valid JSON, wrap the raw text as a single conflict
            if conflict_text.strip() and conflict_text.strip() != "[]":
                conflicts_data = [
                    {
                        "type": "conflict",
                        "title": "Unparsed conflict report",
                        "old_memory_id": None,
                        "old_content": None,
                        "new_memory_id": None,
                        "new_content": None,
                        "description": conflict_text,
                        "recommendation": "merge",
                        "resolved": False,
                        "resolution": None,
                    }
                ]

        # Save structured JSON for interactive resolution
        json_path = conflicts_dir / f"{agent_id}_{date}_conflicts.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(conflicts_data, f, indent=2, default=str)

        return {
            "status": "success",
            "json_path": str(json_path),
            "conflict_count": len(conflicts_data),
        }
