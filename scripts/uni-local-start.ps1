$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$state = Join-Path $root '.uni-local'
$pg = 'C:\Program Files\PostgreSQL\17\bin'
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$configFile = Join-Path $state 'credentials.json'
if (!(Test-Path -LiteralPath $configFile)) {
    $config = @{ username = 'uni_local'; password = ([guid]::NewGuid().ToString('N')); db_password = ([guid]::NewGuid().ToString('N')); jwt = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')) }
    $config | ConvertTo-Json | Set-Content -LiteralPath $configFile -Encoding UTF8
}
$config = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
$data = Join-Path $state 'pgdata'
if (!(Test-Path -LiteralPath (Join-Path $data 'PG_VERSION'))) {
    if (Get-NetTCPConnection -LocalPort 55437 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 55437 is already in use; refusing to use an unknown database.' }
    $pwFile = Join-Path $state 'pg-init-password.tmp'
    [IO.File]::WriteAllText($pwFile, $config.db_password)
    try { & "$pg\initdb.exe" -D $data -U uni_local --auth=scram-sha-256 --encoding=UTF8 --locale=C --pwfile=$pwFile; if ($LASTEXITCODE) { throw 'initdb failed' } }
    finally { Remove-Item -LiteralPath $pwFile -Force }
    Add-Content -LiteralPath (Join-Path $data 'postgresql.conf') -Value "`nlisten_addresses = '127.0.0.1'`nport = 55437"
}
& "$pg\pg_ctl.exe" status -D $data *> $null
if ($LASTEXITCODE) { & "$pg\pg_ctl.exe" start -D $data -l (Join-Path $state 'postgres.log') -w; if ($LASTEXITCODE) { throw 'Isolated PostgreSQL failed to start' } }
$env:PGPASSWORD = $config.db_password
try {
    $exists = & "$pg\psql.exe" -h 127.0.0.1 -p 55437 -U uni_local -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='uni_phase1'"
    if ($LASTEXITCODE) { throw 'Isolated PostgreSQL connection failed' }
    if ($exists -ne '1') { & "$pg\createdb.exe" -h 127.0.0.1 -p 55437 -U uni_local uni_phase1; if ($LASTEXITCODE) { throw 'createdb failed' } }
} finally { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
$env:DATABASE_URL = 'postgresql+psycopg://uni_local:' + $config.db_password + '@127.0.0.1:55437/uni_phase1'
$env:WMS_ENV = 'development'
$env:JWT_SECRET_KEY = $config.jwt
$env:CORS_ORIGINS = '["http://localhost:5177","http://127.0.0.1:5177"]'
$env:BUSINESS_TIMEZONE = 'America/Los_Angeles'
$env:DOCUMENT_STORAGE_ROOT = Join-Path $state 'documents'
$env:UNI_API_ORIGIN = 'http://127.0.0.1:8017'
Push-Location (Join-Path $root 'backend')
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE) { throw 'Migration failed' }
    & $python (Join-Path $PSScriptRoot 'uni_local_seed.py')
    if ($LASTEXITCODE) { throw 'Seed failed' }
} finally { Pop-Location }
$services = @(
    @{ name='api'; port=8017; file=$python; args='-m uvicorn app.main:app --host 127.0.0.1 --port 8017'; cwd=(Join-Path $root 'backend') },
    @{ name='web'; port=5177; file=(Get-Command node.exe).Source; args='node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5177 --strictPort'; cwd=(Join-Path $root 'frontend') }
)
foreach ($service in $services) {
    $pidFile = Join-Path $state ($service.name + '.pid')
    $listener = Get-NetTCPConnection -LocalPort $service.port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        if (!(Test-Path $pidFile)) { throw "Port $($service.port) belongs to another process." }
        $savedPid = [int](Get-Content $pidFile)
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
        if (($owner.ProcessId -ne $savedPid -and $owner.ParentProcessId -ne $savedPid) -or $owner.CommandLine -notlike ('*' + $service.args + '*')) { throw "Port $($service.port) belongs to another process." }
        $owner.ProcessId | Set-Content -LiteralPath $pidFile
        continue
    }
    $process = Start-Process -FilePath $service.file -ArgumentList $service.args -WorkingDirectory $service.cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state ($service.name+'.log')) -RedirectStandardError (Join-Path $state ($service.name+'.err.log'))
    $process.Id | Set-Content -LiteralPath $pidFile
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 200
        $listener = Get-NetTCPConnection -LocalPort $service.port -State Listen -ErrorAction SilentlyContinue
    } until ($listener -or (Get-Date) -gt $deadline)
    if (!$listener) { throw "$($service.name) did not start; inspect .uni-local/$($service.name).err.log" }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
    if (($owner.ProcessId -ne $process.Id -and $owner.ParentProcessId -ne $process.Id) -or $owner.CommandLine -notlike ('*' + $service.args + '*')) { throw "Unexpected process listening on $($service.port)." }
    $owner.ProcessId | Set-Content -LiteralPath $pidFile
}
Write-Output 'Local UI: http://127.0.0.1:5177  API: http://127.0.0.1:8017'
Write-Output 'Local credentials are in .uni-local/credentials.json (not committed).'
