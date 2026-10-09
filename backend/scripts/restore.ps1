param([Parameter(Mandatory=$true)][string]$InputFile)
$ErrorActionPreference = 'Stop'
if (-not $env:DATABASE_URL) { throw 'Set DATABASE_URL before running restore.' }
if (-not (Test-Path -LiteralPath $InputFile)) { throw "Backup not found: $InputFile" }
pg_restore --clean --if-exists --no-owner --dbname=$env:DATABASE_URL $InputFile
Write-Output "Backup restored: $InputFile"
