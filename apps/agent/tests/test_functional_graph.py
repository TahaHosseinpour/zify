"""Functional tests that build and run the real compiled graph.

Every node is stubbed via monkeypatch (LLM quota was exhausted throughout this
project, so no test may depend on a live model), but the graph itself — nodes,
edges, conditional routing, the `defer=True` join barriers — is the real thing
from build_graph(). These tests exist specifically to catch wiring bugs that
unit tests on individual functions cannot see: the double-fuse regression this
suite pins down actually shipped once, silently, until traced by hand.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from tests.conftest import item

from app import graph as G


def track(monkeypatch, name, order, rows=None, delay=0.0):
    """Patch graph.<name> with a stub that records its call and returns rows
    into retrieved_raw, the same shape every real retrieval node returns."""
    async def node(state):
        if delay:
            await asyncio.sleep(delay)
        order.append(name)
        return {"retrieved_raw": list(rows or [])}

    monkeypatch.setattr(G, name, node)


def track_plain(monkeypatch, name, order, result=None):
    async def node(state):
        order.append(name)
        return dict(result or {})

    monkeypatch.setattr(G, name, node)


@pytest.fixture
def order():
    return []


class TestGraphCompiles:
    def test_build_graph_compiles_without_a_checkpointer(self):
        graph = G.build_graph()
        assert graph is not None

    def test_all_router_targets_exist_as_nodes(self):
        """Every string router_after_intent / route_fan_out_* can return must
        be a real node name in build_graph, or LangGraph raises at compile
        time — but only for the *reachable* combination it tries, so a stale
        target could hide until a specific intent exercised it in production."""
        graph = G.build_graph()
        node_names = set(graph.get_graph().nodes.keys())
        for target in ("fan_out_explore", "fan_out_product", "ask_question",
                       "handle_purchase", "smalltalk_reply"):
            assert target in node_names
        for target in ("sql_filter_explore", "vector_faq_explore", "vector_shop_info_explore"):
            assert target in node_names
        for target in ("sql_query_product", "vector_faq_product", "vector_shop_info_product"):
            assert target in node_names


class TestExploreFanOutBarrier:
    """The SQL→vector chain is two nodes deep; FAQ and shop-info are one. A
    plain multi-edge join only waits for branches that finish in the *same*
    superstep — without defer=True, fuse_results_explore used to run twice,
    and so did suggest_products, doubling the LLM cost per turn silently."""

    async def _run(self, monkeypatch, order, intent="browse"):
        async def analyze(state):
            return {"intent": intent, "mode": "explore", "retrieved_raw": None,
                    "retrieved_context": [], "shown_products": []}

        track_plain(monkeypatch, "maybe_summarize", order, {})
        monkeypatch.setattr(G, "analyze_intent", analyze)
        track(monkeypatch, "sql_filter_explore", order, delay=0.05)  # deepest branch
        track(monkeypatch, "vector_search_explore", order, rows=[item("p1", score=0.5)])
        track(monkeypatch, "vector_faq", order, rows=[item("f1", typ="faq", score=0.3)])
        track(monkeypatch, "vector_shop_info", order, rows=[item("s1", typ="shop_info", score=0.2)])

        real_fuse = G.fuse_results_explore

        async def fuse(state):
            order.append("FUSE")
            return await real_fuse(state)

        monkeypatch.setattr(G, "fuse_results_explore", fuse)
        track_plain(monkeypatch, "suggest_products", order, {"messages": [AIMessage(content="x")]})

        graph = G.build_graph()
        return await graph.ainvoke({"messages": [], "shop_id": "s1", "mode": "explore"}, {})

    async def test_fuse_and_generation_each_run_exactly_once(self, monkeypatch, order):
        await self._run(monkeypatch, order)
        assert order.count("FUSE") == 1
        assert order.count("suggest_products") == 1

    async def test_the_deep_branch_lands_before_fuse_runs(self, monkeypatch, order):
        await self._run(monkeypatch, order)
        fuse_index = order.index("FUSE")
        assert order.index("sql_filter_explore") < fuse_index
        assert order.index("vector_search_explore") < fuse_index

    async def test_all_three_branch_types_reach_the_final_context(self, monkeypatch, order):
        result = await self._run(monkeypatch, order)
        types = {i["type"] for i in result["retrieved_context"]}
        assert types == {"product", "faq", "shop_info"}

    async def test_faq_branch_is_absent_for_a_pure_product_search(self, monkeypatch, order):
        result = await self._run(monkeypatch, order, intent="search_product")
        assert "vector_faq" not in order
        types = {i["type"] for i in result["retrieved_context"]}
        assert "faq" not in types
        assert types == {"product", "shop_info"}


class TestProductFanOutBarrier:
    async def test_fuse_and_generation_each_run_exactly_once(self, monkeypatch, order):
        async def analyze(state):
            return {"intent": "browse", "mode": "product", "product_id": "p9",
                     "retrieved_raw": None, "retrieved_context": []}

        track_plain(monkeypatch, "maybe_summarize", order, {})
        monkeypatch.setattr(G, "analyze_intent", analyze)
        track(monkeypatch, "sql_query_product", order, rows=[item("p9", score=0.1)], delay=0.05)
        track(monkeypatch, "vector_search_product", order, rows=[item("p1", score=0.5)])
        track(monkeypatch, "vector_faq", order, rows=[item("f1", typ="faq", score=0.3)])
        track(monkeypatch, "vector_shop_info", order, rows=[item("s1", typ="shop_info", score=0.2)])

        real_fuse = G.fuse_context_product

        async def fuse(state):
            order.append("FUSE")
            return await real_fuse(state)

        monkeypatch.setattr(G, "fuse_context_product", fuse)
        track_plain(monkeypatch, "product_agent", order, {"messages": [AIMessage(content="x")]})

        graph = G.build_graph()
        result = await graph.ainvoke({"messages": [], "shop_id": "s1", "mode": "product"}, {})

        assert order.count("FUSE") == 1
        assert order.count("product_agent") == 1
        types = sorted(i["type"] for i in result["retrieved_context"])
        assert types == ["faq", "product", "product", "shop_info"]


class TestClosingTurnsSkipRetrieval:
    """Objection/compare/buy_intent must never re-embed the objection text or
    overwrite the numbered list the customer is referring to."""

    async def _run_with_retrieval_tripwire(self, monkeypatch, order, intent, shown):
        async def analyze(state):
            return {"intent": intent, "mode": "explore", "product_id": None,
                     "retrieved_raw": None, "retrieved_context": [],
                     "shown_products": shown, "objection": "price"}

        async def tripwire(state):
            order.append("RETRIEVAL_RAN")
            return {"retrieved_raw": []}

        track_plain(monkeypatch, "maybe_summarize", order, {})
        monkeypatch.setattr(G, "analyze_intent", analyze)
        for name in ("sql_filter_explore", "vector_search_explore", "vector_faq", "vector_shop_info"):
            monkeypatch.setattr(G, name, tripwire)

        async def fake_llm_invoke(messages):
            order.append("LLM")
            return AIMessage(content="پاسخ")

        class FakeLLM:
            ainvoke = staticmethod(fake_llm_invoke)

        monkeypatch.setattr(G, "llm", FakeLLM())

        class FakeShopTable:
            @staticmethod
            async def find_unique(**kw):
                return None

        class FakeDB:
            shop = FakeShopTable()

        monkeypatch.setattr(G, "db", FakeDB())

        graph = G.build_graph()
        return await graph.ainvoke({"messages": [], "shop_id": "s1", "mode": "explore"}, {})

    @pytest.mark.parametrize("intent", ["objection", "compare", "buy_intent"])
    async def test_no_retrieval_node_ever_runs(self, monkeypatch, order, intent):
        shown = [item("p1", price=1000, url="https://shop/1")]
        await self._run_with_retrieval_tripwire(monkeypatch, order, intent, shown)
        assert "RETRIEVAL_RAN" not in order
        assert order.count("LLM") == 1

    async def test_shown_products_are_put_back_in_retrieved_context(self, monkeypatch, order):
        shown = [item("p1", price=1000, url="https://shop/1"), item("p2", price=2000)]
        result = await self._run_with_retrieval_tripwire(monkeypatch, order, "objection", shown)
        assert [i["id"] for i in result["retrieved_context"]] == ["p1", "p2"]

    async def test_delay_objection_turns_off_buy_actions(self, monkeypatch, order):
        shown = [item("p1", price=1000, url="https://shop/1")]

        async def analyze(state):
            return {"intent": "objection", "mode": "explore", "product_id": None,
                     "retrieved_raw": None, "retrieved_context": [],
                     "shown_products": shown, "objection": "delay"}

        track_plain(monkeypatch, "maybe_summarize", order, {})
        monkeypatch.setattr(G, "analyze_intent", analyze)

        async def fake_llm_invoke(messages):
            return AIMessage(content="پاسخ")

        class FakeLLM:
            ainvoke = staticmethod(fake_llm_invoke)

        monkeypatch.setattr(G, "llm", FakeLLM())

        class FakeShopTable:
            @staticmethod
            async def find_unique(**kw):
                return None

        class FakeDB:
            shop = FakeShopTable()

        monkeypatch.setattr(G, "db", FakeDB())

        graph = G.build_graph()
        result = await graph.ainvoke({"messages": [], "shop_id": "s1", "mode": "explore"}, {})
        assert result["buy_actions"] is False

    async def test_buy_intent_keeps_buy_actions_on(self, monkeypatch, order):
        shown = [item("p1", price=1000, url="https://shop/1")]
        result = await self._run_with_retrieval_tripwire(monkeypatch, order, "buy_intent", shown)
        assert result["buy_actions"] is True
