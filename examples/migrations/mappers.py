"""
Mapper registry for the migrations example.

Core providers (mem0, letta, supermemory, okf) and their shared helpers are
imported directly from the installed memanto package. Custom providers added
in this example (chatgpt, claude, gemini, zep, hindsight, langgraph, notion,
obsidian, chroma) are implemented here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from memanto.app.constants import VALID_MEMORY_TYPES
from memanto.cli.migrate.mappers import (
    _attach_footer,
    _coerce_type,
    _format_supporting_data,
    _now_utc,
    _parse_dt,
    _title_from,
    map_letta,
    map_mem0,
    map_okf,
    map_supermemory,
    type_breakdown,
)

_DEFAULT_TITLE_CHARS = 80
_MAX_CONTENT_CHARS = 10000
_MAX_FOOTER_CHARS = 800


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

def map_claude(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for conv in export.get("memories", []) or []:
        if not isinstance(conv, dict):
            continue
        conv_title = (conv.get("name") or "").strip() or None

        for msg in conv.get("chat_messages", []) or []:
            try:
                if msg.get("sender") != "human":
                    continue
                text = msg.get("text")
                content = (text if isinstance(text, str) else "").strip()
                if not content:
                    parts = msg.get("content") or []
                    content = " ".join(
                        p["text"] for p in parts
                        if isinstance(p, dict) and p.get("type") == "text" and p.get("text", "").strip()
                    ).strip()
                if not content:
                    continue

                footer = _format_supporting_data([
                    ("Conversation", conv_title),
                    ("Conversation id", conv.get("uuid")),
                    ("Message id", msg.get("uuid")),
                ])
                rows.append({
                    "title": conv_title or _title_from(content),
                    "content": _attach_footer(content, footer),
                    "type": None,
                    "tags": [],
                    "confidence": 0.8,
                    "source": "claude",
                    "source_ref": str(msg.get("uuid")) if msg.get("uuid") else None,
                    "provenance": "imported",
                    "created_at": _parse_dt(msg.get("created_at")),
                    "updated_at": migrated_at,
                })
            except (AttributeError, TypeError):
                continue

    return rows


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def map_gemini(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for conv in export.get("memories", []) or []:
        try:
            messages = conv.get("messages") or []
            created_at = _parse_dt(conv.get("createdTime"))
        except (AttributeError, TypeError):
            continue

        for msg_idx, msg in enumerate(messages):
            try:
                if msg.get("role") != "user":
                    continue
                content = (msg.get("text") or "").strip()
                if not content:
                    continue
            except (AttributeError, TypeError):
                continue

            conv_id = conv.get("id")
            footer = _format_supporting_data([("Conversation id", conv_id)])
            rows.append({
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": None,
                "tags": [],
                "confidence": 0.8,
                "source": "gemini",
                "source_ref": f"{conv_id}:{msg_idx}" if conv_id else None,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            })

    return rows


# ---------------------------------------------------------------------------
# ChatGPT
# ---------------------------------------------------------------------------

def map_chatgpt(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for conv in export.get("memories", []) or []:
        if not isinstance(conv, dict):
            continue
        mapping = conv.get("mapping") or {}
        if not isinstance(mapping, dict):
            continue
        current_node = conv.get("current_node")
        if not mapping or not current_node:
            continue

        seen: set[str] = set()
        user_nodes: list[dict[str, Any]] = []
        node_id = current_node

        while node_id and node_id not in seen:
            seen.add(node_id)
            node = mapping.get(node_id)
            if not isinstance(node, dict):
                break
            msg = node.get("message")
            if isinstance(msg, dict):
                author = msg.get("author") or {}
                content_obj = msg.get("content") or {}
                if (
                    author.get("role") == "user"
                    and content_obj.get("content_type", "text") != "user_editable_context"
                ):
                    parts = content_obj.get("parts") or []
                    content = " ".join(p for p in parts if isinstance(p, str) and p.strip())
                    if content:
                        user_nodes.append(node)
            node_id = node.get("parent")

        user_nodes.reverse()
        conv_title = (conv.get("title") or "").strip() or None

        for node in user_nodes:
            msg = node["message"]
            parts = (msg.get("content") or {}).get("parts") or []
            content = " ".join(p for p in parts if isinstance(p, str) and p.strip())
            created_at = _parse_dt(msg.get("create_time")) or _parse_dt(conv.get("create_time"))
            footer = _format_supporting_data([
                ("Conversation", conv_title),
                ("Conversation id", conv.get("id")),
                ("Node id", node.get("id")),
            ])
            rows.append({
                "title": conv_title or _title_from(content),
                "content": _attach_footer(content, footer),
                "type": None,
                "tags": [],
                "confidence": 0.8,
                "source": "chatgpt",
                "source_ref": str(node.get("id")) if node.get("id") else None,
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            })

    return rows


# ---------------------------------------------------------------------------
# Zep
# ---------------------------------------------------------------------------

def map_zep(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for edge in export.get("memories", []) or []:
        try:
            content = (edge.get("fact") or "").strip()
            if not content:
                continue
            rating = edge.get("score") if "score" in edge else edge.get("relevance")
            try:
                confidence = min(1.0, max(0.0, float(rating))) if rating is not None else 0.8
            except (TypeError, ValueError):
                confidence = 0.8
            footer = _format_supporting_data([
                ("Edge name", edge.get("name")),
                ("Rating", str(rating) if rating is not None else None),
                ("UUID", edge.get("uuid")),
            ])
            rows.append({
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": "fact",
                "tags": [],
                "confidence": confidence,
                "source": "zep",
                "source_ref": edge.get("uuid"),
                "provenance": "imported",
                "created_at": _parse_dt(edge.get("valid_at") or edge.get("created_at")),
                "updated_at": migrated_at,
            })
        except (AttributeError, TypeError):
            continue

    return rows


# ---------------------------------------------------------------------------
# Hindsight
# ---------------------------------------------------------------------------

_HINDSIGHT_TYPE_MAP: dict[str, str] = {
    "world": "fact",
    "experience": "event",
}


def _hindsight_type(fact_type: str | None) -> str | None:
    if not fact_type:
        return None
    t = fact_type.strip().lower()
    return _HINDSIGHT_TYPE_MAP.get(t) or _coerce_type(t)


def map_hindsight(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for item in export.get("memories", []) or []:
        try:
            content = (item.get("text") or item.get("content") or "").strip()
            if not content:
                continue
            metadata = item.get("metadata") or {}
            footer = _format_supporting_data([
                ("Bank", item.get("bank_id")),
                ("Fact type", item.get("fact_type")),
                ("Context", item.get("context") or None),
                ("Entities", item.get("entities") or None),
                *((k, str(v)) for k, v in metadata.items() if v),
            ])
            rows.append({
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": _hindsight_type(item.get("fact_type")),
                "tags": list(item.get("tags") or []),
                "confidence": 0.8,
                "source": "hindsight",
                "source_ref": item.get("id"),
                "provenance": "imported",
                "created_at": _parse_dt(item.get("date") or item.get("mentioned_at")),
                "updated_at": migrated_at,
            })
        except (AttributeError, TypeError):
            continue

    return rows


# ---------------------------------------------------------------------------
# LangGraph
# ---------------------------------------------------------------------------

def map_langgraph(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for item in export.get("items", []) or []:
        try:
            value = item.get("value")
            if isinstance(value, dict):
                raw_content = value.get("content")
                if raw_content is not None:
                    content = str(raw_content).strip()
                else:
                    content = json.dumps(value, ensure_ascii=False).strip()
            elif isinstance(value, str):
                content = value.strip()
            else:
                content = str(value).strip() if value is not None else ""
            if not content:
                continue

            namespace = item.get("namespace") or []
            if isinstance(namespace, (list, tuple)):
                ns_tag = "/".join(str(p) for p in namespace) if namespace else None
            else:
                ns_tag = str(namespace) if namespace else None

            key = item.get("key")
            footer_pairs: list[tuple[str, Any]] = [("Namespace", ns_tag), ("Key", key)]
            if isinstance(value, dict):
                for k, v in value.items():
                    if k != "content" and v:
                        footer_pairs.append((k.capitalize(), str(v)))
            footer = _format_supporting_data(footer_pairs)

            rows.append({
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": None,
                "tags": [ns_tag] if ns_tag else [],
                "confidence": 0.8,
                "source": "langgraph",
                "source_ref": key,
                "provenance": "imported",
                "created_at": _parse_dt(item.get("created_at")),
                "updated_at": migrated_at,
            })
        except (AttributeError, TypeError):
            continue

    return rows


# ---------------------------------------------------------------------------
# Notion / Obsidian
# ---------------------------------------------------------------------------

def _map_markdown_entry(
    entry: dict[str, Any],
    *,
    source: str,
    memory_type: str,
    migrated_at: Any,
) -> dict[str, Any] | None:
    body = (entry.get("body") or "").strip()
    explicit_title = (entry.get("title") or "").strip()
    stem = (entry.get("filename_stem") or "").strip()

    if not explicit_title and not body:
        return None

    title = explicit_title or stem or _title_from(body)
    content = body if body else explicit_title
    if not content:
        return None

    tags = [str(t) for t in (entry.get("tags") or []) if t]
    footer = _format_supporting_data([("Filename", stem or None)])
    return {
        "title": title,
        "content": _attach_footer(content, footer),
        "type": memory_type,
        "tags": tags,
        "confidence": 0.8,
        "source": source,
        "source_ref": stem or None,
        "provenance": "imported",
        "created_at": _parse_dt(entry.get("created_at")),
        "updated_at": migrated_at,
    }


def map_notion(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()
    for entry in export.get("memories", []) or []:
        try:
            row = _map_markdown_entry(entry, source="notion", memory_type="artifact", migrated_at=migrated_at)
            if row:
                rows.append(row)
        except (AttributeError, TypeError):
            continue
    return rows


def map_obsidian(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()
    for entry in export.get("memories", []) or []:
        try:
            row = _map_markdown_entry(entry, source="obsidian", memory_type="artifact", migrated_at=migrated_at)
            if row:
                rows.append(row)
        except (AttributeError, TypeError):
            continue
    return rows


# ---------------------------------------------------------------------------
# Chroma
# ---------------------------------------------------------------------------

def map_chroma(export: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for item in export.get("memories", []) or []:
        try:
            content = (item.get("document") or "").strip()
            if not content:
                continue
            metadata = item.get("metadata") or {}
            meta_source = metadata.get("source")
            footer_pairs: list[tuple[str, Any]] = []
            if meta_source:
                footer_pairs.append(("source", meta_source))
            for k, v in metadata.items():
                if k != "source" and v is not None:
                    footer_pairs.append((k, str(v)))
            footer = _format_supporting_data(footer_pairs)
            rows.append({
                "title": _title_from(content),
                "content": _attach_footer(content, footer),
                "type": None,
                "tags": [],
                "confidence": 0.8,
                "source": "chroma",
                "source_ref": item.get("id"),
                "provenance": "imported",
                "created_at": None,
                "updated_at": migrated_at,
            })
        except (AttributeError, TypeError):
            continue

    return rows


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MAPPERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "mem0": map_mem0,
    "letta": map_letta,
    "supermemory": map_supermemory,
    "okf": map_okf,
    "chatgpt": map_chatgpt,
    "claude": map_claude,
    "gemini": map_gemini,
    "zep": map_zep,
    "hindsight": map_hindsight,
    "langgraph": map_langgraph,
    "notion": map_notion,
    "obsidian": map_obsidian,
    "chroma": map_chroma,
}
