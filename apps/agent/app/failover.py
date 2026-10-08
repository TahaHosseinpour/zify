"""Provider chains: try the first provider, move to the next when it fails.

Each kind of model call (chat, embedding) has an ordered list of providers.
A call goes to the first one whose circuit breaker (breaker.py) lets it
through; if that fails, the next one answers the same request. graph.py builds
the chains — this module only knows how to walk one.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Optional

import httpx
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables.config import merge_configs, var_child_runnable_config

from .breaker import breaker, is_provider_fault


class ProvidersUnavailable(RuntimeError):
    """Every provider in the chain is behind an open breaker."""


# ── Chat ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatLink:
    name: str  # also the breaker's name
    model: Any  # anything with `ainvoke(messages, config=...)`
    # `with_structured_output(method=...)`; None keeps the model's default.
    structured_method: Optional[str] = None


class _TokenSeen(BaseCallbackHandler):
    """Notes whether a call has streamed any reply text yet."""

    # Sync handlers otherwise run in a thread pool; this one only sets a flag.
    run_inline = True

    def __init__(self) -> None:
        self.seen = False

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        if token:
            self.seen = True


def _config_with(handler: BaseCallbackHandler) -> dict:
    """The surrounding run's config plus one more callback.

    Passing `callbacks` on its own would *replace* the ones inherited from the
    graph run (token streaming, tracing, usage metering) rather than add to
    them, so the inherited config is merged in explicitly.
    """
    own = {"callbacks": [handler]}
    parent = var_child_runnable_config.get()
    return merge_configs(parent, own) if parent else own


class FailoverChat:
    """A chat model made of several, used exactly like one: `ainvoke(messages)`.

    The nodes in graph.py never learn which provider answered.
    """

    def __init__(self, links: list[ChatLink]) -> None:
        if not links:
            raise ValueError("FailoverChat needs at least one link")
        self.links = links

    @property
    def max_tokens(self) -> Optional[int]:
        return getattr(self.links[0].model, "max_tokens", None)

    def with_structured_output(self, schema: Any) -> "FailoverChat":
        return FailoverChat(
            [
                replace(
                    link,
                    model=link.model.with_structured_output(
                        schema, **({"method": link.structured_method} if link.structured_method else {})
                    ),
                )
                for link in self.links
            ]
        )

    async def ainvoke(self, messages: Any) -> Any:
        last_error: Optional[Exception] = None
        for position, link in enumerate(self.links):
            gate = breaker(f"{link.name}-chat")
            if not gate.allow():
                continue

            streamed = _TokenSeen()
            try:
                result = await link.model.ainvoke(messages, config=_config_with(streamed))
            except Exception as err:  # noqa: BLE001 — any failure moves to the next provider
                if is_provider_fault(err):
                    gate.record_failure()
                else:
                    gate.release()
                if streamed.seen:
                    # Part of this reply is already on the customer's screen.
                    # A second provider would start again from the first word
                    # and the customer would read the opening twice, so the
                    # turn fails instead.
                    raise
                last_error = err
                if position < len(self.links) - 1:
                    print(f"[agent] {link.name} chat failed ({type(err).__name__}: {err}) - trying the next provider")
                continue
            except BaseException:
                # Cancelled (the client went away): says nothing about health.
                gate.release()
                raise

            gate.record_success()
            return result

        if last_error is not None:
            raise last_error
        raise ProvidersUnavailable("no chat provider is available (all circuit breakers are open)")


# ── Embeddings ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmbeddingSpace:
    """One embedding model's vector space, and the column that stores it.

    Vectors from different models cannot be compared, so every row keeps one
    vector per space and a query is only ever measured against the column
    written by the model that embedded the query.
    """

    name: str  # also names the breaker: "<name>-embedding"
    column: str


class Vector(list):
    """An embedding that remembers which space it belongs to."""

    def __init__(self, values, space: EmbeddingSpace) -> None:
        super().__init__(values)
        self.space = space


class GeminiEmbeddings:
    """gemini-embedding-001 over the Generative Language REST API.

    Shaped like the part of OpenAIEmbeddings the agent uses (`aembed_query`,
    `aembed_documents`). Texts go one request each: `batchEmbedContents`
    returns a 500 through Metis.
    """

    def __init__(self, base_url: str, api_key: Optional[str], model: str, dimensions: int, timeout: float) -> None:
        self._url = f"{base_url.rstrip('/')}/models/{model}:embedContent"
        self._api_key = api_key or ""
        self._model = model
        self._dimensions = dimensions
        self._timeout = timeout
        # One client per event loop, so the TLS connection is reused.
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    def _http(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._client is None or self._client_loop is not loop:
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._client_loop = loop
        return self._client

    async def _embed(self, text: str, task_type: str) -> list[float]:
        response = await self._http().post(
            self._url,
            headers={"x-goog-api-key": self._api_key},
            json={
                "model": f"models/{self._model}",
                "content": {"parts": [{"text": text}]},
                # The model embeds a customer's question and a catalog row
                # differently on purpose; retrieval is better when each side
                # says which it is.
                "taskType": task_type,
                "outputDimensionality": self._dimensions,
            },
        )
        response.raise_for_status()
        return [float(v) for v in response.json()["embedding"]["values"]]

    async def aembed_query(self, text: str) -> list[float]:
        return await self._embed(text, "RETRIEVAL_QUERY")

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(await asyncio.gather(*(self._embed(t, "RETRIEVAL_DOCUMENT") for t in texts)))
