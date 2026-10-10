"""EMBEDDING_PROVIDER_ORDER, and the cache the benchmarks empty between systems."""

from app import graph as G


class _Embedder:
    async def aembed_query(self, text):
        return [1.0]


def test_the_default_order_asks_the_primary_provider_first(monkeypatch):
    monkeypatch.setattr(G, "fallback_embeddings", _Embedder())
    monkeypatch.setattr(G, "EMBEDDING_PROVIDER_ORDER", [])
    assert [space.name for space, _ in G._embedding_chain()] == [G.PRIMARY_SPACE.name, "gemini"]


def test_a_configured_order_puts_gemini_first(monkeypatch):
    monkeypatch.setattr(G, "fallback_embeddings", _Embedder())
    monkeypatch.setattr(G, "EMBEDDING_PROVIDER_ORDER", ["gemini", G.PRIMARY_SPACE.name])
    assert [space.name for space, _ in G._embedding_chain()] == ["gemini", G.PRIMARY_SPACE.name]


def test_an_unlisted_provider_keeps_its_place_behind_the_listed_ones(monkeypatch):
    monkeypatch.setattr(G, "fallback_embeddings", _Embedder())
    monkeypatch.setattr(G, "EMBEDDING_PROVIDER_ORDER", ["gemini"])
    assert [space.name for space, _ in G._embedding_chain()] == ["gemini", G.PRIMARY_SPACE.name]


def test_clearing_the_caches_empties_both_spaces():
    G._embed_cache["a"] = [1.0]
    G._fallback_embed_cache["a"] = [2.0]
    G.clear_embed_caches()
    assert not G._embed_cache and not G._fallback_embed_cache
