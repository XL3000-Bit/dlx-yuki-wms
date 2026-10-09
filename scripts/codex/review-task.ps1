[CmdletBinding()]
param([switch]$FullBackend)

$ErrorActionPreference = 'Continue'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$taskPath = Join-Path $repoRoot '.codex/CURRENT_TASK.md'
$statePath = Join-Path $repoRoot '.codex/PIPELINE_STATE.md'

function Get-TaskField([string]$Name) {
    $line = Get-Content -LiteralPath $taskPath | Where-Object { $_ -match ("^{0}:\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}:\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Get-ResultField([string[]]$Lines, [string]$Name) {
    $line = $Lines | Where-Object { $_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Set-ColonField([string]$Path, [string]$Name, [string]$Value) {
    $text = Get-Content -Raw -LiteralPath $Path
    $text = [regex]::Replace($text, ('(?m)^' + [regex]::Escape($Name) + ':.*$'), "$Name`: $Value")
    Set-Content -LiteralPath $Path -Value $text -Encoding utf8
}
function Set-EqualsField([string]$Path, [string]$Name, [string]$Value) {
    $text = Get-Content -Raw -LiteralPath $Path
    $text = [regex]::Replace($text, ('(?m)^' + [regex]::Escape($Name) + '\s*=.*$'), "$Name = $Value")
    Set-Content -LiteralPath $Path -Value $text -Encoding utf8
}

Write-Output 'REVIEW_TASK'
if (-not (Test-Path -LiteralPath $taskPath)) { Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
$taskId = Get-TaskField 'TASK_ID'
$expectedBranch = Get-TaskField 'BRANCH'
$baseBranch = Get-TaskField 'BASE_BRANCH'
$startSha = Get-TaskField 'START_SHA'
$promptPath = Get-TaskField 'PROMPT'
$actualBranch = (& git -C $repoRoot branch --show-current).Trim()
$headSha = (& git -C $repoRoot rev-parse HEAD).Trim()
$staged = @(& git -C $repoRoot diff --cached --name-only)
$changedPaths = @(& git -C $repoRoot status --porcelain=v1 --untracked-files=all | ForEach-Object { if ($_.Length -ge 4) { $_.Substring(3) } })
$gitSafetyFailed = $actualBranch -ne $expectedBranch -or $headSha -ne $startSha -or $staged.Count -gt 0
& git -C $repoRoot merge-base --is-ancestor $baseBranch $expectedBranch 2>$null
if ($LASTEXITCODE -ne 0) { $gitSafetyFailed = $true }
$gitDirRaw = (& git -C $repoRoot rev-parse --git-dir).Trim()
$gitDir = if ([IO.Path]::IsPathRooted($gitDirRaw)) { $gitDirRaw } else { Join-Path $repoRoot $gitDirRaw }
foreach ($marker in @('index.lock', 'MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'BISECT_LOG', 'rebase-apply', 'rebase-merge')) {
    if (Test-Path -LiteralPath (Join-Path $gitDir $marker)) { $gitSafetyFailed = $true }
}

if ($gitSafetyFailed) {
    Write-Output ("TASK_ID = {0}" -f $taskId)
    Write-Output ("BRANCH = {0}" -f $actualBranch)
    Write-Output ("START_SHA = {0}" -f $startSha)
    Write-Output ("CHANGED_PATH_COUNT = {0}" -f $changedPaths.Count)
    Write-Output 'SCOPE = NOT_RUN'
    Write-Output 'TESTS = NOT_RUN'
    Write-Output 'BUSINESS_GATE = NOT_RUN'
    Write-Output 'FINAL = SAFETY_STOP'
    exit 1
}

$scopeOutput = @(& (Join-Path $PSScriptRoot 'validate-scope.ps1') 2>&1)
$scopeCode = $LASTEXITCODE
$scopeOutput | Write-Output
$scopeResult = Get-ResultField $scopeOutput 'FINAL'
if ($scopeCode -ne 0 -or $scopeResult -ne 'PASS') {
    Write-Output ("TASK_ID = {0}" -f $taskId)
    Write-Output ("BRANCH = {0}" -f $actualBranch)
    Write-Output ("START_SHA = {0}" -f $startSha)
    Write-Output ("CHANGED_PATH_COUNT = {0}" -f $changedPaths.Count)
    Write-Output 'SCOPE = FAIL'
    Write-Output 'TESTS = NOT_RUN'
    Write-Output 'BUSINESS_GATE = NOT_RUN'
    Write-Output 'FINAL = SAFETY_STOP'
    exit 1
}
$testArgs = @{}
if ($FullBackend) { $testArgs['FullBackend'] = $true }
$testOutput = @(& (Join-Path $PSScriptRoot 'run-tests.ps1') @testArgs 2>&1)
$testCode = $LASTEXITCODE
$testOutput | Write-Output
$testResult = Get-ResultField $testOutput 'FINAL'

$businessResult = 'PASS'
$promptText = if (Test-Path -LiteralPath (Join-Path $repoRoot $promptPath)) { Get-Content -Raw -LiteralPath (Join-Path $repoRoot $promptPath) } else { '' }
$searchablePaths = @($changedPaths | ForEach-Object { $_.Trim('"').Replace('\', '/') } | Where-Object { ($_ -like 'frontend/*' -or $_ -like 'backend/*' -or $_ -like 'backend-java/*') -and (Test-Path -LiteralPath (Join-Path $repoRoot $_)) })
$changedText = ($searchablePaths | ForEach-Object { try { Get-Content -Raw -LiteralPath (Join-Path $repoRoot $_) -ErrorAction Stop } catch { '' } }) -join "`n"
if ($taskId -like 'OUTBOUND_SLICE_*') {
    if ($promptText -match '/api/v1/outbounds/workbench/batch' -and $changedText -notmatch '/api/v1/outbounds/workbench/batch') { $businessResult = 'FAIL' }
    if ($promptText -match 'dispatch-readiness' -and ($changedText -notmatch 'dispatch-readiness' -or $changedText -notmatch 'blocking_reasons')) { $businessResult = 'FAIL' }
    foreach ($token in @('results', 'status', 'reason', 'successful', 'failed')) {
        if ($promptText -match '/api/v1/outbounds/workbench/batch' -and $changedText -notmatch ("\b{0}\b" -f $token)) { $businessResult = 'FAIL' }
    }
}

$final = if ($gitSafetyFailed -or $scopeResult -eq 'SAFETY_STOP') { 'SAFETY_STOP' } elseif ($scopeCode -ne 0 -or $testCode -ne 0 -or $testResult -ne 'PASS' -or $businessResult -ne 'PASS') { 'FAIL' } else { 'READY_FOR_HUMAN_REVIEW' }
Set-ColonField $taskPath 'STATUS' $final
Set-ColonField $taskPath 'RESULT' $final
Set-EqualsField $statePath 'STATE' $final
Set-EqualsField $statePath 'LAST_RESULT' $final
Set-EqualsField $statePath 'LAST_REVIEW' $(if ($final -eq 'READY_FOR_HUMAN_REVIEW') { 'PASS' } else { $final })

Write-Output ("TASK_ID = {0}" -f $taskId)
Write-Output ("BRANCH = {0}" -f $actualBranch)
Write-Output ("START_SHA = {0}" -f $startSha)
Write-Output ("CHANGED_PATH_COUNT = {0}" -f $changedPaths.Count)
Write-Output ("SCOPE = {0}" -f $(if ($scopeResult -eq 'PASS') { 'PASS' } else { 'FAIL' }))
Write-Output ("TESTS = {0}" -f $(if ($testResult -eq 'PASS') { 'PASS' } else { 'FAIL' }))
Write-Output ("BUSINESS_GATE = {0}" -f $businessResult)
Write-Output ("FINAL = {0}" -f $final)
if ($final -ne 'READY_FOR_HUMAN_REVIEW') { exit 1 }
