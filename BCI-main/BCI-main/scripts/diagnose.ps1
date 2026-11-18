$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.runtime/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
Push-Location $projectRoot
try { & $pythonPath -X utf8 scripts/launcher.py diagnose } finally { Pop-Location }
