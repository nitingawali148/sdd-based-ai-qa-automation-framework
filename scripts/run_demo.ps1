<#
.SYNOPSIS
  Guided end-to-end SDD demo. YOU are the human approver: every gate shows what to review and asks you.

.EXAMPLE
  .\scripts\run_demo.ps1 -Approver "Jane Doe"
#>
param(
    [Parameter(Mandatory = $true)][string]$Approver
)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = ".\.venv\Scripts\python.exe"

function Step($title) { Write-Host "`n=== $title ===" -ForegroundColor Cyan }
function Gate($spec, $stage, $review) {
    Write-Host "`nHUMAN GATE: $spec / $stage" -ForegroundColor Yellow
    Write-Host "  Review: $review"
    $answer = Read-Host "  Approve $spec ($stage) as '$Approver'? [y/N]"
    if ($answer -ne "y") { Write-Host "  Not approved - stopping here. Re-run the script when ready."; exit 0 }
    & $py main.py approve $spec --stage $stage --by $Approver --comment "approved in guided demo"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Step "1. Specification Flow (REQ-001 login, REQ-002 user API, REQ-003 ambiguous)"
& $py main.py spec REQ-001
& $py main.py spec REQ-002
& $py main.py spec REQ-003   # expected: NEEDS_CLARIFICATION (shows the validation gate)
foreach ($s in "SPEC-LOGIN-001", "SPEC-USERS-001") {
    $feature = if ($s -eq "SPEC-LOGIN-001") { "user-login" } else { "user-management" }
    Gate $s "spec" "specifications\features\$feature\spec.md"
}

Step "2. Test Design Flow"
foreach ($s in "SPEC-LOGIN-001", "SPEC-USERS-001") { & $py main.py design $s }
Gate "SPEC-LOGIN-001" "test_cases" "specifications\features\user-login\test_cases.md"
Gate "SPEC-USERS-001" "test_cases" "specifications\features\user-management\test_cases.md"

Step "3. Automation Flow"
foreach ($s in "SPEC-LOGIN-001", "SPEC-USERS-001") { & $py main.py automate $s }
Gate "SPEC-LOGIN-001" "scripts" "output\staging\SPEC-LOGIN-001\"
Gate "SPEC-USERS-001" "scripts" "output\staging\SPEC-USERS-001\"

Step "4. Execution Flow (pytest + failure analysis + dashboard)"
& $py main.py execute

Step "5. Change an acceptance criterion (AC-002 message) and run the Change Flow"
$acFile = "specifications\features\user-login\acceptance_criteria.yaml"
$new = "Incorrect email or password. Please try again."
(Get-Content $acFile -Raw -Encoding utf8).Replace("Invalid email or password", $new) | Set-Content $acFile -Encoding utf8
Write-Host "  Edited $acFile : 'Invalid email or password' -> '$new' (AC-002 and AC-005)"
& $py main.py change SPEC-LOGIN-001
Gate "SPEC-LOGIN-001" "spec" "specifications\changes\ (latest CHG record) and the spec diff"
& $py main.py change SPEC-LOGIN-001
Gate "SPEC-LOGIN-001" "test_cases" "regenerated impacted test cases in specifications\features\user-login\test_cases.md"
& $py main.py change SPEC-LOGIN-001
Gate "SPEC-LOGIN-001" "scripts" "output\staging\SPEC-LOGIN-001\ (only impacted regions changed)"
& $py main.py change SPEC-LOGIN-001   # re-executes only impacted tests; the app still shows the old text -> drift

Step "6. Implement the change in the demo app and re-run only the impacted tests"
$env:SDD_DEMO_LOGIN_ERROR = $new
& $py main.py execute SPEC-LOGIN-001
& $py main.py status
Write-Host "`nDashboard: reports\dashboard.html" -ForegroundColor Green
