# Thin wrapper: check dual venvs and MOORCHEH_API_KEY, then run the live round trip.
# Never prints the API key value.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ExamplePython = Join-Path $Root ".venv\Scripts\python.exe"
$RepoRoot = (Resolve-Path (Join-Path $Root "..\..\..")).Path
$RepoPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Get-StrippedEnvValue {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return "" }
    $trimmed = $Value.Trim()
    if ($trimmed.Length -ge 2) {
        $quote = $trimmed[0]
        if (($quote -eq '"' -or $quote -eq "'") -and $trimmed[-1] -eq $quote) {
            $trimmed = $trimmed.Substring(1, $trimmed.Length - 2).Trim()
        }
    }
    return $trimmed
}

function Test-ConfiguredMoorchehApiKey {
    param([AllowNull()][string]$Value)
    $cleaned = Get-StrippedEnvValue $Value
    if (-not $cleaned) { return $false }
    $placeholders = @(
        'your_api_key_here',
        'your_key_here',
        'your_key',
        'your-api-key-here',
        'changeme',
        'replace_me',
        'replace-me',
        'xxx',
        'todo',
        'api_key_here',
        'insert_api_key_here',
        '<your_api_key>',
        '<api_key>',
        'none',
        'null',
        'undefined'
    )
    return $placeholders -notcontains $cleaned.ToLowerInvariant()
}

function Get-EnvFileMoorchehApiKey {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*MOORCHEH_API_KEY\s*=\s*(.*)$') {
            return $Matches[1]
        }
    }
    return $null
}

if (-not (Test-Path $ExamplePython)) {
    Write-Error @"
Example .venv is missing.
From this directory run:
  python -m venv .venv
  .venv\Scripts\python -m pip install -e `".[dev]`"
"@
}

if (-not (Test-Path $RepoPython)) {
    Write-Error @"
Repository-root .venv is missing.
From the memanto repo root run:
  uv sync --group dev
  # or: python -m venv .venv; .venv\Scripts\python -m pip install -e `".[all]`"
"@
}

$keyConfigured = $false
$processKey = $env:MOORCHEH_API_KEY
if ($null -ne $processKey -and $processKey.Trim()) {
    # Explicit process env wins; placeholders do not count as configured.
    $keyConfigured = Test-ConfiguredMoorchehApiKey $processKey
} else {
    $localVal = Get-EnvFileMoorchehApiKey (Join-Path $Root ".env")
    $memantoVal = Get-EnvFileMoorchehApiKey (Join-Path $HOME ".memanto\.env")
    if (Test-ConfiguredMoorchehApiKey $localVal) {
        $keyConfigured = $true
    } elseif (Test-ConfiguredMoorchehApiKey $memantoVal) {
        $keyConfigured = $true
    }
}

if (-not $keyConfigured) {
    Write-Error @"
MOORCHEH_API_KEY is not set.
Get a free key at https://moorcheh.ai/ then either:
  `$env:MOORCHEH_API_KEY = 'your_key'
  copy .env.example to .env and fill it in
  or run memanto once to store the key in ~/.memanto/.env
Placeholder values such as your_api_key_here do not count.
Do not commit .env. This script never prints the key value.
"@
}

& $ExamplePython (Join-Path $Root "record_live_terminal.py") @args
exit $LASTEXITCODE
