#!/usr/bin/env bash
# Round-trip the sample OKF bundle four times and check it reaches a fixed point.
set -euo pipefail
cd "$(dirname "$0")"

python fidelity.py sample/bundle-gen0 --generations 4 --out sample/fidelity-report.md
python -m pytest tests -q
