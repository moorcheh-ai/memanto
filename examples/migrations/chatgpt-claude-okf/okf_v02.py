"""
Upgrade a Memanto-written OKF bundle from spec v0.1 to v0.2.

Memanto's ``OkfExportService`` targets OKF v0.1: it emits ``timestamp`` and puts
YAML frontmatter into every ``index.md``. The spec moved to v0.2 on 19 Aug 2026
(https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md),
which supersedes ``timestamp`` with a ``generated`` block, adds a ``sources``
provenance family, and permits frontmatter in an index file only at the bundle
root and only to declare ``okf_version`` (section 8).

This module layers those changes on top of a bundle the shipped service already
wrote, rather than forking or reimplementing the serializer. The structure,
slugs, stacking and index bodies all remain Memanto's; only frontmatter changes.

Round-trip safety: ``generated`` and ``sources`` are unknown keys to Memanto's
loader, which preserves unknown frontmatter as ``extra`` and surfaces it in the
``[Supporting data]`` footer. Index files are skipped by filename, so rewriting
them cannot affect import.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

OKF_VERSION = "0.2"
RESERVED = {"index.md", "log.md"}

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def _split(text: str) -> tuple[dict[str, Any], str]:
    """Split a document into (frontmatter, body). Missing frontmatter is empty."""
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        # Spec section 11 forbids a consumer from rejecting a bundle over a
        # malformed document, and memanto's own loader degrades the same way.
        return {}, match.group(2)
    return (loaded if isinstance(loaded, dict) else {}), match.group(2)


def _join(frontmatter: dict[str, Any], body: str) -> str:
    front = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    return f"---\n{front}\n---\n\n{body.lstrip()}"


def _source_entry(record: dict[str, Any]) -> dict[str, Any] | None:
    """Build one ``sources`` entry pointing back at where the memory came from."""
    ref = record.get("source_ref")
    if not ref:
        return None
    source = record.get("source") or "unknown"
    entry: dict[str, Any] = {
        "id": ref if ":" in str(ref) else f"{source}:{ref}",
        "author": f"{source}",
    }
    if record.get("source_title"):
        entry["title"] = record["source_title"]
    return entry


def upgrade_documents(
    bundle: Path, records: list[dict[str, Any]], producer: str
) -> int:
    """Add the v0.2 trust and provenance families to every concept document.

    ``generated.at`` deliberately reuses the memory's own ``created_at`` rather
    than the moment this ran. It is the value ``timestamp`` already carries, so a
    v0.1 and a v0.2 consumer agree on the date, and re-running the pipeline does
    not churn committed artifacts. When the source carries no date the key is
    omitted entirely: only ``generated.by`` is required by the spec, and an
    invented date would be worse than an absent one.
    """
    by_id = {r["id"]: r for r in records if r.get("id")}
    upgraded = 0

    for doc in sorted(bundle.rglob("*.md")):
        if doc.name in RESERVED:
            continue
        frontmatter, body = _split(doc.read_text(encoding="utf-8"))
        if not frontmatter:
            # Conformance rule 1: every non-reserved .md needs parseable
            # frontmatter with a non-empty `type`. Memanto writes
            # `metrics/overview.md` as a bare document, which fails that rule.
            frontmatter = {"type": "Metrics", "title": doc.stem.replace("-", " ")}

        record = by_id.get((frontmatter.get("x_memanto") or {}).get("id"))

        generated: dict[str, Any] = {"by": producer}
        if frontmatter.get("timestamp"):
            generated["at"] = frontmatter["timestamp"]
        frontmatter["generated"] = generated

        if record and (entry := _source_entry(record)):
            frontmatter["sources"] = [entry]

        doc.write_text(_join(frontmatter, body), encoding="utf-8")
        upgraded += 1

    return upgraded


def rewrite_indexes(bundle: Path) -> int:
    """Bring index files in line with spec section 8.

    Index files carry no frontmatter, with a single exception: the bundle-root
    ``index.md`` may declare ``okf_version``. Memanto writes ``type``, ``title``
    and a run timestamp into every one of them, which is both non-conformant and
    a source of needless churn in committed bundles.
    """
    rewritten = 0
    for index in sorted(bundle.rglob("index.md")):
        _, body = _split(index.read_text(encoding="utf-8"))
        body = body.lstrip()
        if index.parent == bundle:
            index.write_text(
                _join({"okf_version": OKF_VERSION}, body), encoding="utf-8"
            )
        else:
            index.write_text(body, encoding="utf-8")
        rewritten += 1
    return rewritten


def upgrade(
    bundle: Path, records: list[dict[str, Any]], producer: str
) -> dict[str, int]:
    """Upgrade a bundle in place. Returns counts for reporting."""
    return {
        "documents": upgrade_documents(bundle, records, producer),
        "indexes": rewrite_indexes(bundle),
    }
