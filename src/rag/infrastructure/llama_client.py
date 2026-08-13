from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from rag.domain.errors import ModelUnavailableError
from rag.infrastructure.settings import EmbeddingSettings, LlmSettings


def _health_url(base_url: str) -> str:
    root = base_url.removesuffix("/v1")
    return f"{root}/health"


class LlamaEmbeddingClient:
    def __init__(self, settings: EmbeddingSettings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    async def health(self) -> bool:
        try:
            response = await self._client.get(_health_url(self.settings.base_url))
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [f"{self.settings.document_prefix}{text}" for text in texts]
        return await self._embed(prefixed)

    async def embed_query(self, text: str) -> list[float]:
        result = await self._embed([f"{self.settings.query_prefix}{text}"])
        return result[0]

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.post(
                "/embeddings", json={"model": self.settings.model, "input": list(texts)}
            )
            response.raise_for_status()
            payload = response.json()
            ordered = sorted(payload["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in ordered]
            if len(vectors) != len(texts) or not all(vectors):
                raise ModelUnavailableError("embedding response shape mismatch")
            dimension = len(vectors[0])
            if any(len(vector) != dimension for vector in vectors):
                raise ModelUnavailableError("embedding dimensions are inconsistent")
            return vectors
        except (httpx.HTTPError, KeyError, TypeError, IndexError) as exc:
            raise ModelUnavailableError(f"embedding request failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


class LlamaGenerationClient:
    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    async def health(self) -> bool:
        try:
            response = await self._client.get(_health_url(self.settings.base_url))
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def answer(self, system_prompt: str, user_prompt: str) -> str:
        request: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_output_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": self.settings.enable_thinking},
        }
        try:
            response = await self._client.post("/chat/completions", json=request)
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
        except (httpx.HTTPError, KeyError, TypeError, IndexError) as exc:
            raise ModelUnavailableError(f"generation request failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
