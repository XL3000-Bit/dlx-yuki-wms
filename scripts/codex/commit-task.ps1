[CmdletBinding()]
param(
    [switch]$ValidationOnly,
    [string]$TaskPath,
    [string]$StatePath,
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim() }
if (-not $TaskPath) { $TaskPath = Join-Path $RepoRoot '.codex/CURRENT_TASK.md' }
if (-not $StatePath) { $StatePath = Join-Path $RepoRoot '.codex/PIPELINE_STATE.md' }

function Get-ColonField([string]$Name) {
    $line = Get-Content -LiteralPath $TaskPath | Where-Object { $_ -match ("^{0}:\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}:\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Get-StateField([string]$Name) {
    $line = Get-Content -LiteralPath $StatePath | Where-Object { $_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Set-StateField([string]$Name, [string]$Value) {
    $text = Get-Content -Raw -LiteralPath $StatePath
    $pattern = '(?m)^' + [regex]::Escape($Name) + '\s*=.*$'
    if ($text -match $pattern) { $text = [regex]::Replace($text, $pattern, "$Name = $Value") }
    else { $text = $text.TrimEnd() + "`r`n$Name = $Value`r`n" }
    Set-Content -LiteralPath $StatePath -Value $text -Encoding utf8
}
function Get-ChangedPaths {
    $paths = @()
    $paths += @(& git -C $RepoRoot diff --name-only --diff-filter=ACDMRTUXB)
    $paths += @(& git -C $RepoRoot diff --cached --name-only --diff-filter=ACDMRTUXB)
    $paths += @(& git -C $RepoRoot ls-files --others --exclude-standard)
    return @($paths | ForEach-Object { $_.Replace('\', '/') } | Where-Object { $_ } | Sort-Object -Unique)
}

Write-Output 'COMMIT_TASK'
$state = Get-StateField 'STATE'
$approval = Get-StateField 'AUTO_APPROVAL'
$expectedBranch = Get-ColonField 'BRANCH'
$commitMessage = Get-ColonField 'COMMIT_MESSAGE'
$actualBranch = (& git -C $RepoRoot branch --show-current).Trim()
if ($state -ne 'READY_FOR_COMMIT') { Write-Output 'REASON = PIPELINE_NOT_READY_FOR_COMMIT'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if ($approval -ne 'PASS') { Write-Output 'REASON = AUTO_APPROVAL_NOT_GRANTED'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if (-not $expectedBranch -or $actualBranch -ne $expectedBranch) { Write-Output 'REASON = BRANCH_MISMATCH'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if (-not $commitMessage -or $commitMessage -eq 'NONE') { Write-Output 'REASON = COMMIT_MESSAGE_REQUIRED'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
if ($ValidationOnly) { Write-Output 'FINAL = VALIDATION_PASS'; exit 0 }

$stagedBefore = @(& git -C $RepoRoot diff --cached --name-only)
if ($stagedBefore.Count -gt 0) { Write-Output 'REASON = PREEXISTING_STAGED_PATHS'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
$scopeOutput = @(& (Join-Path $PSScriptRoot 'validate-scope.ps1') 2>&1)
$scopeCode = $LASTEXITCODE
$scopeOutput | Write-Output
if ($scopeCode -ne 0 -or ($scopeOutput -notcontains 'FINAL = PASS')) { Write-Output 'FINAL = SAFETY_STOP'; exit 1 }

Set-StateField 'STATE' 'COMPLETE_PENDING_INTEGRATION'
Set-StateField 'PENDING_PARENT_INTEGRATION' 'YES'
Set-StateField 'LAST_COMMIT' 'CURRENT_TASK_COMMIT'
Set-StateField 'LAST_PUSH' $expectedBranch
$changedPaths = @(Get-ChangedPaths)
if ($changedPaths.Count -eq 0) { Write-Output 'REASON = NO_CHANGED_PATHS'; Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
& git -C $RepoRoot add -- @changedPaths
if ($LASTEXITCODE -ne 0) { Write-Output 'REASON = EXACT_PATH_STAGE_FAILED'; Write-Output 'FINAL = FAIL'; exit 1 }
& git -C $RepoRoot commit -m $commitMessage
if ($LASTEXITCODE -ne 0) { Write-Output 'REASON = COMMIT_FAILED'; Write-Output 'FINAL = FAIL'; exit 1 }
$commitSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
if (@(& git -C $RepoRoot status --porcelain=v1 --untracked-files=all).Count -gt 0) {
    Write-Output 'REASON = WORKTREE_NOT_CLEAN_AFTER_COMMIT'; Write-Output 'FINAL = SAFETY_STOP'; exit 1
}

& git -C $RepoRoot rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>$null | Out-Null
$hasUpstream = $LASTEXITCODE -eq 0
if ($hasUpstream) { & git -C $RepoRoot push } else { & git -C $RepoRoot push -u origin $expectedBranch }
if ($LASTEXITCODE -ne 0) { Write-Output 'REASON = PUSH_FAILED'; Write-Output 'FINAL = FAIL'; exit 1 }
Write-Output ("LAST_COMMIT = {0}" -f $commitSha)
Write-Output ("LAST_PUSH = {0}" -f $expectedBranch)
Write-Output 'PENDING_PARENT_INTEGRATION = YES'
Write-Output 'FINAL = COMPLETE_PENDING_INTEGRATION'
