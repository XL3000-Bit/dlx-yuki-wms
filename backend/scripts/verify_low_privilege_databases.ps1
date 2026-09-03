$ErrorActionPreference = 'Stop'

$backendRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$resultPath = Join-Path $env:LOCALAPPDATA 'Temp\dlx-yuki-wms-phase-b-result.txt'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Backend virtual-environment Python was not found.'
}

function Invoke-SafeAlembicVerification {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('development', 'test')]
        [string]$Environment,

        [Parameter(Mandatory = $true)]
        [string]$RoleName,

        [Parameter(Mandatory = $true)]
        [string]$DatabaseName
    )

    $securePassword = Read-Host "Enter the password for $RoleName" -AsSecureString
    $credential = [System.Net.NetworkCredential]::new('', $securePassword)
    $plainPassword = $credential.Password
    $encodedPassword = [System.Uri]::EscapeDataString($plainPassword)

    try {
        $env:WMS_ENV = $Environment
        $env:DATABASE_URL = "postgresql+psycopg://${RoleName}:${encodedPassword}@localhost:5432/${DatabaseName}"

        Push-Location -LiteralPath $backendRoot
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            # Windows PowerShell 5.1 wraps native stderr (including Alembic INFO
            # logging) as error records. Capture it without treating it as a
            # terminating PowerShell exception; the process exit code remains
            # the authoritative success signal.
            $ErrorActionPreference = 'Continue'
            $output = & $pythonPath -m scripts.safe_alembic 2>&1
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
            Pop-Location
        }

        Add-Content -LiteralPath $resultPath -Value "[$Environment]"
        $output | ForEach-Object {
            Add-Content -LiteralPath $resultPath -Value $_.ToString()
            Write-Host $_.ToString()
        }

        if ($exitCode -ne 0) {
            Add-Content -LiteralPath $resultPath -Value "PHASE_B_${Environment}=FAIL"
            throw "Safe Alembic verification failed for $Environment."
        }

        Add-Content -LiteralPath $resultPath -Value "PHASE_B_${Environment}=PASS"
    }
    finally {
        Remove-Item Env:WMS_ENV -ErrorAction SilentlyContinue
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
        $plainPassword = $null
        $encodedPassword = $null
        $credential = $null
        $securePassword = $null
    }
}

Set-Content -LiteralPath $resultPath -Value 'EXPLICIT_PROCESS_ENV_USED=YES'
Add-Content -LiteralPath $resultPath -Value 'IMPLICIT_ENV_FALLBACK_USED=NO'

Invoke-SafeAlembicVerification `
    -Environment development `
    -RoleName dlx_yuki_wms_dev_user `
    -DatabaseName dlx_yuki_wms_dev

Invoke-SafeAlembicVerification `
    -Environment test `
    -RoleName dlx_yuki_wms_test_user `
    -DatabaseName dlx_yuki_wms_test

Add-Content -LiteralPath $resultPath -Value 'PHASE_B_LOW_PRIVILEGE_VERIFICATION_COMPLETE'
Write-Host 'PHASE_B_LOW_PRIVILEGE_VERIFICATION_COMPLETE'
