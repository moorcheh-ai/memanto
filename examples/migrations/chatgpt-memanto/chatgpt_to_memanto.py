import argparse
import json
from pathlib import Path

from memanto.cli.migrate.mappers import map_chatgpt

def main() -> None:
    parser = argparse.ArgumentParser(description="Convert ChatGPT export to Memanto migration format")
    parser.add_argument("--input", type=str, required=True, help="Path to ChatGPT conversations.json")
    parser.add_argument("--output", type=str, required=True, help="Output migration file")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        export = json.load(f)

    rows = map_chatgpt(export)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"Wrote {len(rows)} mapped memories to {output_path}")

if __name__ == "__main__":
    main()
