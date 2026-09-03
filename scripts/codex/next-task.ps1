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
    $allowedPaths = [Collections.Generic.List[string]]::new()
    $readingAllowedPaths = $false
    foreach ($line in ($match.Groups['body'].Value -split '\r?\n')) {
        if ($line -match '^([A-Z_]+):\s*(.*?)\s*$') { $fields[$matches[1]] = $matches[2] }
        if ($line -match '^ALLOWED_PATHS:\s*(.*?)\s*$') {
            $readingAllowedPaths = $true
            if (-not [string]::IsNullOrWhiteSpace($matches[1])) { $allowedPaths.Add($matches[1].Trim()) }
            continue
        }
        if ($readingAllowedPaths -and $line -match '^\s*-\s*(.*?)\s*$') {
            $allowedPaths.Add($matches[1].Trim())
            continue
        }
        if ($readingAllowedPaths -and -not [string]::IsNullOrWhiteSpace($line)) { $readingAllowedPaths = $false }
    }
    if ($fields['STATUS'] -eq 'READY') {
        $ready += [pscustomobject]@{
            Id = $match.Groups['id'].Value.Trim()
            Fields = $fields
            AllowedPaths = @($allowedPaths)
        }
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
$metadataErrors = [Collections.Generic.List[string]]::new()
if (-not $task.Fields.ContainsKey('ALLOWED_PATHS')) { $metadataErrors.Add('ALLOWED_PATHS') }
if ($task.AllowedPaths.Count -eq 0) { $metadataErrors.Add('ALLOWED_PATHS') }
$invalidAllowedPath = @($task.AllowedPaths | Where-Object {
    [string]::IsNullOrWhiteSpace($_) -or $_ -in @('NONE', 'DECLARATION_REQUIRED', 'DECLARATION_REQUIRED_DURING_PREPARE')
}).Count -gt 0
if ($invalidAllowedPath) { $metadataErrors.Add('ALLOWED_PATHS') }
$pathSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($path in $task.AllowedPaths) {
    if (-not $pathSet.Add($path)) { $metadataErrors.Add('ALLOWED_PATHS_DUPLICATE'); break }
}
$commitMessage = if ($task.Fields.ContainsKey('COMMIT_MESSAGE')) { [string]$task.Fields['COMMIT_MESSAGE'] } else { $null }
if ([string]::IsNullOrWhiteSpace($commitMessage) -or $commitMessage.Trim() -in @('NONE', 'DECLARATION_REQUIRED', 'DECLARATION_REQUIRED_DURING_PREPARE')) {
    $metadataErrors.Add('COMMIT_MESSAGE')
}
$allowedPathsJson = ConvertTo-Json -InputObject @($task.AllowedPaths) -Compress
Write-Output ("TASK_ID = {0}" -f $task.Id)
Write-Output ("LEVEL = {0}" -f $task.Fields['LEVEL'])
Write-Output ("BRANCH = {0}" -f $task.Fields['BRANCH'])
Write-Output ("BASE_BRANCH = {0}" -f $task.Fields['BASE_BRANCH'])
Write-Output ("PROMPT = {0}" -f $task.Fields['PROMPT'])
Write-Output ("BLOCKED_BY = {0}" -f $task.Fields['BLOCKED_BY'])
Write-Output ("ALLOWED_PATH_COUNT = {0}" -f $task.AllowedPaths.Count)
Write-Output ("ALLOWED_PATHS = {0}" -f ($task.AllowedPaths -join '; '))
Write-Output ("ALLOWED_PATHS_JSON = {0}" -f $allowedPathsJson)
Write-Output ("COMMIT_MESSAGE = {0}" -f $commitMessage)
if ($metadataErrors.Count -gt 0) {
    $metadataErrors | Select-Object -Unique | ForEach-Object { Write-Output ("MISSING_OR_INVALID_FIELD = {0}" -f $_) }
    Write-Output 'TASK_METADATA_COMPLETE = FAIL'
    Write-Output 'FINAL = SAFETY_STOP_TASK_METADATA_INCOMPLETE'
    exit 1
}
Write-Output 'TASK_METADATA_COMPLETE = PASS'
Write-Output 'FINAL = PASS'
