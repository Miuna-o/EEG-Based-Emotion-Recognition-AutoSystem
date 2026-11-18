param([string]$ResearchPython = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.runtime/Scripts/python.exe'
Push-Location $projectRoot
try {
    & $pythonPath -X utf8 -m pytest tests/test_workspace_api.py tests/test_job_integrity.py tests/test_reporting_and_io.py tests/test_optional_assistant.py tests/test_review_regressions.py tests/test_json_schema_limits.py tests/test_frontend_contract.py tests/test_versioned_display_code.py tests/test_import_mode_marker.py tests/test_launcher_integration.py tests/test_launcher_port_change.py -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend verification failed.' }
    if ($ResearchPython) {
        & $ResearchPython -B -X utf8 -m unittest discover -s tests -p 'test_legacy*.py' -v
        if ($LASTEXITCODE -ne 0) { throw 'Legacy regression verification failed.' }
        & $ResearchPython -B -X utf8 -m tests.legacy_hidden_smoke
        if ($LASTEXITCODE -ne 0) { throw 'Legacy smoke verification failed.' }
    }
    Push-Location frontend
    try {
        npm run typecheck
        if ($LASTEXITCODE -ne 0) { throw 'Type checking failed.' }
        npm run lint
        if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
        & $pythonPath -X utf8 ../scripts/frontend_e2e.py
        if ($LASTEXITCODE -ne 0) { throw 'End-to-end verification failed. Start API first.' }
    } finally { Pop-Location }
} finally { Pop-Location }
