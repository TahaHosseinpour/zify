"""Deterministic full-graph cases: one turn through the real compiled graph
(build_graph()), with only retrieval stubbed (see helpers.stub_retrieval_nodes)
- analyze_intent's classifier and every generation node's LLM call are real.
Checks look only at structured final-state fields, never at reply text (see
graph_judge_cases.py for that).

Add a scenario by appending a DeterministicGraphCase; remove one by deleting
its entry. test_graph_deterministic.py just iterates this list.
"""

from __future__ import annotations

from helpers import user_says
from tests.conftest import item

from .types import DeterministicGraphCase

_SHOP_CATEGORIES = ["کفش", "لپ‌تاپ"]

_TWO_SHOWN_PRODUCTS = [
    item("p1", price=1_500_000, url="https://shop.test/p1"),
    item("p2", price=2_200_000, url="https://shop.test/p2"),
]

_TWO_OTHER_PRODUCTS = [
    item("p3", price=1_100_000, url="https://shop.test/p3"),
    item("p4", price=1_900_000, url="https://shop.test/p4"),
]


def _base_input(**overrides) -> dict:
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


def _check_search_flow(result: dict) -> None:
    assert result["mode"] == "explore", result["mode"]
    assert result["buy_actions"] is True, result["buy_actions"]
    types = {i["type"] for i in result["retrieved_context"]}
    assert "product" in types, result["retrieved_context"]


def _check_smalltalk_never_touches_retrieval(result: dict) -> None:
    assert result["retrieved_context"] == []
    assert result["buy_actions"] is False, result["buy_actions"]


def _check_buy_intent_closes_from_the_table(result: dict) -> None:
    assert result["buy_actions"] is True, result["buy_actions"]
    assert [i["id"] for i in result["retrieved_context"]] == ["p1", "p2"], result["retrieved_context"]


def _check_compare_keeps_both_products_no_buy_button(result: dict) -> None:
    assert result["buy_actions"] is False, result["buy_actions"]
    assert {i["id"] for i in result["retrieved_context"]} == {"p1", "p2"}, result["retrieved_context"]


def _check_price_objection_keeps_products_no_buy_button(result: dict) -> None:
    assert result["buy_actions"] is False, result["buy_actions"]
    assert {i["id"] for i in result["retrieved_context"]} == {"p1", "p2"}, result["retrieved_context"]


def _check_out_of_catalog_flow(result: dict) -> None:
    assert result["out_of_catalog"] is True, result
    assert result["buy_actions"] is False, result["buy_actions"]
    types = {i["type"] for i in result["retrieved_context"]}
    assert "product" not in types, result["retrieved_context"]


def _check_ordinal_selection_routes_to_product_mode(result: dict) -> None:
    assert result["mode"] == "product", result["mode"]
    assert result["product_id"] == "p2", result["product_id"]
    ids = {i["id"] for i in result["retrieved_context"]}
    assert "p2" in ids, result["retrieved_context"]


def _check_rejected_current_excludes_and_returns_new_products(result: dict) -> None:
    assert {"p1", "p2"} <= set(result["excluded_product_ids"]), result["excluded_product_ids"]
    ids = {i["id"] for i in result["retrieved_context"]}
    assert ids == {"p3", "p4"}, result["retrieved_context"]
    assert "p1" not in ids and "p2" not in ids, result["retrieved_context"]


def _check_needs_clarification_never_touches_retrieval(result: dict) -> None:
    assert result["retrieved_context"] == [], result["retrieved_context"]
    assert result["buy_actions"] is False, result["buy_actions"]


def _check_uncertainty_objection_keeps_products_no_buy_button(result: dict) -> None:
    assert result["buy_actions"] is False, result["buy_actions"]
    assert {i["id"] for i in result["retrieved_context"]} == {"p1", "p2"}, result["retrieved_context"]


def _check_delay_objection_keeps_products_no_buy_button(result: dict) -> None:
    assert result["buy_actions"] is False, result["buy_actions"]
    assert {i["id"] for i in result["retrieved_context"]} == {"p1", "p2"}, result["retrieved_context"]


def _check_new_topic_wipes_filters_end_to_end(result: dict) -> None:
    filters = result["explore_filters"]
    assert filters.get("category") == "لپ‌تاپ", filters
    assert filters.get("maxPrice") != 2_000_000, filters
    assert result["buy_actions"] is True, result["buy_actions"]
    types = {i["type"] for i in result["retrieved_context"]}
    assert "product" in types, result["retrieved_context"]


def _check_faq_question_pulls_shop_info_not_products(result: dict) -> None:
    types = {i["type"] for i in result["retrieved_context"]}
    assert "faq" in types, result["retrieved_context"]
    assert "product" not in types, result["retrieved_context"]
    assert result["buy_actions"] is False, result["buy_actions"]


def _check_brand_filter_applied_end_to_end(result: dict) -> None:
    assert result["explore_filters"].get("brand") == "نایک", result["explore_filters"]
    assert result["buy_actions"] is True, result["buy_actions"]
    types = {i["type"] for i in result["retrieved_context"]}
    assert "product" in types, result["retrieved_context"]


