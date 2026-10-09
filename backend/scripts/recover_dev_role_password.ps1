[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$dataPath = 'C:\Program Files\PostgreSQL\17\data'
$hbaPath = Join-Path $dataPath 'pg_hba.conf'
$pgCtlPath = 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe'
$psqlPath = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
$sqlPath = Join-Path $PSScriptRoot 'recover_dev_role_password.sql'
$restorePath = Join-Path $PSScriptRoot 'restore_pg_hba_after_dev_recovery.ps1'
$resultPath = Join-Path $env:LOCALAPPDATA 'Temp\dlx-yuki-wms-dev-password-recovery-result.txt'
$trustLine = "host postgres postgres 127.0.0.1/32 trust`r`n"
$backupPath = Join-Path $dataPath ('.pg_hba.codex-dev-recovery.' + [Guid]::NewGuid().ToString('N') + '.bak')

Set-Content -LiteralPath $resultPath -Value 'CONTROLLED_DEV_PASSWORD_RECOVERY=STARTED'

if (-not (Test-Path -LiteralPath $hbaPath -PathType Leaf)) {
    throw 'pg_hba.conf was not found.'
}
if (-not (Test-Path -LiteralPath $pgCtlPath -PathType Leaf)) {
    throw 'pg_ctl.exe was not found.'
}
if (-not (Test-Path -LiteralPath $psqlPath -PathType Leaf)) {
    throw 'psql.exe was not found.'
}

$originalHash = (Get-FileHash -LiteralPath $hbaPath -Algorithm SHA256).Hash
$env:WMS_PG_HBA_RECOVERY_PATH = $hbaPath
$env:WMS_PG_HBA_RECOVERY_BACKUP = $backupPath
$env:WMS_PG_HBA_RECOVERY_ORIGINAL_HASH = $originalHash

try {
    Copy-Item -LiteralPath $hbaPath -Destination $backupPath
    $originalBytes = [IO.File]::ReadAllBytes($hbaPath)
    $trustBytes = [Text.Encoding]::UTF8.GetBytes($trustLine)
    $temporaryBytes = [byte[]]::new($trustBytes.Length + $originalBytes.Length)
    [Array]::Copy($trustBytes, 0, $temporaryBytes, 0, $trustBytes.Length)
    [Array]::Copy($originalBytes, 0, $temporaryBytes, $trustBytes.Length, $originalBytes.Length)
    [IO.File]::WriteAllBytes($hbaPath, $temporaryBytes)

    & $pgCtlPath reload -D $dataPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not activate the temporary local recovery rule.'
    }

    & $psqlPath -X -w -h 127.0.0.1 -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1 -f $sqlPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Controlled DEV password recovery did not complete.'
    }

    Set-Content -LiteralPath $resultPath -Value 'CONTROLLED_DEV_PASSWORD_RECOVERY=PASS'
    Write-Host 'Recovery completed; the original authentication configuration is active.' -ForegroundColor Green
} catch {
    Set-Content -LiteralPath $resultPath -Value 'CONTROLLED_DEV_PASSWORD_RECOVERY=FAILED_CLEANUP_ATTEMPTED'
    throw
} finally {
    try {
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $restorePath
    } finally {
        Remove-Item Env:WMS_PG_HBA_RECOVERY_PATH -ErrorAction SilentlyContinue
        Remove-Item Env:WMS_PG_HBA_RECOVERY_BACKUP -ErrorAction SilentlyContinue
        Remove-Item Env:WMS_PG_HBA_RECOVERY_ORIGINAL_HASH -ErrorAction SilentlyContinue
    }
}

Read-Host 'Press Enter to close'
