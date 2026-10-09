[CmdletBinding()]
param([switch]$FullBackend)

$ErrorActionPreference = 'Continue'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()

function Get-ChangedPaths {
    $result = @()
    $result += @(& git -C $repoRoot diff --name-only --diff-filter=ACDMRTUXB)
    $result += @(& git -C $repoRoot diff --cached --name-only --diff-filter=ACDMRTUXB)
    $result += @(& git -C $repoRoot ls-files --others --exclude-standard)
    return @($result | ForEach-Object { $_.Replace('\', '/') } | Where-Object { $_ } | Sort-Object -Unique)
}

$paths = @(Get-ChangedPaths)
$backendChanged = @($paths | Where-Object { $_ -like 'backend/*' }).Count -gt 0
$frontendChanged = @($paths | Where-Object { $_ -like 'frontend/*' }).Count -gt 0
$javaChanged = @($paths | Where-Object { $_ -like 'backend-java/*' -and $_ -like '*.java' }).Count -gt 0
$appChanged = $backendChanged -or $frontendChanged -or $javaChanged
$backendResult = 'NOT_REQUIRED'
$pythonCheck = 'NOT_REQUIRED'
$frontendResult = 'NOT_REQUIRED'
$frontendLint = 'NOT_CONFIGURED'
$frontendTest = 'NOT_CONFIGURED'
$javaResult = 'NOT_REQUIRED'

if ($backendChanged) {
    $pythonFiles = @($paths | Where-Object { $_ -like 'backend/*.py' -or $_ -like 'backend/**/*.py' })
    $syntaxFailed = $false
    foreach ($file in $pythonFiles) {
        $absolute = Join-Path $repoRoot $file
        if (Test-Path -LiteralPath $absolute) {
            & python -c "import pathlib,sys; source=pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'); compile(source, sys.argv[1], 'exec')" $absolute
            if ($LASTEXITCODE -ne 0) { $syntaxFailed = $true }
        }
    }
    $pythonCheck = if ($syntaxFailed) { 'FAIL' } else { 'PASS' }

    $testFiles = @()
    if ($FullBackend) {
        Push-Location (Join-Path $repoRoot 'backend')
        & python -m pytest
        $testCode = $LASTEXITCODE
        Pop-Location
        $backendResult = if ($testCode -eq 0) { 'PASS' } else { 'FAIL' }
    } else {
        $testFiles += @($paths | Where-Object { $_ -like 'backend/tests/test_*.py' -and (Test-Path -LiteralPath (Join-Path $repoRoot $_)) })
        $sourceStems = @($paths | Where-Object { $_ -like 'backend/*.py' -or $_ -like 'backend/**/*.py' } | ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_) } | Sort-Object -Unique)
        $allTests = @(& rg --files (Join-Path $repoRoot 'backend/tests') -g 'test_*.py' 2>$null)
        foreach ($stem in $sourceStems) {
            $testFiles += @($allTests | Where-Object { [System.IO.Path]::GetFileNameWithoutExtension($_) -match [regex]::Escape($stem) })
        }
        $testFiles = @($testFiles | Sort-Object -Unique)
        if ($testFiles.Count -gt 0) {
            $backendRoot = (Join-Path $repoRoot 'backend').TrimEnd('\', '/')
            Push-Location $backendRoot
            $relativeTests = @($testFiles | ForEach-Object {
                $absoluteTest = if ([System.IO.Path]::IsPathRooted($_)) { $_ } else { Join-Path $repoRoot $_ }
                $absoluteTest.Substring($backendRoot.Length).TrimStart('\', '/')
            })
            & python -m pytest @relativeTests
            $testCode = $LASTEXITCODE
            Pop-Location
            $backendResult = if ($testCode -eq 0) { 'PASS' } else { 'FAIL' }
        } else {
            $backendResult = 'NOT_RUN'
        }
    }
}

if ($frontendChanged) {
    $package = Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'frontend/package.json') | ConvertFrom-Json
    Push-Location (Join-Path $repoRoot 'frontend')
    & npm run build
    $buildCode = $LASTEXITCODE
    $frontendResult = if ($buildCode -eq 0) { 'PASS' } else { 'FAIL' }
    if ($package.scripts.PSObject.Properties.Name -contains 'lint') {
        & npm run lint
        $frontendLint = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }
    }
    if ($package.scripts.PSObject.Properties.Name -contains 'test') {
        & npm run test
        $frontendTest = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }
    }
    Pop-Location
}

if ($javaChanged) {
    if (Get-Command mvn -ErrorAction SilentlyContinue) {
        Push-Location (Join-Path $repoRoot 'backend-java')
        & mvn test
        $javaResult = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }
        Pop-Location
    } else { $javaResult = 'NOT_RUN_NO_ENV' }
}

& git -C $repoRoot diff --check
$diffCheck = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }
$failed = $backendResult -in @('FAIL', 'NOT_RUN') -or $pythonCheck -eq 'FAIL' -or $frontendResult -eq 'FAIL' -or $frontendLint -eq 'FAIL' -or $frontendTest -eq 'FAIL' -or $javaResult -in @('FAIL', 'NOT_RUN_NO_ENV') -or $diffCheck -eq 'FAIL'

Write-Output 'RUN_TESTS'
Write-Output ("TEST_SCOPE = {0}" -f $(if (-not $appChanged) { 'DOCS_ONLY' } elseif ($FullBackend) { 'FULL_BACKEND_AND_CHANGED_PROJECTS' } else { 'CHANGED_PROJECTS' }))
Write-Output ("BACKEND = {0}" -f $backendResult)
Write-Output ("PYTHON_CHECK = {0}" -f $pythonCheck)
Write-Output ("FRONTEND_BUILD = {0}" -f $frontendResult)
Write-Output ("FRONTEND_LINT = {0}" -f $frontendLint)
Write-Output ("FRONTEND_TEST = {0}" -f $frontendTest)
Write-Output ("JAVA = {0}" -f $javaResult)
Write-Output ("GIT_DIFF_CHECK = {0}" -f $diffCheck)
Write-Output ("FINAL = {0}" -f $(if ($failed) { 'FAIL' } else { 'PASS' }))
if ($failed) { exit 1 }
