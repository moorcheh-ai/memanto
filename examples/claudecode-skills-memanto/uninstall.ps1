# Uninstaller for Claude Code x Memanto (Windows PowerShell).
$ErrorActionPreference = 'Stop'

$TargetDir = Join-Path $env:USERPROFILE '.claude\hooks\memanto'
$Settings  = Join-Path $env:USERPROFILE '.claude\settings.json'

if (Test-Path $TargetDir) {
    Remove-Item -Recurse -Force $TargetDir
    Write-Host ('Removed {0}' -f $TargetDir)
}

$backups = Get-ChildItem -Path (Split-Path $Settings -Parent) -Filter 'settings.json.bak.*' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending

if ($backups -and $backups.Count -gt 0) {
    Move-Item -Force $backups[0].FullName $Settings
    Write-Host ('Restored settings.json from {0}' -f $backups[0].FullName)
} else {
    Write-Host 'No backup of settings.json found - leaving as-is.'
}

Write-Host 'Uninstall complete. Memories in Memanto were left intact.'
