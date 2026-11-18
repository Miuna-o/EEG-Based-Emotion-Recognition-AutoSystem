param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    & $Python -X utf8 -c "import importlib.util as u,sys; missing=[x for x in ['numpy','scipy','pandas','mne','PyQt5','matplotlib','openai','PIL'] if not u.find_spec(x)]; print('Missing optional research dependencies: '+', '.join(missing)) if missing else None; sys.exit(bool(missing))"
    if ($LASTEXITCODE -ne 0) { throw 'Choose your existing research Python with -Python. No CUDA or models will be installed automatically.' }
    & $Python -X utf8 -m core.UI.main_UI
} finally { Pop-Location }
