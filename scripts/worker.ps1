$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rag-env.ps1"

$env:RAG_CONFIG = 'E:\RAG-Project\config\default.yaml'
Set-Location 'E:\RAG-Project'

uv run python -m rag.worker.main
