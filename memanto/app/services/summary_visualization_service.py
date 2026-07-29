"""
Summary Visualization Service

Generates ASCII-art timeline and graph visualizations from session MD files
and appends them to daily summary markdown files.
"""

import re
from collections import Counter
from datetime import datetime
from pathlib import Path


class SummaryVisualizationService:
    """Generates ASCII-art visualizations for daily summaries"""

    # Regex to parse session summary headings:
    #   ### [2026-02-27 14:30:00] [FACT] Some title
    _HEADING_RE = re.compile(
        r"^###\s+\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+\[(\w+)\]\s+(.+)$",
        re.MULTILINE,
    )
    # Regex to parse confidence lines:
    #   - **Confidence**: `0.85`
    _CONFIDENCE_RE = re.compile(
        r"^\-\s+\*\*Confidence\*\*:\s+`([\d.]+)`",
        re.MULTILINE,
    )

    def generate_visualizations(
        self,
        agent_id: str,
        date: str,
        sessions_dir: Path,
    ) -> str:
        """
        Parse session MD files for a given agent/date and return a
        complete Markdown visualization block.

        Args:
            agent_id: Agent identifier.
            date: Date string (YYYY-MM-DD).
            sessions_dir: Directory containing session summary MD files.

        Returns:
            Markdown string with visual insights (may be empty if no data).
        """
        memories = self._parse_session_files(agent_id, date, sessions_dir)
        return self.build_visualization_markdown(memories)

    def build_visualization_markdown(self, memories: list[dict]) -> str:
        """
        Build the full "Visual Insights" Markdown block from a list of memory
        records (``{timestamp, type, title, confidence}``).

        Shared by the per-day daily-summary path and aggregate metrics export.
        Returns an empty string when there are no memories.
        """
        if not memories:
            return ""

        sections: list[str] = [
            "\n\n---\n",
            "## 📊 Visual Insights\n",
        ]

        timeline = self._build_activity_timeline(memories)
        if timeline:
            sections.append(timeline)

        distribution = self._build_type_distribution(memories)
        if distribution:
            sections.append(distribution)

        confidence = self._build_confidence_overview(memories)
        if confidence:
            sections.append(confidence)

        from memanto.app.utils.temporal_helpers import format_current_local_time

        # Footer
        sections.append(
            f"*Visualizations auto-generated at {format_current_local_time()}*\n"
        )

        return "\n".join(sections)

    def append_visualizations_to_summary(
        self,
        agent_id: str,
        date: str,
        summary_path: Path,
        sessions_dir: Path,
    ) -> bool:
        """
        Generate visualizations and append them to an existing summary MD file.

        Args:
            agent_id: Agent identifier.
            date: Date string (YYYY-MM-DD).
            summary_path: Path to the daily summary MD file.
            sessions_dir: Directory containing session summary MD files.

        Returns:
            True if visualizations were appended, False otherwise.
        """
        viz_markdown = self.generate_visualizations(agent_id, date, sessions_dir)
        if not viz_markdown:
            return False

        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(viz_markdown)

        return True

    # Parsing
    def _parse_session_files(
        self, agent_id: str, date: str, sessions_dir: Path
    ) -> list[dict]:
        """
        Read all session summary MD files for the given agent/date and
        extract structured memory records.

        Returns a list of dicts:
            {"timestamp": datetime, "type": str, "title": str, "confidence": float}
        """
        pattern = f"{agent_id}_{date}_*_summary.md"
        session_files = list(sessions_dir.glob(pattern))
        if not session_files:
            return []

        memories: list[dict] = []

        for file_path in session_files:
            try:
                text = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            headings = list(self._HEADING_RE.finditer(text))
            confidences = list(self._CONFIDENCE_RE.finditer(text))

            for i, match in enumerate(headings):
                ts_str, mem_type, title = match.groups()
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                # Try to pair with the nearest confidence value
                conf = 0.8  # default
                if i < len(confidences):
                    try:
                        conf = float(confidences[i].group(1))
                    except (ValueError, IndexError):
                        pass

                memories.append(
                    {
                        "timestamp": ts,
                        "type": mem_type.upper(),
                        "title": title.strip(),
                        "confidence": conf,
                    }
                )

        # Sort by timestamp
        memories.sort(key=lambda m: m["timestamp"])
        return memories

    # Visualizations
    def _build_activity_timeline(self, memories: list[dict]) -> str:
        """
        Build a horizontal ASCII timeline showing memory events by hour.

        Example:
            Hour  00  03  06  09  12  15  18  21  24
                  ╠═══╬═══╬═══╬═══╬═══╬═══╬═══╬═══╣
                       ●       ●●  ●●● ●        ●●
        """
        if not memories:
            return ""

        # Count memories per hour
        hour_counts: Counter = Counter()
        for m in memories:
            hour_counts[m["timestamp"].hour] += 1

        # Build the hour labels row
        hour_labels = [f"{h:02d}" for h in range(0, 25, 3)]
        label_row = "Hour  " + "  ".join(hour_labels)

        # Build the axis bar
        bar = "      ╠" + "═══╬" * 7 + "═══╣"

        # Build the marker row — each 3-hour slot is 4 chars wide
        marker_parts: list[str] = []
        for slot_start in range(0, 24, 3):
            slot_count = sum(
                hour_counts.get(h, 0) for h in range(slot_start, slot_start + 3)
            )
            if slot_count == 0:
                marker_parts.append("    ")
            else:
                # Use ● markers, capped at 4 per slot to fit
                markers = "●" * min(slot_count, 4)
                marker_parts.append(markers.ljust(4))

        marker_row = "      " + "".join(marker_parts)

        # Count summary
        total = len(memories)
        active_hours = len(hour_counts)

        lines = [
            "### Memory Activity Timeline\n",
            "```",
            label_row,
            bar,
            marker_row,
            "```\n",
            f"**{total}** memories across **{active_hours}** active hours\n",
        ]
        return "\n".join(lines)

    def _build_type_distribution(self, memories: list[dict]) -> str:
        """
        Build a horizontal bar chart of memory type counts.

        Example:
            FACT        ████████████████ 8
            DECISION    ████████ 4
        """
        if not memories:
            return ""

        type_counts = Counter(m["type"] for m in memories)
        if not type_counts:
            return ""

        # Sort by count descending
        sorted_types = type_counts.most_common()
        max_count = sorted_types[0][1]

        # Scale bars to max width of 20 chars
        max_bar_width = 20
        scale = max_bar_width / max_count if max_count > 0 else 1

        # Determine label width for alignment
        max_label_len = max(len(t) for t, _ in sorted_types)

        lines = ["### Memory Type Distribution\n", "```"]
        for mem_type, count in sorted_types:
            bar_len = max(1, round(count * scale))
            bar = "█" * bar_len
            label = mem_type.ljust(max_label_len)
            lines.append(f"{label}  {bar} {count}")
        lines.append("```\n")

        return "\n".join(lines)

    def _build_confidence_overview(self, memories: list[dict]) -> str:
        """
        Build a Markdown table summarizing confidence metrics.
        """
        if not memories:
            return ""

        confidences = [m["confidence"] for m in memories]
        total = len(confidences)
        avg = sum(confidences) / total if total else 0
        high = sum(1 for c in confidences if c >= 0.8)
        medium = sum(1 for c in confidences if 0.5 <= c < 0.8)
        low = sum(1 for c in confidences if c < 0.5)

        lines = [
            "### Confidence Overview\n",
            "| Metric          | Value |",
            "|-----------------|-------|",
            f"| Total Memories  | {total}     |",
            f"| Avg Confidence  | {avg:.2f}  |",
            f"| High (≥0.8)     | {high}     |",
            f"| Medium (0.5–0.8)| {medium}     |",
            f"| Low (<0.5)      | {low}     |",
            "",
        ]
        return "\n".join(lines)
