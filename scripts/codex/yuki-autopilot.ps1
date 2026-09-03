[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Prepare,
    [switch]$Review,
    [switch]$Finish,
    [switch]$Next,
    [switch]$Run,
    [switch]$DryRun,
    [switch]$AutoApprove,
    [switch]$ApproveCommit,
    [switch]$FullBackend
)

$ErrorActionPreference = 'Stop'
if ($AutoApprove -and -not $Run) {
    Write-Output 'FINAL = REFUSED_AUTOAPPROVE_REQUIRES_RUN'
    throw '-AutoApprove is valid only with -Run.'
}
$modes = @($Status, $Prepare, $Review, $Finish, $Next, $Run, $DryRun) | Where-Object { [bool]$_ }
if ($modes.Count -ne 1) {
    throw 'Specify exactly one mode: -Status, -Prepare, -Review, -Finish, -Next, -Run, or -DryRun.'
}

$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$taskPath = Join-Path $repoRoot '.codex/CURRENT_TASK.md'
$statePath = Join-Path $repoRoot '.codex/PIPELINE_STATE.md'
$gitLockPath = (& git -C $repoRoot rev-parse --git-path yuki-autopilot.lock).Trim()
if (-not [IO.Path]::IsPathRooted($gitLockPath)) { $gitLockPath = Join-Path $repoRoot $gitLockPath }

