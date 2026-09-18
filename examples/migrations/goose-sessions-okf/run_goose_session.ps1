param(
    [string]$Goose = "goose",
    [string]$Provider = "chatgpt_codex",
    [string]$Model = "gpt-5.6-luna",
    [string]$SessionName = "ledger-portability-demo"
)

$ErrorActionPreference = "Stop"
$example = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspace = Join-Path $example ".demo-workspace"

if (Test-Path $workspace) {
    Remove-Item -Recurse -Force -LiteralPath $workspace
}
Copy-Item -Recurse -LiteralPath (Join-Path $example "source_project") -Destination $workspace

$env:GOOSE_TELEMETRY_ENABLED = "false"
$env:GOOSE_DISABLE_SESSION_NAMING = "true"
if ($IsWindows -and (Get-Command pwsh -ErrorAction SilentlyContinue)) {
    $env:GOOSE_SHELL = (Get-Command pwsh).Source
}

$system = "Work in this small local Python repository. Use developer tools, make only the requested change, and run the requested tests. Keep replies concise."
$first = "Read README.md, ledger.py and test_ledger.py. Run python -m unittest -v. Fix only reconciliation_key to return a deterministic SHA-256 digest built from merchant_id and external_id. Leave audit_line unchanged for the next turn. Run the tests again and report the remaining failure."
$second = "Continue with the remaining failure. Update only audit_line so it never stores the full customer email. For alex@example.com it must show a***@example.com while preserving the payment amount. Run python -m unittest -v and confirm both tests pass."
$recall = "Without reading the files again, state the three project rules you retained from this session: the reconciliation-key rule, the audit-log privacy rule, and the required completion check. Keep the answer to three short bullets."

function Assert-GooseSucceeded {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "goose $Step failed with exit code $LASTEXITCODE"
    }
}

Push-Location $workspace
try {
    & $Goose run --provider $Provider --model $Model --no-profile --with-builtin developer --name $SessionName --max-turns 12 --system $system --text $first
    Assert-GooseSucceeded "first turn"
    & $Goose run --provider $Provider --model $Model --no-profile --with-builtin developer --resume --name $SessionName --max-turns 10 --text $second
    Assert-GooseSucceeded "second turn"
    & $Goose run --provider $Provider --model $Model --no-profile --resume --name $SessionName --max-turns 4 --text $recall
    Assert-GooseSucceeded "recall turn"
}
finally {
    Pop-Location
}
