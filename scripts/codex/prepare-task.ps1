[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()

function Get-OutputField([string[]]$Lines, [string]$Name) {
    $line = $Lines | Where-Object { $_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Set-StateField([string]$Path, [string]$Name, [string]$Value) {
    $text = Get-Content -Raw -LiteralPath $Path
    $pattern = '(?m)^' + [regex]::Escape($Name) + '\s*=.*$'
    if ($text -match $pattern) { $text = [regex]::Replace($text, $pattern, "$Name = $Value") }
    else { $text = $text.TrimEnd() + "`r`n$Name = $Value`r`n" }
    Set-Content -LiteralPath $Path -Value $text -Encoding utf8
}
function Get-StateField([string]$Path, [string]$Name) {
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}

$cleanOutput = @(& (Join-Path $PSScriptRoot 'verify-clean.ps1') 2>&1)
$cleanCode = $LASTEXITCODE
$cleanOutput | Write-Output
if ($cleanCode -ne 0) { Write-Output 'PREPARE_TASK'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }

$nextOutput = @(& (Join-Path $PSScriptRoot 'next-task.ps1') 2>&1)
$nextCode = $LASTEXITCODE
$nextOutput | Write-Output
if ($nextCode -ne 0 -or (Get-OutputField $nextOutput 'FINAL') -ne 'PASS') {
    Write-Output 'PREPARE_TASK'; Write-Output 'FINAL = SAFETY_STOP'; exit 1
}

$taskId = Get-OutputField $nextOutput 'TASK_ID'
$level = Get-OutputField $nextOutput 'LEVEL'
$branch = Get-OutputField $nextOutput 'BRANCH'
$baseBranch = Get-OutputField $nextOutput 'BASE_BRANCH'
$prompt = Get-OutputField $nextOutput 'PROMPT'

Write-Output 'PREPARE_TASK'
if ($level -notin @('L1', 'L2', 'L3')) { Write-Output 'REASON = INVALID_LEVEL'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if ($level -eq 'L3' -and $env:APPROVED_L3 -ne 'YES') {
    Write-Output 'REASON = APPROVED_L3_REQUIRED'
    Write-Output 'FINAL = SAFETY_STOP'
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $prompt))) {
    Write-Output 'REASON = PROMPT_NOT_FOUND'
    Write-Output 'FINAL = SAFETY_STOP'
    exit 1
}
& git -C $repoRoot show-ref --verify --quiet ("refs/heads/{0}" -f $baseBranch)
if ($LASTEXITCODE -ne 0) { Write-Output 'REASON = LOCAL_BASE_BRANCH_NOT_FOUND'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
$statePath = Join-Path $repoRoot '.codex/PIPELINE_STATE.md'
$lastCompletedSha = Get-StateField $statePath 'LAST_COMPLETED_SHA'
if ($lastCompletedSha -and $lastCompletedSha -ne 'NONE') {
    & git -C $repoRoot merge-base --is-ancestor $lastCompletedSha $baseBranch
    if ($LASTEXITCODE -ne 0) { Write-Output 'REASON = LAST_COMPLETED_TASK_NOT_IN_BASE'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
}

& git -C $repoRoot show-ref --verify --quiet ("refs/heads/{0}" -f $branch)
$taskBranchExists = $LASTEXITCODE -eq 0
if ($taskBranchExists) {
    $baseSha = (& git -C $repoRoot rev-parse $baseBranch).Trim()
    $taskBranchSha = (& git -C $repoRoot rev-parse $branch).Trim()
    if ($baseSha -ne $taskBranchSha) { Write-Output 'REASON = TASK_BRANCH_HISTORY_UNEXPECTED'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
    & git -C $repoRoot switch $branch
} else {
    & git -C $repoRoot switch -c $branch $baseBranch
}
if ($LASTEXITCODE -ne 0) { Write-Output 'REASON = BRANCH_SWITCH_FAILED'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }

$startSha = (& git -C $repoRoot rev-parse HEAD).Trim()
$startedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$currentTask = @"
TASK_ID: $taskId
STATUS: PREPARED
LEVEL: $level
BRANCH: $branch
BASE_BRANCH: $baseBranch
PROMPT: $prompt
START_SHA: $startSha
ALLOWED_PATHS: .codex/CURRENT_TASK.md; .codex/PIPELINE_STATE.md; DECLARATION_REQUIRED
STARTED_AT: $startedAt
RESULT: NONE
"@
Set-Content -LiteralPath (Join-Path $repoRoot '.codex/CURRENT_TASK.md') -Value $currentTask -Encoding utf8
Set-StateField $statePath 'STATE' 'PREPARED'
Set-StateField $statePath 'CURRENT_TASK' $taskId
Set-StateField $statePath 'CURRENT_LEVEL' $level
Set-StateField $statePath 'CURRENT_BRANCH' $branch

Write-Output ("TASK_ID = {0}" -f $taskId)
Write-Output ("BRANCH = {0}" -f $branch)
Write-Output ("START_SHA = {0}" -f $startSha)
Write-Output 'ALLOWED_PATHS = DECLARATION_REQUIRED'
Write-Output 'FINAL = PREPARED'
