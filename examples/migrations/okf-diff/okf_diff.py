#!/usr/bin/env python3
"""Inspect two Open Knowledge Format bundles and explain what changed.

The comparison is semantic rather than file based. Entries are matched by the
stable Memanto id when available, then by resource, then by type and title.
This keeps the report useful when an OKF bundle changes layout or split mode.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from memanto.cli.migrate.okf_loader import load_okf_bundle

SEMANTIC_FIELDS = (
    "type",
    "title",
    "description",
    "resource",
    "tags",
    "timestamp",
    "body",
    "x_memanto",
    "links",
    "extra",
)


@dataclass(frozen=True)
class EntryChange:
    """One matched, added, or removed OKF entry."""

    key: str
    status: str
    title: str
    memory_type: str
    changed_fields: tuple[str, ...]
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclass(frozen=True)
class BundleDiff:
    """Deterministic comparison result for two OKF bundles."""

    before_path: str
    after_path: str
    before_count: int
    after_count: int
    changes: tuple[EntryChange, ...]

    @property
    def counts(self) -> dict[str, int]:
        counter = Counter(change.status for change in self.changes)
        return {
            status: counter.get(status, 0)
            for status in ("added", "removed", "changed", "unchanged")
        }

    @property
    def has_changes(self) -> bool:
        counts = self.counts
        return bool(counts["added"] or counts["removed"] or counts["changed"])

    @property
    def has_removals(self) -> bool:
        return self.counts["removed"] > 0


def _normalized(value: Any) -> Any:
    """Return a JSON-safe value with deterministic mapping and set ordering."""
    if isinstance(value, dict):
        return {str(key): _normalized(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalized(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _semantic_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = {field: _normalized(entry.get(field)) for field in SEMANTIC_FIELDS}
    payload["tags"] = sorted(str(tag) for tag in (entry.get("tags") or []))
    payload["links"] = sorted(str(link) for link in (entry.get("links") or []))
    return payload


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _clean_identity(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _base_key(entry: dict[str, Any]) -> str:
    extension = entry.get("x_memanto")
    if isinstance(extension, dict) and extension.get("id"):
        return f"id:{_clean_identity(extension['id'])}"
    if entry.get("resource"):
        return f"resource:{_clean_identity(entry['resource'])}"
    memory_type = _clean_identity(entry.get("type")) or "unknown"
    title = _clean_identity(entry.get("title")) or "untitled"
    return f"title:{memory_type}:{title}"


def _load_entries(path: str | Path) -> list[dict[str, Any]]:
    loaded = load_okf_bundle(path)
    entries = loaded.get("memories")
    if not isinstance(entries, list):
        raise ValueError(f"OKF loader returned an invalid memories list for {path}")
    return [entry for entry in entries if isinstance(entry, dict)]


def _group_entries(
    entries: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[_base_key(entry)].append(entry)
    for group in grouped.values():
        group.sort(
            key=lambda entry: (_digest(_semantic_payload(entry)), entry["source_path"])
        )
    return dict(grouped)


def _pair_group(
    base_key: str,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]]:
    """Match exact duplicate payloads first, then pair remaining entries."""
    pairs: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = []
    before_remaining = list(before)
    after_remaining = list(after)

    after_by_digest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in after_remaining:
        after_by_digest[_digest(_semantic_payload(entry))].append(entry)

    exact_before_ids: set[int] = set()
    exact_after_ids: set[int] = set()
    for entry in before_remaining:
        matches = after_by_digest.get(_digest(_semantic_payload(entry)), [])
        if matches:
            match = matches.pop(0)
            exact_before_ids.add(id(entry))
            exact_after_ids.add(id(match))
            pairs.append(("", entry, match))

    before_remaining = [
        entry for entry in before_remaining if id(entry) not in exact_before_ids
    ]
    after_remaining = [
        entry for entry in after_remaining if id(entry) not in exact_after_ids
    ]

    pair_count = min(len(before_remaining), len(after_remaining))
    for index in range(pair_count):
        pairs.append(("", before_remaining[index], after_remaining[index]))
    for entry in before_remaining[pair_count:]:
        pairs.append(("", entry, None))
    for entry in after_remaining[pair_count:]:
        pairs.append(("", None, entry))

    pairs.sort(
        key=lambda pair: (
            _digest(_semantic_payload(pair[1] or pair[2] or {})),
            (pair[1] or pair[2] or {}).get("source_path", ""),
        )
    )
    suffix_needed = len(pairs) > 1
    return [
        (
            f"{base_key}#{index + 1}" if suffix_needed else base_key,
            old,
            new,
        )
        for index, (_, old, new) in enumerate(pairs)
    ]


def compare_bundles(before_path: str | Path, after_path: str | Path) -> BundleDiff:
    """Load and compare two OKF bundles."""
    before_entries = _load_entries(before_path)
    after_entries = _load_entries(after_path)
    before_groups = _group_entries(before_entries)
    after_groups = _group_entries(after_entries)

    changes: list[EntryChange] = []
    for base_key in sorted(set(before_groups) | set(after_groups)):
        for key, before, after in _pair_group(
            base_key,
            before_groups.get(base_key, []),
            after_groups.get(base_key, []),
        ):
            old_payload = _semantic_payload(before) if before else None
            new_payload = _semantic_payload(after) if after else None
            if before is None:
                status = "added"
                changed_fields = tuple(SEMANTIC_FIELDS)
            elif after is None:
                status = "removed"
                changed_fields = tuple(SEMANTIC_FIELDS)
            else:
                changed_fields = tuple(
                    field
                    for field in SEMANTIC_FIELDS
                    if old_payload
                    and new_payload
                    and old_payload[field] != new_payload[field]
                )
                status = "changed" if changed_fields else "unchanged"

            visible = after or before or {}
            changes.append(
                EntryChange(
                    key=key,
                    status=status,
                    title=str(visible.get("title") or "Untitled"),
                    memory_type=str(visible.get("type") or "unknown"),
                    changed_fields=changed_fields,
                    before=old_payload,
                    after=new_payload,
                )
            )

    status_order = {"removed": 0, "changed": 1, "added": 2, "unchanged": 3}
    changes.sort(
        key=lambda change: (
            status_order[change.status],
            change.memory_type.casefold(),
            change.title.casefold(),
            change.key,
        )
    )
    return BundleDiff(
        before_path=str(Path(before_path)),
        after_path=str(Path(after_path)),
        before_count=len(before_entries),
        after_count=len(after_entries),
        changes=tuple(changes),
    )


def _serializable(diff: BundleDiff) -> dict[str, Any]:
    return {
        "before_path": diff.before_path,
        "after_path": diff.after_path,
        "before_count": diff.before_count,
        "after_count": diff.after_count,
        "counts": diff.counts,
        "has_changes": diff.has_changes,
        "changes": [asdict(change) for change in diff.changes],
    }


def render_json(diff: BundleDiff) -> str:
    return json.dumps(_serializable(diff), indent=2, sort_keys=True) + "\n"


def _display_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "(empty)"
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _body_patch(before: Any, after: Any) -> str:
    old_lines = str(before or "").splitlines()
    new_lines = str(after or "").splitlines()
    return "\n".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


def render_markdown(diff: BundleDiff) -> str:
    counts = diff.counts
    lines = [
        "# OKF bundle diff",
        "",
        f"- Before: `{diff.before_path}` ({diff.before_count} entries)",
        f"- After: `{diff.after_path}` ({diff.after_count} entries)",
        (
            f"- Result: {counts['added']} added, {counts['removed']} removed, "
            f"{counts['changed']} changed, {counts['unchanged']} unchanged"
        ),
        "",
    ]
    for change in diff.changes:
        if change.status == "unchanged":
            continue
        lines.extend(
            [
                f"## {change.title}",
                "",
                f"- Status: {change.status}",
                f"- Type: `{change.memory_type}`",
                f"- Identity: `{change.key}`",
                f"- Changed fields: {', '.join(change.changed_fields)}",
                "",
            ]
        )
        if "body" in change.changed_fields and change.before and change.after:
            lines.extend(
                [
                    "```diff",
                    _body_patch(change.before.get("body"), change.after.get("body")),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _html_value(value: Any) -> str:
    return html.escape(_display_value(value))


def _change_detail(change: EntryChange) -> str:
    before = change.before or {}
    after = change.after or {}
    fields = change.changed_fields if change.status == "changed" else SEMANTIC_FIELDS
    rows = []
    for field in fields:
        rows.append(
            "<div class='field'>"
            f"<h3>{html.escape(field.replace('_', ' '))}</h3>"
            "<div class='values'>"
            f"<pre>{_html_value(before.get(field))}</pre>"
            f"<pre>{_html_value(after.get(field))}</pre>"
            "</div>"
            "</div>"
        )
    return "".join(rows)


def render_html(diff: BundleDiff) -> str:
    """Render a standalone, searchable HTML inspection report."""
    counts = diff.counts
    rows = []
    for change in diff.changes:
        search = " ".join(
            (change.title, change.memory_type, change.key, *change.changed_fields)
        ).casefold()
        rows.append(
            f"<details class='entry {change.status}' "
            f"data-status='{change.status}' data-search='{html.escape(search)}'>"
            "<summary>"
            f"<span class='status'>{change.status}</span>"
            "<span class='identity'>"
            f"<strong>{html.escape(change.title)}</strong>"
            f"<span>{html.escape(change.memory_type)} · "
            f"{html.escape(change.key)}</span>"
            "</span>"
            f"<span class='field-count'>{len(change.changed_fields)} fields</span>"
            "</summary>"
            f"<div class='detail'>{_change_detail(change)}</div>"
            "</details>"
        )

    stat_blocks = "".join(
        f"<div class='stat {status}'><strong>{counts[status]}</strong>"
        f"<span>{status}</span></div>"
        for status in ("added", "removed", "changed", "unchanged")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OKF bundle diff</title>
<link rel="icon" href="data:,">
<style>
:root {{
  color-scheme: light;
  --ground: #dcecf2;
  --sheet: #f8fcfd;
  --ink: #102a36;
  --muted: #526d78;
  --blue: #006f8f;
  --cyan: #00a8c6;
  --orange: #d64f23;
  --red: #a92530;
  --green: #147a62;
  --shadow: 8px 8px 0 #102a36;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background:
    linear-gradient(rgba(16,42,54,.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(16,42,54,.055) 1px, transparent 1px),
    var(--ground);
  background-size: 24px 24px;
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}}
main {{ width: min(1180px, calc(100% - 40px)); margin: 48px auto 80px; }}
header {{
  background: var(--ink);
  color: var(--sheet);
  padding: clamp(28px, 5vw, 64px);
  box-shadow: var(--shadow);
}}
h1 {{
  margin: 0;
  max-width: 780px;
  font-family: Arial, Helvetica, sans-serif;
  font-size: clamp(48px, 9vw, 104px);
  line-height: .88;
  letter-spacing: -.065em;
}}
.paths {{ margin: 28px 0 0; display: grid; gap: 8px; color: #b9d9e3; }}
.paths span {{ overflow-wrap: anywhere; }}
.stats {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin: 40px 0;
}}
.stat {{ min-height: 132px; padding: 20px; background: var(--sheet); }}
.stat strong {{
  display: block;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 58px;
  line-height: 1;
}}
.stat span {{ display: block; margin-top: 12px; color: var(--muted); }}
.stat.added {{ background: #bcebdc; }}
.stat.removed {{ background: #ffc9c6; }}
.stat.changed {{ background: #ffd5ae; }}
.controls {{
  display: grid;
  grid-template-columns: minmax(240px, 1fr) auto;
  gap: 16px;
  align-items: center;
  margin-bottom: 24px;
}}
input {{
  width: 100%;
  min-height: 52px;
  border: 3px solid var(--ink);
  border-radius: 0;
  background: var(--sheet);
  color: var(--ink);
  font: inherit;
  padding: 0 16px;
}}
.filters {{ display: flex; flex-wrap: wrap; gap: 8px; }}
button {{
  min-height: 44px;
  border: 0;
  border-radius: 0;
  background: var(--ink);
  color: white;
  cursor: pointer;
  font: inherit;
  padding: 0 15px;
}}
button:hover, button[aria-pressed="true"] {{ background: var(--cyan); color: var(--ink); }}
.ledger {{ display: grid; gap: 12px; }}
.entry {{ background: var(--sheet); box-shadow: 4px 4px 0 var(--ink); }}
.entry[hidden] {{ display: none; }}
summary {{
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  min-height: 86px;
  padding: 16px 20px;
  cursor: pointer;
  list-style: none;
}}
summary::-webkit-details-marker {{ display: none; }}
summary:hover {{ background: #ffffff; }}
.status {{ font-weight: 800; }}
.added .status {{ color: var(--green); }}
.removed .status {{ color: var(--red); }}
.changed .status {{ color: var(--orange); }}
.unchanged .status {{ color: var(--blue); }}
.identity {{ min-width: 0; }}
.identity strong {{
  display: block;
  overflow: hidden;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.identity span {{
  display: block;
  margin-top: 6px;
  color: var(--muted);
  overflow-wrap: anywhere;
}}
.field-count {{ color: var(--muted); white-space: nowrap; }}
.detail {{ padding: 4px 20px 24px; }}
.field {{ margin-top: 24px; }}
.field h3 {{ margin: 0 0 10px; font-size: 16px; }}
.values {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
pre {{
  min-height: 72px;
  margin: 0;
  overflow: auto;
  background: var(--ink);
  color: #eaf8fb;
  padding: 16px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}}
.empty {{ display: none; padding: 60px 20px; text-align: center; }}
.empty.visible {{ display: block; }}
footer {{ margin-top: 32px; color: var(--muted); }}
@media (max-width: 760px) {{
  main {{ width: min(100% - 24px, 1180px); margin-top: 20px; }}
  header {{ box-shadow: 5px 5px 0 var(--ink); }}
  .stats {{ grid-template-columns: 1fr 1fr; }}
  .controls {{ grid-template-columns: 1fr; }}
  summary {{ grid-template-columns: 86px minmax(0, 1fr); }}
  .field-count {{ display: none; }}
  .values {{ grid-template-columns: 1fr; }}
}}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ scroll-behavior: auto !important; }}
}}
</style>
</head>
<body>
<main>
  <header>
    <h1>Knowledge changed.</h1>
    <div class="paths">
      <span>Before: {html.escape(diff.before_path)} ({diff.before_count} entries)</span>
      <span>After: {html.escape(diff.after_path)} ({diff.after_count} entries)</span>
    </div>
  </header>
  <section class="stats" aria-label="Change totals">{stat_blocks}</section>
  <section aria-label="Memory changes">
    <div class="controls">
      <input id="search" type="search" placeholder="Search title, type, identity, or field">
      <div class="filters" aria-label="Filter by status">
        <button type="button" data-filter="all" aria-pressed="true">All</button>
        <button type="button" data-filter="added" aria-pressed="false">Added</button>
        <button type="button" data-filter="removed" aria-pressed="false">Removed</button>
        <button type="button" data-filter="changed" aria-pressed="false">Changed</button>
        <button type="button" data-filter="unchanged" aria-pressed="false">Unchanged</button>
      </div>
    </div>
    <div class="ledger">{"".join(rows)}</div>
    <p class="empty">No entries match this view.</p>
  </section>
  <footer>Generated locally. No bundle content leaves this machine.</footer>
</main>
<script>
const search = document.querySelector('#search');
const entries = [...document.querySelectorAll('.entry')];
const buttons = [...document.querySelectorAll('[data-filter]')];
const empty = document.querySelector('.empty');
let filter = 'all';
function applyFilters() {{
  const query = search.value.trim().toLocaleLowerCase();
  let visible = 0;
  for (const entry of entries) {{
    const statusMatch = filter === 'all' || entry.dataset.status === filter;
    const searchMatch = !query || entry.dataset.search.includes(query);
    entry.hidden = !(statusMatch && searchMatch);
    if (!entry.hidden) visible += 1;
  }}
  empty.classList.toggle('visible', visible === 0);
}}
search.addEventListener('input', applyFilters);
for (const button of buttons) {{
  button.addEventListener('click', () => {{
    filter = button.dataset.filter;
    for (const peer of buttons) {{
      peer.setAttribute('aria-pressed', String(peer === button));
    }}
    applyFilters();
  }});
}}
</script>
</body>
</html>
"""


def _write(path: Path | None, content: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two OKF bundles by memory identity and content."
    )
    parser.add_argument("before", type=Path, help="Original OKF bundle or file")
    parser.add_argument("after", type=Path, help="Updated OKF bundle or file")
    parser.add_argument("--json", type=Path, dest="json_path", help="Write JSON report")
    parser.add_argument(
        "--markdown", type=Path, dest="markdown_path", help="Write Markdown report"
    )
    parser.add_argument("--html", type=Path, dest="html_path", help="Write HTML viewer")
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="Exit 1 when any semantic change is present",
    )
    parser.add_argument(
        "--fail-on-removal",
        action="store_true",
        help="Exit 1 when the updated bundle removes an entry",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        diff = compare_bundles(args.before, args.after)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _write(args.json_path, render_json(diff))
    _write(args.markdown_path, render_markdown(diff))
    _write(args.html_path, render_html(diff))

    counts = diff.counts
    print(
        f"{diff.before_count} -> {diff.after_count} entries | "
        f"{counts['added']} added | {counts['removed']} removed | "
        f"{counts['changed']} changed | {counts['unchanged']} unchanged"
    )
    if args.fail_on_removal and diff.has_removals:
        return 1
    if args.fail_on_change and diff.has_changes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
