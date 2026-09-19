# Offline freedom loop (Windows)
param([string]$Mode = "offline")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "== graphiti-okf dry-run (mode=$Mode) =="
python seed_graphiti.py --mode $Mode
python export_graphiti.py --mode $Mode
python adapter.py
python validate_roundtrip.py --mode offline
Write-Host "OKF bundle: $PWD\out\okf-bundle"
