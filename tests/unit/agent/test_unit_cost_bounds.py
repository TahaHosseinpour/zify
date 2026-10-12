"""The limits that bound what one turn - and so one conversation - can cost.

A subscription is priced on a hard ceiling for the model spend of a single
conversation (packages/shared/src/plans.ts). Nothing here calls a model: these
tests pin the pieces that make that ceiling real - how much text can reach a
prompt, how often the LLM fallback may run, and that every call is priced.
"""

from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app import graph as G
from app import intent as jev
from app import metering
from app.intent import IntentResult
from app.prompts import PROMPT_EXTRA_LIMIT, build_system_prompt
from tests.conftest import FakeShop


class TestPromptSizeBounds:
    def test_a_reply_has_a_token_ceiling(self):
        assert G.llm.max_tokens == G.REPLY_MAX_TOKENS == 400

    def test_a_long_product_description_cannot_inflate_the_context(self):
        content = G._product_content(
            {"name": "کفش", "price": 1_500_000, "description": "خیلی خوب " * 500,
             "brand": "نایک", "category": "کفش ورزشی"}
        )
        assert len(content) <= G.PRODUCT_CONTENT_LIMIT

    def test_clipping_a_description_never_costs_the_brand_or_category(self):
        # Filters and answers rely on these; the description is what gives way.
        content = G._product_content(
            {"name": "کفش", "price": 1_500_000, "description": "خیلی خوب " * 500,
             "brand": "نایک", "category": "کفش ورزشی"}
        )
        assert content.endswith("برند: نایک | دسته: کفش ورزشی")
        assert "قیمت: ۱٬۵۰۰٬۰۰۰ تومان" in content

    def test_a_short_product_is_left_exactly_as_it_was(self):
        content = G._product_content(
            {"name": "کفش", "price": 1000, "description": "سبک", "brand": "نایک", "category": None}
        )
        assert content == "محصول: کفش | قیمت: ۱٬۰۰۰ تومان | سبک | برند: نایک"

    def test_the_shop_owners_extra_instructions_are_capped_in_the_system_prompt(self):
        shop = FakeShop()
        shop.systemPromptExtra = "ط" * 5000
        prompt = build_system_prompt(shop)
        assert "ط" * PROMPT_EXTRA_LIMIT in prompt
        assert "ط" * (PROMPT_EXTRA_LIMIT + 1) not in prompt

    def test_jev_never_reads_more_than_the_message_limit_of_a_customer_turn(self):
        state = jev.build_state([HumanMessage(content="س" * 5000), AIMessage(content="ج" * 5000)])
        customer, seller = state["conversation"]
        assert len(customer["text"]) == jev.CUSTOMER_TEXT_LIMIT
        assert len(seller["text"]) == jev.SELLER_TEXT_LIMIT

    def test_the_explore_context_holds_six_rows(self):
        assert G.EXPLORE_CONTEXT_LIMIT == 6


