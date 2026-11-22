"""AI provider abstraction. Switch providers with LLM_PROVIDER in .env; nothing else changes.

Providers:
  none      - no AI key: answers with the best-matching official text (extractive)
  openai    - OpenAI API
  azure     - Azure OpenAI (recommended for a university deployment)
  anthropic - Anthropic Claude
"""
from __future__ import annotations

import logging
from typing import Iterator

from .config import settings

log = logging.getLogger(__name__)


class Provider:
    name = "none"
    generative = False

    def stream(self, system: str, user: str) -> Iterator[str]:
        raise NotImplementedError


class OpenAIProvider(Provider):
    generative = True

    def __init__(self, azure: bool = False) -> None:
        from openai import AzureOpenAI, OpenAI
        if azure:
            self.name = "azure"
            self.client = AzureOpenAI(api_key=settings.AZURE_OPENAI_API_KEY,
                                      azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                                      api_version=settings.AZURE_OPENAI_API_VERSION)
            self.model = settings.AZURE_OPENAI_DEPLOYMENT
        else:
            self.name = "openai"
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            self.model = settings.OPENAI_MODEL

    def stream(self, system: str, user: str) -> Iterator[str]:
        resp = self.client.chat.completions.create(
            model=self.model, stream=True, temperature=0.1,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        for chunk in resp:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class AnthropicProvider(Provider):
    name = "anthropic"
    generative = True

    def __init__(self) -> None:
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def stream(self, system: str, user: str) -> Iterator[str]:
        self.last_stop = ""
        # Generous room: answers are ~170 words, but some models spend part of the budget before writing.
        with self.client.messages.stream(model=settings.ANTHROPIC_MODEL, max_tokens=2000, system=system,
                                         messages=[{"role": "user", "content": user}]) as s:
            for text in s.text_stream:
                yield text
            try:
                self.last_stop = s.get_final_message().stop_reason or ""
            except Exception:
                self.last_stop = ""


def get_provider() -> Provider:
    p = settings.LLM_PROVIDER
    try:
        if p == "openai" and settings.OPENAI_API_KEY:
            return OpenAIProvider()
        if p == "azure" and settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_DEPLOYMENT:
            return OpenAIProvider(azure=True)
        if p == "anthropic" and settings.ANTHROPIC_API_KEY:
            return AnthropicProvider()
    except Exception as e:  # missing package or bad config
        log.warning("LLM provider %s unavailable: %s", p, e)
    if p != "none":
        log.warning("LLM_PROVIDER=%s but its key/settings are missing; using extractive answers.", p)
    return Provider()


# ---------- Embeddings (vector search) ----------

class Embedder:
    name = "none"

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        return None


class OpenAIEmbedder(Embedder):
    def __init__(self, azure: bool = False) -> None:
        from openai import AzureOpenAI, OpenAI
        if azure:
            self.name = "azure"
            self.client = AzureOpenAI(api_key=settings.AZURE_OPENAI_API_KEY,
                                      azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                                      api_version=settings.AZURE_OPENAI_API_VERSION)
            self.model = settings.AZURE_OPENAI_EMBED_DEPLOYMENT
        else:
            self.name = "openai"
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            self.model = settings.OPENAI_EMBED_MODEL

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            resp = self.client.embeddings.create(model=self.model, input=[t[:8000] for t in texts[i:i + 64]])
            out.extend(d.embedding for d in resp.data)
        return out


class LocalEmbedder(Embedder):
    """Small static embedding model (model2vec) that runs on the server itself: no API key, no cost,
    fast on a small CPU. Gives semantic search ("how do I pay my bill" ~ "payment plans") alongside keywords."""
    name = "local"

    def __init__(self) -> None:
        from model2vec import StaticModel
        self.model = StaticModel.from_pretrained(settings.LOCAL_EMBED_MODEL)

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        vecs = self.model.encode([t[:2000] for t in texts], batch_size=256)
        return [[round(float(x), 5) for x in v] for v in vecs]


_local: Embedder | None = None


def _local_embedder() -> Embedder:
    global _local
    if _local is None:
        try:
            _local = LocalEmbedder()
        except Exception as ex:  # model not installed or not downloaded: keyword search only
            log.warning("Local embeddings unavailable: %s", ex)
            _local = Embedder()
    return _local


def get_embedder() -> Embedder:
    e = settings.EMBEDDINGS_PROVIDER
    if e == "auto":
        e = {"openai": "openai", "azure": "azure"}.get(
            settings.LLM_PROVIDER, "openai" if settings.OPENAI_API_KEY else "local")
    if e == "local":
        return _local_embedder()
    try:
        if e == "openai" and settings.OPENAI_API_KEY:
            return OpenAIEmbedder()
        if e == "azure" and settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_EMBED_DEPLOYMENT:
            return OpenAIEmbedder(azure=True)
    except Exception as ex:
        log.warning("Embeddings unavailable: %s", ex)
    return Embedder()
