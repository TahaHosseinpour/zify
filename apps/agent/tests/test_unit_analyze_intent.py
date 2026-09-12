"""Unit tests for analyze_intent's state-merging logic.

analyze_intent is the single busiest node in the graph — every rule that keeps
conversation state consistent across turns lives here (filter merging, sticky
objections, ordinal resolution, exclusion lists, the buy_actions reset). The
LLM classification itself is stubbed to return a fixed IntentResult, so these
tests are about the merge logic, not the model's judgment.
"""

import pytest
from tests.conftest import item

from app import graph as G
from app.graph import ExploreFiltersModel, IntentResult


def install_classifier(monkeypatch, result: IntentResult, categories=None):
    class FakeStructuredLLM:
        @staticmethod
        async def ainvoke(messages):
            return result

    monkeypatch.setattr(G, "structured_llm", FakeStructuredLLM())

    async def fake_categories(shop_id):
        return categories or []

    monkeypatch.setattr(G, "shop_categories", fake_categories)


def base_state(**overrides):
    state = {
        "shop_id": "s1",
        "messages": [],
        "mode": "explore",
        "explore_filters": {},
        "excluded_product_ids": [],
        "shown_products": [],
    }
    state.update(overrides)
    return state


class TestFilterMerging:
    async def test_new_filters_merge_onto_existing(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing",
                         explore_filters=ExploreFiltersModel(maxPrice=500)),
        )
        state = base_state(explore_filters={"category": "کفش"})
        updates = await G.analyze_intent(state)
        assert updates["explore_filters"] == {"category": "کفش", "maxPrice": 500}

    async def test_new_topic_wipes_prior_filters(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing",
                         explore_filters=ExploreFiltersModel(category="لپ‌تاپ"),
                         new_topic=True),
        )
        state = base_state(explore_filters={"category": "کفش", "maxPrice": 500})
        updates = await G.analyze_intent(state)
        assert updates["explore_filters"] == {"category": "لپ‌تاپ"}

    async def test_cleared_filters_remove_specific_keys_even_without_new_topic(self, monkeypatch):
        # A merge alone can only ever add — this is the only way a wrong
        # filter the model invented once gets taken back.
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage="browsing",
                         cleared_filters=["maxPrice"]),
        )
        state = base_state(explore_filters={"category": "کفش", "maxPrice": 500})
        updates = await G.analyze_intent(state)
        assert updates["explore_filters"] == {"category": "کفش"}

    async def test_category_not_in_shop_vocabulary_is_dropped(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing",
                         explore_filters=ExploreFiltersModel(category="فرش")),
            categories=["کفش", "لپ‌تاپ"],
        )
        updates = await G.analyze_intent(base_state())
        assert "category" not in updates["explore_filters"]

    async def test_category_matching_shop_vocabulary_case_insensitively_survives(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing",
                         explore_filters=ExploreFiltersModel(category="کفش")),
            categories=["کفش", "لپ‌تاپ"],
        )
        updates = await G.analyze_intent(base_state())
        assert updates["explore_filters"]["category"] == "کفش"

    async def test_empty_shop_vocabulary_does_not_block_any_category(self, monkeypatch):
        # A shop with no categorized products yet shouldn't have every search
        # silently stripped of its category guess.
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing",
                         explore_filters=ExploreFiltersModel(category="هرچیزی")),
            categories=[],
        )
        updates = await G.analyze_intent(base_state())
        assert updates["explore_filters"]["category"] == "هرچیزی"


class TestRelativePriceIntegration:
    async def test_cheaper_becomes_a_max_price_bound_from_shown_products(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing",
                         relative_price="cheaper"),
        )
        shown = [item("p1", price=2_000_000), item("p2", price=1_000_000)]
        updates = await G.analyze_intent(base_state(shown_products=shown))
        assert updates["explore_filters"]["maxPrice"] == 1_000_000 - G.PRICE_EPSILON

    async def test_relative_price_bound_replaces_the_opposite_bound(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing",
                         relative_price="pricier"),
        )
        shown = [item("p1", price=2_000_000)]
        state = base_state(explore_filters={"maxPrice": 500_000}, shown_products=shown)
        updates = await G.analyze_intent(state)
        assert "maxPrice" not in updates["explore_filters"]
        assert updates["explore_filters"]["minPrice"] == 2_000_000 + G.PRICE_EPSILON


