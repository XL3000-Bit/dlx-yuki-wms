$ErrorActionPreference = 'Stop'

$backendRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$resultPath = Join-Path $env:LOCALAPPDATA 'Temp\dlx-yuki-wms-phase-c-result.txt'
$roleName = 'dlx_yuki_wms_dev_user'
$databaseName = 'dlx_yuki_wms_dev'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Backend virtual-environment Python was not found.'
}

$securePassword = Read-Host "Enter the password for $roleName" -AsSecureString
$credential = [System.Net.NetworkCredential]::new('', $securePassword)
$plainPassword = $credential.Password
$encodedPassword = [System.Uri]::EscapeDataString($plainPassword)

try {
    $env:WMS_ENV = 'development'
    $env:DATABASE_URL = "postgresql+psycopg://${roleName}:${encodedPassword}@localhost:5432/${databaseName}"
    Set-Content -LiteralPath $resultPath -Value 'EXPLICIT_PROCESS_ENV_USED=YES'
    Add-Content -LiteralPath $resultPath -Value 'IMPLICIT_ENV_FALLBACK_USED=NO'

    Push-Location -LiteralPath $backendRoot
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & $pythonPath -m scripts.discover_dev_seed_state 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }

    $output | ForEach-Object {
        Add-Content -LiteralPath $resultPath -Value $_.ToString()
        Write-Host $_.ToString()
    }

    if ($exitCode -ne 0) {
        throw "Phase C discovery stopped with exit code $exitCode."
    }
}
finally {
    Remove-Item Env:WMS_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    $plainPassword = $null
    $encodedPassword = $null
    $credential = $null
    $securePassword = $null
}
