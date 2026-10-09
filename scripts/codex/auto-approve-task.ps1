[CmdletBinding()]
param(
    [string]$Level,
    [string]$ReviewResult,
    [string]$Scope,
    [string]$Tests,
    [string]$BusinessGate,
    [string]$GitDiffCheck,
    [string]$UnauthorizedPaths,
    [string]$ProtectedPathsChanged,
    [string]$StagedPaths,
    [string]$DatabaseConnections,
    [string]$DatabaseWrites,
    [string]$MigrationFilesChanged,
    [string]$PdaFilesChanged,
    [string]$EasyFreightWrites,
    [switch]$EvaluateOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$taskPath = Join-Path $repoRoot '.codex/CURRENT_TASK.md'
$statePath = Join-Path $repoRoot '.codex/PIPELINE_STATE.md'
$suppliedParameterNames = @($PSBoundParameters.Keys)

function Get-ColonField([string]$Name) {
    $line = Get-Content -LiteralPath $taskPath | Where-Object { $_ -match ("^{0}:\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}:\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Get-StateField([string]$Name) {
    $line = Get-Content -LiteralPath $statePath | Where-Object { $_ -match ("^{0}\s*=\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}\s*=\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Set-StateField([string]$Name, [string]$Value) {
    $text = Get-Content -Raw -LiteralPath $statePath
    $pattern = '(?m)^' + [regex]::Escape($Name) + '\s*=.*$'
    if ($text -match $pattern) { $text = [regex]::Replace($text, $pattern, "$Name = $Value") }
    else { $text = $text.TrimEnd() + "`r`n$Name = $Value`r`n" }
    Set-Content -LiteralPath $statePath -Value $text -Encoding utf8
}
function Resolve-Value([string]$Provided, [string]$ParameterName, [string]$StateName) {
    if ($suppliedParameterNames -contains $ParameterName) { return $Provided }
    return Get-StateField $StateName
}

Write-Output 'AUTO_APPROVE_TASK'
if ($suppliedParameterNames -notcontains 'Level') { $Level = Get-ColonField 'LEVEL' }
$ReviewResult = Resolve-Value $ReviewResult 'ReviewResult' 'REVIEW_RESULT'
$Scope = Resolve-Value $Scope 'Scope' 'SCOPE'
$Tests = Resolve-Value $Tests 'Tests' 'TESTS'
$BusinessGate = Resolve-Value $BusinessGate 'BusinessGate' 'BUSINESS_GATE'
$GitDiffCheck = Resolve-Value $GitDiffCheck 'GitDiffCheck' 'GIT_DIFF_CHECK'
$UnauthorizedPaths = Resolve-Value $UnauthorizedPaths 'UnauthorizedPaths' 'UNAUTHORIZED_PATHS'
$ProtectedPathsChanged = Resolve-Value $ProtectedPathsChanged 'ProtectedPathsChanged' 'PROTECTED_PATHS_CHANGED'
$StagedPaths = Resolve-Value $StagedPaths 'StagedPaths' 'STAGED_PATHS'
$DatabaseConnections = Resolve-Value $DatabaseConnections 'DatabaseConnections' 'DATABASE_CONNECTIONS'
$DatabaseWrites = Resolve-Value $DatabaseWrites 'DatabaseWrites' 'DATABASE_WRITES'
$MigrationFilesChanged = Resolve-Value $MigrationFilesChanged 'MigrationFilesChanged' 'MIGRATION_FILES_CHANGED'
$PdaFilesChanged = Resolve-Value $PdaFilesChanged 'PdaFilesChanged' 'PDA_FILES_CHANGED'
$EasyFreightWrites = Resolve-Value $EasyFreightWrites 'EasyFreightWrites' 'EASYFREIGHT_WRITES'

if (-not $EvaluateOnly) {
    $StagedPaths = [string]@(& git -C $repoRoot diff --cached --name-only).Count
    & git -C $repoRoot diff --check
    $GitDiffCheck = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }
    $changedPaths = @(& git -C $repoRoot status --porcelain=v1 --untracked-files=all | ForEach-Object { $_.Substring(3) })
    $MigrationFilesChanged = if (@($changedPaths | Where-Object { $_ -match '(^|/)(migrations?|alembic)(/|$)' }).Count) { 'YES' } else { 'NO' }
    $PdaFilesChanged = if (@($changedPaths | Where-Object { $_ -match '(^|/)[^/]*(pda|scan)[^/]*($|/)' }).Count) { 'YES' } else { 'NO' }
}

$values = [ordered]@{
    LEVEL = $Level
    REVIEW_RESULT = $ReviewResult
    SCOPE = $Scope
    TESTS = $Tests
    BUSINESS_GATE = $BusinessGate
    GIT_DIFF_CHECK = $GitDiffCheck
    UNAUTHORIZED_PATHS = $UnauthorizedPaths
    PROTECTED_PATHS_CHANGED = $ProtectedPathsChanged
    STAGED_PATHS = $StagedPaths
    DATABASE_CONNECTIONS = $DatabaseConnections
    DATABASE_WRITES = $DatabaseWrites
    MIGRATION_FILES_CHANGED = $MigrationFilesChanged
    PDA_FILES_CHANGED = $PdaFilesChanged
    EASYFREIGHT_WRITES = $EasyFreightWrites
}
$values.GetEnumerator() | ForEach-Object { Write-Output ("{0} = {1}" -f $_.Key, $_.Value) }

if ($Level -eq 'L3') { Write-Output 'FINAL = REFUSED_L3_AUTO_APPROVAL'; exit 1 }
$requiredPass = @($Scope, $Tests, $BusinessGate, $GitDiffCheck)
$requiredZero = @($UnauthorizedPaths, $ProtectedPathsChanged, $StagedPaths, $DatabaseConnections, $DatabaseWrites, $EasyFreightWrites)
$failed = $Level -notin @('L1', 'L2') -or
    $ReviewResult -ne 'READY_FOR_HUMAN_REVIEW' -or
    @($requiredPass | Where-Object { $_ -ne 'PASS' }).Count -gt 0 -or
    @($requiredZero | Where-Object { $_ -ne '0' }).Count -gt 0 -or
    $MigrationFilesChanged -ne 'NO' -or $PdaFilesChanged -ne 'NO'
if ($failed) { Write-Output 'FINAL = REFUSED_AUTO_APPROVAL_GATE_FAILED'; exit 1 }

if (-not $EvaluateOnly) {
    Set-StateField 'STATE' 'READY_FOR_COMMIT'
    Set-StateField 'AUTO_APPROVAL' 'PASS'
}
Write-Output 'PIPELINE_STATE = READY_FOR_COMMIT'
Write-Output 'AUTO_APPROVAL = PASS'
Write-Output 'FINAL = READY_FOR_COMMIT'
