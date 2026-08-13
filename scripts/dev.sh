#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export RAG_CONFIG="${RAG_CONFIG:-$(pwd)/config/default.yaml}"
exec uv run uvicorn rag.api.app:app --host 127.0.0.1 --port 8000 --reload
