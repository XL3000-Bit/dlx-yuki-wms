$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$state = Join-Path $root '.uni-local'
foreach ($name in @('api', 'web')) {
    $pidFile = Join-Path $state ($name + '.pid')
    if (Test-Path -LiteralPath $pidFile) {
        $servicePid = [int](Get-Content -LiteralPath $pidFile)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$servicePid"
        if ($process -and (($name -eq 'api' -and $process.CommandLine -like '*uvicorn*8017*') -or ($name -eq 'web' -and $process.CommandLine -like '*vite*5177*'))) { Stop-Process -Id $servicePid }
        elseif ($process) { throw "PID $servicePid was reused; refusing to stop it." }
        Remove-Item -LiteralPath $pidFile
    }
}
$data = Join-Path $state 'pgdata'
if (Test-Path -LiteralPath (Join-Path $data 'postmaster.pid')) { & 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe' stop -D $data -m fast -w }
Write-Output 'UNI local services stopped; database and documents retained.'
