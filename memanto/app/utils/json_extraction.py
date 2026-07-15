"""Helpers for extracting structured JSON from LLM responses."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def iter_json_arrays(text: str) -> Iterator[list[Any]]:
    """Yield JSON arrays embedded in a possibly noisy LLM response.

    LLMs often return valid JSON with short prose, labels, or markdown fences.
    A naive first-``[``/last-``]`` slice fails when that prose contains its own
    brackets. Scanning each candidate ``[`` with JSONDecoder keeps extraction
    tolerant without accepting malformed JSON.
    """
    if not text:
        return

    candidates = [match.group(1).strip() for match in _FENCE_RE.finditer(text)]
    candidates.append(_FENCE_RE.sub("", text).strip())

    decoder = json.JSONDecoder()
    seen: set[str] = set()

    for candidate in candidates:
        if not candidate:
            continue
        for match in re.finditer(r"\[", candidate):
            fragment = candidate[match.start() :]
            try:
                parsed, end = decoder.raw_decode(fragment)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, list):
                continue
            raw = fragment[:end]
            if raw in seen:
                continue
            seen.add(raw)
            yield parsed