class TestFallbackAllowance:
    """Jev's answer stands even when it is unsure. The LLM classifier is a
    full extra call and runs only when Jev can't be reached - at most
    MAX_INTENT_FALLBACKS times in one conversation."""

    @pytest.fixture
    def classifiers(self, monkeypatch):
        calls = {"jev": [], "llm": 0}

        async def fake_jev_classify(messages, *, allow_uncertain=False, **kwargs):
            calls["jev"].append(allow_uncertain)
            if not allow_uncertain:
                raise jev.JevUnavailable("intent too uncertain")
            return IntentResult(intent="browse")

        async def jev_down(messages, **kwargs):
            raise jev.JevUnavailable("HTTP 529")

        calls["take_jev_down"] = lambda: monkeypatch.setattr(jev, "classify", jev_down)

        class FakeStructuredLLM:
            @staticmethod
            async def ainvoke(messages):
                calls["llm"] += 1
                return IntentResult(intent="search_product")

        monkeypatch.setattr(jev, "enabled", lambda: True)
        monkeypatch.setattr(jev, "classify", fake_jev_classify)
        monkeypatch.setattr(G, "structured_llm", FakeStructuredLLM())
        return calls

    async def test_an_unsure_jev_is_taken_at_its_word_without_the_llm(self, classifiers):
        result = await G.classify_intent({"intent_fallbacks": 0}, [], [], [])
        assert classifiers["jev"] == [True]  # always asked for its best guess
        assert classifiers["llm"] == 0
        assert result.intent == "browse"
        assert result._via_fallback is False

    async def test_an_unreachable_jev_falls_back_to_the_llm_and_the_result_says_so(self, classifiers):
        classifiers["take_jev_down"]()
        result = await G.classify_intent({"intent_fallbacks": 0}, [], [], [])
        assert result.intent == "search_product"
        assert result._via_fallback is True
        assert classifiers["llm"] == 1

    async def test_jev_down_and_allowance_spent_still_answers_without_the_llm(self, monkeypatch, classifiers):
        async def always_down(messages, **kwargs):
            raise jev.JevUnavailable("HTTP 529")

        monkeypatch.setattr(jev, "classify", always_down)
        result = await G.classify_intent({"intent_fallbacks": G.MAX_INTENT_FALLBACKS}, [], [], [])
        assert result.intent == "other"
        assert classifiers["llm"] == 0

    async def test_analyze_intent_counts_each_fallback_in_the_conversation_state(self, monkeypatch):
        async def fake_classify_intent(state, recent, categories, brands):
            result = IntentResult(intent="browse")
            result._via_fallback = True
            return result

        async def no_vocabulary(shop_id):
            return []

        monkeypatch.setattr(G, "classify_intent", fake_classify_intent)
        monkeypatch.setattr(G, "shop_categories", no_vocabulary)
        monkeypatch.setattr(G, "shop_brands", no_vocabulary)

        updates = await G.analyze_intent({"shop_id": "s1", "messages": [], "intent_fallbacks": 1})
        assert updates["intent_fallbacks"] == 2

    async def test_a_jev_answer_leaves_the_fallback_count_alone(self, monkeypatch):
        async def fake_classify_intent(state, recent, categories, brands):
            return IntentResult(intent="browse")

        async def no_vocabulary(shop_id):
            return []

        monkeypatch.setattr(G, "classify_intent", fake_classify_intent)
        monkeypatch.setattr(G, "shop_categories", no_vocabulary)
        monkeypatch.setattr(G, "shop_brands", no_vocabulary)

        updates = await G.analyze_intent({"shop_id": "s1", "messages": [], "intent_fallbacks": 1})
        assert updates["intent_fallbacks"] == 1

    def test_the_fallback_marker_is_not_part_of_the_schema_the_llm_fills_in(self):
        assert "_via_fallback" not in IntentResult.model_json_schema()["properties"]


class TestMetering:
    def test_every_kind_of_call_is_priced(self):
        meter = metering.TurnMeter(jev_tokens=1_000_000, embedding_tokens=1_000_000)
        # 1M tokens of each, at the list prices: 0.15 + 0.60 + 0.042 + 0.02.
        assert metering.turn_cost_usd(1_000_000, 1_000_000, meter) == pytest.approx(0.812)

    def test_calls_outside_langchain_report_into_the_turns_meter(self):
        meter = metering.start_turn()
        metering.add_jev_tokens(4000)
        metering.add_jev_tokens(500)
        metering.add_embedding_text("کفش ورزشی نایک")
        assert meter.jev_tokens == 4500
        assert meter.embedding_tokens > 0

    def test_the_conversation_is_the_third_part_of_the_thread_id(self):
        assert metering.conversation_id_from_thread("shop:user:conv") == "conv"
        assert metering.conversation_id_from_thread("shop:playground-1") is None

    async def test_a_turn_is_added_to_its_conversation_and_written_to_the_ledger(self, monkeypatch):
        statements = []

        class FakeDB:
            @staticmethod
            async def execute_raw(sql, *params):
                statements.append((sql, params))

            @staticmethod
            async def query_raw(sql, *params):
                return [{"value": "300000"}]

        monkeypatch.setattr(metering, "db", FakeDB())
        monkeypatch.setattr(metering, "_rate", None)

        meter = metering.TurnMeter(jev_tokens=3500)
        cost = await metering.record_turn("shop-1", "shop-1:user-1:conv-1", 1500, 220, meter)

        # (1500 x 0.15 + 220 x 0.60 + 3500 x 0.042) / 1M dollars, at 300,000.
        assert cost == Decimal("151.20")
        update, insert = statements
        assert 'UPDATE conversations SET "costToman"' in update[0]
        assert update[1] == ("151.20", "conv-1")
        assert "INSERT INTO usage_records" in insert[0]
        assert insert[1][1:7] == ("shop-1", "conv-1", 1500, 220, 3500, 0)

    async def test_a_failed_write_never_breaks_the_turn(self, monkeypatch):
        class BrokenDB:
            @staticmethod
            async def execute_raw(sql, *params):
                raise RuntimeError("connection lost")

            @staticmethod
            async def query_raw(sql, *params):
                raise RuntimeError("connection lost")

        monkeypatch.setattr(metering, "db", BrokenDB())
        monkeypatch.setattr(metering, "_rate", None)
        cost = await metering.record_turn("shop-1", "a:b:c", 1000, 100, metering.TurnMeter())
        assert cost > 0
