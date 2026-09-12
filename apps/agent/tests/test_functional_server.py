"""Functional tests for the /chat HTTP contract both clients (Telegram bot and
the admin playground) depend on.

An async httpx client over ASGITransport is used instead of FastAPI's sync
TestClient. TestClient runs each request on its own portal thread with its own
event loop, separate from the pytest-asyncio session loop that connects
`real_db` — and Prisma's client holds loop-bound internals (an asyncio.Event),
so a handler that touches the real db from that other loop breaks with
"bound to a different event loop". Requesting over ASGITransport in an async
test runs the handler on the *same* loop as everything else in this session.

ASGITransport does not invoke the lifespan protocol, same as a bare
TestClient(app) without the `with` block, so the real DB-connecting lifespan
never fires — app.state.graph is set directly to a graph built from
build_graph() with every node stubbed. chat_config is stubbed too, so nothing
here depends on the Langfuse container being reachable.

This is exactly the layer where the buy_actions / purchaseUrl / mode+productId
bugs shipped: the underlying graph logic was correct in isolation, but nothing
verified the shape of what actually crossed the wire to a client.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from tests.conftest import item

from app import graph as G
from app import server as S


def new_client():
    return AsyncClient(transport=ASGITransport(app=S.app), base_url="http://test")


def build_stubbed_app(monkeypatch, analyze_result, search_results=None):
    """A real compiled graph with analyze_intent stubbed to a fixed decision
    and every LLM/DB call stubbed, wired into the real FastAPI app."""

    async def analyze(state):
        return dict(analyze_result)

    monkeypatch.setattr(G, "analyze_intent", analyze)

    async def no_summarize(state):
        return {}

    monkeypatch.setattr(G, "maybe_summarize", no_summarize)

    async def fake_llm_invoke(messages):
        return AIMessage(content="پاسخ آزمایشی")

    class FakeLLM:
        ainvoke = staticmethod(fake_llm_invoke)

    monkeypatch.setattr(G, "llm", FakeLLM())

    class FakeShopTable:
        @staticmethod
        async def find_unique(**kw):
            return None  # generation nodes fall back to an empty system prompt

    class FakeProductTable:
        @staticmethod
        async def find_first(**kw):
            return None

    class FakeDB:
        shop = FakeShopTable()
        product = FakeProductTable()

        @staticmethod
        async def query_raw(*a, **kw):
            return []

    monkeypatch.setattr(G, "db", FakeDB())

    async def no_retrieval(state):
        return {"retrieved_raw": []}

    for name in ("sql_filter_explore", "vector_faq",
                 "vector_shop_info", "sql_query_product", "vector_search_product"):
        monkeypatch.setattr(G, name, no_retrieval)

    # vector_search_explore is the one branch a test can populate: fuse_results_
    # explore is real, so this is what actually reaches retrieved_context/
    # shown_products — an analyze_intent stub setting retrieved_context
    # directly would just get overwritten by that real fuse node, same as
    # in production.
    async def vector_search_stub(state):
        return {"retrieved_raw": list(search_results or [])}

    monkeypatch.setattr(G, "vector_search_explore", vector_search_stub)

    def fake_chat_config(thread_id, shop_id, mode, product_id=None):
        return {"configurable": {"thread_id": thread_id}}

    monkeypatch.setattr(S, "chat_config", fake_chat_config)

    S.app.state.graph = G.build_graph()
    return new_client()


REQUIRED_BODY = {"shopId": "s1", "threadId": "s1:u1", "message": "سلام"}


class TestHealth:
    async def test_health_reports_ok(self):
        async with new_client() as client:
            res = await client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"ok": True}


class TestChatErrorHandling:
    async def test_an_exception_inside_a_node_becomes_a_generic_500(self, monkeypatch):
        """A customer must never see a stack trace or an internal error
        message — whatever broke inside the graph, /chat's contract is a
        opaque 500 with a fixed body."""

        async def boom(state):
            raise RuntimeError("something exploded inside a node")

        monkeypatch.setattr(G, "analyze_intent", boom)

        async def no_summarize(state):
            return {}

        monkeypatch.setattr(G, "maybe_summarize", no_summarize)

        def fake_chat_config(thread_id, shop_id, mode, product_id=None):
            return {"configurable": {"thread_id": thread_id}}

        monkeypatch.setattr(S, "chat_config", fake_chat_config)
        S.app.state.graph = G.build_graph()

        async with new_client() as client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        assert res.status_code == 500
        assert res.json() == {"error": "internal error"}
        assert "RuntimeError" not in res.text
        assert "exploded" not in res.text


@pytest.mark.db
class TestResetMemory:
    """Runs against the real database — the endpoint's whole job is a raw
    DELETE across the checkpoint tables, which a mock can't meaningfully
    verify (does the LIKE pattern actually scope to one shop, does a missing
    table get tolerated rather than 500ing)."""

    async def test_missing_shop_id_is_a_400(self):
        async with new_client() as client:
            res = await client.post("/admin/reset-memory", json={})
        assert res.status_code == 400

    async def test_deletes_only_rows_for_the_given_shop(self, real_db):
        # Unique per run: a prior failed run must never leave a row behind
        # that collides with this run's INSERT and turns a real failure into a
        # false "table not present" skip.
        run = uuid.uuid4().hex[:8]
        target_shop = f"test-shop-{run}"
        other_shop = f"other-shop-{run}"
        thread_id = f"{target_shop}:end-user-1"
        other_thread_id = f"{other_shop}:end-user-1"
        try:
            try:
                await real_db.execute_raw(
                    "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, "
                    "checkpoint, metadata) VALUES ($1, '', 'c1', '{}', '{}')",
                    thread_id,
                )
                await real_db.execute_raw(
                    "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, "
                    "checkpoint, metadata) VALUES ($1, '', 'c1', '{}', '{}')",
                    other_thread_id,
                )
            except Exception as exc:
                pytest.skip(f"checkpoints table not usable in this environment: {exc}")

            async with new_client() as client:
                res = await client.post("/admin/reset-memory", json={"shopId": target_shop})
            assert res.status_code == 200
            assert res.json()["deletedRows"] >= 1

            remaining = await real_db.query_raw(
                "SELECT thread_id FROM checkpoints WHERE thread_id = $1", thread_id
            )
            assert remaining == []

            untouched = await real_db.query_raw(
                "SELECT thread_id FROM checkpoints WHERE thread_id = $1", other_thread_id
            )
            assert len(untouched) == 1
        finally:
            await real_db.execute_raw(
                "DELETE FROM checkpoints WHERE thread_id IN ($1, $2)", thread_id, other_thread_id
            )


class TestChatValidation:
    async def test_missing_shop_id_is_a_400(self):
        async with new_client() as client:
            res = await client.post("/chat", json={"threadId": "t", "message": "hi"})
        assert res.status_code == 400

    async def test_missing_message_is_a_400(self):
        async with new_client() as client:
            res = await client.post("/chat", json={"shopId": "s1", "threadId": "t"})
        assert res.status_code == 400

    async def test_missing_thread_id_is_a_400(self):
        async with new_client() as client:
            res = await client.post("/chat", json={"shopId": "s1", "message": "hi"})
        assert res.status_code == 400


class TestChatResponseShape:
    async def test_smalltalk_turn_has_no_products_and_shows_buy_actions_by_default(self, monkeypatch):
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "smalltalk", "mode": "explore", "retrieved_raw": None,
             "retrieved_context": [], "buy_actions": True},
        )
        async with client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        assert res.status_code == 200
        body = res.json()
        assert body["reply"] == "پاسخ آزمایشی"
        assert body["products"] == []
        assert body["purchaseUrl"] is None
        assert body["showBuyActions"] is True

    async def test_search_turn_returns_products_and_a_pinned_url_when_unambiguous(self, monkeypatch):
        # A single result is unambiguous even with no explicit pin — matches
        # single_purchase_url's own rule (see test_unit_closing.py).
        found = [item("p1", price=1000, url="https://shop/1", score=0.1)]
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "search_product", "mode": "explore", "product_id": None,
             "retrieved_raw": None, "retrieved_context": [], "buy_actions": True},
            search_results=found,
        )
        async with client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        body = res.json()
        assert body["suggestedProductIds"] == ["p1"]
        assert body["purchaseUrl"] == "https://shop/1"
        assert body["products"][0]["price"] == 1000

    async def test_six_products_no_pin_gives_no_ambiguous_purchase_url(self, monkeypatch):
        found = [item(f"p{i}", price=1000 * i, url=f"https://shop/{i}", score=0.1 * i)
                 for i in range(1, 7)]
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "search_product", "mode": "explore", "product_id": None,
             "retrieved_raw": None, "retrieved_context": [], "buy_actions": True},
            search_results=found,
        )
        async with client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        body = res.json()
        assert len(body["products"]) == 6
        assert body["purchaseUrl"] is None

    async def test_delay_objection_turns_off_buy_actions_over_the_wire(self, monkeypatch):
        # This is the exact regression this project fixed: a "let me think"
        # reply must not carry showBuyActions: true to the client.
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "objection", "mode": "explore", "objection": "delay",
             "product_id": None, "retrieved_raw": None,
             "retrieved_context": [item("p1", price=1000, url="https://shop/1")],
             "buy_actions": False},
        )
        async with client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        body = res.json()
        assert body["showBuyActions"] is False

    async def test_missing_buy_actions_key_defaults_to_true(self, monkeypatch):
        # A node that forgets to set buy_actions must not silently suppress
        # buy buttons everywhere by accident.
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "browse", "mode": "explore", "retrieved_raw": None,
             "retrieved_context": []},
        )
        async with client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        assert res.json()["showBuyActions"] is True

    async def test_mode_and_product_id_round_trip_for_the_next_turn(self, monkeypatch):
        # Both the Telegram bot and the playground carry these forward as the
        # next turn's request — this is the exact bug where mode/productId
        # got silently reset every turn.
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "search_product", "mode": "product", "product_id": "p1",
             "retrieved_raw": None, "retrieved_context": []},
        )
        async with client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        body = res.json()
        assert body["mode"] == "product"
        assert body["productId"] == "p1"

    async def test_debug_flag_off_by_default(self, monkeypatch):
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "browse", "mode": "explore", "retrieved_raw": None, "retrieved_context": []},
        )
        async with client:
            res = await client.post("/chat", json=REQUIRED_BODY)
        assert "debug" not in res.json()

    async def test_debug_flag_on_includes_the_state_panel_payload(self, monkeypatch):
        client = build_stubbed_app(
            monkeypatch,
            {"intent": "browse", "mode": "explore", "retrieved_raw": None, "retrieved_context": []},
        )
        async with client:
            res = await client.post("/chat", json={**REQUIRED_BODY, "debug": True})
        debug = res.json()["debug"]
        assert "path" in debug
        assert "filterStatus" in debug
        assert "latencyMs" in debug
        assert debug["latencyMs"] >= 0
