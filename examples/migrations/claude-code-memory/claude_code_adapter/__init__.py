"""Claude Code conversation memory adapter.

Parses Claude Code JSONL session archives and converts durable knowledge into
an OKF bundle consumable by ``memanto migrate okf``.
"""

from claude_code_adapter.extractor import extract_memories
from claude_code_adapter.okf_writer import write_okf_bundle
from claude_code_adapter.parser import ConversationTurn, parse_claude_jsonl

__all__ = [
    "parse_claude_jsonl",
    "ConversationTurn",
    "extract_memories",
    "write_okf_bundle",
]
