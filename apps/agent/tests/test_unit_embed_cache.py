"""Unit tests for the embed() memoisation layer.

Three fan-out branches embed the same query text concurrently; without
sharing, that's three paid API calls per turn for identical input. This is
also the kind of concurrency bug that only shows up under real overlap, not
when you eyeball the code, so it's exercised with real asyncio concurrency
rather than sequential awaits.
"""

import asyncio

import pytest

from app import graph as G


@pytest.fixture(autouse=True)
def clear_embed_cache():
    G._embed_cache.clear()
    G._embed_inflight.clear()
    yield
    G._embed_cache.clear()
    G._embed_inflight.clear()


def install_fake_embeddings(monkeypatch, delay=0.02, vec=(0.5, 0.5)):
    calls = {"n": 0}

    class FakeEmbeddings:
        async def aembed_query(self, text):
            calls["n"] += 1
            await asyncio.sleep(delay)
            return list(vec)

    monkeypatch.setattr(G, "embeddings", FakeEmbeddings())
    return calls


class TestEmbedSharing:
    async def test_concurrent_calls_for_the_same_text_hit_the_api_once(self, monkeypatch):
        calls = install_fake_embeddings(monkeypatch)
        results = await asyncio.gather(*[G.embed("لپ تاپ گیمینگ") for _ in range(5)])
        assert calls["n"] == 1
        assert all(r == results[0] for r in results)

    async def test_different_texts_each_get_their_own_call(self, monkeypatch):
        calls = install_fake_embeddings(monkeypatch)
        await asyncio.gather(G.embed("متن ۱"), G.embed("متن ۲"))
        assert calls["n"] == 2

    async def test_repeat_call_after_completion_is_served_from_cache(self, monkeypatch):
        calls = install_fake_embeddings(monkeypatch)
        await G.embed("لپ تاپ")
        await G.embed("لپ تاپ")
        assert calls["n"] == 1

    async def test_failed_call_does_not_poison_the_text_for_later_turns(self, monkeypatch):
        class BoomOnce:
            def __init__(self):
                self.calls = 0

            async def aembed_query(self, text):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("upstream 402")
                return [0.1]

        fake = BoomOnce()
        monkeypatch.setattr(G, "embeddings", fake)

        with pytest.raises(RuntimeError):
            await G.embed("متن")

        assert "متن" not in G._embed_inflight
        # A later attempt must actually retry, not reuse a poisoned cache entry.
        result = await G.embed("متن")
        assert result == [0.1]
        assert fake.calls == 2

    async def test_cache_is_bounded_and_evicts_oldest(self, monkeypatch):
        install_fake_embeddings(monkeypatch)
        monkeypatch.setattr(G, "_EMBED_CACHE_MAX", 2)
        await G.embed("a")
        await G.embed("b")
        await G.embed("c")  # evicts "a"
        assert "a" not in G._embed_cache
        assert "b" in G._embed_cache
        assert "c" in G._embed_cache

    async def test_a_waiting_call_gets_the_same_vector_the_winner_produced(self, monkeypatch):
        install_fake_embeddings(monkeypatch, vec=(1.0, 2.0, 3.0))
        a, b = await asyncio.gather(G.embed("x"), G.embed("x"))
        assert a == [1.0, 2.0, 3.0]
        assert b == a
