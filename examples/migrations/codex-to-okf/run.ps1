param(
    [string]$Source,
    [string]$Output
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Source) { $Source = Join-Path $Root 'sample_data\codex-rollout-sanitized.jsonl' }
if (-not $Output) { $Output = Join-Path $Root 'sample_output\okf-bundle' }

$Reexported = Join-Path $Root 'sample_output\reexported-okf'
$PortabilityReport = Join-Path $Root 'sample_output\portability-parity.json'
python (Join-Path $Root 'codex_to_okf.py') $Source $Output `
    --title 'A real Codex task: from changing context to portable memory'
python (Join-Path $Root 'validate_roundtrip.py') $Output `
    --golden (Join-Path $Root 'golden_qa.json') `
    --report (Join-Path $Root 'sample_output\recall-parity.json')

python (Join-Path $Root 'validate_portability.py') $Output $Reexported `
    --report $PortabilityReport `
    --replace

Write-Host 'Dry-run with Memanto:'
Write-Host "  memanto migrate okf `"$Output`" --dry-run"
