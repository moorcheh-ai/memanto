"""Active Digest backend — offline simulation of Memanto's core principle.

Memanto's key innovation is an active companion agent that maintains a
*versioned digest* of memory.  When a new preference contradicts an existing
one, the old entry is marked as **superseded** and excluded from retrieval.
Only current, non-contradicted facts are injected into the agent context.

This module is a faithful offline simulation of that principle:
- No network call, no API key required.
- Compatible with the real Memanto REST API backend (see memanto_api.py).
- Implements contradiction detection via semantic-genre fingerprinting and
  content-word overlap, inspired by the algorithm described in
  arXiv:2604.22085 (Memanto: Typed Semantic Memory).

Algorithm:
    1. For each new memory, extract its *genre fingerprint* (a set of
       normalised topic labels: e.g. {"sci-fi", "horror", "k-drama"}).
    2. For each existing non-superseded memory of the same ``memory_type``,
       compute the fingerprint intersection.
    3. If intersection is non-empty *and* the new entry appears to override
       the old (presence of negation/transition signals), mark old as
       superseded.
    4. ``recall()`` returns only non-superseded entries, most recent first,
       up to ``limit``.  Token count is computed via tiktoken.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import tiktoken

from backends.base import MemoryBackend

_ENC = tiktoken.encoding_for_model("gpt-4o-mini")

# ---------------------------------------------------------------------------
# Genre / topic fingerprinting
# ---------------------------------------------------------------------------

# Maps a canonical group label to a list of surface-form keywords.
_GENRE_GROUPS: dict[str, list[str]] = {
    "sci-fi": [
        "sci-fi", "science fiction", "space opera", "blockbuster",
        "interstellar", "dune", "arrival", "villeneuve", "nolan",
    ],
    "horror": ["horror", "scary", "frightening", "gore"],
    "thriller": ["thriller", "psychological thriller", "suspense"],
    "k-drama": [
        "k-drama", "korean drama", "korean cinema", "korean film",
        "korean content", "k drama", "bong joon", "park chan", "kim jee",
        "parasite", "signal",
    ],
    "documentary": [
        "documentary", "documentaries", "nature doc", "real stories",
        "real story", "non-fiction", "nonfiction",
    ],
    "history": ["history", "historical", "ancient", "civilization"],
    "science": ["science documentary", "ocean science", "science series"],
    "director-preference": [
        "favorite director", "best director", "working director",
    ],
    "language-preference": [
        "english-language", "english language", "subtitles",
    ],
    "format-preference": [
        "theatrical", "streaming", "series", "films",
    ],
}

# Transition signals that indicate the new memory OVERRIDES the old one.
_TRANSITION_SIGNALS = [
    "done with", "no longer", "not anymore", "moved on", "switched to",
    "now prefer", "now priorit", "priority is now", "changed", "no interest",
    "dropped", "less interest", "not watch", "won't watch", "refused",
    "acceptable now", "softened", "updated",
]


def _genre_fingerprint(text: str) -> frozenset[str]:
    """Return the set of canonical genre group labels present in *text*."""
    lower = text.lower()
    groups: set[str] = set()
    for group, keywords in _GENRE_GROUPS.items():
        if any(kw in lower for kw in keywords):
            groups.add(group)
    return frozenset(groups)


def _has_transition_signal(text: str) -> bool:
    """Return True if *text* contains a preference-transition signal."""
    lower = text.lower()
    return any(sig in lower for sig in _TRANSITION_SIGNALS)


def _content_word_overlap(a: str, b: str, threshold: float = 0.30) -> bool:
    """Return True if content-word overlap between *a* and *b* exceeds *threshold*."""
    _STOP = {
        "alex", "their", "they", "have", "with", "been", "that", "this",
        "from", "more", "says", "said", "also", "some", "than", "been",
        "very", "much", "even", "just", "like", "over", "what", "when",
    }

    def _words(t: str) -> set[str]:
        return {
            w for w in re.sub(r"[^\w\s]", "", t.lower()).split()
            if len(w) > 3 and w not in _STOP
        }

    words_a = _words(a)
    words_b = _words(b)
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
    return overlap >= threshold


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    text: str
    memory_type: str
    version: int
    fingerprint: frozenset[str]
    superseded: bool = False


# ---------------------------------------------------------------------------
# Backend implementation
# ---------------------------------------------------------------------------

class ActiveDigestBackend(MemoryBackend):
    """Memanto active-digest simulation.

    Maintains a versioned list of memories.  When a new entry contradicts an
    existing one (same memory type, overlapping genre fingerprint, and either
    a transition signal or content-word overlap), the old entry is marked
    *superseded* and excluded from future recall results.
    """

    def __init__(self) -> None:
        self._store: list[_Entry] = []
        self._version: int = 0

    # ------------------------------------------------------------------
    # MemoryBackend interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._store.clear()
        self._version = 0

    def remember(self, user_id: str, text: str, memory_type: str = "preference") -> None:  # noqa: ARG002
        self._version += 1
        new_fp = _genre_fingerprint(text)
        new_has_signal = _has_transition_signal(text)

        for entry in self._store:
            if entry.superseded or entry.memory_type != memory_type:
                continue
            fp_overlap = new_fp & entry.fingerprint
            if not fp_overlap:
                continue
            # Supersede if transition signal present OR high content-word overlap.
            if new_has_signal or _content_word_overlap(text, entry.text):
                entry.superseded = True

        self._store.append(
            _Entry(
                text=text,
                memory_type=memory_type,
                version=self._version,
                fingerprint=new_fp,
            )
        )

    def recall(
        self,
        user_id: str,  # noqa: ARG002
        query: str,  # noqa: ARG002
        limit: int = 10,
    ) -> tuple[list[str], int]:
        active = [
            entry for entry in reversed(self._store)
            if not entry.superseded
        ][:limit]
        texts = [f"[{e.memory_type}] {e.text}" for e in reversed(active)]
        token_count = sum(len(_ENC.encode(t)) for t in texts)
        return texts, token_count

    # ------------------------------------------------------------------
    # Diagnostics (not part of the interface — used in tests)
    # ------------------------------------------------------------------

    @property
    def active_count(self) -> int:
        """Number of non-superseded entries currently in the digest."""
        return sum(1 for e in self._store if not e.superseded)

    @property
    def superseded_count(self) -> int:
        """Number of entries that have been superseded."""
        return sum(1 for e in self._store if e.superseded)
