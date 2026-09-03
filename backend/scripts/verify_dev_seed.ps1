$ErrorActionPreference = 'Stop'

$Host.UI.RawUI.WindowTitle = 'DLX Yuki WMS - Phase E DEV Verification'
$backendRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$resultPath = Join-Path $env:LOCALAPPDATA 'Temp\dlx-yuki-wms-phase-e-result.txt'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Backend virtual-environment Python was not found.'
}

$dbSecurePassword = Read-Host 'DEV database role password (input hidden)' -AsSecureString
$dbCredential = [System.Net.NetworkCredential]::new('', $dbSecurePassword)
$dbPlainPassword = $dbCredential.Password
$encodedDbPassword = [System.Uri]::EscapeDataString($dbPlainPassword)

try {
    $env:WMS_ENV = 'development'
    $env:DATABASE_URL = "postgresql+psycopg://dlx_yuki_wms_dev_user:${encodedDbPassword}@localhost:5432/dlx_yuki_wms_dev"
    Push-Location -LiteralPath $backendRoot
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & $pythonPath -m scripts.verify_dev_seed 2>&1
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
        throw 'Phase E DEV verification stopped safely.'
    }
}
finally {
    Remove-Item Env:WMS_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    $encodedDbPassword = $null
    $dbPlainPassword = $null
    $dbCredential = $null
    $dbSecurePassword = $null
}
