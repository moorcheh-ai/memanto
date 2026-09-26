"""Query-safety helpers for text sent to backend retrieval endpoints.

The Moorcheh retrieval backends parse ``#key:value`` tokens inside the
``query`` field as server-side metadata filters (an undocumented query DSL).
Text that is not fully trusted must not be able to steer that filter
channel: a memory whose content ends in ``#agent:<value>`` becomes, via the
daily summary / conflict digest retrieval queries that are built verbatim
from memory contents, a dormant payload that can suppress or select the
documents the LLM is allowed to see (context manipulation).

See ``docs/security/findings-2026-09-14.md`` (FINDING-05) for the full
analysis and reproduction.
"""

import re

# A filter token is a ``#`` immediately followed by a key, a colon and a
# non-space value. Requiring a value right after the colon keeps ordinary
# markdown headers (``# Session Summary``) and bare hashtags intact.
_FILTER_TOKEN = re.compile(r"(^|\s)#([A-Za-z0-9_.\-]+):(\S+)")


def neutralize_filter_syntax(text: str) -> str:
    """Defuse backend ``#key:value`` filter tokens in untrusted text.

    Strips only the leading ``#`` from tokens like ``#agent:guest`` so the
    words survive for semantic search while the token stops matching the
    backend filter DSL. Trusted filter parameters (type/tags/metadata
    filters built by the app itself) are unaffected — this helper must be
    applied to free text only, never to the structured filter channel.

    Args:
        text: Free text that will be sent as (part of) a backend ``query``.

    Returns:
        The same text with ``#key:value`` tokens rewritten to ``key:value``.
    """
    return _FILTER_TOKEN.sub(r"\1\2:\3", text)
