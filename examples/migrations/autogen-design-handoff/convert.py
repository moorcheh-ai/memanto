"""Convert your own ListMemory.dump_component().model_dump(mode='json') file."""

import argparse
import json
from pathlib import Path

from migrate_demo import to_okf


def main() -> None:
    """Convert a supplied ListMemory snapshot into a new lossless OKF bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", type=Path)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    source = json.loads(args.component.read_text())
    print(json.dumps(to_okf(source, args.bundle), indent=2))


if __name__ == "__main__":
    main()