GRAPH_DETERMINISTIC_CASES: list[DeterministicGraphCase] = [
    DeterministicGraphCase(
        id="search_flow_routes_to_explore_and_shows_products",
        input_state=_base_input(messages=user_says("کفش ورزشی زیر ۲.۵ میلیون دارید؟")),
        expected="mode == 'explore', buy_actions is True, retrieved_context has a 'product'",
        retrieval={"vector_search_explore": _TWO_SHOWN_PRODUCTS},
        check=_check_search_flow,
    ),
    DeterministicGraphCase(
        id="smalltalk_never_touches_retrieval",
        input_state=_base_input(messages=user_says("سلام خوبی؟")),
        expected="retrieved_context == [], buy_actions is False",
        retrieval={},
        check=_check_smalltalk_never_touches_retrieval,
    ),
    DeterministicGraphCase(
        id="buy_intent_closes_from_the_table_without_new_retrieval",
        input_state=_base_input(
            messages=user_says("این دوتا کفش رو نشونم دادید", "بله", "همینو میخوام بخرم، لینک بده"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="buy_actions is True, retrieved_context == the 2 shown products (no new retrieval)",
        retrieval={},
        check=_check_buy_intent_closes_from_the_table,
    ),
    DeterministicGraphCase(
        id="compare_keeps_both_products_and_no_buy_button",
        input_state=_base_input(
            messages=user_says("بین این دوتا کدوم بهتره؟"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="buy_actions is False (compare is not a buy move), both shown products stay in retrieved_context",
        retrieval={},
        check=_check_compare_keeps_both_products_no_buy_button,
    ),
    DeterministicGraphCase(
        id="price_objection_keeps_products_and_turns_off_buy_button",
        input_state=_base_input(
            messages=user_says("این کفش چنده؟", "۱۵۰۰ تومنه", "خیلی گرونه"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="buy_actions is False (any objection move disables it), both shown products stay in retrieved_context",
        retrieval={},
        check=_check_price_objection_keeps_products_no_buy_button,
    ),
    DeterministicGraphCase(
        id="out_of_catalog_request_returns_no_products_and_no_buy_button",
        input_state=_base_input(messages=user_says("موتور سیکلت برقی دارید؟")),
        expected="out_of_catalog is True, buy_actions is False, retrieved_context has no 'product'",
        retrieval={"vector_search_explore": []},
        check=_check_out_of_catalog_flow,
    ),
    DeterministicGraphCase(
        id="ordinal_selection_routes_to_product_mode_and_loads_it",
        input_state=_base_input(
            messages=user_says("دومی رو میخوام"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="mode == 'product', product_id == 'p2', retrieved_context includes p2",
        retrieval={"sql_query_product": [item("p2", price=2_200_000, url="https://shop.test/p2")]},
        check=_check_ordinal_selection_routes_to_product_mode,
    ),
    DeterministicGraphCase(
        id="rejected_current_excludes_old_products_and_shows_new_ones",
        input_state=_base_input(
            messages=user_says("این‌ها رو نمی‌خوام، یه چیز دیگه نشون بده"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="excluded_product_ids includes p1/p2, retrieved_context is the new p3/p4 only",
        retrieval={"vector_search_explore": _TWO_OTHER_PRODUCTS},
        check=_check_rejected_current_excludes_and_returns_new_products,
    ),
    DeterministicGraphCase(
        id="vague_request_routes_to_ask_question_not_retrieval",
        input_state=_base_input(messages=user_says("یک کفش می‌خوام")),
        expected="needs_clarification/ask_question intent routes to ask_question, never touching retrieval - retrieved_context stays [], buy_actions False",
        retrieval={},
        check=_check_needs_clarification_never_touches_retrieval,
    ),
    DeterministicGraphCase(
        id="uncertainty_objection_keeps_products_and_turns_off_buy_button",
        input_state=_base_input(
            messages=user_says("این کفش رو ببینید", "بفرمایید", "مطمئن نیستم این برام مناسب باشه"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="buy_actions is False, both shown products stay in retrieved_context",
        retrieval={},
        check=_check_uncertainty_objection_keeps_products_no_buy_button,
    ),
    DeterministicGraphCase(
        id="delay_objection_keeps_products_and_turns_off_buy_button",
        input_state=_base_input(
            messages=user_says("این دوتا رو دیدید", "بله", "بذار یکم فکر کنم"),
            shown_products=_TWO_SHOWN_PRODUCTS,
        ),
        expected="buy_actions is False, both shown products stay in retrieved_context",
        retrieval={},
        check=_check_delay_objection_keeps_products_no_buy_button,
    ),
    DeterministicGraphCase(
        id="new_topic_wipes_filters_and_searches_the_new_category",
        input_state=_base_input(
            messages=user_says(
                "کفش زیر ۲ میلیون می‌خوام",
                "چند مدل کفش زیر ۲ میلیون داریم، کدوم رو دوست دارید؟",
                "یه لپ‌تاپ اداری برای کارای روزمره می‌خوام",
            ),
            explore_filters={"category": "کفش", "maxPrice": 2_000_000},
        ),
        expected="explore_filters.category becomes 'لپ‌تاپ', old maxPrice gone, a product is retrieved and shown",
        retrieval={"vector_search_explore": [item("laptop-1", price=21_500_000, url="https://shop.test/laptop-1")]},
        check=_check_new_topic_wipes_filters_end_to_end,
    ),
    DeterministicGraphCase(
        id="complete_faq_question_pulls_shop_info_not_products",
        input_state=_base_input(messages=user_says("ارسال چطوریه؟")),
        expected="a complete informational question retrieves faq/shop-info, not products; buy_actions stays False",
        retrieval={
            "vector_faq": [item("faq-shipping", typ="faq")],
            "vector_search_explore": [],
        },
        check=_check_faq_question_pulls_shop_info_not_products,
    ),
    DeterministicGraphCase(
        id="brand_named_without_a_price_is_applied_end_to_end",
        input_state=_base_input(messages=user_says("کفش نایک می‌خوام")),
        expected="explore_filters.brand == 'نایک', a product is retrieved and shown, buy_actions True",
        retrieval={"vector_search_explore": [item("nike-1", price=1_450_000, url="https://shop.test/nike-1")]},
        check=_check_brand_filter_applied_end_to_end,
    ),
]
