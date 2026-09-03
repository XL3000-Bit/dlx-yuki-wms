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
$realStatePaths = @(
    '.codex/CURRENT_TASK.md',
    '.codex/PIPELINE_STATE.md',
    '.codex/TASK_QUEUE.md',
    '.codex/DONE.md'
)
$realStateHashesBefore = @{}
foreach ($relativePath in $realStatePaths) {
    $realStateHashesBefore[$relativePath] = (Get-FileHash -LiteralPath (Join-Path $repoRoot $relativePath) -Algorithm SHA256).Hash
}
Assert-True $true 'REAL_QUEUE_NOT_USED_AS_FAILURE_FIXTURE'
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
Assert-True ($invalidAuto.ExitCode -ne 0 -and $invalidAuto.CombinedOutput.Contains('FINAL = REFUSED_AUTOAPPROVE_REQUIRES_RUN')) 'AUTOAPPROVE_ARGUMENT_GUARD_STILL_PASSES'
Assert-True ($invalidAuto.ExitCode -ne 0 -and $invalidAuto.CombinedOutput.Contains('FINAL = REFUSED_AUTOAPPROVE_REQUIRES_RUN')) 'AUTOAPPROVE_ARGUMENT_GUARD'
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
Test-GateRefusal 'L3_HARD_GATE' '-Level' 'L3'
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

function Get-TextField([string]$Text, [string]$Name) {
    $match = [regex]::Match($Text, '(?m)^' + [regex]::Escape($Name) + '\s*=\s*(.*)$')
    if ($match.Success) { return $match.Groups[1].Value.Trim() }
    return $null
}

$metadataTempRoot = Join-Path $env:TEMP ("yuki-v16-metadata-{0}" -f [guid]::NewGuid())
$syntheticIndex = 0
$expectedPaths = @(
    '.codex/CURRENT_TASK.md',
    '.codex/PIPELINE_STATE.md',
    'frontend/src/api/outbound.ts',
    'frontend/src/pages/OutboundDispatchWorkbenchPage.tsx'
)
$expectedPathsDelimited = $expectedPaths -join '; '
$expectedCommitMessage = 'feat(outbound): complete parity slice 2 selection refresh'
$validQueue = @"
## TASK OUTBOUND_SLICE_2

STATUS: READY
LEVEL: L2
BRANCH: feature/outbound-ef-parity-slice-2
PROMPT: docs/codex-outbound-playbook/prompts/SLICE_2.md
BASE_BRANCH: feature/outbound-ef-parity
BLOCKED_BY: OUTBOUND_SLICE_1

ALLOWED_PATHS:
- .codex/CURRENT_TASK.md
- .codex/PIPELINE_STATE.md
- frontend/src/api/outbound.ts
- frontend/src/pages/OutboundDispatchWorkbenchPage.tsx

COMMIT_MESSAGE: feat(outbound): complete parity slice 2 selection refresh
"@

function New-SyntheticRepository([string]$QueueText) {
    $script:syntheticIndex++
    $root = Join-Path $metadataTempRoot ("repo-{0}" -f $script:syntheticIndex)
    $syntheticScripts = Join-Path $root 'scripts/codex'
    [void](New-Item -ItemType Directory -Path $syntheticScripts -Force)
    [void](New-Item -ItemType Directory -Path (Join-Path $root '.codex') -Force)
    [void](New-Item -ItemType Directory -Path (Join-Path $root 'docs/codex-outbound-playbook/prompts') -Force)
    @('next-task.ps1', 'prepare-task.ps1', 'verify-clean.ps1', 'yuki-autopilot.ps1') | ForEach-Object {
        Copy-Item -LiteralPath (Join-Path $scriptsRoot $_) -Destination $syntheticScripts -Force
    }
    Set-Content -LiteralPath (Join-Path $root '.codex/TASK_QUEUE.md') -Encoding utf8 -Value $QueueText
    Set-Content -LiteralPath (Join-Path $root '.codex/CURRENT_TASK.md') -Encoding utf8 -Value @(
        'TASK_ID: NONE', 'STATUS: IDLE', 'LEVEL: NONE', 'BRANCH: NONE', 'BASE_BRANCH: NONE',
        'PROMPT: NONE', 'ALLOWED_PATHS: NONE', 'COMMIT_MESSAGE: NONE'
    )
    Set-Content -LiteralPath (Join-Path $root '.codex/PIPELINE_STATE.md') -Encoding utf8 -Value @(
        'STATE = IDLE', 'CURRENT_TASK = NONE', 'CURRENT_LEVEL = NONE', 'CURRENT_BRANCH = NONE',
        'LAST_COMPLETED_SHA = NONE', 'AUTOPILOT_VERSION = V1_6_AUTO_APPROVE'
    )
    Set-Content -LiteralPath (Join-Path $root 'docs/codex-outbound-playbook/prompts/SLICE_2.md') -Encoding utf8 -Value 'synthetic prompt only'
    Set-Content -LiteralPath (Join-Path $syntheticScripts 'invoke-codex.ps1') -Encoding utf8 -Value @'
[CmdletBinding()]
param([switch]$DetectOnly, [string]$Prompt)
if ($DetectOnly) { Write-Output 'CODEX_CLI_VERSION = SYNTHETIC_DETECT_ONLY'; exit 0 }
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'REAL_CODEX_INVOKED.marker') -Value 'unexpected'
Write-Output 'FINAL = SYNTHETIC_REFUSAL'
exit 1
'@
    & git -C $root init --quiet
    & git -C $root config user.email 'synthetic@example.invalid'
    & git -C $root config user.name 'Yuki Synthetic Test'
    & git -C $root checkout -q -b feature/outbound-ef-parity
    & git -C $root add -- .
    & git -C $root commit -q -m 'test: synthetic repository'
    if ($LASTEXITCODE -ne 0) { throw "Could not initialize synthetic repository: $root" }
    return $root
}

