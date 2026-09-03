[CmdletBinding(DefaultParameterSetName = 'Invoke')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Invoke')]
    [string]$Prompt,
    [Parameter(ParameterSetName = 'Detect')]
    [switch]$DetectOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
$codexCommand = Get-Command codex -ErrorAction SilentlyContinue

function Get-CodexDetection {
    if (-not $codexCommand) {
        return [pscustomobject]@{ Available = $false; Version = 'NONE'; Supported = $false }
    }

    $version = ((& codex --version 2>&1) -join ' ').Trim()
    $versionCode = $LASTEXITCODE
    $topHelp = @(& codex --help 2>&1)
    $topHelpCode = $LASTEXITCODE
    $execHelp = @(& codex exec --help 2>&1)
    $execHelpCode = $LASTEXITCODE
    $supported = $versionCode -eq 0 -and $topHelpCode -eq 0 -and $execHelpCode -eq 0 -and
        (($topHelp -join "`n") -match '\bexec\b') -and
        (($execHelp -join "`n") -match 'Run Codex non-interactively|codex exec')
    return [pscustomobject]@{
        Available = $true
        Version = $(if ($version) { $version } else { 'UNKNOWN' })
        Supported = $supported
    }
}
function Write-Detection($Detection) {
    Write-Output ("CODEX_CLI_AVAILABLE = {0}" -f $(if ($Detection.Available) { 'YES' } else { 'NO' }))
    Write-Output ("CODEX_CLI_VERSION = {0}" -f $Detection.Version)
    Write-Output ("CODEX_NON_INTERACTIVE_SUPPORTED = {0}" -f $(if ($Detection.Supported) { 'YES' } else { 'NO' }))
}

$detection = Get-CodexDetection
if ($DetectOnly) {
    Write-Detection $detection
    exit 0
}

Write-Output 'INVOKE_CODEX'
Write-Detection $detection
if (-not $detection.Supported) {
    Write-Output 'FINAL = SAFETY_STOP_CODEX_NON_INTERACTIVE_UNAVAILABLE'
    exit 1
}

$lastMessagePath = [IO.Path]::GetTempFileName()
try {
    $Prompt | & codex exec --cd $repoRoot --sandbox workspace-write --ask-for-approval never --output-last-message $lastMessagePath -
    $codexExitCode = $LASTEXITCODE
    if (Test-Path -LiteralPath $lastMessagePath) {
        $lastMessage = (Get-Content -Raw -LiteralPath $lastMessagePath).Trim()
        if ($lastMessage) {
            Write-Output 'CODEX_LAST_MESSAGE_BEGIN'
            Write-Output $lastMessage
            Write-Output 'CODEX_LAST_MESSAGE_END'
        }
    }
    Write-Output ("CODEX_EXIT_CODE = {0}" -f $codexExitCode)
    if ($codexExitCode -ne 0) {
        Write-Output 'FINAL = FAIL'
        exit $codexExitCode
    }
    Write-Output 'FINAL = PASS'
} finally {
    Remove-Item -LiteralPath $lastMessagePath -Force -ErrorAction SilentlyContinue
}
