"""Run the reproducible lead scenarios through a live n8n webhook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def main() -> int:
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
        result = payload.get("result", payload)
        qualification = result.get("qualification") or {}
        results.append(
            {
                "company": (result.get("lead") or {}).get("company"),
                "score": qualification.get("score"),
                "route": qualification.get("route"),
                "status": "executed by n8n",
            }
        )

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
