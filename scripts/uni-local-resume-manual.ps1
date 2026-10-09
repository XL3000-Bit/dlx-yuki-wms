# Manual recovery only: existing credentials/database, no migration or seed.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$state = Join-Path $root '.uni-local'
$pg = 'C:\Program Files\PostgreSQL\17\bin'
$data = Join-Path $state 'pgdata'
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
foreach ($required in @((Join-Path $state 'credentials.json'), (Join-Path $data 'PG_VERSION'), $python, "$pg\pg_ctl.exe")) {
    if (!(Test-Path -LiteralPath $required)) { throw "Missing existing local artifact: $required" }
}
$config = Get-Content -LiteralPath (Join-Path $state 'credentials.json') -Raw | ConvertFrom-Json
if (!$config.db_password -or !$config.jwt) { throw 'Existing local credentials are incomplete.' }
$node = (Get-Command node.exe -ErrorAction Stop).Source
$dbPort = [int](& "$pg\postgres.exe" -D $data -C port)
if ($LASTEXITCODE -or $dbPort -lt 1) { throw 'Cannot read existing database port.' }
& "$pg\pg_ctl.exe" status -D $data *> $null
if ($LASTEXITCODE) {
    if (Get-NetTCPConnection -LocalPort $dbPort -State Listen -ErrorAction SilentlyContinue) { throw "Port $dbPort is occupied; no process was stopped." }
    & "$pg\pg_ctl.exe" start -D $data -l (Join-Path $state 'postgres.log') -w
    if ($LASTEXITCODE) { throw 'Existing test database failed to start.' }
}
$dbPid = [int](Get-Content -LiteralPath (Join-Path $data 'postmaster.pid') -TotalCount 1)
$dbListener = Get-NetTCPConnection -LocalPort $dbPort -State Listen -ErrorAction Stop
if (@($dbListener | Where-Object { $_.OwningProcess -ne $dbPid }).Count) { throw 'Unexpected database listener; refusing to continue.' }
$env:PGPASSWORD = $config.db_password
try {
    & "$pg\psql.exe" -h 127.0.0.1 -p $dbPort -U uni_local -d uni_phase1 -tAc 'SELECT 1'
    if ($LASTEXITCODE) { throw 'Existing test database is not accessible.' }
} finally { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
$env:DATABASE_URL = 'postgresql+psycopg://uni_local:' + [Uri]::EscapeDataString($config.db_password) + "@127.0.0.1:$dbPort/uni_phase1"
$env:WMS_ENV = 'development'
$env:JWT_SECRET_KEY = $config.jwt
$env:CORS_ORIGINS = '["http://localhost:5177","http://127.0.0.1:5177","http://localhost:5277","http://127.0.0.1:5277"]'
$env:BUSINESS_TIMEZONE = 'America/Los_Angeles'
$env:DOCUMENT_STORAGE_ROOT = Join-Path $state 'documents'
$env:UNI_API_ORIGIN = 'http://127.0.0.1:8017'
$services = @(
    @{ name='api'; port=8017; file=$python; args='-m uvicorn app.main:app --host 127.0.0.1 --port 8017'; cwd=(Join-Path $root 'backend') },
    @{ name='web'; port=5277; file=$node; args='node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5277 --strictPort'; cwd=(Join-Path $root 'frontend') }
)
foreach ($service in $services) {
    $pidFile = Join-Path $state ($service.name + '.pid')
    $listener = Get-NetTCPConnection -LocalPort $service.port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        if (!(Test-Path -LiteralPath $pidFile)) { throw "Port $($service.port) is occupied; no process was stopped." }
        $expectedPid = [int](Get-Content -LiteralPath $pidFile)
    } else {
        $process = Start-Process -FilePath $service.file -ArgumentList $service.args -WorkingDirectory $service.cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state ($service.name+'.log')) -RedirectStandardError (Join-Path $state ($service.name+'.err.log'))
        $expectedPid = $process.Id
        $expectedPid | Set-Content -LiteralPath $pidFile
        $deadline = (Get-Date).AddSeconds(20)
        do {
            Start-Sleep -Milliseconds 200
            $listener = Get-NetTCPConnection -LocalPort $service.port -State Listen -ErrorAction SilentlyContinue
        } until ($listener -or (Get-Date) -gt $deadline)
        if (!$listener) { throw "$($service.name) failed to listen; inspect .uni-local/$($service.name).err.log" }
    }
    foreach ($entry in $listener) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($entry.OwningProcess)"
        if (($owner.ProcessId -ne $expectedPid -and $owner.ParentProcessId -ne $expectedPid) -or $owner.CommandLine -notlike ('*' + $service.args + '*')) { throw "Unexpected process on $($service.port); no process was stopped." }
    }
    $listener[0].OwningProcess | Set-Content -LiteralPath $pidFile
}
$schema = Invoke-RestMethod 'http://127.0.0.1:8017/openapi.json'
if (!$schema.paths.PSObject.Properties['/api/v1/uni-bols/dispatch/{ob_id}']) { throw 'API is reachable but dispatch association route is missing. No process was stopped.' }
Write-Output 'Association route is present. UI: http://127.0.0.1:5277/outbound/dispatch?selected_ob=35'
