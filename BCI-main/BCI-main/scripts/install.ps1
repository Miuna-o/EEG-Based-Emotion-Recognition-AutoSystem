param([switch]$LegacyCertificates)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $devIsRunning = $false
    $devProbe = New-Object System.Net.Sockets.TcpClient
    try { $devProbe.Connect('127.0.0.1', 5173); $devIsRunning = $true } catch { } finally { $devProbe.Dispose() }
    if ($devIsRunning) { throw 'Port 5173 is in use. Stop the development server before installation; no Node process was terminated.' }
    python -c "import sys; assert sys.version_info[:2] == (3,13), 'Use Python 3.13 for the verified lock file.'"
    if ($LASTEXITCODE -ne 0) { throw 'Python version mismatch.' }
    if (!(Test-Path -LiteralPath '.runtime/Scripts/python.exe')) {
        python -m venv .runtime
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create local environment.' }
    }
    $installOptions = @('-m', 'pip', 'install', '-r', 'backend/requirements.lock', '--no-cache-dir', '--disable-pip-version-check', '--timeout', '15', '--retries', '1')
    if ($LegacyCertificates) { $installOptions += '--use-deprecated=legacy-certs' }
    & ./.runtime/Scripts/python.exe @installOptions
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    Push-Location frontend
    try {
        npm ci --cache .npm-cache --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    & ./.runtime/Scripts/python.exe -X utf8 scripts/launcher.py diagnose
} finally { Pop-Location }
