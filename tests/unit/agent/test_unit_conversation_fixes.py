"""Unit tests for behaviours fixed after the four-way comparison benchmark:
a price objection that poisoned the next search, clarifying questions asked in
a loop, objections answered without the shop's own facts, a second product in
the same message, and cards that did not follow the reply.
"""

from langchain_core.messages import AIMessage, HumanMessage

from app import graph as G
from app.graph import ExploreFiltersModel, IntentResult
from app.prompts import build_explore_prompt
from tests.conftest import item
from tests.unit.agent.test_unit_analyze_intent import base_state, install_classifier


class TestObjectionDoesNotBecomeAFilter:
    async def test_the_price_and_brand_of_the_product_objected_to_are_not_searched_by(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="objection", objection="price",
                         explore_filters=ExploreFiltersModel(brand="دل", maxPrice=24_000_000)),
        )
        updates = await G.analyze_intent(base_state(explore_filters={"category": "لپ‌تاپ"}))
        assert updates["explore_filters"] == {"category": "لپ‌تاپ"}
        assert updates["price_anchor"] == 24_000_000

    async def test_cheaper_is_measured_against_the_price_objected_to(self, monkeypatch):
        install_classifier(monkeypatch, IntentResult(intent="search_product", relative_price="cheaper"))
        shown = [item("cheap", price=15_200_000), item("mid", price=19_800_000)]
        updates = await G.analyze_intent(base_state(shown_products=shown, price_anchor=24_000_000.0))
        assert updates["explore_filters"]["maxPrice"] == 24_000_000 - G.PRICE_EPSILON
        # Used once: the next "cheaper" is measured against what was shown.
        assert updates["price_anchor"] is None

    async def test_cheaper_than_the_product_objected_to_is_not_limited_to_its_brand(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", relative_price="cheaper",
                         explore_filters=ExploreFiltersModel(brand="دل")),
            brands=["دل", "نایک"],
        )
        updates = await G.analyze_intent(
            base_state(explore_filters={"category": "لپ‌تاپ"}, price_anchor=24_000_000.0)
        )
        assert "brand" not in updates["explore_filters"]
        # A brand the customer asked for before the objection still holds.
        updates = await G.analyze_intent(
            base_state(explore_filters={"brand": "نایک"}, price_anchor=2_000_000.0)
        )
        assert updates["explore_filters"]["brand"] == "نایک"

    async def test_without_an_objection_cheaper_still_means_cheaper_than_the_list(self, monkeypatch):
        install_classifier(monkeypatch, IntentResult(intent="search_product", relative_price="cheaper"))
        shown = [item("cheap", price=15_200_000), item("mid", price=19_800_000)]
        updates = await G.analyze_intent(base_state(shown_products=shown))
        assert updates["explore_filters"]["maxPrice"] == 15_200_000 - G.PRICE_EPSILON

    async def test_a_new_topic_forgets_the_anchor(self, monkeypatch):
        install_classifier(monkeypatch, IntentResult(intent="search_product", new_topic=True))
        updates = await G.analyze_intent(base_state(price_anchor=24_000_000.0))
        assert updates["price_anchor"] is None


class TestOneClarifyingQuestionPerTopic:
    async def test_the_first_vague_message_gets_a_question_and_becomes_the_search_query(self, monkeypatch):
        install_classifier(monkeypatch, IntentResult(intent="needs_clarification"))
        state = base_state(messages=[HumanMessage(content="برای تولد خانمم یه هدیه می‌خوام")])
        updates = await G.analyze_intent(state)
        assert updates["intent"] == "needs_clarification"
        assert updates["clarify_count"] == 1
        assert updates["must_suggest"] is False
        assert updates["explore_filters"]["query"] == "برای تولد خانمم یه هدیه می‌خوام"

    async def test_a_second_one_in_a_row_becomes_a_search_that_must_suggest(self, monkeypatch):
        install_classifier(monkeypatch, IntentResult(intent="needs_clarification"))
        updates = await G.analyze_intent(base_state(clarify_count=1, explore_filters={"query": "هدیه"}))
        assert updates["intent"] == "search_product"
        assert updates["must_suggest"] is True
        assert updates["explore_filters"]["query"] == "هدیه"
        assert G.router_after_intent({**base_state(), **updates}) == "fan_out_explore"

    async def test_a_new_topic_may_be_asked_about_again(self, monkeypatch):
        install_classifier(monkeypatch, IntentResult(intent="needs_clarification", new_topic=True))
        updates = await G.analyze_intent(base_state(clarify_count=1))
        assert updates["intent"] == "needs_clarification"
        assert updates["clarify_count"] == 1

    def test_an_owed_suggestion_is_not_cut_by_the_distance_floor(self):
        far = item("gift", score=G.RELEVANCE_MAX_DISTANCE + 0.1)
        state = {"retrieved_raw": [far], "must_suggest": True}
        assert G._rank_and_trim(state, 6) == [far]
        assert G._rank_and_trim({"retrieved_raw": [far]}, 6) == []


