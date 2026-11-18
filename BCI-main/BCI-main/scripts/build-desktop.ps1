param([switch]$SkipFrontend)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $projectRoot '.desktop-build'
$previousCliHome = $env:DOTNET_CLI_HOME
$previousNugetPackages = $env:NUGET_PACKAGES
$previousFirstRun = $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE
Push-Location $projectRoot
try {
    $env:DOTNET_CLI_HOME = Join-Path $buildRoot 'dotnet-cli'
    $env:NUGET_PACKAGES = Join-Path $buildRoot 'packages'
    $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
    & ./.runtime/Scripts/python.exe -B -X utf8 scripts/prepare_desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'Desktop assets could not be prepared.' }
    if (!$SkipFrontend) {
        Push-Location frontend
        try {
            npm run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        } finally { Pop-Location }
    }
    dotnet restore desktop/Xinlan.Desktop.csproj --source "$buildRoot/feed" -p:NuGetAudit=false
    if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency restore failed.' }
    dotnet publish desktop/Xinlan.Desktop.csproj -c Release --no-restore --no-self-contained -o desktop/dist
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
    $shell = New-Object -ComObject WScript.Shell
    $appName = [string][char]0x5FC3 + [char]0x6F9C
    $shortcut = $shell.CreateShortcut((Join-Path $projectRoot ($appName + '.lnk')))
    $shortcut.TargetPath = Join-Path $projectRoot ('desktop/dist/' + $appName + '.exe')
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = $shortcut.TargetPath + ',0'
    $shortcut.Description = 'Xinlan Desktop Workbench'
    $shortcut.Save()
    Write-Output ('Desktop app: ' + $shortcut.TargetPath)
} finally {
    Pop-Location
    $env:DOTNET_CLI_HOME = $previousCliHome
    $env:NUGET_PACKAGES = $previousNugetPackages
    $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = $previousFirstRun
}
