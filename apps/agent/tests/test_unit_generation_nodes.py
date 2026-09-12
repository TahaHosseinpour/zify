"""Unit tests for the terminal generation nodes: suggest_products,
product_agent, ask_question, smalltalk_reply, handle_purchase.

These are the nodes that actually produce the text (and the retrieved_context)
a customer sees. LLM and shop/product lookups are stubbed via the fake_llm /
fake_shop_db fixtures; what's under test is that each node builds its prompt
from the right pieces of state and returns the shape server.py expects.
"""

from tests.conftest import item

from app import graph as G


def base_state(**overrides):
    state = {
        "shop_id": "s1",
        "messages": [],
        "retrieved_context": [],
        "stage": "browsing",
        "value_driver": None,
        "objection": None,
        "filters_dropped": [],
        "out_of_catalog": False,
        "summary": None,
    }
    state.update(overrides)
    return state


class TestSuggestProducts:
    async def test_returns_the_llm_reply_as_a_message(self, fake_llm, fake_shop_db):
        result = await G.suggest_products(base_state())
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "پاسخ آزمایشی"

    async def test_out_of_catalog_flag_reaches_the_prompt(self, fake_llm, fake_shop_db):
        await G.suggest_products(base_state(out_of_catalog=True))
        last_prompt = fake_llm[-1]
        context_message = last_prompt[-1].content
        assert "ندارد" in context_message or "موجود" in context_message

    async def test_filters_dropped_reaches_the_prompt(self, fake_llm, fake_shop_db):
        await G.suggest_products(base_state(filters_dropped=["maxPrice"]))
        last_prompt = fake_llm[-1]
        context_message = last_prompt[-1].content
        assert "محدودیت" in context_message

    async def test_retrieved_products_are_listed_in_the_prompt(self, fake_llm, fake_shop_db):
        products = [item("p1", score=0.1), item("p2", score=0.2)]
        await G.suggest_products(base_state(retrieved_context=products))
        last_prompt = fake_llm[-1]
        context_message = last_prompt[-1].content
        assert "content-p1" in context_message
        assert "content-p2" in context_message

    async def test_missing_shop_short_circuits_without_calling_the_llm(self, fake_llm, monkeypatch):
        class NoShop:
            @staticmethod
            async def find_unique(**kw):
                return None

        class FakeDB:
            shop = NoShop()

        monkeypatch.setattr(G, "db", FakeDB())
        result = await G.suggest_products(base_state())
        assert "فروشگاه یافت نشد" in result["messages"][0].content
        assert fake_llm == []  # never reached the LLM call


class TestProductAgent:
    async def test_returns_the_llm_reply(self, fake_llm, fake_shop_db):
        result = await G.product_agent(base_state())
        assert result["messages"][0].content == "پاسخ آزمایشی"

    async def test_uses_the_product_prompt_builder_not_the_explore_one(self, fake_llm, fake_shop_db, monkeypatch):
        calls = {"product": 0, "explore": 0}
        real_product = G.build_product_prompt
        real_explore = G.build_explore_prompt

        def tracked_product(*a, **kw):
            calls["product"] += 1
            return real_product(*a, **kw)

        def tracked_explore(*a, **kw):
            calls["explore"] += 1
            return real_explore(*a, **kw)

        monkeypatch.setattr(G, "build_product_prompt", tracked_product)
        monkeypatch.setattr(G, "build_explore_prompt", tracked_explore)
        await G.product_agent(base_state())
        assert calls["product"] == 1
        assert calls["explore"] == 0


