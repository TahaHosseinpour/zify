"""Deterministic node cases: analyze_intent, called with the real classifier
LLM (temperature=0), asserted against an exact expected field.

analyze_intent never shows retrieved_context/shown_products *content* to the
LLM (only the conversation transcript - see app/graph.py's analyze_intent),
so tests/conftest.py's placeholder `item()` is accurate here: only
`metadata.price`/`type`/`id` are ever read by the node itself, and content
text is irrelevant to what the classifier sees.

Add a scenario by appending a DeterministicNodeCase; remove one by deleting
its entry. test_node_deterministic.py just iterates this list - it has no
per-case logic of its own.
"""

from __future__ import annotations

from app.graph import PRICE_EPSILON

from helpers import user_says
from tests.conftest import item

from .types import DeterministicNodeCase

_SHOP_CATEGORIES = ["کفش", "لپ‌تاپ"]

_TWO_SHOWN_PRODUCTS = [
    item("p1", price=1_500_000, url="https://shop.test/p1"),
    item("p2", price=2_200_000, url="https://shop.test/p2"),
]


def _base_state(**overrides) -> dict:
    state = {
        "shop_id": "shop-1",
        "mode": "explore",
        "shop_categories": _SHOP_CATEGORIES,
        "shop_brands": [],
        "shown_products": [],
        "explore_filters": {},
        "excluded_product_ids": [],
    }
    state.update(overrides)
    return state


def _check_smalltalk_greeting(update: dict) -> None:
    assert update["intent"] == "smalltalk"


def _check_vague_request_needs_clarification(update: dict) -> None:
    assert update["intent"] in ("needs_clarification", "ask_question")


def _check_search_with_budget(update: dict) -> None:
    assert update["intent"] == "search_product"
    filters = update["explore_filters"]
    assert filters.get("category") == "کفش", filters
    assert filters.get("maxPrice") == 2_000_000, filters


def _check_ready_to_buy(update: dict) -> None:
    assert update["intent"] == "buy_intent"


def _check_price_objection(update: dict) -> None:
    assert update["intent"] == "objection"
    assert update["objection"] == "price"


def _check_ordinal_pins_second_product(update: dict) -> None:
    assert update.get("mode") == "product", update.get("mode")
    assert update.get("product_id") == "p2", update.get("product_id")


def _check_compare_intent(update: dict) -> None:
    assert update["intent"] == "compare"
    # derive_mode forces "compare" back to explore even if the previous turn
    # had pinned a single product - a comparison is never about just one.
    assert update["mode"] == "explore", update["mode"]


def _check_new_topic_wipes_the_old_budget(update: dict) -> None:
    assert update["intent"] == "search_product"
    filters = update["explore_filters"]
    assert filters.get("category") == "لپ‌تاپ", filters
    # new_topic=True means the old کفش/maxPrice constraints must not survive.
    assert "maxPrice" not in filters or filters["maxPrice"] != 2_000_000, filters


def _check_cleared_filter_drops_only_that_key(update: dict) -> None:
    filters = update["explore_filters"]
    assert "maxPrice" not in filters, filters
    # brand was never touched by "بودجه مهم نیست", so it must survive the merge.
    assert filters.get("brand") == "نایک", filters


def _check_cheapest_sort(update: dict) -> None:
    assert update.get("sort") == "price_asc", update.get("sort")


def _check_relative_price_cheaper_bounds_from_shown(update: dict) -> None:
    filters = update["explore_filters"]
    expected_max = min(1_500_000, 2_200_000) - PRICE_EPSILON
    assert filters.get("maxPrice") == expected_max, filters


def _check_rejected_current_excludes_shown_products(update: dict) -> None:
    assert set(update["excluded_product_ids"]) == {"p1", "p2"}, update["excluded_product_ids"]


def _check_out_of_catalog_flag(update: dict) -> None:
    assert update["out_of_catalog"] is True, update


def _check_brand_only_filter(update: dict) -> None:
    assert update["intent"] == "search_product"
    filters = update["explore_filters"]
    assert filters.get("category") == "کفش", filters
    assert filters.get("brand") == "نایک", filters


def _check_price_range_sets_both_bounds(update: dict) -> None:
    filters = update["explore_filters"]
    assert filters.get("minPrice") == 500_000, filters
    assert filters.get("maxPrice") == 1_000_000, filters


def _check_priciest_sort(update: dict) -> None:
    assert update.get("sort") == "price_desc", update.get("sort")


def _check_objection_resolved_clears_objection(update: dict) -> None:
    assert update["objection"] is None, update["objection"]


def _check_low_price_value_driver(update: dict) -> None:
    assert update.get("value_driver") == "low_price", update.get("value_driver")


def _check_high_quality_value_driver(update: dict) -> None:
    assert update.get("value_driver") == "high_quality", update.get("value_driver")


def _check_best_quality_in_price_value_driver(update: dict) -> None:
    assert update.get("value_driver") == "best_quality_in_price", update.get("value_driver")


