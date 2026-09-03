[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$hbaPath = $env:WMS_PG_HBA_RECOVERY_PATH
$backupPath = $env:WMS_PG_HBA_RECOVERY_BACKUP
$originalHash = $env:WMS_PG_HBA_RECOVERY_ORIGINAL_HASH
$trustPrefix = [Text.Encoding]::UTF8.GetBytes("host postgres postgres 127.0.0.1/32 trust`r`n")
$pgCtlPath = 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe'
$dataPath = 'C:\Program Files\PostgreSQL\17\data'

if ([string]::IsNullOrWhiteSpace($hbaPath) -or [string]::IsNullOrWhiteSpace($backupPath)) {
    throw 'Recovery environment is incomplete.'
}

if (-not (Test-Path -LiteralPath $hbaPath -PathType Leaf)) {
    throw 'pg_hba.conf is missing.'
}

$currentBytes = [IO.File]::ReadAllBytes($hbaPath)
$currentHash = (Get-FileHash -LiteralPath $hbaPath -Algorithm SHA256).Hash

if ($currentHash -eq $originalHash) {
    if (Test-Path -LiteralPath $backupPath -PathType Leaf) {
        Remove-Item -LiteralPath $backupPath -Force
    }
    exit 0
}

$hasTrustPrefix = $currentBytes.Length -ge $trustPrefix.Length
for ($index = 0; $hasTrustPrefix -and $index -lt $trustPrefix.Length; $index++) {
    if ($currentBytes[$index] -ne $trustPrefix[$index]) {
        $hasTrustPrefix = $false
    }
}

if ($hasTrustPrefix) {
    $cleanBytes = [byte[]]::new($currentBytes.Length - $trustPrefix.Length)
    [Array]::Copy($currentBytes, $trustPrefix.Length, $cleanBytes, 0, $cleanBytes.Length)
    [IO.File]::WriteAllBytes($hbaPath, $cleanBytes)
} elseif (Test-Path -LiteralPath $backupPath -PathType Leaf) {
    Copy-Item -LiteralPath $backupPath -Destination $hbaPath -Force
} else {
    throw 'Unable to prove that the temporary authentication rule was removed.'
}

& $pgCtlPath reload -D $dataPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'PostgreSQL configuration reload failed during recovery cleanup.'
}

if (Test-Path -LiteralPath $backupPath -PathType Leaf) {
    Remove-Item -LiteralPath $backupPath -Force
}

Write-Host 'TEMPORARY_LOCAL_TRUST_REMOVED=PASS'
