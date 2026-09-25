# Start the live local stack. Configuration and data stay in ignored local files.
param([switch]$ApiOnly)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot 'apps/api'
$webDir = Join-Path $repoRoot 'apps/web'
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
$logDir = Join-Path $repoRoot '.cache/local'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Wait-Endpoint([string]$Url, [string]$Service, $Process) {
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if (Test-Endpoint $Url) { return }
        if ($null -ne $Process -and $Process.HasExited) {
            throw "$Service stopped. See the logs in $logDir."
        }
        Start-Sleep -Seconds 1
    }
    throw "$Service did not become available. See the logs in $logDir."
}

if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install apps/api/requirements-dev.lock first.' }
if (-not (Test-Path -LiteralPath (Join-Path $apiDir '.env'))) { throw 'Configure apps/api/.env first; see README.md.' }

# Reuse the already provisioned portable PostgreSQL cluster on this workstation.
# Other installations should start their configured PostgreSQL separately.
$pgCtl = Join-Path $repoRoot '.cache/postgres-portable/pgsql/bin/pg_ctl.exe'
$pgData = Join-Path $repoRoot '.cache/pg-stage2/data'
if ((Test-Path -LiteralPath $pgCtl) -and (Test-Path -LiteralPath $pgData)) {
    & $pgCtl status -D $pgData *> $null
    if ($LASTEXITCODE -ne 0) {
        $connectionFile = Join-Path $repoRoot '.cache/pg-stage2/connection.json'
        if (-not (Test-Path -LiteralPath $connectionFile)) { throw 'Portable PostgreSQL connection settings are missing.' }
        $pgPort = [int]((Get-Content -Raw -LiteralPath $connectionFile | ConvertFrom-Json).port)
        if ($pgPort -lt 1 -or $pgPort -gt 65535) { throw 'Invalid PostgreSQL port.' }
        & $pgCtl start -D $pgData -l (Join-Path $logDir 'postgres.log') -o "-p $pgPort -h 127.0.0.1" -w
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL could not start.' }
    }
}

if (-not (Test-Endpoint 'http://127.0.0.1:8000/api/v1/health/live')) {
    Push-Location $apiDir
    try {
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed. Check apps/api/.env and PostgreSQL.' }
    } finally { Pop-Location }
    $apiProcess = Start-Process -FilePath $python -WorkingDirectory $apiDir -WindowStyle Hidden -PassThru `
        -ArgumentList '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '8000', '--no-access-log' `
        -RedirectStandardOutput (Join-Path $logDir 'api.stdout.log') -RedirectStandardError (Join-Path $logDir 'api.stderr.log')
    $apiProcess.Id | Set-Content (Join-Path $logDir 'api.pid')
    Wait-Endpoint 'http://127.0.0.1:8000/api/v1/health/live' 'API' $apiProcess
}

if ($ApiOnly) {
    Write-Host 'Local API is available at http://127.0.0.1:8000'
    exit 0
}

if (-not (Test-Endpoint 'http://localhost:3000/register')) {
    $env:NEXT_PUBLIC_DATA_MODE = 'live'
    $env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
    $webProcess = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $webDir -WindowStyle Hidden -PassThru `
        -ArgumentList '/d', '/c', 'npm.cmd run dev' `
        -RedirectStandardOutput (Join-Path $logDir 'web.stdout.log') -RedirectStandardError (Join-Path $logDir 'web.stderr.log')
    $webProcess.Id | Set-Content (Join-Path $logDir 'web.pid')
    Wait-Endpoint 'http://localhost:3000/register' 'Website' $webProcess
}

if (-not (Test-Endpoint 'http://localhost:3000/api/v1/health/live')) {
    throw 'The website cannot reach the API. Set API_PROXY_TARGET=http://127.0.0.1:8000 in apps/web/.env.local and restart the website.'
}
Write-Host 'Live workspace is available at http://localhost:3000/register'
Write-Host "Logs: $logDir"
