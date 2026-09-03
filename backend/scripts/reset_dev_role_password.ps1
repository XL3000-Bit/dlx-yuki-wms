[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scriptPath = Join-Path $PSScriptRoot 'reset_dev_role_password.sql'
$preferredPsql = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'

if (Test-Path -LiteralPath $preferredPsql -PathType Leaf) {
    $psqlPath = $preferredPsql
} else {
    $psqlCommand = Get-Command psql.exe -ErrorAction SilentlyContinue
    if ($null -eq $psqlCommand) {
        throw 'psql.exe was not found.'
    }
    $psqlPath = $psqlCommand.Source
}

Write-Host 'This operation only resets dlx_yuki_wms_dev_user on the postgres maintenance database.'
Write-Host 'First enter the PostgreSQL administrator password; then enter the new DEV password twice.'

& $psqlPath -X -W -h localhost -p 5432 -U postgres -d postgres -v ON_ERROR_STOP=1 -f $scriptPath
if ($LASTEXITCODE -ne 0) {
    throw "DEV role password reset failed with exit code $LASTEXITCODE."
}

Write-Host 'Password reset finished. You may close this window.' -ForegroundColor Green
Read-Host 'Press Enter to close'
