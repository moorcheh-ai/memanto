"""Export a real public GitHub issue discussion as an OKF memory bundle."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

API_ROOT = "https://api.github.com"


def _fetch_json(url: str) -> Any:
    """Fetch one GitHub API JSON document with a bounded request timeout."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "memanto-okf-portability-showcase",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API returned HTTP {exc.code} for {url}") from exc


def fetch_issue_archive(
    repository: str, issue_number: int, max_comments: int | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch an issue and all public comments, following GitHub pagination."""
    issue_url = f"{API_ROOT}/repos/{repository}/issues/{issue_number}"
    issue = _fetch_json(issue_url)

    comments: list[dict[str, Any]] = []
    page = 1
    while max_comments is None or len(comments) < max_comments:
        remaining = 100 if max_comments is None else max_comments - len(comments)
        per_page = min(100, remaining)
        url = f"{issue_url}/comments?per_page={per_page}&page={page}"
        batch = _fetch_json(url)
        if not batch:
            break
        comments.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return issue, comments


def _slug(text: str) -> str:
    """Create a filesystem-safe deterministic slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return slug[:60].rstrip("-") or "memory"


def _chunks(text: str, limit: int = 7000) -> list[str]:
    """Split Markdown losslessly near paragraph boundaries under ``limit``."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while len(text) - start > limit:
        boundary = text.rfind("\n\n", start, start + limit + 1)
        end = boundary + 2 if boundary > start else start + limit
        chunks.append(text[start:end])
        start = end
    chunks.append(text[start:])
    return chunks


def _frontmatter(record: dict[str, Any]) -> str:
    """Render one record's portable OKF frontmatter."""
    data = {
        "type": record["type"],
        "title": record["title"],
        "description": record["description"],
        "resource": record["resource"],
        "tags": record["tags"],
        "timestamp": record["timestamp"],
        "x_memanto": {
            "id": record["id"],
            "source": "github",
            "provenance": "imported",
            "confidence": 1.0,
            "type": record["type"],
        },
    }
    return str(yaml.safe_dump(data, sort_keys=False, allow_unicode=True)).strip()


def records_from_archive(
    issue: dict[str, Any], comments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Turn a genuine GitHub archive into deterministic OKF records."""
    labels = [label["name"] for label in issue.get("labels", [])]
    issue_parts = _chunks(issue.get("body") or "(No issue body)")
    records: list[dict[str, Any]] = []
    for index, body in enumerate(issue_parts, start=1):
        suffix = f" (part {index}/{len(issue_parts)})" if len(issue_parts) > 1 else ""
        resource = issue["html_url"]
        if len(issue_parts) > 1:
            resource += f"#okf-part-{index}"
        records.append(
            {
                "id": f"github-issue-{issue['id']}-part-{index}",
                "type": "artifact",
                "title": issue["title"] + suffix,
                "description": (
                    f"GitHub issue #{issue['number']} in "
                    f"{issue['repository_url'].split('/repos/')[-1]}{suffix}."
                ),
                "resource": resource,
                "tags": ["github", "issue", issue["state"], f"part:{index}", *labels],
                "timestamp": issue["created_at"],
                "body": body,
            }
        )
    for comment in comments:
        author = comment["user"]["login"]
        comment_parts = _chunks(comment.get("body") or "(Empty comment)")
        for index, body in enumerate(comment_parts, start=1):
            suffix = (
                f" (part {index}/{len(comment_parts)})"
                if len(comment_parts) > 1
                else ""
            )
            records.append(
                {
                    "id": f"github-comment-{comment['id']}-part-{index}",
                    "type": "observation",
                    "title": (
                        f"Comment by {author} on issue #{issue['number']}{suffix}"
                    ),
                    "description": f"Public GitHub comment by {author}{suffix}.",
                    "resource": comment["html_url"],
                    "tags": [
                        "github",
                        "issue-comment",
                        f"author:{author}",
                        f"part:{index}",
                    ],
                    "timestamp": comment["created_at"],
                    "body": body,
                }
            )
    return records


def _markdown_label(text: str) -> str:
    """Escape characters that can terminate a Markdown link label."""
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def write_bundle(records: list[dict[str, Any]], output: Path) -> None:
    """Write records as a loader-compatible OKF bundle without overwriting."""
    if output.exists() and any(output.rglob("*.md")):
        raise FileExistsError(f"Refusing to overwrite an existing bundle: {output}")

    links_by_type: dict[str, list[tuple[str, str]]] = {}
    for record in records:
        memory_type = record["type"]
        type_dir = output / "memories" / memory_type
        type_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{_slug(record['title'])}-{_slug(record['id'])}.md"
        body = record["body"]
        document = f"---\n{_frontmatter(record)}\n---\n\n{body}"
        if not document.endswith("\n"):
            document += "\n"
        (type_dir / filename).write_text(document, encoding="utf-8")
        links_by_type.setdefault(memory_type, []).append((record["title"], filename))

    memory_links: list[tuple[str, str]] = []
    for memory_type, links in sorted(links_by_type.items()):
        type_dir = output / "memories" / memory_type
        lines = ["---", "type: index", f"title: {memory_type}", "---", ""]
        lines.extend(
            f"- [{_markdown_label(title)}]({filename})" for title, filename in links
        )
        (type_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        memory_links.append((memory_type, f"{memory_type}/index.md"))

    memories_dir = output / "memories"
    lines = ["---", "type: index", "title: memories", "---", ""]
    lines.extend(f"- [{title}]({target})" for title, target in memory_links)
    (memories_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    root = ["---", "type: index", "title: GitHub issue memory", "---", ""]
    root.append("- [memories](memories/index.md)")
    (output / "index.md").write_text("\n".join(root) + "\n", encoding="utf-8")


def main() -> int:
    """Run the public GitHub archive exporter."""
    parser = argparse.ArgumentParser(
        description="Export a real public GitHub issue discussion to OKF."
    )
    parser.add_argument("repository", help="GitHub repository as owner/name")
    parser.add_argument("issue", type=int, help="Issue number")
    parser.add_argument("output", type=Path, help="New OKF bundle directory")
    parser.add_argument("--max-comments", type=int, default=None)
    args = parser.parse_args()

    issue, comments = fetch_issue_archive(
        args.repository, args.issue, args.max_comments
    )
    records = records_from_archive(issue, comments)
    write_bundle(records, args.output)
    print(
        f"Exported 1 issue and {len(comments)} comments "
        f"({len(records)} OKF memories) to {args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
