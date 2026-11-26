# Start the SDD QA Automation Dashboard and open it in the browser.
# Uses the framework's virtual environment (FastAPI, uvicorn, PyYAML and Playwright are already installed there).
param([int]$Port = 8090)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$parent = Split-Path -Parent $here
$framework = if ($env:SDD_FRAMEWORK_DIR) { $env:SDD_FRAMEWORK_DIR }
             elseif ((Test-Path (Join-Path $parent "main.py")) -and (Test-Path (Join-Path $parent "specifications"))) { $parent }
             else { Join-Path $parent "qa-sdd-crewai-framework" }
$py = Join-Path $framework ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Framework venv not found at $py - falling back to 'python' (install requirements.txt first)." -ForegroundColor Yellow
    $py = "python"
}
$env:DASHBOARD_PORT = "$Port"
Start-Job -ScriptBlock { param($p) Start-Sleep -Seconds 3; Start-Process "http://127.0.0.1:$p" } -ArgumentList $Port | Out-Null
Set-Location $here
& $py server.py