class TestObjectionStickiness:
    async def test_objection_persists_across_turns_when_not_mentioned(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing", objection=None),
        )
        updates = await G.analyze_intent(base_state(objection="price"))
        assert updates["objection"] == "price"

    async def test_objection_resolved_clears_it(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage="browsing", objection_resolved=True),
        )
        updates = await G.analyze_intent(base_state(objection="price"))
        assert updates["objection"] is None

    async def test_new_objection_overrides_the_old_one(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="objection", mode="explore", stage="browsing", objection="delay"),
        )
        updates = await G.analyze_intent(base_state(objection="price"))
        assert updates["objection"] == "delay"


class TestOrdinalResolution:
    async def test_selected_index_resolves_to_a_concrete_product_and_pins_mode(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage="browsing", selected_index=2),
        )
        shown = [item("first"), item("second"), item("third")]
        updates = await G.analyze_intent(base_state(mode="explore", shown_products=shown))
        assert updates["product_id"] == "second"
        assert updates["mode"] == "product"

    async def test_out_of_range_index_is_ignored(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage="browsing", selected_index=99),
        )
        shown = [item("only_one")]
        updates = await G.analyze_intent(base_state(shown_products=shown))
        assert "product_id" not in updates
        assert updates["mode"] == "explore"

    async def test_leaving_product_mode_forgets_the_pinned_product(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing"),
        )
        # search_product forces mode back to explore per derive_mode.
        updates = await G.analyze_intent(base_state(mode="product", product_id="old"))
        assert updates["mode"] == "explore"
        assert updates["product_id"] is None


class TestExclusionList:
    async def test_new_topic_clears_exclusions(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing", new_topic=True),
        )
        updates = await G.analyze_intent(base_state(excluded_product_ids=["old1", "old2"]))
        assert updates["excluded_product_ids"] == []

    async def test_rejected_current_excludes_the_shown_products(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing", rejected_current=True),
        )
        shown = [item("a"), item("b")]
        updates = await G.analyze_intent(base_state(shown_products=shown))
        assert set(updates["excluded_product_ids"]) == {"a", "b"}

    async def test_exclusions_accumulate_without_duplicates_across_turns(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="search_product", mode="explore", stage="browsing", rejected_current=True),
        )
        shown = [item("a"), item("b")]
        state = base_state(excluded_product_ids=["a"], shown_products=shown)
        updates = await G.analyze_intent(state)
        assert updates["excluded_product_ids"] == ["a", "b"]


class TestPerTurnResets:
    async def test_retrieval_buffers_reset_every_turn(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage="browsing"),
        )
        updates = await G.analyze_intent(base_state())
        assert updates["retrieved_raw"] is None  # RESET_CONTEXT sentinel
        assert updates["retrieved_context"] == []
        assert updates["candidate_ids"] == []
        assert updates["filter_status"] == G.FILTER_NONE

    async def test_buy_actions_resets_to_true_every_turn(self, monkeypatch):
        # Only handle_purchase turns it off; every other turn must default back
        # on, or a "let me think" turn's False would leak into the next reply.
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage="browsing"),
        )
        updates = await G.analyze_intent(base_state())
        assert updates["buy_actions"] is True

    async def test_value_driver_persists_when_unstated(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage="browsing", value_driver=None),
        )
        state = base_state(value_driver="low_price")
        updates = await G.analyze_intent(state)
        assert updates["value_driver"] == "low_price"

    async def test_stage_persists_when_the_model_leaves_it_null(self, monkeypatch):
        # See test_unit_schema_contract.py: stage is Optional[str], so the
        # model can actually emit null when the message doesn't make the
        # stage clear, and the previous turn's value survives.
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage=None),
        )
        state = base_state(stage="considering")
        updates = await G.analyze_intent(state)
        assert updates["stage"] == "considering"

    async def test_stage_also_persists_via_empty_string(self, monkeypatch):
        install_classifier(
            monkeypatch,
            IntentResult(intent="browse", mode="explore", stage=""),
        )
        state = base_state(stage="considering")
        updates = await G.analyze_intent(state)
        assert updates["stage"] == "considering"
