$env:UV_PYTHON_INSTALL_DIR = 'E:\RAG-Project\.tools\python'
$env:UV_CACHE_DIR = 'E:\RAG-Project\.cache\uv'
$env:UV_PYTHON_NO_REGISTRY = '1'
$env:PATH = 'E:\RAG-Project\.tools\uv\0.11.32;' + $env:PATH

Write-Host 'Local RAG environment configured.'
Write-Host 'Run: uv sync --frozen'