function Get-ColonField([string]$Path, [string]$Name) {
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match ("^{0}:\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}:\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Get-StateField([string]$Name) {
    $line = Get-Content -LiteralPath $statePath | Where-Object { $_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Get-OutputField([object[]]$Lines, [string]$Name) {
    $line = $Lines | Where-Object { [string]$_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($null -ne $line) { return (([string]$line) -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Get-NextTaskOutput {
    $lines = @(& (Join-Path $PSScriptRoot 'next-task.ps1') 2>&1)
    return [pscustomobject]@{ Code = $LASTEXITCODE; Lines = $lines }
}
function Write-CodexDetection {
    & (Join-Path $PSScriptRoot 'invoke-codex.ps1') -DetectOnly
}

if ($Status) {
    Write-Output 'YUKI_AUTOPILOT_STATUS'
    $taskLevel = Get-ColonField $taskPath 'LEVEL'
    $taskStatus = Get-ColonField $taskPath 'STATUS'
    $pipelineState = Get-StateField 'STATE'
    Write-Output ("AUTOPILOT_VERSION = {0}" -f $(if (Get-StateField 'AUTOPILOT_VERSION') { Get-StateField 'AUTOPILOT_VERSION' } else { 'V1_6_AUTO_APPROVE' }))
    Write-Output ("AUTOPILOT_RUNNING = {0}" -f $(if (Test-Path -LiteralPath $gitLockPath) { 'YES' } else { 'NO' }))
    Write-CodexDetection
    Write-Output ("CURRENT_TASK = {0}" -f $(if (Get-ColonField $taskPath 'TASK_ID') { Get-ColonField $taskPath 'TASK_ID' } else { 'NONE' }))
    Write-Output ("CURRENT_TASK_LEVEL = {0}" -f $(if ($taskLevel) { $taskLevel } else { 'NONE' }))
    Write-Output ("CURRENT_TASK_STATUS = {0}" -f $(if ($taskStatus) { $taskStatus } else { $pipelineState }))
    Write-Output ("CURRENT_BRANCH = {0}" -f (& git -C $repoRoot branch --show-current).Trim())
    Write-Output ("REVIEW_RESULT = {0}" -f $(if (Get-StateField 'REVIEW_RESULT') { Get-StateField 'REVIEW_RESULT' } else { 'NONE' }))
    Write-Output ("AUTO_APPROVE_ENABLED = {0}" -f $(if ($taskLevel -in @('L1', 'L2')) { 'YES' } else { 'NO' }))
    Write-Output ("READY_FOR_COMMIT = {0}" -f $(if ($pipelineState -eq 'READY_FOR_COMMIT') { 'YES' } else { 'NO' }))
    Write-Output ("LAST_COMMIT = {0}" -f $(if (Get-StateField 'LAST_COMMIT') { Get-StateField 'LAST_COMMIT' } else { 'NONE' }))
    Write-Output ("LAST_PUSH = {0}" -f $(if (Get-StateField 'LAST_PUSH') { Get-StateField 'LAST_PUSH' } else { 'NONE' }))
    Write-Output ("PENDING_PARENT_INTEGRATION = {0}" -f $(if (Get-StateField 'PENDING_PARENT_INTEGRATION') { Get-StateField 'PENDING_PARENT_INTEGRATION' } else { 'NO' }))
    exit 0
}
if ($Next) { & (Join-Path $PSScriptRoot 'next-task.ps1'); exit $LASTEXITCODE }
if ($Prepare) { & (Join-Path $PSScriptRoot 'prepare-task.ps1'); exit $LASTEXITCODE }
if ($Review) { & (Join-Path $PSScriptRoot 'review-task.ps1') -FullBackend:$FullBackend; exit $LASTEXITCODE }
if ($Finish) { & (Join-Path $PSScriptRoot 'finish-task.ps1') -ApproveCommit:$ApproveCommit; exit $LASTEXITCODE }

if ($DryRun) {
    $taskId = Get-ColonField $taskPath 'TASK_ID'
    $level = Get-ColonField $taskPath 'LEVEL'
    $branch = Get-ColonField $taskPath 'BRANCH'
    $baseBranch = Get-ColonField $taskPath 'BASE_BRANCH'
    $prompt = Get-ColonField $taskPath 'PROMPT'
    $allowedPaths = Get-ColonField $taskPath 'ALLOWED_PATHS'
    $commitMessage = Get-ColonField $taskPath 'COMMIT_MESSAGE'
    $wouldPrepare = -not $taskId -or $taskId -eq 'NONE'
    $nextResult = Get-NextTaskOutput
    $nextOutput = $nextResult.Lines
    $queueTaskId = Get-OutputField $nextOutput 'TASK_ID'
    $queueAllowedPaths = Get-OutputField $nextOutput 'ALLOWED_PATHS'
    $queueAllowedPathCount = Get-OutputField $nextOutput 'ALLOWED_PATH_COUNT'
    $queueCommitMessage = Get-OutputField $nextOutput 'COMMIT_MESSAGE'
    $metadataComplete = Get-OutputField $nextOutput 'TASK_METADATA_COMPLETE'
    $final = Get-OutputField $nextOutput 'FINAL'
    $metadataDrift = $false
    if ($wouldPrepare) {
        $taskId = $queueTaskId
        $level = Get-OutputField $nextOutput 'LEVEL'
        $branch = Get-OutputField $nextOutput 'BRANCH'
        $baseBranch = Get-OutputField $nextOutput 'BASE_BRANCH'
        $prompt = Get-OutputField $nextOutput 'PROMPT'
        $allowedPaths = $queueAllowedPaths
        $commitMessage = $queueCommitMessage
    } elseif ($nextResult.Code -eq 0 -and $final -eq 'PASS' -and $metadataComplete -eq 'PASS') {
        $metadataDrift = $taskId -cne $queueTaskId -or
            $allowedPaths -cne $queueAllowedPaths -or
            $commitMessage -cne $queueCommitMessage
    }
    $metadataValid = $nextResult.Code -eq 0 -and $final -eq 'PASS' -and $metadataComplete -eq 'PASS' -and -not $metadataDrift
    $allowedPathCount = if ($wouldPrepare) { $queueAllowedPathCount } elseif ($allowedPaths) {
        @($allowedPaths -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ }).Count
    } else { 0 }
    $canAutoApprove = $metadataValid -and $level -in @('L1', 'L2')
    Write-Output 'YUKI_AUTOPILOT_DRY_RUN'
    Write-Output ("TASK_ID = {0}" -f $(if ($taskId) { $taskId } else { 'NONE' }))
    Write-Output ("LEVEL = {0}" -f $(if ($level) { $level } else { 'UNKNOWN' }))
    Write-Output ("BRANCH = {0}" -f $(if ($branch) { $branch } else { 'UNKNOWN' }))
    Write-Output ("BASE_BRANCH = {0}" -f $(if ($baseBranch) { $baseBranch } else { 'UNKNOWN' }))
    Write-Output ("PROMPT = {0}" -f $(if ($prompt) { $prompt } else { 'UNKNOWN' }))
    Write-Output ("ALLOWED_PATH_COUNT = {0}" -f $allowedPathCount)
    Write-Output ("ALLOWED_PATHS = {0}" -f $(if ($allowedPaths) { $allowedPaths } else { 'UNKNOWN' }))
    Write-Output ("COMMIT_MESSAGE = {0}" -f $(if ($commitMessage) { $commitMessage } else { 'UNKNOWN' }))
    Write-Output ("TASK_METADATA_COMPLETE = {0}" -f $(if ($metadataValid) { 'PASS' } else { 'FAIL' }))
    Write-Output ("WOULD_PREPARE = {0}" -f $(if ($wouldPrepare) { 'YES' } else { 'NO' }))
    Write-Output ("WOULD_INVOKE_CODEX = {0}" -f $(if ($metadataValid) { 'YES' } else { 'NO' }))
    Write-Output ("WOULD_AUTO_APPROVE = {0}" -f $(if ($canAutoApprove) { 'YES' } else { 'NO' }))
    Write-Output ("WOULD_COMMIT = {0}" -f $(if ($canAutoApprove) { 'YES' } else { 'NO' }))
    Write-Output ("WOULD_PUSH = {0}" -f $(if ($canAutoApprove) { 'YES' } else { 'NO' }))
    Write-CodexDetection
    Write-Output 'MUTATIONS = 0'
    if ($metadataDrift) {
        Write-Output 'FINAL = SAFETY_STOP_TASK_METADATA_DRIFT'
        exit 1
    }
    if (-not $metadataValid) {
        foreach ($missing in @('ALLOWED_PATHS', 'COMMIT_MESSAGE')) {
            if (-not (Get-OutputField $nextOutput $missing)) { Write-Output ("MISSING_FIELD = {0}" -f $missing) }
        }
        Write-Output 'FINAL = SAFETY_STOP_TASK_METADATA_INCOMPLETE'
        exit 1
    }
    Write-Output 'FINAL = DRY_RUN_COMPLETE'
    exit 0
}

$lockStream = $null
$lockOwned = $false
try {
    if (Test-Path -LiteralPath $gitLockPath) {
        Write-Output 'FINAL = SAFETY_STOP_AUTOPILOT_ALREADY_RUNNING'
        exit 1
    }
    try {
        $lockStream = [IO.File]::Open($gitLockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        $lockOwned = $true
    } catch [IO.IOException] {
        Write-Output 'FINAL = SAFETY_STOP_AUTOPILOT_ALREADY_RUNNING'
        exit 1
    }

    Write-Output 'YUKI_AUTOPILOT_RUN'
    if ((Get-ColonField $taskPath 'TASK_ID') -eq 'NONE') {
        & (Join-Path $PSScriptRoot 'prepare-task.ps1')
        if ($LASTEXITCODE -ne 0) { Write-Output 'FINAL = FAIL_PREPARE'; exit $LASTEXITCODE }
    }

    & (Join-Path $PSScriptRoot 'run-current-task.ps1') -FullBackend:$FullBackend
    if ($LASTEXITCODE -ne 0) { Write-Output 'FINAL = FAIL_RUN_CURRENT_TASK'; exit $LASTEXITCODE }

    if (-not $AutoApprove) {
        Write-Output 'FINAL = READY_FOR_HUMAN_REVIEW'
        exit 0
    }

    $level = Get-ColonField $taskPath 'LEVEL'
    if ($level -eq 'L3') {
        Write-Output 'AUTO_APPROVAL = REFUSED_L3_AUTO_APPROVAL'
        Write-Output 'FINAL = READY_FOR_HUMAN_REVIEW'
        exit 0
    }

    & (Join-Path $PSScriptRoot 'auto-approve-task.ps1')
    if ($LASTEXITCODE -ne 0) { Write-Output 'FINAL = FAIL_AUTO_APPROVAL'; exit $LASTEXITCODE }

    & (Join-Path $PSScriptRoot 'commit-task.ps1')
    if ($LASTEXITCODE -ne 0) { Write-Output 'FINAL = FAIL_COMMIT_OR_PUSH'; exit $LASTEXITCODE }

    Write-Output 'FINAL = COMPLETE_PENDING_INTEGRATION'
} finally {
    if ($lockStream) { $lockStream.Dispose() }
    if ($lockOwned -and (Test-Path -LiteralPath $gitLockPath)) {
        Remove-Item -LiteralPath $gitLockPath -Force
    }
}
