from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class AppSettings(BaseModel):
    environment: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = Path("./data")


class ModelEndpointSettings(BaseModel):
    base_url: str
    model: str
    api_key: str = "local-no-key"
    request_timeout_seconds: float = 180.0

    @field_validator("base_url")
    @classmethod
    def local_endpoint_only(cls, value: str) -> str:
        allowed = ("http://127.0.0.1", "http://localhost", "https://127.0.0.1")
        if not value.startswith(allowed):
            raise ValueError("model endpoint must be loopback in local mode")
        return value.rstrip("/")


class LlmSettings(ModelEndpointSettings):
    max_output_tokens: int = 1024
    temperature: float = 0.1
    enable_thinking: bool = False


class EmbeddingSettings(ModelEndpointSettings):
    batch_size: int = 8
    document_prefix: str = ""
    query_prefix: str = ""
    fingerprint: str = "replace-with-model-sha256"


class QdrantSettings(BaseModel):
    url: str = "http://127.0.0.1:6333"
    api_key: str | None = None
    active_alias_template: str = "repo_{repo_id}__active"
    distance: str = "cosine"


class SqliteSettings(BaseModel):
    path: Path = Path("./data/sqlite/rag.db")
    migrations_dir: Path = Path("./migrations")
    busy_timeout_ms: int = 5000


class IngestionSettings(BaseModel):
    worker_poll_seconds: float = 2.0
    max_file_bytes: int = 1_048_576
    embedding_batch_size: int = 8
    chunk_target_tokens: int = 500
    chunk_max_tokens: int = 900
    chunk_min_tokens: int = 80
    text_overlap_tokens: int = 80
    follow_symlinks: bool = False
    include_submodules: bool = False
    allow_remote_git: bool = False
    web_allowed_hosts: tuple[str, ...] = ("cn.vuejs.org",)
    web_request_timeout_seconds: float = 30.0
    chunker_version: str = "code-v1"


class RetrievalSettings(BaseModel):
    dense_top_k: int = 30
    lexical_top_k: int = 30
    fused_top_k: int = 20
    final_top_k: int = 8
    rrf_k: int = 60
    max_chunks_per_file: int = 3
    context_token_budget: int = 8_000


class SecuritySettings(BaseModel):
    redact_secrets: bool = True
    reject_binary: bool = True
    admin_token: str = "change-me-local-admin-token"
    log_prompts: bool = False


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    llm: LlmSettings = Field(
        default_factory=lambda: LlmSettings(base_url="http://127.0.0.1:8080/v1", model="local-chat")
    )
    embedding: EmbeddingSettings = Field(
        default_factory=lambda: EmbeddingSettings(
            base_url="http://127.0.0.1:8081/v1", model="local-embedding"
        )
    )
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    sqlite: SqliteSettings = Field(default_factory=SqliteSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)


_ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "RAG_DATA_DIR": ("app", "data_dir"),
    "RAG_LLM_BASE_URL": ("llm", "base_url"),
    "RAG_LLM_MODEL": ("llm", "model"),
    "RAG_LLM_API_KEY": ("llm", "api_key"),
    "RAG_EMBEDDING_BASE_URL": ("embedding", "base_url"),
    "RAG_EMBEDDING_MODEL": ("embedding", "model"),
    "RAG_EMBEDDING_API_KEY": ("embedding", "api_key"),
    "RAG_QDRANT_URL": ("qdrant", "url"),
    "RAG_QDRANT_API_KEY": ("qdrant", "api_key"),
    "RAG_SQLITE_PATH": ("sqlite", "path"),
    "RAG_ADMIN_TOKEN": ("security", "admin_token"),
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(config_path: Path | str | None = None) -> Settings:
    data: dict[str, Any] = {}
    if config_path:
        path = Path(config_path)
        if path.exists():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                raise ValueError("configuration root must be an object")
            data = loaded

    env_overlay: dict[str, Any] = {}
    for env_name, (section, key) in _ENV_OVERRIDES.items():
        if value := os.getenv(env_name):
            env_overlay.setdefault(section, {})[key] = value
    return Settings.model_validate(_deep_merge(data, env_overlay))
