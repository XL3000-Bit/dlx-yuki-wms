[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$queuePath = Join-Path $repoRoot '.codex/TASK_QUEUE.md'

Write-Output 'NEXT_TASK'
if (-not (Test-Path -LiteralPath $queuePath)) {
    Write-Output 'FINAL = SAFETY_STOP_QUEUE_NOT_FOUND'
    exit 1
}

$content = Get-Content -Raw -LiteralPath $queuePath
$taskMatches = [regex]::Matches($content, '(?ms)^## TASK\s+(?<id>[^\r\n]+)\s*\r?\n(?<body>.*?)(?=^## TASK\s+|\z)')
$ready = @()
foreach ($match in $taskMatches) {
    $fields = @{}
    foreach ($line in ($match.Groups['body'].Value -split '\r?\n')) {
        if ($line -match '^([A-Z_]+):\s*(.*?)\s*$') { $fields[$matches[1]] = $matches[2] }
    }
    if ($fields['STATUS'] -eq 'READY') {
        $ready += [pscustomobject]@{ Id = $match.Groups['id'].Value.Trim(); Fields = $fields }
    }
}

if ($ready.Count -eq 0) {
    Write-Output 'FINAL = NO_READY_TASK'
    exit 0
}
if ($ready.Count -gt 1) {
    Write-Output ("READY_TASK_COUNT = {0}" -f $ready.Count)
    Write-Output 'FINAL = SAFETY_STOP_MULTIPLE_READY_TASKS'
    exit 1
}

$task = $ready[0]
foreach ($required in @('LEVEL', 'BRANCH', 'BASE_BRANCH', 'PROMPT', 'BLOCKED_BY')) {
    if (-not $task.Fields.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($task.Fields[$required])) {
        Write-Output ("MISSING_FIELD = {0}" -f $required)
        Write-Output 'FINAL = SAFETY_STOP_INVALID_TASK'
        exit 1
    }
}
Write-Output ("TASK_ID = {0}" -f $task.Id)
Write-Output ("LEVEL = {0}" -f $task.Fields['LEVEL'])
Write-Output ("BRANCH = {0}" -f $task.Fields['BRANCH'])
Write-Output ("BASE_BRANCH = {0}" -f $task.Fields['BASE_BRANCH'])
Write-Output ("PROMPT = {0}" -f $task.Fields['PROMPT'])
Write-Output ("BLOCKED_BY = {0}" -f $task.Fields['BLOCKED_BY'])
Write-Output 'FINAL = PASS'
