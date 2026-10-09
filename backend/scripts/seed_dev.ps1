$ErrorActionPreference = 'Stop'

$Host.UI.RawUI.WindowTitle = 'DLX Yuki WMS - Phase D DEV Seed'
$backendRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$resultPath = Join-Path $env:LOCALAPPDATA 'Temp\dlx-yuki-wms-phase-d-result.txt'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Backend virtual-environment Python was not found.'
}

$dbSecurePassword = Read-Host 'DEV database role password (input hidden)' -AsSecureString
$seedSecurePassword = Read-Host 'DEV synthetic application-user password, minimum 12 characters (input hidden)' -AsSecureString
$dbCredential = [System.Net.NetworkCredential]::new('', $dbSecurePassword)
$seedCredential = [System.Net.NetworkCredential]::new('', $seedSecurePassword)
$dbPlainPassword = $dbCredential.Password
$seedPlainPassword = $seedCredential.Password
$encodedDbPassword = [System.Uri]::EscapeDataString($dbPlainPassword)

try {
    $env:WMS_ENV = 'development'
    $env:DATABASE_URL = "postgresql+psycopg://dlx_yuki_wms_dev_user:${encodedDbPassword}@localhost:5432/dlx_yuki_wms_dev"
    $env:DEV_SEED_USER_PASSWORD = $seedPlainPassword

    Push-Location -LiteralPath $backendRoot
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # SQLAlchemy/Alembic may log informational messages to stderr. The
        # native process exit code is the authoritative success signal.
        $ErrorActionPreference = 'Continue'
        $output = & $pythonPath -m scripts.seed_dev 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }

    $outputText = $output | ForEach-Object { $_.ToString() }
    Set-Content -LiteralPath $resultPath -Value $outputText
    $outputText | ForEach-Object { Write-Host $_ }
    Write-Host "Sanitized result: $resultPath"

    if ($exitCode -ne 0) {
        throw 'Phase D DEV seed stopped safely; transaction was rolled back.'
    }
}
finally {
    Remove-Item Env:WMS_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:DEV_SEED_USER_PASSWORD -ErrorAction SilentlyContinue
    $encodedDbPassword = $null
    $dbPlainPassword = $null
    $seedPlainPassword = $null
    $dbCredential = $null
    $seedCredential = $null
    $dbSecurePassword = $null
    $seedSecurePassword = $null
}

