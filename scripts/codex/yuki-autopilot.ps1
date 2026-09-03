[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Prepare,
    [switch]$Review,
    [switch]$Finish,
    [switch]$Next,
    [switch]$ApproveCommit,
    [switch]$FullBackend
)

$ErrorActionPreference = 'Stop'
$modes = @($Status, $Prepare, $Review, $Finish, $Next) | Where-Object { $_ }
if ($modes.Count -ne 1) { throw 'Specify exactly one mode: -Status, -Prepare, -Review, -Finish, or -Next.' }
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()

if ($Status) {
    Write-Output 'YUKI_AUTOPILOT_STATUS'
    Write-Output '--- PIPELINE_STATE ---'
    Get-Content -LiteralPath (Join-Path $repoRoot '.codex/PIPELINE_STATE.md')
    Write-Output '--- CURRENT_TASK ---'
    Get-Content -LiteralPath (Join-Path $repoRoot '.codex/CURRENT_TASK.md')
    Write-Output '--- NEXT_READY_TASK ---'
    & (Join-Path $PSScriptRoot 'next-task.ps1')
    Write-Output '--- GIT ---'
    Write-Output ("BRANCH = {0}" -f (& git -C $repoRoot branch --show-current).Trim())
    Write-Output ("HEAD = {0}" -f (& git -C $repoRoot rev-parse HEAD).Trim())
    & git -C $repoRoot status --short --untracked-files=all
    exit 0
}
if ($Next) { & (Join-Path $PSScriptRoot 'next-task.ps1'); exit $LASTEXITCODE }
if ($Prepare) { & (Join-Path $PSScriptRoot 'prepare-task.ps1'); exit $LASTEXITCODE }
if ($Review) { & (Join-Path $PSScriptRoot 'review-task.ps1') -FullBackend:$FullBackend; exit $LASTEXITCODE }
if ($Finish) { & (Join-Path $PSScriptRoot 'finish-task.ps1') -ApproveCommit:$ApproveCommit; exit $LASTEXITCODE }
