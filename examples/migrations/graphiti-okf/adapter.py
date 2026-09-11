#!/usr/bin/env python3
"""Graphiti export JSON → OKF v0.2 bundle (examples-only adapter)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_EXPORT = ROOT / 'out' / 'graphiti_export.json'
DEFAULT_OKF = ROOT / 'out' / 'okf-bundle'
DEFAULT_SUMMARY = ROOT / 'out' / 'migration_summary.json'

MEMANTO_TYPES = {
    'fact', 'preference', 'goal', 'decision', 'artifact', 'learning', 'event',
    'instruction', 'relationship', 'context', 'observation', 'commitment', 'error',
}

RELATION_TYPE_MAP: dict[str, str] = {
    'PREFERS': 'preference',
    'PREFERS_CARRIER': 'preference',
    'DECIDED': 'decision',
    'COMMITTED_TO': 'commitment',
    'HAS_GOAL': 'goal',
    'INSTRUCTS': 'instruction',
    'PARTNER_OF': 'relationship',
    'REPORTS_TO': 'relationship',
    'WORKS_AT': 'relationship',
    'LIVES_IN': 'fact',
    'TRAVELED_TO': 'event',
    'EXPERIENCED': 'event',
    'USES': 'artifact',
}


def _slug(text: str, limit: int = 60) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    s = s or 'memory'
    if len(s) <= limit:
        return s
    suffix = hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]
    return f"{s[:limit - len(suffix) - 1].rstrip('-')}-{suffix}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def classify_edge(edge: dict[str, Any]) -> str:
    name = (edge.get('name') or edge.get('relation_type') or '').upper()
    if name in RELATION_TYPE_MAP:
        return RELATION_TYPE_MAP[name]
    fact = (edge.get('fact') or '').lower()
    if 'prefer' in fact:
        return 'preference'
    if 'decid' in fact or 'only refundable' in fact:
        return 'decision'
    if 'commit' in fact:
        return 'commitment'
    if 'goal' in fact or 'aim' in fact:
        return 'goal'
    if 'instruct' in fact or 'always' in fact:
        return 'instruction'
    return 'fact'


def classify_entity(entity: dict[str, Any]) -> str:
    labels = {str(x).lower() for x in entity.get('labels') or []}
    if 'person' in labels or 'organization' in labels:
        return 'context'
    if 'artifact' in labels:
        return 'artifact'
    return 'context'


def classify_episode(ep: dict[str, Any]) -> str:
    desc = (ep.get('source_description') or '').lower()
    content = (ep.get('content') or '').lower()
    if 'policy' in desc or 'decision' in desc:
        return 'decision'
    if 'instruction' in desc or 'standing' in desc:
        return 'instruction'
    if 'hiccup' in desc or 'declined' in content:
        return 'error'
    if 'goal' in desc or 'goal:' in content:
        return 'goal'
    if 'commit' in desc or 'commit' in content:
        return 'commitment'
    if 'ops note' in desc:
        return 'observation'
    # Unmatched text episodes fall through to observation (generic fallback last).
    return 'observation'


def _frontmatter(meta: dict[str, Any]) -> str:
    # Minimal YAML emitter (avoid requiring PyYAML for dry-run)
    lines = ['---']
    for key, value in meta.items():
        if key == 'x_memanto' and isinstance(value, dict):
            lines.append('x_memanto:')
            for k, v in value.items():
                lines.append(f'  {k}: {_yaml_scalar(v)}')
        elif key == 'generated' and isinstance(value, dict):
            lines.append('generated:')
            for k, v in value.items():
                lines.append(f'  {k}: {_yaml_scalar(v)}')
        elif key == 'tags' and isinstance(value, list):
            inner = ', '.join(json.dumps(str(t)) for t in value)
            lines.append(f'tags: [{inner}]')
        else:
            lines.append(f'{key}: {_yaml_scalar(value)}')
    lines.append('---')
    return '\n'.join(lines)


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    # Always quote strings so OKF frontmatter stays unambiguous (e.g. okf_version: "0.2").
    return json.dumps(str(value))


def _write_memory(
    okf_root: Path,
    mem_type: str,
    filename: str,
    meta: dict[str, Any],
    body: str,
) -> Path:
    type_dir = okf_root / 'memories' / mem_type
    type_dir.mkdir(parents=True, exist_ok=True)
    path = type_dir / filename
    path.write_text(_frontmatter(meta) + '\n\n' + body.strip() + '\n', encoding='utf-8')
    return path


def adapt(export: dict[str, Any], okf_root: Path) -> dict[str, Any]:
    if okf_root.exists():
        # Clean previous memories only
        mem = okf_root / 'memories'
        if mem.exists():
            for p in mem.rglob('*'):
                if p.is_file():
                    p.unlink()
    okf_root.mkdir(parents=True, exist_ok=True)
    (okf_root / 'memories').mkdir(exist_ok=True)

    group_id = export.get('group_id') or 'graphiti'
    entities = {e['uuid']: e for e in export.get('entities', [])}
    invalidated = {i['edge_uuid']: i for i in export.get('invalidated', [])}
    counts: Counter[str] = Counter()
    written: list[str] = []
    skipped = 0

    # Edges → primary durable memories
    for edge in export.get('edges', []):
        mem_type = classify_edge(edge)
        inv = invalidated.get(edge.get('uuid', ''))
        superseded = bool(edge.get('invalid_at')) or inv is not None
        src = entities.get(edge.get('source') or edge.get('source_node_uuid', ''), {})
        tgt = entities.get(edge.get('target') or edge.get('target_node_uuid', ''), {})
        src_name = src.get('name') or edge.get('source_entity_name') or edge.get('source')
        tgt_name = tgt.get('name') or edge.get('target_entity_name') or edge.get('target')
        rel = edge.get('name') or edge.get('relation_type') or 'RELATED_TO'
        fact = edge.get('fact') or f'{src_name} -[{rel}]-> {tgt_name}'
        title = fact if len(fact) <= 80 else fact[:77] + '...'
        tags = [f'group:{group_id}', f'relation:{rel}', 'source:graphiti']
        provenance = 'corrected' if (superseded is False and any(
            i.get('superseded_by') == edge.get('uuid') for i in export.get('invalidated', [])
        )) else ('imported' if not superseded else 'imported')
        if any(i.get('superseded_by') == edge.get('uuid') for i in export.get('invalidated', [])):
            provenance = 'corrected'
            tags.append('current')
        if superseded:
            tags.append('superseded')
            mem_type = 'observation' if mem_type == 'preference' else mem_type
            tags.append('preference-history' if 'PREFERS' in rel else 'history')

        confidence = 0.5 if superseded else 0.9
        generated_at = edge.get('valid_at') or export.get('exported_at') or _now()
        meta = {
            'type': mem_type,
            'title': title,
            'description': fact.split('.')[0][:120],
            'tags': tags,
            'generated': {'by': 'process:graphiti', 'at': generated_at},
            'resource': f"graphiti:edge:{edge.get('uuid')}",
            'x_memanto': {
                'confidence': confidence,
                'provenance': provenance,
                'source': 'graphiti',
                'id': edge.get('uuid'),
                'type': mem_type,
            },
        }
        body_lines = [
            fact,
            '',
            f'Graph relation: {src_name} -[{rel}]-> {tgt_name}',
        ]
        if edge.get('valid_at'):
            body_lines.append(f"Valid from: {edge['valid_at']}")
        if edge.get('invalid_at'):
            body_lines.append(f"Invalidated at: {edge['invalid_at']}")
        if inv:
            body_lines.append(
                f"Superseded by `{inv.get('superseded_by')}` — {inv.get('reason', '')}".strip()
            )
        body_lines += [
            '',
            '[Supporting data]',
            f"- group_id: {group_id}",
            f"- episodes: {', '.join(edge.get('episodes') or [])}",
            f"- valid_at: {edge.get('valid_at')}",
            f"- invalid_at: {edge.get('invalid_at')}",
        ]
        fname = _slug(f"{rel}-{src_name}-{tgt_name}-{edge.get('uuid', '')}") + '.md'
        rel_path = _write_memory(okf_root, mem_type, fname, meta, '\n'.join(body_lines))
        written.append(str(rel_path.relative_to(okf_root)))
        counts[mem_type] += 1

    # Entities → context
    for ent in export.get('entities', []):
        mem_type = classify_entity(ent)
        summary = ent.get('summary') or ent.get('name')
        title = ent.get('name') or ent.get('uuid')
        meta = {
            'type': mem_type,
            'title': title,
            'description': (summary or '')[:120],
            'tags': [f'group:{group_id}', 'entity', 'source:graphiti']
            + [f"label:{l}" for l in (ent.get('labels') or []) if l != 'Entity'],
            'generated': {
                'by': 'process:graphiti',
                'at': export.get('exported_at') or _now(),
            },
            'resource': f"graphiti:entity:{ent.get('uuid')}",
            'x_memanto': {
                'confidence': 0.8,
                'provenance': 'imported',
                'source': 'graphiti',
                'id': ent.get('uuid'),
                'type': mem_type,
            },
        }
        body = f"{summary}\n\n[Supporting data]\n- labels: {', '.join(ent.get('labels') or [])}\n"
        fname = _slug(f"entity-{title}-{ent.get('uuid')}") + '.md'
        rel_path = _write_memory(okf_root, mem_type, fname, meta, body)
        written.append(str(rel_path.relative_to(okf_root)))
        counts[mem_type] += 1

    # Selected episodes → observation / instruction / etc. (skip fluff duplicates of edges)
    for ep in export.get('episodes', []):
        # Keep policy / instruction / error / ops episodes as first-class memories
        mem_type = classify_episode(ep)
        if mem_type == 'observation' and ep.get('source') == 'message':
            # Avoid duplicating every chat line; keep structured ops notes only
            if ep.get('id') not in {'ep-13'}:
                skipped += 1
                continue
        content = ep.get('content') or ''
        title = (ep.get('name') or content[:60]).replace('-', ' ')
        meta = {
            'type': mem_type,
            'title': title,
            'description': content[:120],
            'tags': [f'group:{group_id}', 'episode', 'source:graphiti'],
            'generated': {
                'by': 'process:graphiti',
                'at': ep.get('reference_time') or _now(),
            },
            'resource': f"graphiti:episode:{ep.get('uuid') or ep.get('id')}",
            'x_memanto': {
                'confidence': 0.7,
                'provenance': 'imported',
                'source': 'graphiti',
                'id': ep.get('uuid') or ep.get('id'),
                'type': mem_type,
            },
        }
        body = (
            f"{content}\n\n[Supporting data]\n"
            f"- episode_id: {ep.get('id')}\n"
            f"- source: {ep.get('source')}\n"
            f"- source_description: {ep.get('source_description')}\n"
        )
        fname = _slug(f"episode-{ep.get('id')}-{title}") + '.md'
        rel_path = _write_memory(okf_root, mem_type, fname, meta, body)
        written.append(str(rel_path.relative_to(okf_root)))
        counts[mem_type] += 1

    # indexes
    (okf_root / 'index.md').write_text(
        _frontmatter(
            {
                'type': 'index',
                'title': f'Graphiti → OKF ({group_id})',
                'okf_version': '0.2',
                'description': 'Portable knowledge liberated from a Graphiti temporal graph.',
                'generated': {'by': 'process:graphiti-okf-adapter', 'at': _now()},
            }
        )
        + '\n\n# Graphiti → OKF bundle\n\n'
        + f'Group: `{group_id}`\n\n'
        + 'See [memories/](memories/).\n',
        encoding='utf-8',
    )
    mem_index = okf_root / 'memories' / 'index.md'
    type_links = '\n'.join(f'- [{t}/]({t}/) — {counts[t]}' for t in sorted(counts))
    mem_index.write_text(
        _frontmatter({'type': 'index', 'title': 'Memories', 'okf_version': '0.2'})
        + '\n\n# Memories\n\n'
        + type_links
        + '\n',
        encoding='utf-8',
    )
    for t in counts:
        (okf_root / 'memories' / t / 'index.md').write_text(
            _frontmatter({'type': 'index', 'title': t, 'okf_version': '0.2'})
            + f'\n\n# {t}\n\nMapped from Graphiti export.\n',
            encoding='utf-8',
        )

    summary = {
        'source': 'graphiti',
        'group_id': group_id,
        'source_count': {
            'episodes': len(export.get('episodes', [])),
            'entities': len(export.get('entities', [])),
            'edges': len(export.get('edges', [])),
            'invalidated': len(export.get('invalidated', [])),
        },
        'mapped_count': sum(counts.values()),
        'skipped_episodes': skipped,
        'per_type': dict(sorted(counts.items())),
        'okf_root': (
            str(okf_root.resolve().relative_to(ROOT))
            if okf_root.resolve().is_relative_to(ROOT)
            else str(okf_root)
        ),
        'files': written,
        'generated_at': _now(),
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description='Adapt Graphiti export → OKF v0.2')
    parser.add_argument('--export', type=Path, default=DEFAULT_EXPORT)
    parser.add_argument('--okf', type=Path, default=DEFAULT_OKF)
    parser.add_argument('--summary', type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    export = json.loads(args.export.read_text(encoding='utf-8'))
    summary = adapt(export, args.okf)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(f"OKF bundle → {args.okf}")
    print(f"mapped={summary['mapped_count']} types={summary['per_type']}")
    print(f"summary → {args.summary}")


if __name__ == '__main__':
    main()