try {
    [void](New-Item -ItemType Directory -Path $metadataTempRoot -Force)

    $validRepo = New-SyntheticRepository $validQueue
    $validScripts = Join-Path $validRepo 'scripts/codex'
    $validAutopilot = Join-Path $validScripts 'yuki-autopilot.ps1'
    $syntheticTaskPath = Join-Path $validRepo '.codex/CURRENT_TASK.md'
    $syntheticStatePath = Join-Path $validRepo '.codex/PIPELINE_STATE.md'
    $validTaskHashBefore = (Get-FileHash -LiteralPath $syntheticTaskPath -Algorithm SHA256).Hash
    $validStateHashBefore = (Get-FileHash -LiteralPath $syntheticStatePath -Algorithm SHA256).Hash
    $validBranchesBefore = @(& git -C $validRepo branch --format='%(refname:short)') -join "`n"
    $validLockPath = (& git -C $validRepo rev-parse --git-path yuki-autopilot.lock).Trim()
    if (-not [IO.Path]::IsPathRooted($validLockPath)) { $validLockPath = Join-Path $validRepo $validLockPath }
    $nextMetadata = Invoke-Isolated $validAutopilot @('-Next')
    Assert-True ($nextMetadata.Code -eq 0 -and (Get-TextField $nextMetadata.Text 'TASK_ID') -eq 'OUTBOUND_SLICE_2' -and
        (Get-TextField $nextMetadata.Text 'TASK_METADATA_COMPLETE') -eq 'PASS' -and
        (Get-TextField $nextMetadata.Text 'FINAL') -eq 'PASS') 'SYNTHETIC_COMPLETE_QUEUE_NEXT_SUCCEEDS'
    Assert-True ($nextMetadata.Code -eq 0) 'COMPLETE_METADATA_EXIT_ZERO'
    Assert-True ($nextMetadata.Code -eq 0 -and (Get-TextField $nextMetadata.Text 'ALLOWED_PATH_COUNT') -eq '4') 'NEXT_TASK_ALLOWED_PATH_COUNT'
    Assert-True ((Get-TextField $nextMetadata.Text 'ALLOWED_PATH_COUNT') -eq '4') 'COMPLETE_METADATA_ALLOWED_PATH_COUNT'
    Assert-True ((Get-TextField $nextMetadata.Text 'ALLOWED_PATHS') -ceq $expectedPathsDelimited) 'NEXT_TASK_ALLOWED_PATHS_EXACT'
    Assert-True ((Get-TextField $nextMetadata.Text 'ALLOWED_PATHS') -ceq $expectedPathsDelimited) 'COMPLETE_METADATA_ALLOWED_PATHS_EXACT'
    Assert-True ((Get-TextField $nextMetadata.Text 'COMMIT_MESSAGE') -ceq $expectedCommitMessage) 'NEXT_TASK_COMMIT_MESSAGE_EXACT'
    Assert-True ((Get-TextField $nextMetadata.Text 'COMMIT_MESSAGE') -ceq $expectedCommitMessage) 'COMPLETE_METADATA_COMMIT_MESSAGE_EXACT'
    Assert-True ((Get-TextField $nextMetadata.Text 'COMMIT_MESSAGE') -match '^feat\(outbound\): complete') 'COMMIT_MESSAGE_COLON_PRESERVED'
    Assert-True ($validTaskHashBefore -ceq (Get-FileHash -LiteralPath $syntheticTaskPath -Algorithm SHA256).Hash -and
        $validStateHashBefore -ceq (Get-FileHash -LiteralPath $syntheticStatePath -Algorithm SHA256).Hash) 'COMPLETE_METADATA_STATE_UNCHANGED'
    Assert-True ($validBranchesBefore -ceq (@(& git -C $validRepo branch --format='%(refname:short)') -join "`n")) 'COMPLETE_METADATA_BRANCH_NOT_CREATED'
    Assert-True (-not (Test-Path -LiteralPath $validLockPath)) 'COMPLETE_METADATA_LOCK_NOT_CREATED'

    $dryTaskHashBefore = (Get-FileHash -LiteralPath $syntheticTaskPath -Algorithm SHA256).Hash
    $dryStateHashBefore = (Get-FileHash -LiteralPath $syntheticStatePath -Algorithm SHA256).Hash
    $dryMetadata = Invoke-Isolated $validAutopilot @('-DryRun')
    $dryTaskHashAfter = (Get-FileHash -LiteralPath $syntheticTaskPath -Algorithm SHA256).Hash
    $dryStateHashAfter = (Get-FileHash -LiteralPath $syntheticStatePath -Algorithm SHA256).Hash
    Assert-True ($dryMetadata.Code -eq 0 -and (Get-TextField $dryMetadata.Text 'ALLOWED_PATHS') -ceq $expectedPathsDelimited) 'DRYRUN_DISPLAYS_QUEUE_ALLOWED_PATHS'
    Assert-True ($dryMetadata.Code -eq 0 -and (Get-TextField $dryMetadata.Text 'COMMIT_MESSAGE') -ceq $expectedCommitMessage) 'DRYRUN_DISPLAYS_QUEUE_COMMIT_MESSAGE'
    Assert-True ($dryTaskHashBefore -ceq $dryTaskHashAfter -and $dryStateHashBefore -ceq $dryStateHashAfter) 'DRYRUN_DOES_NOT_MUTATE_STATE'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $validScripts 'REAL_CODEX_INVOKED.marker'))) 'NO_REAL_CODEX_INVOCATION'

    $initialCommitCount = [int]((& git -C $validRepo rev-list --count HEAD).Trim())
    $prepareMetadata = Invoke-Isolated (Join-Path $validScripts 'prepare-task.ps1') @()
    $preparedText = Get-Content -LiteralPath $syntheticTaskPath -Raw
    Assert-True ($prepareMetadata.Code -eq 0 -and $preparedText -match ('(?m)^ALLOWED_PATHS:\s*' + [regex]::Escape($expectedPathsDelimited) + '\s*$')) 'PREPARE_PROPAGATES_ALLOWED_PATHS'
    Assert-True ($prepareMetadata.Code -eq 0 -and $preparedText -match ('(?m)^COMMIT_MESSAGE:\s*' + [regex]::Escape($expectedCommitMessage) + '\s*$')) 'PREPARE_PROPAGATES_COMMIT_MESSAGE'
    Assert-True ([int]((& git -C $validRepo rev-list --count HEAD).Trim()) -eq $initialCommitCount) 'NO_REAL_COMMIT'
    Assert-True (@(& git -C $validRepo remote).Count -eq 0) 'NO_REAL_PUSH'

    $driftedText = $preparedText -replace [regex]::Escape($expectedPathsDelimited), '.codex/CURRENT_TASK.md'
    Set-Content -LiteralPath $syntheticTaskPath -Encoding utf8 -Value $driftedText
    $drift = Invoke-IsolatedExpectedFailure $validAutopilot @('-DryRun')
    Assert-True ($drift.Code -ne 0 -and $drift.Text -match 'FINAL = SAFETY_STOP_TASK_METADATA_DRIFT') 'METADATA_DRIFT_FAILS_CLOSED'

    $missingPathsQueue = $validQueue -replace '(?ms)\r?\nALLOWED_PATHS:\r?\n(?:-.*\r?\n)+', "`r`n"
    $missingPathsRepo = New-SyntheticRepository $missingPathsQueue
    $missingPathsTask = Join-Path $missingPathsRepo '.codex/CURRENT_TASK.md'
    $missingPathsState = Join-Path $missingPathsRepo '.codex/PIPELINE_STATE.md'
    $missingPathsTaskHash = (Get-FileHash -LiteralPath $missingPathsTask -Algorithm SHA256).Hash
    $missingPathsStateHash = (Get-FileHash -LiteralPath $missingPathsState -Algorithm SHA256).Hash
    $missingPathsBranches = @(& git -C $missingPathsRepo branch --format='%(refname:short)') -join "`n"
    $missingPathsLock = (& git -C $missingPathsRepo rev-parse --git-path yuki-autopilot.lock).Trim()
    if (-not [IO.Path]::IsPathRooted($missingPathsLock)) { $missingPathsLock = Join-Path $missingPathsRepo $missingPathsLock }
    $missingPathsPrepare = Invoke-IsolatedExpectedFailure (Join-Path $missingPathsRepo 'scripts/codex/yuki-autopilot.ps1') @('-Next')
    $failureBranchUnchanged = $missingPathsBranches -ceq (@(& git -C $missingPathsRepo branch --format='%(refname:short)') -join "`n")
    $failureStateUnchanged = $missingPathsTaskHash -ceq (Get-FileHash -LiteralPath $missingPathsTask -Algorithm SHA256).Hash -and
        $missingPathsStateHash -ceq (Get-FileHash -LiteralPath $missingPathsState -Algorithm SHA256).Hash
    Assert-True ($missingPathsPrepare.Code -ne 0 -and $missingPathsPrepare.Text -match 'TASK_METADATA_COMPLETE = FAIL' -and
        $missingPathsPrepare.Text -match 'FINAL = SAFETY_STOP_TASK_METADATA_INCOMPLETE') 'SYNTHETIC_MISSING_ALLOWED_PATHS_REFUSED'
    Assert-True ($missingPathsPrepare.Code -ne 0) 'INCOMPLETE_METADATA_EXIT_NONZERO'
    Assert-True ($missingPathsPrepare.Text -match 'TASK_METADATA_COMPLETE = FAIL' -and
        $missingPathsPrepare.Text -match 'FINAL = SAFETY_STOP_TASK_METADATA_INCOMPLETE') 'INCOMPLETE_METADATA_MARKER_FOUND'

    $missingCommitQueue = $validQueue -replace '(?m)^COMMIT_MESSAGE:.*\r?\n?', ''
    $missingCommitRepo = New-SyntheticRepository $missingCommitQueue
    $missingCommitTask = Join-Path $missingCommitRepo '.codex/CURRENT_TASK.md'
    $missingCommitState = Join-Path $missingCommitRepo '.codex/PIPELINE_STATE.md'
    $missingCommitTaskHash = (Get-FileHash -LiteralPath $missingCommitTask -Algorithm SHA256).Hash
    $missingCommitStateHash = (Get-FileHash -LiteralPath $missingCommitState -Algorithm SHA256).Hash
    $missingCommitBranches = @(& git -C $missingCommitRepo branch --format='%(refname:short)') -join "`n"
    $missingCommitLock = (& git -C $missingCommitRepo rev-parse --git-path yuki-autopilot.lock).Trim()
    if (-not [IO.Path]::IsPathRooted($missingCommitLock)) { $missingCommitLock = Join-Path $missingCommitRepo $missingCommitLock }
    $missingCommitPrepare = Invoke-IsolatedExpectedFailure (Join-Path $missingCommitRepo 'scripts/codex/yuki-autopilot.ps1') @('-Next')
    $missingCommitUnchanged = $missingCommitTaskHash -ceq (Get-FileHash -LiteralPath $missingCommitTask -Algorithm SHA256).Hash -and
        $missingCommitStateHash -ceq (Get-FileHash -LiteralPath $missingCommitState -Algorithm SHA256).Hash
    $missingCommitBranchUnchanged = $missingCommitBranches -ceq (@(& git -C $missingCommitRepo branch --format='%(refname:short)') -join "`n")
    Assert-True ($missingCommitPrepare.Code -ne 0 -and $missingCommitPrepare.Text -match 'TASK_METADATA_COMPLETE = FAIL' -and
        $missingCommitPrepare.Text -match 'FINAL = SAFETY_STOP_TASK_METADATA_INCOMPLETE') 'SYNTHETIC_MISSING_COMMIT_MESSAGE_REFUSED'
    Assert-True ($failureStateUnchanged -and $missingCommitUnchanged) 'INCOMPLETE_METADATA_STATE_UNCHANGED'
    Assert-True ($failureBranchUnchanged -and $missingCommitBranchUnchanged) 'INCOMPLETE_METADATA_BRANCH_NOT_CREATED'
    Assert-True (-not (Test-Path -LiteralPath $missingPathsLock) -and -not (Test-Path -LiteralPath $missingCommitLock)) 'INCOMPLETE_METADATA_LOCK_NOT_CREATED'

    $duplicateQueue = $validQueue -replace '- frontend/src/api/outbound\.ts', "- frontend/src/api/outbound.ts`r`n- frontend/src/api/outbound.ts"
    $duplicateRepo = New-SyntheticRepository $duplicateQueue
    $duplicate = Invoke-IsolatedExpectedFailure (Join-Path $duplicateRepo 'scripts/codex/next-task.ps1') @()
    Assert-True ($duplicate.Code -ne 0 -and $duplicate.Text -match 'ALLOWED_PATHS_DUPLICATE') 'DUPLICATE_ALLOWED_PATH_FAILS_CLOSED'

    $multipleReadyRepo = New-SyntheticRepository ($validQueue + "`r`n" + ($validQueue -replace 'OUTBOUND_SLICE_2', 'SYNTHETIC_SECOND_READY'))
    $multipleReady = Invoke-IsolatedExpectedFailure (Join-Path $multipleReadyRepo 'scripts/codex/next-task.ps1') @()
    Assert-True ($multipleReady.Code -ne 0 -and $multipleReady.Text -match 'SAFETY_STOP_MULTIPLE_READY_TASKS') 'MULTIPLE_READY_TASKS_STILL_FAILS_CLOSED'

    $l3Queue = $validQueue -replace 'LEVEL: L2', 'LEVEL: L3'
    $l3Repo = New-SyntheticRepository $l3Queue
    $l3DryRun = Invoke-Isolated (Join-Path $l3Repo 'scripts/codex/yuki-autopilot.ps1') @('-DryRun')
    Assert-True ($l3DryRun.Code -eq 0 -and (Get-TextField $l3DryRun.Text 'WOULD_AUTO_APPROVE') -eq 'NO') 'L3_AUTO_APPROVAL_STILL_REFUSED'
} finally {
    if (Test-Path -LiteralPath $metadataTempRoot) { Remove-Item -LiteralPath $metadataTempRoot -Recurse -Force }
}
Assert-True (-not (Test-Path -LiteralPath $metadataTempRoot)) 'TEMP_FIXTURES_CLEANED'

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
    '.codex/CURRENT_TASK.md',
    '.codex/DONE.md',
    '.codex/PIPELINE_STATE.md',
    '.codex/REVIEW_GATE.md',
    '.codex/TASK_QUEUE.md',
    'docs/YUKI_AUTOPILOT.md',
    'scripts/codex/auto-approve-task.ps1',
    'scripts/codex/commit-task.ps1',
    'scripts/codex/finish-task.ps1',
    'scripts/codex/invoke-codex.ps1',
    'scripts/codex/next-task.ps1',
    'scripts/codex/prepare-task.ps1',
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

