$ErrorActionPreference = 'Stop'

$qdrantExecutable = 'D:\application\qdrant\qdrant.exe'
$qdrantWorkingDirectory = 'D:\application\qdrant'
$logDirectory = 'E:\RAG-Project\data\logs'

if (-not (Test-Path -LiteralPath $qdrantExecutable)) {
    throw "Qdrant executable not found: $qdrantExecutable"
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

$env:QDRANT__SERVICE__HOST = '127.0.0.1'
$env:QDRANT__TELEMETRY_DISABLED = 'true'

$process = Start-Process `
    -FilePath $qdrantExecutable `
    -WorkingDirectory $qdrantWorkingDirectory `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$logDirectory\qdrant.stdout.log" `
    -RedirectStandardError "$logDirectory\qdrant.stderr.log" `
    -PassThru

Write-Host "Qdrant started with PID $($process.Id) on 127.0.0.1:6333/6334."
