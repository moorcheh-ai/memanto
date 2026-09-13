$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python build_sample_archive.py

python -c @"
from pathlib import Path
import json
from hindsight_mapper import export_hindsight_to_okf

showcase = Path('.')
archive = showcase / 'sample-data' / 'project-atlas-agent.zip'
okf_dir = showcase / 'sample-data' / 'okf-bundle'
result = export_hindsight_to_okf(archive, okf_dir, agent_id='project-atlas-agent')
print(json.dumps(result['migration_summary'], indent=2))
"@

python -m pytest tests/ -q -c pytest.ini
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python validation/validate_roundtrip.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "OKF bundle ready at: $Root\sample-data\okf-bundle"
