[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$scriptsRoot = Join-Path $repoRoot 'scripts/codex'
$pwsh = (Get-Process -Id $PID).Path
$failures = [Collections.Generic.List[string]]::new()

function Assert-True([bool]$Condition, [string]$Name) {
    if ($Condition) { Write-Output "PASS = $Name" } else { $failures.Add($Name); Write-Output "FAIL = $Name" }
}
function Invoke-Isolated([string]$Script, [string[]]$Arguments) {
    $output = @(& $pwsh -NoLogo -NoProfile -File $Script @Arguments 2>&1)
    return [pscustomobject]@{ Code = $LASTEXITCODE; Text = ($output -join "`n") }
}

Write-Output 'YUKI_AUTOPILOT_V1_6_TESTS'

$parseErrors = @()
Get-ChildItem -LiteralPath $scriptsRoot -Filter '*.ps1' -Recurse | ForEach-Object {
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    $parseErrors += $errors
}
Assert-True ($parseErrors.Count -eq 0) 'all PowerShell scripts parse'

$autopilot = Join-Path $scriptsRoot 'yuki-autopilot.ps1'
$parameters = (Get-Command $autopilot).Parameters.Keys
Assert-True ($parameters -contains 'Run' -and $parameters -contains 'AutoApprove' -and $parameters -contains 'DryRun') '-Run, -AutoApprove, and -DryRun parse'

$status = Invoke-Isolated $autopilot @('-Status')
Assert-True ($status.Code -eq 0 -and $status.Text -match 'AUTOPILOT_VERSION = V1_6_AUTO_APPROVE' -and
    $status.Text -match 'AUTOPILOT_RUNNING = NO' -and $status.Text -match 'CURRENT_TASK_LEVEL =' -and
    $status.Text -match 'READY_FOR_COMMIT =' -and $status.Text -match 'PENDING_PARENT_INTEGRATION =') '-Status reports V1.6 state'
$next = Invoke-Isolated $autopilot @('-Next')
Assert-True ($next.Code -eq 0 -and $next.Text -match 'NEXT_TASK') '-Next succeeds'
$dryRunStatusBefore = (& git -C $repoRoot status --porcelain=v1 --untracked-files=all 2>&1 | Out-String)
$dryRunTaskHashBefore = (Get-FileHash -LiteralPath (Join-Path $repoRoot '.codex/CURRENT_TASK.md') -Algorithm SHA256).Hash
$dryRunStateHashBefore = (Get-FileHash -LiteralPath (Join-Path $repoRoot '.codex/PIPELINE_STATE.md') -Algorithm SHA256).Hash
$dryRun = Invoke-Isolated $autopilot @('-DryRun')
$dryRunStatusAfter = (& git -C $repoRoot status --porcelain=v1 --untracked-files=all 2>&1 | Out-String)
$dryRunTaskHashAfter = (Get-FileHash -LiteralPath (Join-Path $repoRoot '.codex/CURRENT_TASK.md') -Algorithm SHA256).Hash
$dryRunStateHashAfter = (Get-FileHash -LiteralPath (Join-Path $repoRoot '.codex/PIPELINE_STATE.md') -Algorithm SHA256).Hash
Assert-True ($dryRun.Code -eq 0 -and $dryRun.Text -match 'MUTATIONS = 0' -and $dryRun.Text -match 'CODEX_CLI_VERSION' -and
    $dryRun.Text -match 'BASE_BRANCH =' -and $dryRun.Text -match 'ALLOWED_PATHS =') '-DryRun detects without mutation'
Assert-True ($dryRunStatusAfter -ceq $dryRunStatusBefore) 'DryRun leaves the worktree path set unchanged'
Assert-True ($dryRunTaskHashAfter -ceq $dryRunTaskHashBefore) 'DryRun leaves CURRENT_TASK unchanged'
Assert-True ($dryRunStateHashAfter -ceq $dryRunStateHashBefore) 'DryRun leaves PIPELINE_STATE unchanged'
$pipelineStateText = Get-Content -LiteralPath (Join-Path $repoRoot '.codex/PIPELINE_STATE.md') -Raw
$easyFreightCounterMatches = [regex]::Matches($pipelineStateText, '(?m)^EASYFREIGHT_WRITES\s*=\s*0\s*$')
Assert-True ($easyFreightCounterMatches.Count -eq 1) 'Pipeline state has one unambiguous zero EasyFreight write counter'
$invalidAuto = Invoke-Isolated $autopilot @('-Status', '-AutoApprove')
Assert-True ($invalidAuto.Code -ne 0 -and $invalidAuto.Text -match 'valid only with -Run') '-AutoApprove is rejected outside -Run'

$autoApprove = Join-Path $scriptsRoot 'auto-approve-task.ps1'
$passArgs = @(
    '-EvaluateOnly', '-Level', 'L2', '-ReviewResult', 'READY_FOR_HUMAN_REVIEW',
    '-Scope', 'PASS', '-Tests', 'PASS', '-BusinessGate', 'PASS', '-GitDiffCheck', 'PASS',
    '-UnauthorizedPaths', '0', '-ProtectedPathsChanged', '0', '-StagedPaths', '0',
    '-DatabaseConnections', '0', '-DatabaseWrites', '0', '-MigrationFilesChanged', 'NO',
    '-PdaFilesChanged', 'NO', '-EasyFreightWrites', '0'
)
$gatePass = Invoke-Isolated $autoApprove $passArgs
Assert-True ($gatePass.Code -eq 0 -and $gatePass.Text -match 'FINAL = READY_FOR_COMMIT') 'L2 all-pass auto-approval succeeds'

function Test-GateRefusal([string]$Name, [string]$Parameter, [string]$Value) {
    $argsCopy = [Collections.Generic.List[string]]::new()
    foreach ($item in $passArgs) { $argsCopy.Add($item) }
    $index = $argsCopy.IndexOf($Parameter)
    if ($index -ge 0) { $argsCopy[$index + 1] = $Value }
    $result = Invoke-Isolated $autoApprove $argsCopy.ToArray()
    Assert-True ($result.Code -ne 0 -and $result.Text -match 'REFUSED') $Name
}
Test-GateRefusal 'L3 auto-approval is refused' '-Level' 'L3'
Test-GateRefusal 'scope failure refuses auto-approval' '-Scope' 'FAIL'
Test-GateRefusal 'test failure refuses auto-approval' '-Tests' 'FAIL'
Test-GateRefusal 'database activity refuses auto-approval' '-DatabaseConnections' '1'
Test-GateRefusal 'migration change refuses auto-approval' '-MigrationFilesChanged' 'YES'
Test-GateRefusal 'PDA change refuses auto-approval' '-PdaFilesChanged' 'YES'

$gitLockPath = (& git -C $repoRoot rev-parse --git-path yuki-autopilot.lock).Trim()
if (-not [IO.Path]::IsPathRooted($gitLockPath)) { $gitLockPath = Join-Path $repoRoot $gitLockPath }
Assert-True (-not (Test-Path -LiteralPath $gitLockPath)) 'run lock starts absent'
$ownedTestLock = $false
try {
    [IO.File]::WriteAllText($gitLockPath, 'synthetic self-test lock')
    $ownedTestLock = $true
    $lockedRun = Invoke-Isolated $autopilot @('-Run')
    Assert-True ($lockedRun.Code -ne 0 -and $lockedRun.Text -match 'SAFETY_STOP_AUTOPILOT_ALREADY_RUNNING') 'pre-existing run lock refuses -Run'
    Assert-True (Test-Path -LiteralPath $gitLockPath) 'pre-existing run lock is not auto-deleted'
} finally {
    if ($ownedTestLock -and (Test-Path -LiteralPath $gitLockPath)) { Remove-Item -LiteralPath $gitLockPath -Force }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("yuki-v16-test-{0}" -f [guid]::NewGuid())
New-Item -ItemType Directory -Path $tempRoot | Out-Null
try {
    $branch = (& git -C $repoRoot branch --show-current).Trim()
    $tempTask = Join-Path $tempRoot 'CURRENT_TASK.md'
    $tempState = Join-Path $tempRoot 'PIPELINE_STATE.md'
    Set-Content -LiteralPath $tempTask -Encoding utf8 -Value @("TASK_ID: SYNTHETIC", "BRANCH: $branch", 'COMMIT_MESSAGE: NONE')
    Set-Content -LiteralPath $tempState -Encoding utf8 -Value @('STATE = READY_FOR_COMMIT', 'AUTO_APPROVAL = PASS')
    $missingCommit = Invoke-Isolated (Join-Path $scriptsRoot 'commit-task.ps1') @('-ValidationOnly', '-TaskPath', $tempTask, '-StatePath', $tempState, '-RepoRoot', $repoRoot)
    Assert-True ($missingCommit.Code -ne 0 -and $missingCommit.Text -match 'COMMIT_MESSAGE_REQUIRED') 'missing commit message stops safely'
} finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
}

$commitSource = Get-Content -Raw -LiteralPath (Join-Path $scriptsRoot 'commit-task.ps1')
$autopilotSource = Get-Content -Raw -LiteralPath $autopilot
Assert-True ($commitSource -notmatch '(?im)git\s+[^\r\n]*add\s+(?:\.\s*$|-A\b|--all\b)') 'commit path never stages all changes'
Assert-True ($commitSource -notmatch '(?im)git\s+[^\r\n]*(?:merge|rebase|pull|push\s+[^\r\n]*--force)\b') 'commit path has no integration or force-push command'
Assert-True (@([regex]::Matches($autopilotSource, "'commit-task\.ps1'" )).Count -eq 1) '-Run can invoke commit only once'
Assert-True ($autopilotSource -notmatch '(?im)^\s*(?:while|do)\b') '-Run has no task loop'
Assert-True ($autopilotSource -match 'CreateNew' -and $autopilotSource -match 'lockOwned') 'per-worktree lock is ownership guarded'
Assert-True ($autopilotSource -match 'SAFETY_STOP_AUTOPILOT_ALREADY_RUNNING') 'concurrent run uses the required safety stop'

$workingChanges = @(& git -C $repoRoot status --porcelain=v1 --untracked-files=all)
$stagedChanges = @(& git -C $repoRoot diff --cached --name-only)
Assert-True ($stagedChanges.Count -eq 0) 'tests leave staged paths at zero'
Assert-True ($workingChanges.Count -gt 0) 'upgrade changes remain uncommitted'

if ($failures.Count -gt 0) {
    Write-Output ("FAILURES = {0}" -f ($failures -join '; '))
    Write-Output 'FINAL = FAIL'
    exit 1
}
Write-Output 'FINAL = PASS'