def _check_best_price_in_quality_value_driver(update: dict) -> None:
    assert update.get("value_driver") == "best_price_in_quality", update.get("value_driver")


def _check_complete_question_is_browse_not_clarification(update: dict) -> None:
    assert update["intent"] == "browse", update["intent"]


def _check_out_of_range_ordinal_is_ignored(update: dict) -> None:
    # Only 2 products were ever shown; "the 10th one" must not resolve to
    # anything - product_id/mode stay whatever they'd be without an ordinal.
    assert update.get("mode") != "product", update.get("mode")
    assert "product_id" not in update or update.get("product_id") is None, update.get("product_id")


def _check_uncertainty_objection_without_explicit_reason(update: dict) -> None:
    assert update["intent"] == "objection", update["intent"]
    assert update["objection"] == "uncertainty", update["objection"]


NODE_DETERMINISTIC_CASES: list[DeterministicNodeCase] = [
    DeterministicNodeCase(
        id="smalltalk_greeting",
        node="analyze_intent",
        state=_base_state(messages=user_says("سلام")),
        expected="intent == 'smalltalk'",
        check=_check_smalltalk_greeting,
    ),
    DeterministicNodeCase(
        id="vague_request_needs_clarification",
        node="analyze_intent",
        state=_base_state(messages=user_says("یک کفش می‌خوام")),
        expected="intent in ('needs_clarification', 'ask_question') - no type/use/budget given",
        check=_check_vague_request_needs_clarification,
    ),
    DeterministicNodeCase(
        id="search_with_budget_sets_category_and_max_price",
        node="analyze_intent",
        state=_base_state(messages=user_says("کفش زیر ۲ میلیون تومان می‌خوام")),
        expected="intent == 'search_product', explore_filters.category == 'کفش', explore_filters.maxPrice == 2_000_000",
        check=_check_search_with_budget,
    ),
    DeterministicNodeCase(
        id="ready_to_buy",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("سلام، این کفش رو دارید؟", "بله موجوده", "همینو میخوام، لینک بده"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="intent == 'buy_intent'",
        check=_check_ready_to_buy,
    ),
    DeterministicNodeCase(
        id="price_objection",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("این کفش چنده؟", "۱۵۰۰ تومنه", "خیلی گرونه"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="intent == 'objection', objection == 'price'",
        check=_check_price_objection,
    ),
    DeterministicNodeCase(
        id="ordinal_reference_pins_the_second_shown_product",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("دومی رو میخوام"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="mode == 'product', product_id == 'p2' (the 2nd shown product)",
        check=_check_ordinal_pins_second_product,
    ),
    DeterministicNodeCase(
        id="compare_two_shown_products",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("بین این دوتا کدوم بهتره؟"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="intent == 'compare', mode == 'explore'",
        check=_check_compare_intent,
    ),
    DeterministicNodeCase(
        id="new_topic_wipes_the_old_budget_filter",
        node="analyze_intent",
        state=_base_state(
            messages=user_says(
                "کفش زیر ۲ میلیون می‌خوام",
                "چند مدل کفش زیر ۲ میلیون داریم، کدوم رو دوست دارید؟",
                "یه لپ‌تاپ اداری برای کارای روزمره می‌خوام",
            ),
            explore_filters={"category": "کفش", "maxPrice": 2_000_000},
        ),
        expected="intent == 'search_product', new_topic clears the old کفش/maxPrice filters, explore_filters.category == 'لپ‌تاپ'",
        check=_check_new_topic_wipes_the_old_budget,
    ),
    DeterministicNodeCase(
        id="cleared_filter_drops_only_the_named_key",
        node="analyze_intent",
        state=_base_state(
            messages=user_says(
                "کفش نایک زیر ۲ میلیون می‌خوام",
                "چند مدل کفش نایک زیر ۲ میلیون داریم، این‌ها رو نشونتون میدم",
                "بودجه‌ای که گفتم رو فراموش کن، حتی اگه گرون‌تر باشه هم برام مهم نیست",
            ),
            explore_filters={"category": "کفش", "brand": "نایک", "maxPrice": 2_000_000},
        ),
        expected="cleared_filters removes maxPrice only; brand='نایک' survives the merge",
        check=_check_cleared_filter_drops_only_that_key,
    ),
    DeterministicNodeCase(
        id="superlative_cheapest_sets_sort_price_asc",
        node="analyze_intent",
        state=_base_state(messages=user_says("ارزون‌ترین کفشی که دارید چیه؟")),
        expected="sort == 'price_asc'",
        check=_check_cheapest_sort,
    ),
    DeterministicNodeCase(
        id="relative_cheaper_bounds_from_the_lowest_shown_price",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("ارزون‌ترش رو دارید؟"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected=f"explore_filters.maxPrice == min(shown prices) - {PRICE_EPSILON} == {1_500_000 - PRICE_EPSILON}",
        check=_check_relative_price_cheaper_bounds_from_shown,
    ),
    DeterministicNodeCase(
        id="rejected_current_excludes_the_shown_products",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("این‌ها رو نمی‌خوام، یه چیز دیگه نشون بده"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="excluded_product_ids == {'p1', 'p2'}",
        check=_check_rejected_current_excludes_shown_products,
    ),
    DeterministicNodeCase(
        id="request_outside_shop_vocabulary_sets_out_of_catalog",
        node="analyze_intent",
        state=_base_state(messages=user_says("موتور سیکلت برقی دارید؟")),
        expected="out_of_catalog == True (این فروشگاه فقط کفش/لپ‌تاپ دارد)",
        check=_check_out_of_catalog_flag,
    ),
    DeterministicNodeCase(
        id="brand_named_without_a_price_sets_category_and_brand",
        node="analyze_intent",
        state=_base_state(messages=user_says("کفش نایک می‌خوام")),
        expected="intent == 'search_product', explore_filters.category == 'کفش', explore_filters.brand == 'نایک'",
        check=_check_brand_only_filter,
    ),
    DeterministicNodeCase(
        id="explicit_price_range_sets_min_and_max",
        node="analyze_intent",
        state=_base_state(messages=user_says("کفش بین ۵۰۰ هزار تا ۱ میلیون تومان می‌خوام")),
        expected="explore_filters.minPrice == 500_000, explore_filters.maxPrice == 1_000_000",
        check=_check_price_range_sets_both_bounds,
    ),
    DeterministicNodeCase(
        id="superlative_priciest_sets_sort_price_desc",
        node="analyze_intent",
        state=_base_state(messages=user_says("گرون‌ترین لپ‌تاپی که دارید چیه؟")),
        expected="sort == 'price_desc'",
        check=_check_priciest_sort,
    ),
    DeterministicNodeCase(
        id="accepting_the_objection_clears_it",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("این کفش چنده؟", "۱۵۰۰ تومنه", "خیلی گرونه", "برای همین کیفیت قابل قبوله", "باشه قبول دارم"),
            shown_products=_TWO_SHOWN_PRODUCTS,
            objection="price",
        ),
        expected="objection resolved by acceptance -> objection is None",
        check=_check_objection_resolved_clears_objection,
    ),
    DeterministicNodeCase(
        id="explicit_low_price_preference_sets_value_driver",
        node="analyze_intent",
        state=_base_state(messages=user_says("ارزون‌ترین رو می‌خوام، کیفیتش برام مهم نیست")),
        expected="value_driver == 'low_price'",
        check=_check_low_price_value_driver,
    ),
    DeterministicNodeCase(
        id="complete_informational_question_is_browse_not_clarification",
        node="analyze_intent",
        state=_base_state(messages=user_says("چند تا شعبه دارید؟")),
        expected="intent == 'browse' (complete, answerable question - not needs_clarification)",
        check=_check_complete_question_is_browse_not_clarification,
    ),
    DeterministicNodeCase(
        id="ordinal_reference_past_the_shown_list_is_ignored",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("دهمی رو میخوام"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="only 2 products were shown - selected_index=10 must not resolve to a product_id or pin mode",
        check=_check_out_of_range_ordinal_is_ignored,
    ),
    DeterministicNodeCase(
        id="uncertainty_objection_without_an_explicit_reason",
        node="analyze_intent",
        state=_base_state(
            messages=user_says("این کفش رو ببینید", "بفرمایید", "مطمئن نیستم این برام مناسب باشه"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="intent == 'objection', objection == 'uncertainty'",
        check=_check_uncertainty_objection_without_explicit_reason,
    ),
    # Every earlier value_driver case was a budget-conscious customer
    # (low_price). These three cover the rest of the driver_map - a customer
    # who explicitly wants quality/brand over price, in each of its shapes.
    DeterministicNodeCase(
        id="explicit_quality_over_price_preference_sets_value_driver",
        node="analyze_intent",
        state=_base_state(messages=user_says("کیفیتش برام از هر چیز دیگه‌ای مهم‌تره، حتی اگه گرون‌تر باشه")),
        expected="value_driver == 'high_quality'",
        check=_check_high_quality_value_driver,
    ),
    DeterministicNodeCase(
        id="best_quality_within_a_stated_budget_sets_value_driver",
        node="analyze_intent",
        state=_base_state(messages=user_says("توی بودجه ۲۰ میلیون، بهترین کیفیت رو می‌خوام")),
        expected="value_driver == 'best_quality_in_price'",
        check=_check_best_quality_in_price_value_driver,
    ),
    DeterministicNodeCase(
        id="cheapest_at_a_stated_quality_level_sets_value_driver",
        node="analyze_intent",
        state=_base_state(messages=user_says("یه لپ‌تاپ خوب برای گیم می‌خوام ولی ارزون‌ترینش رو با همون کیفیت")),
        expected="value_driver == 'best_price_in_quality'",
        check=_check_best_price_in_quality_value_driver,
    ),
]
