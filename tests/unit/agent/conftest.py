"""Unit tests never reach a model provider, so each one starts with every
circuit breaker closed and no second embedding provider - whatever the local
.env configures. Tests of the failover itself install their own fakes."""

import pytest

from app import breaker
from app import graph as G


class _NoNetworkEmbeddings:
    async def aembed_query(self, text):
        raise RuntimeError("unit tests must not call an embedding provider")


@pytest.fixture(autouse=True)
def isolated_providers(monkeypatch):
    breaker.reset_all()
    monkeypatch.setattr(G, "fallback_embeddings", None)
    monkeypatch.setattr(G, "embeddings", _NoNetworkEmbeddings())
    yield
    breaker.reset_all()
