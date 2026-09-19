#!/usr/bin/env python3
"""Offline golden Q&A: export JSON facts vs OKF markdown bodies."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EXPORT = ROOT / 'out' / 'graphiti_export.json'
OKF = ROOT / 'out' / 'okf-bundle'
QA = ROOT / 'out' / 'golden_qa.json'
REPORT = ROOT / 'out' / 'validation_report.md'


def load_okf_corpus(okf_root: Path) -> str:
    parts: list[str] = []
    mem = okf_root / 'memories'
    if not mem.exists():
        return ''
    for path in sorted(mem.rglob('*.md')):
        if path.name == 'index.md':
            continue
        parts.append(path.read_text(encoding='utf-8'))
    return '\n'.join(parts).lower()


def index_okf_memories(okf_root: Path) -> dict[str, str]:
    """Map Graphiti edge/entity/episode ids → memory markdown body."""
    by_id: dict[str, str] = {}
    mem = okf_root / 'memories'
    if not mem.exists():
        return by_id
    id_line = re.compile(
        r'(?m)^(?:resource:\s*"(?:graphiti:(?:edge|entity|episode):)?([^"]+)"'
        r'|  id:\s*"([^"]+)")\s*$'
    )
    for path in mem.rglob('*.md'):
        if path.name == 'index.md':
            continue
        body = path.read_text(encoding='utf-8')
        for m in id_line.finditer(body):
            key = m.group(1) or m.group(2)
            if key:
                by_id[key] = body
    return by_id


def default_qa(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Build golden questions from known edges."""
    qa = [
        {
            'id': 'q1',
            'question': 'Where does Alex Rivera live?',
            'expect_any': ['seattle'],
            'edge_uuid': 'e-lives',
        },
        {
            'id': 'q2',
            'question': 'What seat does Alex prefer?',
            'expect_any': ['aisle'],
            'edge_uuid': 'e-aisle',
        },
        {
            'id': 'q3',
            'question': 'What meal preference was superseded?',
            'expect_any': ['vegetarian'],
            'edge_uuid': 'e-veg',
        },
        {
            'id': 'q4',
            'question': 'What is the current diet after the flip?',
            'expect_any': ['fish', 'poultry'],
            'edge_uuid': 'e-diet-new',
        },
        {
            'id': 'q5',
            'question': 'Work-trip fare policy?',
            'expect_any': ['refundable'],
            'edge_uuid': 'e-refundable',
        },
        {
            'id': 'q6',
            'question': "Who is Alex's partner?",
            'expect_any': ['jordan'],
            'edge_uuid': 'e-partner',
        },
        {
            'id': 'q7',
            'question': 'October travel goal destination?',
            'expect_any': ['tokyo'],
            'edge_uuid': 'e-tokyo',
        },
        {
            'id': 'q8',
            'question': 'Backup hotel payment card?',
            'expect_any': ['9001', 'amex'],
            'edge_uuid': 'e-card',
        },
    ]
    # Ensure expected strings exist in export too
    corpus = json.dumps(export).lower()
    for item in qa:
        item['export_hit'] = any(x in corpus for x in item['expect_any'])
    return qa


def validate_facts_against_memories(
    export: dict[str, Any], memories: dict[str, str]
) -> list[dict[str, Any]]:
    """Each exported edge fact must appear in its corresponding OKF memory."""
    results: list[dict[str, Any]] = []
    for edge in export.get('edges', []):
        uuid = edge.get('uuid') or ''
        fact = (edge.get('fact') or '').strip()
        body = memories.get(uuid, '')
        ok = bool(body) and (not fact or fact.lower() in body.lower())
        results.append(
            {
                'id': f'fact:{uuid}',
                'question': f'Edge {uuid} fact present in mapped memory',
                'passed': ok,
                'expect_any': [fact[:80]] if fact else [],
            }
        )
    return results


