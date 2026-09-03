[CmdletBinding()]
param([switch]$ApproveCommit)

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$taskPath = Join-Path $repoRoot '.codex/CURRENT_TASK.md'
$statePath = Join-Path $repoRoot '.codex/PIPELINE_STATE.md'

function Get-TaskField([string]$Name) {
    $line = Get-Content -LiteralPath $taskPath | Where-Object { $_ -match ("^{0}:\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}:\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Set-Field([string]$Path, [string]$Name, [string]$Value) {
    $text = Get-Content -Raw -LiteralPath $Path
    $text = [regex]::Replace($text, ('(?m)^' + [regex]::Escape($Name) + '\s*=.*$'), "$Name = $Value")
    Set-Content -LiteralPath $Path -Value $text -Encoding utf8
}

Write-Output 'FINISH_TASK'
$result = Get-TaskField 'RESULT'
$taskId = Get-TaskField 'TASK_ID'
$branch = Get-TaskField 'BRANCH'
if ($result -ne 'READY_FOR_HUMAN_REVIEW') {
    Write-Output ("REVIEW_RESULT = {0}" -f $result)
    Write-Output 'FINAL = REFUSED_REVIEW_NOT_READY'
    exit 1
}
if (-not $ApproveCommit) {
    Write-Output 'FINAL = HUMAN_APPROVAL_REQUIRED'
    exit 0
}

Set-Field $statePath 'STATE' 'READY_FOR_COMMIT'
$paths = @(& git -C $repoRoot status --porcelain=v1 --untracked-files=all | ForEach-Object { if ($_.Length -ge 4) { $_.Substring(3).Trim('"') } } | Sort-Object -Unique)
$quotedPaths = @($paths | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ' '
Write-Output 'PIPELINE_STATE = READY_FOR_COMMIT'
Write-Output 'RECOMMENDED_GIT_COMMANDS_BEGIN'
Write-Output ("git add -- {0}" -f $quotedPaths)
Write-Output ("git commit -m 'feat(yuki): complete {0}'" -f $taskId.ToLowerInvariant().Replace('_', '-'))
Write-Output ("git push -u origin '{0}'" -f $branch)
Write-Output 'RECOMMENDED_GIT_COMMANDS_END'
Write-Output 'AUTO_COMMIT = NO'
Write-Output 'AUTO_PUSH = NO'
Write-Output 'FINAL = READY_FOR_COMMIT'
