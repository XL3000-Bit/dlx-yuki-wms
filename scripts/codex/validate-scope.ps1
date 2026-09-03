[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$taskPath = Join-Path $repoRoot '.codex/CURRENT_TASK.md'

function Get-TaskField([string]$Name) {
    $line = Get-Content -LiteralPath $taskPath | Where-Object { $_ -match ("^{0}:\s*" -f [regex]::Escape($Name)) } | Select-Object -Last 1
    if ($line) { return ($line -replace ("^{0}:\s*" -f [regex]::Escape($Name)), '').Trim() }
    return $null
}
function Test-Allowed([string]$Path, [string[]]$Patterns) {
    foreach ($pattern in $Patterns) {
        $normalized = $pattern.Trim().Replace('\', '/')
        if ($normalized.EndsWith('/**')) {
            $prefix = $normalized.Substring(0, $normalized.Length - 3).TrimEnd('/')
            if ($Path -eq $prefix -or $Path.StartsWith($prefix + '/', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        } elseif ([System.Management.Automation.WildcardPattern]::new($normalized, 'IgnoreCase').IsMatch($Path)) { return $true }
    }
    return $false
}

Write-Output 'VALIDATE_SCOPE'
if (-not (Test-Path -LiteralPath $taskPath)) { Write-Output 'FINAL = SAFETY_STOP'; exit 1 }
$allowedRaw = Get-TaskField 'ALLOWED_PATHS'
$patterns = @($allowedRaw -split '[;,]' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$declarationMissing = (-not $allowedRaw) -or $allowedRaw -in @('NONE', 'DECLARATION_REQUIRED') -or $patterns -contains 'DECLARATION_REQUIRED'

$changed = @(& git -C $repoRoot status --porcelain=v1 -z --untracked-files=all) -join ''
$paths = @()
if ($changed.Length -gt 0) {
    $entries = $changed -split "`0" | Where-Object { $_ }
    for ($i = 0; $i -lt $entries.Count; $i++) {
        $entry = $entries[$i]
        if ($entry.Length -lt 4) { continue }
        $status = $entry.Substring(0, 2)
        $path = $entry.Substring(3).Replace('\', '/')
        $paths += $path
        if ($status -match '[RC]') {
            $i++
            if ($i -lt $entries.Count) { $paths += $entries[$i].Replace('\', '/') }
        }
    }
}
$paths = @($paths | Sort-Object -Unique)
$protectedPatterns = @(
    'backend/alembic/**', 'alembic/**', 'migrations/**', 'backend/.env',
    '*pda*', 'backend/**/inbound*', 'frontend/**/inbound*',
    'backend/**/fba*', 'frontend/**/fba*', '*auth*', '*security*'
)
$authorized = @()
$unauthorized = @()
$protected = @()
foreach ($path in $paths) {
    $isAllowed = Test-Allowed $path $patterns
    if ($isAllowed) { $authorized += $path } else { $unauthorized += $path }
    if (-not $isAllowed -and (Test-Allowed $path $protectedPatterns)) { $protected += $path }
}
if ($declarationMissing) { $unauthorized += 'DECLARATION_REQUIRED' }

Write-Output ("TOTAL_CHANGED_PATHS = {0}" -f $paths.Count)
Write-Output ("AUTHORIZED_PATHS = {0}" -f $authorized.Count)
Write-Output ("UNAUTHORIZED_PATHS = {0}" -f $unauthorized.Count)
Write-Output ("PROTECTED_PATHS_CHANGED = {0}" -f $protected.Count)
foreach ($path in $unauthorized) { Write-Output ("UNAUTHORIZED = {0}" -f $path) }
foreach ($path in $protected) { Write-Output ("PROTECTED = {0}" -f $path) }
$failed = $unauthorized.Count -gt 0 -or $protected.Count -gt 0
Write-Output ("FINAL = {0}" -f $(if ($failed) { 'SAFETY_STOP' } else { 'PASS' }))
if ($failed) { exit 1 }
