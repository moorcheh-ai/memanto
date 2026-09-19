"""Run the reproducible lead scenarios through a live n8n webhook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def main() -> int:
    """Execute every committed demo scenario through the live n8n webhook."""
    parser = argparse.ArgumentParser(
        description="Send demo scenarios through the live LeadOps n8n workflow."
    )
    parser.add_argument(
        "--webhook-url",
        default="http://localhost:5679/webhook/lead-intake",
    )
    parser.add_argument(
        "--inputs",
        default=str(HERE / "demo-inputs.json"),
    )
    args = parser.parse_args()

    leads = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    if not isinstance(leads, list) or not leads:
        parser.error("--inputs must contain a non-empty JSON list")

    results = []
    for lead in leads:
        request = Request(
            args.webhook_url,
            data=json.dumps(lead).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("n8n webhook response must be a JSON object")
        result = payload.get("result", payload)
        if isinstance(result, list):
            if len(result) != 1 or not isinstance(result[0], dict):
                raise ValueError("n8n webhook result list must contain one object")
            result = result[0]
        if not isinstance(result, dict):
            raise ValueError("n8n webhook result must be a JSON object")
        qualification = result.get("qualification") or {}
        if not isinstance(qualification, dict):
            raise ValueError("n8n webhook qualification must be a JSON object")
        lead = result.get("lead") or {}
        if not isinstance(lead, dict):
            raise ValueError("n8n webhook lead must be a JSON object")
        results.append(
            {
                "company": lead.get("company"),
                "score": qualification.get("score"),
                "route": qualification.get("route"),
                "status": "executed by n8n",
            }
        )

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
