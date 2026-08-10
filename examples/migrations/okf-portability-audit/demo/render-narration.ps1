param(
    [string]$OutputPath = "$PSScriptRoot\memanto-okf-portability-demo-v3.wav"
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Speech

$narration = @'
Your AI agent can remember everything, until the platform changes. This is a real migration from GitHub issue sixteen oh nine into Open Knowledge Format: plain Markdown you can inspect and carry. The current submission runs one reproducible command. It exports one issue and thirty-one comments into thirty-three O K F memories. Memanto's official dry run maps all thirty-three and skips zero. Next, the production loader, mapper, classifier, and exporter perform a full round trip. The audit compares every portable field. Thirty-three in. Thirty-three out. Zero removed. Zero changed. Five golden questions score five out of five before migration and five out of five after it. The result is lossless, recall is preserved, and each memory opens as readable Markdown with its original source link. No cloud write, no secret, and no invented performance claim. The code, tests, sample bundle, audit receipt, and this reproducible demo are linked in pull request eighteen thirteen. Agent memory should belong to its user. Memanto plus O K F makes that portable. AI-assisted production. Every result shown comes from the real command at commit E F seven seven zero six two.
'@

$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $speaker.SelectVoice('Microsoft Zira Desktop')
    $speaker.Rate = 1
    $speaker.Volume = 100
    $speaker.SetOutputToWaveFile($OutputPath)
    $speaker.Speak($narration)
}
finally {
    $speaker.Dispose()
}

Write-Output $OutputPath
