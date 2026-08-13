[CmdletBinding()]
param(
    [switch]$Restart,
    [switch]$SkipWorker,
    [switch]$SkipDependencySync
)

$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$toolUv = Join-Path $projectRoot '.tools\uv\0.11.32\uv.exe'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$ragctl = Join-Path $projectRoot '.venv\Scripts\ragctl.exe'
$configPath = Join-Path $projectRoot 'config\default.yaml'
$runDirectory = Join-Path $projectRoot 'data\run'
$logDirectory = Join-Path $projectRoot 'data\logs'
$apiPidFile = Join-Path $runDirectory 'rag-api.pid'
$workerPidFile = Join-Path $runDirectory 'rag-worker.pid'

function Write-Step {
    param([string]$Message)
    Write-Host "[RAG] $Message" -ForegroundColor Cyan
}

function Test-HttpHealth {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 3
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Wait-HttpHealth {
    param(
        [string]$Name,
        [string]$Uri,
        [int]$Attempts = 30
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        if (Test-HttpHealth -Uri $Uri) {
            Write-Host "  OK  $Name ($Uri)" -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 500
    }

    throw "$Name did not become healthy: $Uri"
}

function Get-TrackedProcess {
    param([string]$PidFile)

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $null
    }

    $savedPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($savedPid -notmatch '^\d+$') {
        Remove-Item -LiteralPath $PidFile -Force
        return $null
    }

    $process = Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item -LiteralPath $PidFile -Force
        return $null
    }
    return $process
}

function Stop-TrackedProcess {
    param(
        [string]$Name,
        [string]$PidFile
    )

    $process = Get-TrackedProcess -PidFile $PidFile
    if ($process) {
        Write-Step "Stopping $Name (PID $($process.Id))"
        Stop-Process -Id $process.Id -ErrorAction Stop
        Wait-Process -Id $process.Id -Timeout 15 -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Start-BackgroundProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$PidFile,
        [string]$StdoutLog,
        [string]$StderrLog
    )

    $existing = Get-TrackedProcess -PidFile $PidFile
    if ($existing) {
        Write-Host "  OK  $Name already running (PID $($existing.Id))" -ForegroundColor Green
        return $existing
    }

    $launcher = Join-Path $projectRoot 'scripts\launch-detached.py'
    $launcherOutput = & $python $launcher $projectRoot $StdoutLog $StderrLog $FilePath @Arguments
    if ($LASTEXITCODE -ne 0 -or $launcherOutput -notmatch '^\d+$') {
        throw "Failed to start $Name in detached mode."
    }
    $startedPid = [int]$launcherOutput
    Set-Content -LiteralPath $PidFile -Value $startedPid -Encoding ascii
    Write-Host "  OK  $Name started (PID $startedPid)" -ForegroundColor Green
    return $startedPid
}

New-Item -ItemType Directory -Force -Path $runDirectory, $logDirectory | Out-Null
$env:RAG_CONFIG = $configPath
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.tools\python'
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
$env:UV_PYTHON_NO_REGISTRY = '1'

if ($Restart) {
    Stop-TrackedProcess -Name 'RAG API' -PidFile $apiPidFile
    Stop-TrackedProcess -Name 'RAG Worker' -PidFile $workerPidFile
}

Write-Step 'Checking project runtime'
if (-not (Test-Path -LiteralPath $toolUv)) {
    throw "uv was not found: $toolUv. Run the environment installation steps first."
}

if (-not $SkipDependencySync) {
    & $toolUv sync --frozen
    if ($LASTEXITCODE -ne 0) {
        throw 'uv sync --frozen failed.'
    }
}

if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $ragctl)) {
    throw 'The project virtual environment is incomplete. Run: uv sync --frozen'
}

Write-Step 'Checking Qdrant'
if (-not (Test-HttpHealth -Uri 'http://127.0.0.1:6333/healthz')) {
    & (Join-Path $projectRoot 'scripts\start-qdrant-local.ps1')
}
Wait-HttpHealth -Name 'Qdrant' -Uri 'http://127.0.0.1:6333/healthz'

Write-Step 'Checking llama.cpp services'
Wait-HttpHealth -Name 'LLM' -Uri 'http://127.0.0.1:8080/health' -Attempts 4
Wait-HttpHealth -Name 'Embedding' -Uri 'http://127.0.0.1:8081/health' -Attempts 4

Write-Step 'Initializing database and checking dependencies'
& $ragctl init-db
if ($LASTEXITCODE -ne 0) {
    throw 'Database initialization failed.'
}
& $ragctl doctor
if ($LASTEXITCODE -ne 0) {
    throw 'Dependency health check failed.'
}

Write-Step 'Starting application processes'
$null = Start-BackgroundProcess `
    -Name 'RAG API' `
    -FilePath $python `
    -Arguments @('-m', 'uvicorn', 'rag.api.app:app', '--host', '127.0.0.1', '--port', '8000') `
    -PidFile $apiPidFile `
    -StdoutLog (Join-Path $logDirectory 'rag-api.stdout.log') `
    -StderrLog (Join-Path $logDirectory 'rag-api.stderr.log')

Wait-HttpHealth -Name 'RAG API' -Uri 'http://127.0.0.1:8000/health/ready'

if (-not $SkipWorker) {
    $null = Start-BackgroundProcess `
        -Name 'RAG Worker' `
        -FilePath $python `
        -Arguments @('-m', 'rag.worker.main') `
        -PidFile $workerPidFile `
        -StdoutLog (Join-Path $logDirectory 'rag-worker.stdout.log') `
        -StderrLog (Join-Path $logDirectory 'rag-worker.stderr.log')
}

Write-Host ''
Write-Host 'Local Git RAG is ready.' -ForegroundColor Green
Write-Host '  API:      http://127.0.0.1:8000'
Write-Host '  Swagger:  http://127.0.0.1:8000/docs'
Write-Host '  Qdrant:   http://127.0.0.1:6333/dashboard'
Write-Host "  Logs:     $logDirectory"
Write-Host "  PID files: $runDirectory"
Write-Host ''
Write-Host 'Use .\start.bat -Restart to restart API and Worker.'
