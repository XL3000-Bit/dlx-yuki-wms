[CmdletBinding()]
param([switch]$FullBackend)

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$taskPath = Join-Path $repoRoot '.codex/CURRENT_TASK.md'
$statePath = Join-Path $repoRoot '.codex/PIPELINE_STATE.md'

function Get-ColonField([string]$Name) {
    $line = Get-Content -LiteralPath $taskPath | Where-Object { $_ -match ("^{0}:\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}:\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Get-OutputField([string[]]$Lines, [string]$Name) {
    $line = $Lines | Where-Object { $_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Set-StateField([string]$Name, [string]$Value) {
    $text = Get-Content -Raw -LiteralPath $statePath
    $pattern = '(?m)^' + [regex]::Escape($Name) + '\s*=.*$'
    if ($text -match $pattern) { $text = [regex]::Replace($text, $pattern, "$Name = $Value") }
    else { $text = $text.TrimEnd() + "`r`n$Name = $Value`r`n" }
    Set-Content -LiteralPath $statePath -Value $text -Encoding utf8
}

Write-Output 'RUN_CURRENT_TASK'
if (-not (Test-Path -LiteralPath $taskPath)) { Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
$taskId = Get-ColonField 'TASK_ID'
$status = Get-ColonField 'STATUS'
$level = Get-ColonField 'LEVEL'
$expectedBranch = Get-ColonField 'BRANCH'
$promptRelative = Get-ColonField 'PROMPT'
$allowedPaths = Get-ColonField 'ALLOWED_PATHS'
$actualBranch = (& git -C $repoRoot branch --show-current).Trim()

if (-not $taskId -or $taskId -eq 'NONE') { Write-Output 'REASON = NO_CURRENT_TASK'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if ($status -notin @('PREPARED', 'RUNNABLE')) { Write-Output 'REASON = TASK_NOT_PREPARED'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if ($actualBranch -ne $expectedBranch) { Write-Output 'REASON = BRANCH_MISMATCH'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if (-not $promptRelative -or $promptRelative -eq 'NONE' -or -not (Test-Path -LiteralPath (Join-Path $repoRoot $promptRelative))) {
    Write-Output 'REASON = PROMPT_NOT_FOUND'; Write-Output 'FINAL = SAFETY_STOP'; exit 1
}
if (-not $allowedPaths -or $allowedPaths -eq 'NONE' -or $allowedPaths -match '(^|[;,]\s*)DECLARATION_REQUIRED($|[;,])') {
    Write-Output 'REASON = ALLOWED_PATHS_NOT_DECLARED'; Write-Output 'FINAL = SAFETY_STOP'; exit 1
}
if ($level -eq 'L3' -and $env:APPROVED_L3 -ne 'YES') {
    Write-Output 'REASON = APPROVED_L3_REQUIRED'; Write-Output 'FINAL = SAFETY_STOP'; exit 1
}

$instruction = @"
Repo is $repoRoot.

Read:
.codex/AGENTS.md
.codex/CURRENT_TASK.md
.codex/REVIEW_GATE.md

Read only the PROMPT specified in CURRENT_TASK.md.

Execute only this task.
Do not start another task.
Do not commit.
Do not push.
Do not merge/rebase.
Do not modify paths outside ALLOWED_PATHS.

Stop at:
READY_FOR_HUMAN_REVIEW
FAIL
SAFETY_STOP
"@

& (Join-Path $PSScriptRoot 'invoke-codex.ps1') -Prompt $instruction
if ($LASTEXITCODE -ne 0) { Write-Output 'FINAL = FAIL'; exit 1 }

$scopeOutput = @(& (Join-Path $PSScriptRoot 'validate-scope.ps1') 2>&1)
$scopeCode = $LASTEXITCODE
$scopeOutput | Write-Output
$scope = Get-OutputField $scopeOutput 'FINAL'
$unauthorized = Get-OutputField $scopeOutput 'UNAUTHORIZED_PATHS'
$protected = Get-OutputField $scopeOutput 'PROTECTED_PATHS_CHANGED'
Set-StateField 'SCOPE' $(if ($scopeCode -eq 0 -and $scope -eq 'PASS') { 'PASS' } else { 'FAIL' })
Set-StateField 'UNAUTHORIZED_PATHS' $(if ($unauthorized) { $unauthorized } else { 'UNKNOWN' })
Set-StateField 'PROTECTED_PATHS_CHANGED' $(if ($protected) { $protected } else { 'UNKNOWN' })
if ($scopeCode -ne 0 -or $scope -ne 'PASS') { Write-Output 'FINAL = SAFETY_STOP'; exit 1 }

$testArgs = @{}
if ($FullBackend) { $testArgs.FullBackend = $true }
$testOutput = @(& (Join-Path $PSScriptRoot 'run-tests.ps1') @testArgs 2>&1)
$testCode = $LASTEXITCODE
$testOutput | Write-Output
$tests = Get-OutputField $testOutput 'FINAL'
$diffCheck = Get-OutputField $testOutput 'GIT_DIFF_CHECK'
Set-StateField 'TESTS' $(if ($testCode -eq 0 -and $tests -eq 'PASS') { 'PASS' } else { 'FAIL' })
Set-StateField 'GIT_DIFF_CHECK' $(if ($diffCheck) { $diffCheck } else { 'UNKNOWN' })
if ($testCode -ne 0 -or $tests -ne 'PASS') { Write-Output 'FINAL = FAIL'; exit 1 }

$reviewOutput = @(& (Join-Path $PSScriptRoot 'review-task.ps1') @testArgs 2>&1)
$reviewCode = $LASTEXITCODE
$reviewOutput | Write-Output
$reviewResult = Get-OutputField $reviewOutput 'FINAL'
$businessGate = Get-OutputField $reviewOutput 'BUSINESS_GATE'
Set-StateField 'REVIEW_RESULT' $(if ($reviewResult) { $reviewResult } else { 'UNKNOWN' })
Set-StateField 'BUSINESS_GATE' $(if ($businessGate) { $businessGate } else { 'UNKNOWN' })
$stagedCount = @(& git -C $repoRoot diff --cached --name-only).Count
Set-StateField 'STAGED_PATHS' ([string]$stagedCount)
if ($reviewCode -ne 0 -or $reviewResult -ne 'READY_FOR_HUMAN_REVIEW') { Write-Output ("FINAL = {0}" -f $(if ($reviewResult) { $reviewResult } else { 'FAIL' })); exit 1 }
Write-Output 'FINAL = READY_FOR_HUMAN_REVIEW'
