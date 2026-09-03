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
function Invoke-IsolatedExpectedFailure([string]$Script, [string[]]$Arguments) {
    if ($PSVersionTable.PSEdition -eq 'Core') {
        $childPowerShell = (Get-Command pwsh -CommandType Application -ErrorAction Stop).Source
    } else {
        $childPowerShell = Join-Path $PSHOME 'powershell.exe'
    }
    if (-not (Test-Path -LiteralPath $childPowerShell -PathType Leaf)) {
        throw "PowerShell child executable was not found: $childPowerShell"
    }

    $tempRoot = Join-Path $env:TEMP ("yuki-v16-expected-failure-{0}" -f [guid]::NewGuid())
    $stdoutPath = Join-Path $tempRoot 'stdout.txt'
    $stderrPath = Join-Path $tempRoot 'stderr.txt'
    $process = $null
    try {
        [void](New-Item -ItemType Directory -Path $tempRoot)
        $childArguments = @(
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy', 'Bypass',
            '-File', ('"{0}"' -f $Script.Replace('"', '\"'))
        ) + $Arguments
        $process = Start-Process -FilePath $childPowerShell -ArgumentList $childArguments `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru -Wait
        if ($null -eq $process) { throw 'Expected-failure child process did not start.' }

        $process.WaitForExit()
        $process.Refresh()
        if (-not $process.HasExited) { throw 'Expected-failure child process did not exit.' }
        if ($null -eq $process.ExitCode) { throw 'Expected-failure child process did not expose an exit code.' }

        $exitCode = [int]$process.ExitCode
        $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { '' }
        $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { '' }
        $combinedOutput = @($stdout, $stderr) -join "`n"
        if ($exitCode -eq 0) { throw 'Expected-failure child process unexpectedly succeeded.' }

        return [pscustomobject]@{
            ProcessStarted = $true
            ExitCode = $exitCode
            StdOut = $stdout
            StdErr = $stderr
            CombinedOutput = $combinedOutput
            Code = $exitCode
            Text = $combinedOutput
        }
    } finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
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
Assert-True ($status.Code -eq 0) 'STATUS_EXIT_CODE_ZERO'
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
Assert-True ($dryRun.Code -eq 0) 'DRYRUN_EXIT_CODE_ZERO'
Assert-True ($dryRunStatusAfter -ceq $dryRunStatusBefore) 'DryRun leaves the worktree path set unchanged'
Assert-True ($dryRunTaskHashAfter -ceq $dryRunTaskHashBefore) 'DryRun leaves CURRENT_TASK unchanged'
Assert-True ($dryRunStateHashAfter -ceq $dryRunStateHashBefore) 'DryRun leaves PIPELINE_STATE unchanged'
$pipelineStateText = Get-Content -LiteralPath (Join-Path $repoRoot '.codex/PIPELINE_STATE.md') -Raw
$easyFreightCounterMatches = [regex]::Matches($pipelineStateText, '(?m)^EASYFREIGHT_WRITES\s*=\s*0\s*$')
Assert-True ($easyFreightCounterMatches.Count -eq 1) 'Pipeline state has one unambiguous zero EasyFreight write counter'
$invalidStatePaths = @(
    '.codex/CURRENT_TASK.md',
    '.codex/PIPELINE_STATE.md',
    '.codex/TASK_QUEUE.md',
    '.codex/DONE.md'
)
$invalidStateHashesBefore = @{}
foreach ($relativePath in $invalidStatePaths) {
    $fullPath = Join-Path $repoRoot $relativePath
    $invalidStateHashesBefore[$relativePath] = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash
}
$invalidLockPath = (& git -C $repoRoot rev-parse --git-path yuki-autopilot.lock).Trim()
if (-not [IO.Path]::IsPathRooted($invalidLockPath)) { $invalidLockPath = Join-Path $repoRoot $invalidLockPath }
Assert-True (-not (Test-Path -LiteralPath $invalidLockPath)) 'INVALID_INVOCATION_LOCK_STARTS_ABSENT'
$invalidAutoStatusBefore = (& git -C $repoRoot status --porcelain=v1 --untracked-files=all 2>&1 | Out-String)
$invalidAuto = Invoke-IsolatedExpectedFailure $autopilot @('-Status', '-AutoApprove')
$invalidAutoStatusAfter = (& git -C $repoRoot status --porcelain=v1 --untracked-files=all 2>&1 | Out-String)
$invalidStateHashesAfter = @{}
foreach ($relativePath in $invalidStatePaths) {
    $fullPath = Join-Path $repoRoot $relativePath
    $invalidStateHashesAfter[$relativePath] = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash
}
$invalidStateUnchanged = @($invalidStatePaths | Where-Object {
    $invalidStateHashesBefore[$_] -cne $invalidStateHashesAfter[$_]
}).Count -eq 0
Assert-True $invalidAuto.ProcessStarted 'EXPECTED_FAILURE_PROCESS_STARTED'
Assert-True ($null -ne $invalidAuto.ExitCode) 'EXPECTED_FAILURE_HAS_EXIT_CODE'
Assert-True ($invalidAuto.ExitCode -ne 0) 'EXPECTED_FAILURE_EXIT_CODE_NONZERO'
Assert-True ($invalidAuto.CombinedOutput.Contains('FINAL = REFUSED_AUTOAPPROVE_REQUIRES_RUN')) 'EXPECTED_REFUSAL_MARKER_FOUND'
Assert-True ($invalidAuto.ExitCode -ne 0 -and $invalidAuto.CombinedOutput.Contains('FINAL = REFUSED_AUTOAPPROVE_REQUIRES_RUN')) 'AUTOAPPROVE_WITHOUT_RUN_REFUSED'
Assert-True ($invalidAutoStatusAfter -ceq $invalidAutoStatusBefore -and $invalidStateUnchanged) 'INVALID_INVOCATION_STATE_UNCHANGED'
Assert-True (-not (Test-Path -LiteralPath $invalidLockPath)) 'INVALID_INVOCATION_LOCK_NOT_CREATED'

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
    $result = Invoke-IsolatedExpectedFailure $autoApprove $argsCopy.ToArray()
    Assert-True ($result.Code -ne 0 -and $result.Text -match 'REFUSED') $Name
}
Test-GateRefusal 'L3_AUTO_APPROVAL_REFUSED' '-Level' 'L3'
Test-GateRefusal 'SCOPE_FAIL_CLOSED' '-Scope' 'FAIL'
Test-GateRefusal 'TEST_FAIL_CLOSED' '-Tests' 'FAIL'
Test-GateRefusal 'DB_FAIL_CLOSED' '-DatabaseConnections' '1'
Test-GateRefusal 'MIGRATION_FAIL_CLOSED' '-MigrationFilesChanged' 'YES'
Test-GateRefusal 'PDA change refuses auto-approval' '-PdaFilesChanged' 'YES'

