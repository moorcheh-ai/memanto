#!/usr/bin/env bash
set -e
echo "ChatGPT Liberation — 15-min reproduce"
python -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
pip install -q -r requirements.txt
pip install -q -e ../../..
python scripts/build_sample_archive.py
python scripts/run_migration.py --source sample-data --okf-out sample-data/okf-bundle
python scripts/validate_roundtrip.py
pytest -q --override-ini="addopts="
echo "Done — see sample-data/okf-bundle, savings_report.md, recall-parity.md"
