# Windows equivalent of run_all.sh. Same pipeline, PowerShell spelling.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Error ".env missing. Copy .env.example → .env and fill in the keys."
}

Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    $k, $v = $_ -split '=', 2
    if ($k -and $v -ne $null) {
        [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim().Trim('"'), "Process")
    }
}

$Python = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} elseif (Test-Path "..\..\..\.venv-graphiti\Scripts\python.exe") {
    # Dev convenience: the overnight session's shared venv.
    "..\..\..\.venv-graphiti\Scripts\python.exe"
} else {
    "python"
}

$AgentId = if ($env:MEMANTO_AGENT_ID) { $env:MEMANTO_AGENT_ID } else { "graphiti-okf-demo" }
New-Item -ItemType Directory -Force -Path data, data\validation, okf_bundle_sample | Out-Null

function Step($msg) {
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "▶ $msg" -ForegroundColor Cyan
    Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
}

$backend = if ($env:GRAPHITI_BACKEND) { $env:GRAPHITI_BACKEND } else { "neo4j" }
if ($backend -eq "neo4j") {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Step "Starting Neo4j (docker compose)"
        docker compose up -d
        Write-Host "Waiting for Neo4j bolt..."
        for ($i = 0; $i -lt 60; $i++) {
            docker compose exec -T neo4j cypher-shell -u neo4j -p $env:NEO4J_PASSWORD "RETURN 1" 2>$null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 2
        }
    } else {
        Write-Error "docker not found. Set GRAPHITI_BACKEND=kuzu for the zero-Docker fallback, or install Docker Desktop."
    }
}

Step "Phase 1 — populate Graphiti"
& $Python scripts\populate_graphiti.py

Step "Phase 1 — export raw Graphiti state"
& $Python scripts\export_graphiti.py

Step "Phase 2 — adapt Graphiti → OKF + provider JSON"
& $Python scripts\graphiti_to_memanto.py

Step "Phase 2 — dry-run OKF import"
memanto migrate okf data\graphiti_okf_bundle --dry-run | Tee-Object -FilePath data\okf_dry_run.txt

Step "Phase 2 — dry-run provider-JSON (savings report)"
memanto migrate mem0 --file data\memanto_provider_import.json --dry-run | Tee-Object -FilePath data\provider_dry_run.txt
$report = Get-ChildItem "$env:USERPROFILE\.memanto\migrate\mem0\*\migrate-report.md" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($report) {
    Copy-Item $report.FullName data\savings_report.txt -Force
    Write-Host "Saved savings report → data\savings_report.txt"
}

Step "Phase 2 — real OKF import into agent $AgentId"
memanto agent create --id $AgentId 2>$null
memanto agent activate $AgentId
memanto migrate okf data\graphiti_okf_bundle --agent $AgentId | Tee-Object -FilePath data\okf_import.txt

Step "Phase 3 — round-trip validation"
& $Python scripts\run_validation.py --agent $AgentId

Step "Phase 4 — export OKF (pre-consolidation)"
if (Test-Path data\okf_pre_consolidation) { Remove-Item -Recurse -Force data\okf_pre_consolidation }
memanto memory export --okf --agent $AgentId -o data\okf_pre_consolidation --split file

Step "Phase 4 — populate + migrate second source (Mem0)"
& $Python scripts\populate_mem0.py
memanto migrate mem0 --file data\mem0_export.json --agent $AgentId --report | Tee-Object -FilePath data\mem0_import.txt

Step "Phase 4 — export OKF (post-consolidation) + diff"
if (Test-Path okf_bundle_sample) { Remove-Item -Recurse -Force okf_bundle_sample }
memanto memory export --okf --agent $AgentId -o okf_bundle_sample --split file
# Directory-level consolidation evidence (no commit required).
$diffPath = "data\consolidation_diff.txt"
$preFiles = Get-ChildItem data\okf_pre_consolidation -Recurse -File | ForEach-Object { $_.FullName.Substring((Resolve-Path data\okf_pre_consolidation).Path.Length + 1) }
$postFiles = Get-ChildItem okf_bundle_sample -Recurse -File | ForEach-Object { $_.FullName.Substring((Resolve-Path okf_bundle_sample).Path.Length + 1) }
$added = $postFiles | Where-Object { $_ -notin $preFiles }
$removed = $preFiles | Where-Object { $_ -notin $postFiles }
@(
    "Consolidation directory diff",
    "pre : data/okf_pre_consolidation",
    "post: okf_bundle_sample",
    "added   ($($added.Count)):",
    ($added | ForEach-Object { "  + $_" }),
    "removed ($($removed.Count)):",
    ($removed | ForEach-Object { "  - $_" })
) | Set-Content $diffPath
Write-Host "Consolidation diff → $diffPath"

Step "Done"
Write-Host "Artifacts under data/ and okf_bundle_sample/."
