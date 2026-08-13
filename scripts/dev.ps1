$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\rag-env.ps1"

$env:RAG_CONFIG = 'E:\RAG-Project\config\default.yaml'
Set-Location 'E:\RAG-Project'

uv run uvicorn rag.api.app:app --host 127.0.0.1 --port 8000 --reload