$gitLockPath = (& git -C $repoRoot rev-parse --git-path yuki-autopilot.lock).Trim()
if (-not [IO.Path]::IsPathRooted($gitLockPath)) { $gitLockPath = Join-Path $repoRoot $gitLockPath }
Assert-True (-not (Test-Path -LiteralPath $gitLockPath)) 'run lock starts absent'
$ownedTestLock = $false
try {
    [IO.File]::WriteAllText($gitLockPath, 'synthetic self-test lock')
    $ownedTestLock = $true
    $lockedRun = Invoke-IsolatedExpectedFailure $autopilot @('-Run')
    Assert-True ($lockedRun.Code -ne 0 -and $lockedRun.Text -match 'SAFETY_STOP_AUTOPILOT_ALREADY_RUNNING') 'RUN_LOCK'
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
    $missingCommit = Invoke-IsolatedExpectedFailure (Join-Path $scriptsRoot 'commit-task.ps1') @('-ValidationOnly', '-TaskPath', $tempTask, '-StatePath', $tempState, '-RepoRoot', $repoRoot)
    Assert-True ($missingCommit.Code -ne 0 -and $missingCommit.Text -match 'COMMIT_MESSAGE_REQUIRED') 'MISSING_COMMIT_MESSAGE_REFUSED'
} finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
}

$commitSource = Get-Content -Raw -LiteralPath (Join-Path $scriptsRoot 'commit-task.ps1')
$autopilotSource = Get-Content -Raw -LiteralPath $autopilot
Assert-True ($commitSource -notmatch '(?im)git\s+[^\r\n]*add\s+(?:\.\s*$|-A\b|--all\b)') 'commit path never stages all changes'
Assert-True ($commitSource -notmatch '(?im)git\s+[^\r\n]*(?:merge|rebase|pull|push\s+[^\r\n]*--force)\b') 'PARENT_NOT_AUTO_INTEGRATED'
Assert-True (@([regex]::Matches($autopilotSource, "'commit-task\.ps1'" )).Count -eq 1) '-Run can invoke commit only once'
Assert-True ($autopilotSource -notmatch '(?im)^\s*(?:while|do)\b') 'NEXT_TASK_NOT_STARTED'
Assert-True ($autopilotSource -match 'CreateNew' -and $autopilotSource -match 'lockOwned') 'per-worktree lock is ownership guarded'
Assert-True ($autopilotSource -match 'SAFETY_STOP_AUTOPILOT_ALREADY_RUNNING') 'concurrent run uses the required safety stop'

$workingChanges = @(& git -C $repoRoot status --porcelain=v1 --untracked-files=all)
$stagedChanges = @(& git -C $repoRoot diff --cached --name-only)
$authorizedInfrastructurePaths = @(
    '.codex/AGENTS.md',
    '.codex/PIPELINE_STATE.md',
    '.codex/REVIEW_GATE.md',
    'docs/YUKI_AUTOPILOT.md',
    'scripts/codex/auto-approve-task.ps1',
    'scripts/codex/commit-task.ps1',
    'scripts/codex/finish-task.ps1',
    'scripts/codex/invoke-codex.ps1',
    'scripts/codex/run-current-task.ps1',
    'scripts/codex/tests/yuki-autopilot-v1.6.tests.ps1',
    'scripts/codex/yuki-autopilot.ps1'
)
$changedPaths = @($workingChanges | ForEach-Object {
    if ($_.Length -ge 4) { $_.Substring(3).Trim() } else { $_ }
})
$unauthorizedChanges = @($changedPaths | Where-Object { $authorizedInfrastructurePaths -notcontains $_ })
Assert-True ($stagedChanges.Count -eq 0) 'tests leave staged paths at zero'
Assert-True (($workingChanges.Count -eq 0) -or ($unauthorizedChanges.Count -eq 0)) 'CLEAN_COMMITTED_CONTEXT_SUPPORTED'
Assert-True ($unauthorizedChanges.Count -eq 0) 'DIRTY_AUTHORIZED_CONTEXT_SUPPORTED'

Write-Output 'REAL_BUSINESS_TASK_EXECUTED = NO'
Write-Output 'REAL_COMMIT_PERFORMED_BY_TEST = NO'
Write-Output 'REAL_PUSH_PERFORMED_BY_TEST = NO'

if ($failures.Count -gt 0) {
    Write-Output ("FAILURES = {0}" -f ($failures -join '; '))
    Write-Output 'FINAL = FAIL'
    exit 1
}
Write-Output 'FINAL = PASS'
