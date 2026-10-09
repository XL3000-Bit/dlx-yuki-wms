param([string]$Output = "..\backups\dlx-wms-$(Get-Date -Format yyyyMMdd-HHmmss).dump")
$ErrorActionPreference = 'Stop'
if (-not $env:DATABASE_URL) { throw 'Set DATABASE_URL before running backup.' }
$folder = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $folder | Out-Null
pg_dump --format=custom --no-owner --file=$Output $env:DATABASE_URL
Write-Output "Backup created: $Output"