def validate_superseded_preference(
    export: dict[str, Any], memories: dict[str, str]
) -> dict[str, Any]:
    """Assert e-veg carries invalidation / superseded state in its OKF memory."""
    veg = next((e for e in export.get('edges', []) if e.get('uuid') == 'e-veg'), None)
    body = memories.get('e-veg', '')
    body_l = body.lower()
    ok = bool(veg and veg.get('invalid_at') and body)
    if ok:
        ok = (
            'invalidated' in body_l
            or 'superseded' in body_l
            or str(veg.get('invalid_at')).lower() in body_l
        )
        inv = export.get('invalidated') or []
        if inv:
            ok = ok and any(i.get('edge_uuid') == 'e-veg' for i in inv)
    return {
        'id': 'superseded-e-veg',
        'question': 'Superseded vegetarian preference retains invalidation state',
        'passed': bool(ok),
        'expect_any': ['invalidated', 'superseded'],
    }


def run_offline(export: dict[str, Any], okf_root: Path, qa: list[dict[str, Any]]) -> dict[str, Any]:
    corpus = load_okf_corpus(okf_root)
    memories = index_okf_memories(okf_root)
    results = []
    passed = 0
    for item in qa:
        edge_uuid = item.get('edge_uuid')
        if edge_uuid and edge_uuid in memories:
            haystack = memories[edge_uuid].lower()
        else:
            # Preserve expectation checks when no edge mapping is available.
            haystack = corpus
        ok = any(x.lower() in haystack for x in item['expect_any'])
        results.append(
            {
                'id': item['id'],
                'question': item['question'],
                'passed': ok,
                'expect_any': item['expect_any'],
            }
        )
        if ok:
            passed += 1

    fact_results = validate_facts_against_memories(export, memories)
    for r in fact_results:
        results.append(r)
        if r['passed']:
            passed += 1

    superseded = validate_superseded_preference(export, memories)
    results.append(superseded)
    if superseded['passed']:
        passed += 1

    total = len(results)
    return {
        'mode': 'offline',
        'total': total,
        'passed': passed,
        'failed': total - passed,
        'results': results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('offline', 'live'), default='offline')
    parser.add_argument('--export', type=Path, default=EXPORT)
    parser.add_argument('--okf', type=Path, default=OKF)
    parser.add_argument('--qa', type=Path, default=QA)
    parser.add_argument('--report', type=Path, default=REPORT)
    args = parser.parse_args()

    if args.mode == 'live':
        raise SystemExit(
            'live validation needs MOORCHEH_API_KEY + memanto CLI; '
            'use --mode offline for $0 dry-run'
        )

    export = json.loads(args.export.read_text(encoding='utf-8'))
    if args.qa.exists():
        qa = json.loads(args.qa.read_text(encoding='utf-8'))
        if isinstance(qa, dict):
            qa = qa.get('questions', [])
    else:
        qa = default_qa(export)
        args.qa.parent.mkdir(parents=True, exist_ok=True)
        args.qa.write_text(
            json.dumps({'questions': qa}, indent=2) + '\n', encoding='utf-8'
        )

    # Merge edge_uuid hints from defaults when committed QA lacks them.
    defaults = {q['id']: q for q in default_qa(export)}
    for item in qa:
        hint = defaults.get(item.get('id'), {})
        if 'edge_uuid' not in item and 'edge_uuid' in hint:
            item['edge_uuid'] = hint['edge_uuid']

    report = run_offline(export, args.okf, qa)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Validation report (offline)',
        '',
        f"- passed: **{report['passed']}/{report['total']}**",
        f"- failed: {report['failed']}",
        '',
        '| id | question | pass |',
        '| --- | --- | --- |',
    ]
    for r in report['results']:
        lines.append(
            f"| {r['id']} | {r['question']} | {'✅' if r['passed'] else '❌'} |"
        )
    args.report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('mode', 'passed', 'failed', 'total')}, indent=2))
    print(f'report → {args.report}')
    if report['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
