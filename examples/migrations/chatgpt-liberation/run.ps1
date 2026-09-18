Write-Host "ChatGPT Liberation — 15-min reproduce"
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
pip install -q -e ..\..\..
python scripts/build_sample_archive.py
python scripts/run_migration.py --source sample-data --okf-out sample-data/okf-bundle
python scripts/validate_roundtrip.py
pytest -q --override-ini="addopts="
Write-Host "Done — see sample-data/okf-bundle, savings_report.md, recall-parity.md"
