"""One-command LangGraph checkpoint to OKF migration demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from convert import convert
from generate_source import generate
from validate_roundtrip import validate


def run(base_dir: Path) -> dict[str, object]:
    base_dir.mkdir(parents=True, exist_ok=True)
    source = generate(base_dir)
    conversion = convert(base_dir)
    validation = validate(base_dir)
    result = {
        "source": source,
        "conversion": conversion,
        "validation": validation,
    }
    (base_dir / "reports" / "demo-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    result = run(args.base_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