class TestAlsoNamed:
    def scoped(self):
        return [item("shoe", score=0.4) | {"metadata": {"name": "کفش دویدن نایک پگاسوس"}}]

    def state(self, text):
        return {
            "shop_id": "s1",
            "messages": [HumanMessage(content=text)],
            "filter_effective": {"category": "کفش ورزشی"},
        }

    def install(self, monkeypatch, names):
        async def fake_search(shop_id, vec, k, candidate_ids=None, filters=None, exclude_ids=None):
            assert "category" not in (filters or {})
            return [item(n, score=0.6) | {"metadata": {"name": n}} for n in names]

        monkeypatch.setattr(G, "vector_search_products", fake_search)

    async def test_a_second_product_named_in_the_message_is_added(self, monkeypatch):
        self.install(monkeypatch, ["جوراب ورزشی بسته ۳تایی", "ساک ورزشی"])
        added = await G._also_named(
            self.state("یه کفش دویدن می‌خوام با یه بسته جوراب ورزشی"), [0.0], self.scoped()
        )
        assert [i["id"] for i in added] == ["جوراب ورزشی بسته ۳تایی"]
        # Ranked with the best in-category row, not left for the gap to trim.
        assert added[0]["score"] == 0.4

    async def test_another_kind_of_the_same_thing_is_not(self, monkeypatch):
        self.install(monkeypatch, ["کفش کتانی روزمره ریباک"])
        assert await G._also_named(self.state("کفش دویدن می‌خوام"), [0.0], self.scoped()) == []

    async def test_a_product_the_message_does_not_name_is_not(self, monkeypatch):
        self.install(monkeypatch, ["جوراب ورزشی بسته ۳تایی"])
        assert await G._also_named(self.state("کفش دویدن می‌خوام"), [0.0], self.scoped()) == []

    async def test_it_only_looks_when_a_category_scoped_the_search(self, monkeypatch):
        self.install(monkeypatch, ["جوراب ورزشی بسته ۳تایی"])
        state = {**self.state("کفش با جوراب"), "filter_effective": {}}
        assert await G._also_named(state, [0.0], self.scoped()) == []


class TestNothingElsePrompt:
    def test_a_rejected_only_option_is_not_described_as_out_of_stock(self):
        prompt = build_explore_prompt([], "browsing", out_of_catalog=True, nothing_else=True)
        assert "مدل دیگری از این کالا موجود نیست" in prompt
        assert "فروشگاه چیزی که مشتری خواسته را ندارد" not in prompt
        # No objection move on top: the product it is about was just turned down.
        with_objection = build_explore_prompt([], "browsing", objection="uncertainty", nothing_else=True)
        assert "نگرانش کرده" not in with_objection

    def test_it_applies_only_to_a_product_search_after_a_rejection(self):
        empty = {"intent": "search_product", "excluded_product_ids": ["p1"], "retrieved_context": []}
        assert G._nothing_else(empty)
        assert not G._nothing_else({**empty, "excluded_product_ids": []})
        assert not G._nothing_else({**empty, "intent": "browse"})
        assert not G._nothing_else({**empty, "retrieved_context": [item("p2")]})