class TestAskQuestion:
    async def test_returns_the_llm_reply(self, fake_llm, fake_shop_db, monkeypatch):
        async def fake_embed(text):
            return [0.1]

        async def no_faq(shop_id, vec, k):
            return []

        async def no_shop_info(shop_id, vec, k):
            return []

        monkeypatch.setattr(G, "embed", fake_embed)
        monkeypatch.setattr(G, "vector_search_faq", no_faq)
        monkeypatch.setattr(G, "vector_search_shop_info", no_shop_info)

        result = await G.ask_question(base_state(messages=[]))
        assert result["messages"][0].content == "پاسخ آزمایشی"

    async def test_out_of_catalog_adds_the_no_interrogation_instruction(
        self, fake_llm, fake_shop_db, monkeypatch
    ):
        async def fake_embed(text):
            return [0.1]

        async def no_faq(shop_id, vec, k):
            return []

        async def no_shop_info(shop_id, vec, k):
            return []

        async def categories(shop_id):
            return ["کفش"]

        monkeypatch.setattr(G, "embed", fake_embed)
        monkeypatch.setattr(G, "vector_search_faq", no_faq)
        monkeypatch.setattr(G, "vector_search_shop_info", no_shop_info)
        monkeypatch.setattr(G, "shop_categories", categories)

        await G.ask_question(base_state(out_of_catalog=True))
        prompt_text = fake_llm[-1][-1].content
        assert "ندارد" in prompt_text
        assert "کفش" in prompt_text  # available categories are suggested

    async def test_needs_clarification_adds_the_clarify_instruction(self, fake_llm, fake_shop_db, monkeypatch):
        async def fake_embed(text):
            return [0.1]

        async def no_faq(shop_id, vec, k):
            return []

        async def no_shop_info(shop_id, vec, k):
            return []

        monkeypatch.setattr(G, "embed", fake_embed)
        monkeypatch.setattr(G, "vector_search_faq", no_faq)
        monkeypatch.setattr(G, "vector_search_shop_info", no_shop_info)

        await G.ask_question(base_state(intent="needs_clarification"))
        prompt_text = fake_llm[-1][-1].content
        assert "سوال کوتاه" in prompt_text


class TestSmalltalkReply:
    async def test_clears_retrieved_context_and_does_not_touch_shown_products(self, fake_llm, fake_shop_db):
        result = await G.smalltalk_reply(base_state())
        assert result["retrieved_context"] == []
        assert "shown_products" not in result

    async def test_instructs_the_model_not_to_suggest_products(self, fake_llm, fake_shop_db):
        await G.smalltalk_reply(base_state())
        prompt_text = fake_llm[-1][-1].content
        assert "هیچ محصولی پیشنهاد نده" in prompt_text


class TestHandlePurchase:
    async def test_no_pinned_product_uses_shown_products_list(self, fake_llm, fake_shop_db):
        shown = [item("p1", url="https://shop/1"), item("p2")]
        result = await G.handle_purchase(
            base_state(product_id=None, shown_products=shown, intent="buy_intent")
        )
        assert result["retrieved_context"] == shown
        assert result["buy_actions"] is True

    async def test_pinned_product_overrides_the_shown_list(self, fake_llm, fake_shop_db):
        pinned_product = type(
            "P", (), {
                "id": "pinned1", "name": "n", "price": 100, "description": None,
                "category": None, "brand": None, "productUrl": "https://shop/pinned",
                "imageUrl": None, "stock": 1,
            },
        )()
        fake_shop_db["pinned1"] = pinned_product
        result = await G.handle_purchase(
            base_state(product_id="pinned1", shown_products=[item("other")], intent="buy_intent")
        )
        assert [i["id"] for i in result["retrieved_context"]] == ["pinned1"]

    async def test_nothing_on_the_table_asks_instead_of_guessing(self, fake_llm, fake_shop_db):
        await G.handle_purchase(base_state(product_id=None, shown_products=[], intent="buy_intent"))
        prompt_text = fake_llm[-1][-1].content
        assert "کوتاه بپرس" in prompt_text

    async def test_delay_move_never_sets_buy_actions(self, fake_llm, fake_shop_db):
        shown = [item("p1", url="https://shop/1")]
        result = await G.handle_purchase(
            base_state(product_id=None, shown_products=shown, intent="objection", objection="delay")
        )
        assert result["buy_actions"] is False
