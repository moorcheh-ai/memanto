"""Regression coverage for explicit instruction authority rendering."""

from claudecode_memanto.profile import MemoryProfile


def test_explicit_statement_renders_in_exact_rules_section() -> None:
    """Explicit user instructions must render under the authoritative Rules section."""
    instruction = "Use pytest for project tests."
    block = MemoryProfile(
        [
            {
                "type": "instruction",
                "content": instruction,
                "confidence": 1.0,
                "provenance": "explicit_statement",
            }
        ]
    ).format_context_block()

    assert "\nRules (explicit user instructions):\n" in block
    assert instruction in block
    rules = block.split("\nRules (explicit user instructions):\n", 1)[1]
    assert instruction in rules
    assert "context-only" not in block