class TestHandlePurchase:
    def two_laptops(self):
        return [
            item("lenovo") | {"metadata": {"name": "لپ‌تاپ دانشجویی لنوو آیدیاپد", "productUrl": "u1"}},
            item("asus") | {"metadata": {"name": "لپ‌تاپ دانشجویی ایسوس ویووبوک", "productUrl": "u2"}},
        ]

    def install_llm(self, monkeypatch, reply):
        prompts = []

        class FakeLLM:
            @staticmethod
            async def ainvoke(messages):
                prompts.append(messages[-1].content)
                return AIMessage(content=reply)

        monkeypatch.setattr(G, "llm", FakeLLM())
        return prompts

    async def test_buying_one_of_two_shows_only_the_card_the_reply_names(self, monkeypatch, fake_shop_db):
        self.install_llm(monkeypatch, "عالی! لپ‌تاپ دانشجویی لنوو آیدیاپد — لینک خرید: u1")
        result = await G.handle_purchase(
            {"shop_id": "s1", "messages": [], "intent": "buy_intent", "shown_products": self.two_laptops()}
        )
        assert [i["id"] for i in result["retrieved_context"]] == ["lenovo"]

    async def test_a_reply_that_names_neither_keeps_both(self, monkeypatch, fake_shop_db):
        self.install_llm(monkeypatch, "کدام را می‌خواهید؟")
        result = await G.handle_purchase(
            {"shop_id": "s1", "messages": [], "intent": "buy_intent", "shown_products": self.two_laptops()}
        )
        assert len(result["retrieved_context"]) == 2

    async def test_an_uncertainty_objection_is_given_the_shops_own_facts(self, monkeypatch, fake_shop_db):
        async def fake_facts(state):
            return "\n\n## سوالات متداول و اطلاعات کسب‌وکار:\nهمه محصولات ۷ روز ضمانت بازگشت دارند."

        monkeypatch.setattr(G, "_shop_facts", fake_facts)
        prompts = self.install_llm(monkeypatch, "پاسخ")
        state = {"shop_id": "s1", "messages": [], "intent": "objection", "shown_products": self.two_laptops()[:1]}
        await G.handle_purchase({**state, "objection": "uncertainty"})
        assert "۷ روز ضمانت بازگشت" in prompts[-1]
        # So is "شاید از جای دیگه بخرم": the facts are the reason to stay.
        await G.handle_purchase({**state, "objection": "delay"})
        assert "۷ روز ضمانت بازگشت" in prompts[-1]
        # A customer who has decided needs none of it.
        await G.handle_purchase({**state, "intent": "buy_intent"})
        assert "۷ روز ضمانت بازگشت" not in prompts[-1]

    async def test_a_price_objection_is_offered_only_cheaper_products_not_already_shown(self, monkeypatch, fake_shop_db):
        seen = {}

        async def fake_embed(text):
            seen["text"] = text
            return [0.0]

        async def fake_search(shop_id, vec, k, candidate_ids=None, filters=None, exclude_ids=None):
            seen.update(filters=filters, exclude=exclude_ids)
            return [item("omen", price=38_000_000) | {"metadata": {"name": "لپ‌تاپ گیمینگ اچ‌پی امن", "price": 38_000_000}}]

        monkeypatch.setattr(G, "embed", fake_embed)
        monkeypatch.setattr(G, "vector_search_products", fake_search)
        monkeypatch.setattr(G, "_shop_facts", lambda state: _no_facts())
        prompts = self.install_llm(monkeypatch, "اگر بودجه مهم است، لپ‌تاپ گیمینگ اچ‌پی امن هم هست.")
        tuf = item("tuf", price=42_000_000) | {"metadata": {"name": "لپ‌تاپ گیمینگ ایسوس TUF", "price": 42_000_000}}
        result = await G.handle_purchase(
            {"shop_id": "s1", "messages": [], "intent": "objection", "objection": "price",
             "shown_products": [tuf], "explore_filters": {"category": "لپ‌تاپ"}}
        )
        assert seen["filters"] == {"category": "لپ‌تاپ", "maxPrice": 42_000_000 - G.PRICE_EPSILON}
        assert seen["exclude"] == ["tuf"]
        assert seen["text"] == "لپ‌تاپ گیمینگ ایسوس TUF"
        assert "گزینه‌های جایگزین" in prompts[-1] and "اچ‌پی امن" not in prompts[-1].split("گزینه‌های جایگزین (")[0].split("محصولاتی که مشتری")[1]
        # The alternative the reply offered gets a card and joins the table.
        assert [i["id"] for i in result["retrieved_context"]] == ["tuf", "omen"]
        assert [i["id"] for i in result["shown_products"]] == ["tuf", "omen"]

    async def test_an_alternative_the_reply_did_not_offer_is_not_shown(self, monkeypatch, fake_shop_db):
        async def fake_alternatives(state, items, move):
            return [item("omen") | {"metadata": {"name": "لپ‌تاپ گیمینگ اچ‌پی امن"}}]

        monkeypatch.setattr(G, "_alternatives", fake_alternatives)
        monkeypatch.setattr(G, "_shop_facts", lambda state: _no_facts())
        self.install_llm(monkeypatch, "این قیمت بابت پردازنده i7 و کارت گرافیک RTX 4060 است.")
        result = await G.handle_purchase(
            {"shop_id": "s1", "messages": [], "intent": "objection", "objection": "price",
             "shown_products": self.two_laptops()[:1]}
        )
        assert [i["id"] for i in result["retrieved_context"]] == ["lenovo"]
        assert "shown_products" not in result

    async def test_an_embedding_failure_does_not_cost_the_customer_the_reply(self, monkeypatch, fake_shop_db):
        self.install_llm(monkeypatch, "پاسخ")
        result = await G.handle_purchase(
            {"shop_id": "s1", "messages": [HumanMessage(content="اگه خراب بود چی؟")], "intent": "objection",
             "objection": "uncertainty", "shown_products": self.two_laptops()[:1]}
        )
        assert result["messages"][0].content == "پاسخ"


async def _no_facts():
    return ""