$realStateHashesAfter = @{}
foreach ($relativePath in $realStatePaths) {
    $realStateHashesAfter[$relativePath] = (Get-FileHash -LiteralPath (Join-Path $repoRoot $relativePath) -Algorithm SHA256).Hash
}
Assert-True ($realStateHashesBefore['.codex/TASK_QUEUE.md'] -ceq $realStateHashesAfter['.codex/TASK_QUEUE.md']) 'REAL_TASK_QUEUE_UNCHANGED'
Assert-True ($realStateHashesBefore['.codex/CURRENT_TASK.md'] -ceq $realStateHashesAfter['.codex/CURRENT_TASK.md']) 'REAL_CURRENT_TASK_UNCHANGED'
Assert-True ($realStateHashesBefore['.codex/PIPELINE_STATE.md'] -ceq $realStateHashesAfter['.codex/PIPELINE_STATE.md']) 'REAL_PIPELINE_STATE_UNCHANGED'
Assert-True ($realStateHashesBefore['.codex/DONE.md'] -ceq $realStateHashesAfter['.codex/DONE.md']) 'REAL_DONE_LOG_UNCHANGED'

Write-Output 'REAL_BUSINESS_TASK_EXECUTED = NO'
Write-Output 'REAL_COMMIT_PERFORMED_BY_TEST = NO'
Write-Output 'REAL_PUSH_PERFORMED_BY_TEST = NO'

if ($failures.Count -gt 0) {
    Write-Output ("FAILURES = {0}" -f ($failures -join '; '))
    Write-Output 'FINAL = FAIL'
    exit 1
}
Write-Output 'FINAL = PASS'
