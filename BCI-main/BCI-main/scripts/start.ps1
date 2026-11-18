param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.runtime/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/install.ps1 first.' }
Push-Location $projectRoot
try {
    if ($NoBrowser) { & $pythonPath -X utf8 scripts/launcher.py start --no-browser }
    else { & $pythonPath -X utf8 scripts/launcher.py start }
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed; run scripts/diagnose.ps1.' }
} finally { Pop-Location }
