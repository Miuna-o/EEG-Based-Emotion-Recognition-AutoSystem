$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.runtime/Scripts/python.exe'
Push-Location $projectRoot
try {
    & $pythonPath -X utf8 scripts/launcher.py stop
    if ($LASTEXITCODE -ne 0) { throw 'Stop failed; no external process was terminated.' }
} finally { Pop-Location }
