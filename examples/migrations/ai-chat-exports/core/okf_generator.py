from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core.models import MemoryEntity


class OKFGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)

    def generate_bundle(self, entities: list[MemoryEntity]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        memories_dir = self.output_dir / "memories"
        metrics_dir = self.output_dir / "metrics"

        type_groups: dict[str, list[MemoryEntity]] = {}
        for e in entities:
            type_groups.setdefault(e.source_type.value, []).append(e)

        for mem_type, group in type_groups.items():
            type_dir = memories_dir / mem_type
            type_dir.mkdir(parents=True, exist_ok=True)
            for entity in group:
                self._write_memory(entity, type_dir)
            self._write_type_index(group, type_dir, mem_type)

        self._write_bundle_index(type_groups, memories_dir)
        self._write_metrics(entities, type_groups, metrics_dir)

        return self.output_dir

    def _write_memory(self, entity: MemoryEntity, type_dir: Path) -> Path:
        filepath = type_dir / self._filename(entity)

        ts = ""
        if entity.timestamp:
            ts = entity.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

        tags_str = ", ".join(entity.tags) if entity.tags else ""

        lines = [
            "---",
            f"type: {entity.source_type.value}",
            f'title: "{MemoryEntity._escape_yaml(entity.title)}"',
            f'description: "{MemoryEntity._escape_yaml(entity.content[:120])}"',
            f"tags: [{tags_str}]",
        ]
        if ts:
            lines.append(f"timestamp: {ts}")
        if entity.source_ref:
            lines.append(f"resource: {entity.source_ref}")
        lines.append("x_memanto:")
        lines.append(f"  confidence: {entity.confidence}")
        lines.append(f"  provenance: {entity.provenance}")
        lines.append(f"  source: {entity.source}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {entity.title}")
        lines.append("")
        lines.append(entity.content)

        filepath.write_text("\n".join(lines), encoding="utf-8")
        return filepath

    def _filename(self, entity: MemoryEntity) -> str:
        unique_id = entity.source_ref.split("/")[-1] if entity.source_ref else ""
        base = self._safe_filename(entity.title)
        if unique_id:
            return f"{base}-{unique_id}.md"
        return f"{base}.md"

    def _write_type_index(
        self, entities: list[MemoryEntity], type_dir: Path, mem_type: str
    ) -> None:
        lines = [f"# {mem_type}", ""]
        for e in entities:
            filename = self._filename(e)
            lines.append(f"- [{e.title}]({filename})")
        (type_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")

    def _write_bundle_index(
        self, type_groups: dict[str, list[MemoryEntity]], memories_dir: Path
    ) -> None:
        lines = ["# OKF Memory Bundle", ""]
        for mem_type, group in sorted(type_groups.items()):
            lines.append(f"## {mem_type} ({len(group)})")
            lines.append("")
            lines.append(f"- [Browse {mem_type}](memories/{mem_type}/index.md)")
            lines.append("")

        (self.output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")

    def _write_metrics(
        self,
        entities: list[MemoryEntity],
        type_groups: dict[str, list[MemoryEntity]],
        metrics_dir: Path,
    ) -> None:
        metrics_dir.mkdir(parents=True, exist_ok=True)

        type_counts = Counter(e.source_type.value for e in entities)
        source_counts = Counter(e.source for e in entities)
        total_tags: Counter = Counter()
        for e in entities:
            total_tags.update(e.tags)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        lines = [
            "# Migration Metrics",
            "",
            f"**Generated:** {now}",
            f"**Total memories:** {len(entities)}",
            "",
            "## By type",
            "",
        ]

        max_count = max(type_counts.values()) if type_counts else 1
        lines.extend(["| Type | Count | Share |", "| --- | --- | --- |"])
        for mem_type, count in type_counts.most_common():
            bar_len = int((count / max_count) * 20) if max_count else 0
            bar = "\u2588" * bar_len
            pct = (count / len(entities) * 100) if entities else 0
            lines.append(f"| {mem_type:<20} | {count:>4} ({pct:.0f}%) | {bar} |")

        lines.extend(["", "## By source", ""])
        for src, count in source_counts.most_common():
            lines.append(f"- **{src or 'unknown'}**: {count}")

        if total_tags:
            lines.extend(["", "## Top tags", ""])
            for tag, count in total_tags.most_common(10):
                lines.append(f"- `{tag}`: {count}")

        (metrics_dir / "overview.md").write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _safe_filename(title: str, max_len: int = 80) -> str:
        safe = ""
        for ch in title:
            if ch.isalnum() or ch in ("-", "_"):
                safe += ch
            elif ch in (" ", "\t"):
                safe += "-"
        safe = safe.strip("-").lower()
        if len(safe) > max_len:
            safe = safe[:max_len].rstrip("-")
        return safe or "unnamed"
