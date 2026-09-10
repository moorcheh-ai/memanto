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


def default_qa(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Build golden questions from known edges."""
    entities = {e['uuid']: e['name'] for e in export.get('entities', [])}
    qa = [
        {
            'id': 'q1',
            'question': 'Where does Alex Rivera live?',
            'expect_any': ['seattle'],
        },
        {
            'id': 'q2',
            'question': 'What seat does Alex prefer?',
            'expect_any': ['aisle'],
        },
        {
            'id': 'q3',
            'question': 'What meal preference was superseded?',
            'expect_any': ['vegetarian'],
        },
        {
            'id': 'q4',
            'question': 'What is the current diet after the flip?',
            'expect_any': ['fish', 'poultry'],
        },
        {
            'id': 'q5',
            'question': 'Work-trip fare policy?',
            'expect_any': ['refundable'],
        },
        {
            'id': 'q6',
            'question': 'Who is Alex\'s partner?',
            'expect_any': ['jordan'],
        },
        {
            'id': 'q7',
            'question': 'October travel goal destination?',
            'expect_any': ['tokyo'],
        },
        {
            'id': 'q8',
            'question': 'Backup hotel payment card?',
            'expect_any': ['9001', 'amex'],
        },
    ]
    # Ensure expected strings exist in export too
    corpus = json.dumps(export).lower()
    for item in qa:
        item['export_hit'] = any(x in corpus for x in item['expect_any'])
    return qa


def run_offline(export: dict[str, Any], okf_root: Path, qa: list[dict[str, Any]]) -> dict[str, Any]:
    corpus = load_okf_corpus(okf_root)
    results = []
    passed = 0
    for item in qa:
        ok = any(x.lower() in corpus for x in item['expect_any'])
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
    return {
        'mode': 'offline',
        'total': len(qa),
        'passed': passed,
        'failed': len(qa) - passed,
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
