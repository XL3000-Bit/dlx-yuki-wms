[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) {
    Write-Output 'VERIFY_CLEAN'
    Write-Output 'FINAL = FAIL'
    exit 1
}
$repoRoot = $repoRoot.Trim()

$branch = (& git -C $repoRoot symbolic-ref --quiet --short HEAD 2>$null)
$headSha = (& git -C $repoRoot rev-parse HEAD 2>$null)
$statusLines = @(& git -C $repoRoot status --porcelain=v1 --untracked-files=all)
$stagedPaths = @(& git -C $repoRoot diff --cached --name-only --diff-filter=ACDMRTUXB)
$gitDirRaw = (& git -C $repoRoot rev-parse --git-dir 2>$null).Trim()
$gitDir = if ([System.IO.Path]::IsPathRooted($gitDirRaw)) { $gitDirRaw } else { Join-Path $repoRoot $gitDirRaw }

$operationMarkers = @('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'BISECT_LOG')
$operationActive = $false
foreach ($marker in $operationMarkers) {
    if (Test-Path -LiteralPath (Join-Path $gitDir $marker)) { $operationActive = $true }
}
foreach ($directory in @('rebase-apply', 'rebase-merge')) {
    if (Test-Path -LiteralPath (Join-Path $gitDir $directory)) { $operationActive = $true }
}
$indexLocked = Test-Path -LiteralPath (Join-Path $gitDir 'index.lock')
$detached = [string]::IsNullOrWhiteSpace(($branch -join ''))
$dirty = $statusLines.Count -gt 0
$failed = $dirty -or ($stagedPaths.Count -gt 0) -or $operationActive -or $indexLocked -or $detached

Write-Output 'VERIFY_CLEAN'
Write-Output ("BRANCH = {0}" -f $(if ($detached) { 'DETACHED' } else { ($branch -join '').Trim() }))
Write-Output ("HEAD = {0}" -f ($headSha -join '').Trim())
Write-Output ("WORKTREE = {0}" -f $(if ($dirty) { 'DIRTY' } else { 'CLEAN' }))
Write-Output ("STAGED = {0}" -f $stagedPaths.Count)
Write-Output ("GIT_OPERATION_ACTIVE = {0}" -f $(if ($operationActive) { 'YES' } else { 'NO' }))
Write-Output ("INDEX_LOCK = {0}" -f $(if ($indexLocked) { 'YES' } else { 'NO' }))
Write-Output ("FINAL = {0}" -f $(if ($failed) { 'FAIL' } else { 'PASS' }))

if ($failed) { exit 1 }
