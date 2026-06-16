"""Shared ingestion-tax estimates for provider analyze comparisons."""

from __future__ import annotations

from typing import Any

# Illustrative ingest pricing — not provider billing. Sensible range for reports:
#   input  $0.10–$0.20 / 1M  (content/embedding pipeline)
#   output $0.60–$1.50 / 1M  (extraction LLM writes facts)
DEFAULT_INPUT_USD_PER_1M = 0.15
DEFAULT_OUTPUT_USD_PER_1M = 1.00

# Mem0 export lacks raw source text; scale stored memory text to estimate ingest.
DEFAULT_SOURCE_MULTIPLIER = 2.5


def estimate_ingestion_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    assumptions: dict[str, Any],
) -> dict[str, Any]:
    """
    Estimate LLM extraction cost at ingest time.

    Ingest has two billable parts we model separately:
      - Input: content processed (embedding / ingest pipeline) @ input rate
      - Output: facts the extraction AI model writes @ output rate
    We do not have provider invoices — token counts come from the export.
    """
    input_rate = float(assumptions["extraction_usd_per_1m_input_tokens"])
    output_rate = float(assumptions["extraction_usd_per_1m_output_tokens"])

    input_cost = (input_tokens / 1_000_000) * input_rate
    output_cost = (output_tokens / 1_000_000) * output_rate
    total_cost = input_cost + output_cost

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_extraction_tokens": input_tokens + output_tokens,
        "input_cost_usd": round(input_cost, 4),
        "output_cost_usd": round(output_cost, 4),
        "total_cost_usd": round(total_cost, 4),
        "tokens_saved": input_tokens + output_tokens,
    }
