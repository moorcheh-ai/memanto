"""Fixture-driven Graphiti LLMClient mock — structured extract, $0.

Matches response_model schema fields / class name and episode text from the
lived-in fixture so ``add_episode`` can run without OpenAI spend.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'lived_in_script.json'


def _load_fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding='utf-8'))


def _episode_blob(messages: list[Any]) -> str:
    parts = []
    for m in messages:
        content = getattr(m, 'content', None)
        if content is None and isinstance(m, dict):
            content = m.get('content', '')
        parts.append(str(content or ''))
    return '\n'.join(parts)


def _find_episode(fixture: dict[str, Any], blob: str) -> dict[str, Any] | None:
    # Prefer longest content match so short substrings don't collide.
    best = None
    best_len = -1
    for ep in fixture.get('episodes', []):
        c = ep.get('content', '')
        if c and c in blob and len(c) > best_len:
            best = ep
            best_len = len(c)
    return best


def _entities_for_episode(fixture: dict[str, Any], ep: dict[str, Any] | None) -> list[dict[str, Any]]:
    if ep is None:
        return []
    eg = fixture['expected_graph']
    ent_by_id = {e['uuid']: e for e in eg['entities']}
    names: list[str] = []
    for edge in eg['edges']:
        if ep['id'] in edge.get('episodes', []):
            for key in ('source', 'target'):
                name = ent_by_id[edge[key]]['name']
                if name not in names:
                    names.append(name)
    # Always include speaker-ish Alex when present in content
    if ep.get('content', '').startswith('Alex') and 'Alex Rivera' not in names:
        names.insert(0, 'Alex Rivera')
    out = []
    for i, name in enumerate(names):
        out.append({'name': name, 'entity_type_id': 0, 'episode_indices': [0]})
    return out


def _edges_for_episode(fixture: dict[str, Any], ep: dict[str, Any] | None) -> list[dict[str, Any]]:
    if ep is None:
        return []
    eg = fixture['expected_graph']
    ent_by_id = {e['uuid']: e for e in eg['entities']}
    edges = []
    for edge in eg['edges']:
        if ep['id'] not in edge.get('episodes', []):
            continue
        # For preference flip episode, emit the NEW preference and mark old invalid in timestamps path
        if ep['id'] == 'ep-10' and edge['uuid'] == 'e-veg':
            continue
        edges.append(
            {
                'source_entity_name': ent_by_id[edge['source']]['name'],
                'target_entity_name': ent_by_id[edge['target']]['name'],
                'relation_type': edge['name'],
                'fact': edge['fact'],
                'valid_at': edge.get('valid_at'),
                'invalid_at': edge.get('invalid_at') if edge['uuid'] != 'e-veg' else None,
                'episode_indices': [0],
            }
        )
    return edges


def _schema_fields(response_model: type | None) -> set[str]:
    if response_model is None:
        return set()
    fields = getattr(response_model, 'model_fields', None)
    if fields is not None:
        return set(fields.keys())
    # pydantic v1
    return set(getattr(response_model, '__fields__', {}).keys())


def _model_name(response_model: type | None) -> str:
    return getattr(response_model, '__name__', '') if response_model else ''


class MockLLMClient:
    """Minimal Graphiti LLMClient-compatible mock.

    Implements ``generate_response`` and ``_generate_response`` plus the
    attributes Graphiti's base client expects (config, set_tracer, …).
    """

    def __init__(self, fixture_path: Path | None = None) -> None:
        path = fixture_path or _FIXTURE
        self.fixture = json.loads(path.read_text(encoding='utf-8'))
        self.model = 'mock-graphiti-llm'
        self.small_model = 'mock-graphiti-llm-small'
        self.temperature = 0.0
        self.max_tokens = 4096
        self.cache_enabled = False
        self.tracer = None

        # Soft-import LLMConfig if present so we look more like a real client
        try:
            from graphiti_core.llm_client.config import LLMConfig

            self.config = LLMConfig(model=self.model, small_model=self.small_model)
        except Exception:
            self.config = type('Cfg', (), {'model': self.model})()

    def set_tracer(self, tracer: Any) -> None:
        self.tracer = tracer

    async def _generate_response(
        self,
        messages: list[Any],
        response_model: type | None = None,
        max_tokens: int = 4096,
        model_size: Any = None,
    ) -> dict[str, Any]:
        return await self.generate_response(messages, response_model, max_tokens, model_size)

    async def generate_response(
        self,
        messages: list[Any],
        response_model: type | None = None,
        max_tokens: int = 4096,
        model_size: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        blob = _episode_blob(messages)
        ep = _find_episode(self.fixture, blob)
        name = _model_name(response_model)
        fields = _schema_fields(response_model)
        logger.debug('MockLLM generate_response model=%s fields=%s ep=%s', name, fields, ep and ep.get('id'))

        # Entity extraction
        if 'extracted_entities' in fields or name in {'ExtractedEntities', 'ExtractedEntitiesModel'}:
            return {'extracted_entities': _entities_for_episode(self.fixture, ep)}

        # Edge extraction
        if 'edges' in fields and 'relation_type' not in fields:
            # ExtractedEdges has edges: list[Edge]
            return {'edges': _edges_for_episode(self.fixture, ep)}
        if name in {'ExtractedEdges', 'ExtractedEdgesModel'}:
            return {'edges': _edges_for_episode(self.fixture, ep)}

        # Single Edge schema mishit — return empty list wrapper if needed
        if {'source_entity_name', 'target_entity_name', 'relation_type', 'fact'} <= fields:
            edges = _edges_for_episode(self.fixture, ep)
            return edges[0] if edges else {
                'source_entity_name': 'Alex Rivera',
                'target_entity_name': 'Seattle',
                'relation_type': 'RELATED_TO',
                'fact': 'noop',
                'valid_at': None,
                'invalid_at': None,
                'episode_indices': [0],
            }

        # Summaries
        if 'summary' in fields and 'summaries' not in fields and 'name' not in fields:
            summary = (ep or {}).get('content', 'Entity summary')[:400]
            return {'summary': summary}
        if 'summaries' in fields:
            ents = _entities_for_episode(self.fixture, ep)
            return {
                'summaries': [
                    {'name': e['name'], 'summary': f"Summary for {e['name']}."}
                    for e in ents
                ]
            }

        # Dedupe nodes — usually asks which duplicate; return empty / keep all
        if 'duplicate_nodes' in fields or 'duplicates' in fields:
            if 'duplicate_nodes' in fields:
                return {'duplicate_nodes': []}
            return {'duplicates': []}
        if 'is_duplicate' in fields:
            return {'is_duplicate': False, 'uuid': None}
        if 'resolved_nodes' in fields:
            return {'resolved_nodes': []}

        # Dedupe edges / contradiction
        if 'duplicate_facts' in fields:
            return {'duplicate_facts': []}
        if 'contradicted_facts' in fields:
            # On diet flip, mark vegetarian edge contradicted if mentioned
            if ep and ep.get('id') == 'ep-10':
                return {'contradicted_facts': [0]}  # index hint; Graphiti may ignore
            return {'contradicted_facts': []}

        # Timestamps
        if 'timestamps' in fields:
            n = len(re.findall(r'fact', blob, flags=re.I)) or 1
            ref = (ep or {}).get('reference_time')
            return {
                'timestamps': [
                    {'valid_at': ref, 'invalid_at': None} for _ in range(min(n, 8))
                ]
            }
        if {'valid_at', 'invalid_at'} <= fields and 'edges' not in fields:
            ref = (ep or {}).get('reference_time')
            inv = '2026-07-18T16:45:00Z' if (ep and ep.get('id') == 'ep-10' and 'vegetarian' in blob.lower()) else None
            return {'valid_at': ref, 'invalid_at': inv}

        # Attributes — return empty / nulls
        if 'attributes' in fields:
            return {'attributes': {}}

        # Classification
        if 'entity_type_id' in fields and 'name' in fields:
            return {'name': 'Alex Rivera', 'entity_type_id': 0, 'episode_indices': [0]}

        # Generic fallback: empty structure matching field names with safe defaults
        out: dict[str, Any] = {}
        for f in fields:
            if f.endswith('s'):
                out[f] = []
            elif f in {'summary', 'fact', 'name', 'content'}:
                out[f] = ''
            elif f in {'is_duplicate'}:
                out[f] = False
            else:
                out[f] = None
        if not out:
            out = {'result': 'ok'}
        logger.debug('MockLLM fallback for model=%s -> %s', name, list(out))
        return out
