"""Deterministic ranking cases: fuse_results_explore / fuse_context_product,
called directly against a curated retrieved_raw pool (no real embeddings, no
DB, no LLM - these two nodes are pure Python over `score`). Consumed by
test_node_deterministic.py alongside node_deterministic_cases.py.

Uses cases/catalog_40.py's 40-product pool for the two "at scale" scenarios
(a real shoe/laptop query against a full realistic-sized catalog) and small
hand-built pools for the specific ranking rules documented in app/graph.py
(the relevance floor, its bypass when SQL already proved the category/brand,
dedup, the pinned product's priority, FAQ/shop-info's exemption, and the
explore vs. product context limits).

Add a scenario by appending a DeterministicNodeCase; remove one by deleting
its entry.
"""

from __future__ import annotations

from app.graph import EXPLORE_CONTEXT_LIMIT
from app.state import RetrievedItem

from .catalog_40 import ALL_40, CASUAL_SHOES, OFFICE_LAPTOPS, RUNNING_SHOES, pool_with_scores
from .types import DeterministicNodeCase


def _base_state(**overrides) -> dict:
    state = {
        "shop_id": "shop-1",
        "filter_effective": {},
        "product_id": None,
    }
    state.update(overrides)
    return state


def _faq(id_: str, score: float) -> RetrievedItem:
    return RetrievedItem(id=id_, type="faq", content=f"faq-{id_}", score=score)


def _shop_info(id_: str, score: float) -> RetrievedItem:
    return RetrievedItem(id=id_, type="shop_info", content=f"info-{id_}", score=score)


def _check_shoe_query_surfaces_only_relevant_shoes(update: dict) -> None:
    ids = [i["id"] for i in update["retrieved_context"]]
    assert ids == [s["id"] for s in RUNNING_SHOES[:EXPLORE_CONTEXT_LIMIT]], ids
    assert update["out_of_catalog"] is False, update["out_of_catalog"]


def _check_laptop_query_surfaces_only_relevant_laptops(update: dict) -> None:
    ids = [i["id"] for i in update["retrieved_context"]]
    assert ids == [l["id"] for l in OFFICE_LAPTOPS[:EXPLORE_CONTEXT_LIMIT]], ids
    assert update["out_of_catalog"] is False, update["out_of_catalog"]


def _check_semantic_filter_skips_the_floor(update: dict) -> None:
    ids = {i["id"] for i in update["retrieved_context"]}
    assert len(update["retrieved_context"]) == EXPLORE_CONTEXT_LIMIT, update["retrieved_context"]
    assert {"shoe-run-0", "shoe-run-1", "shoe-run-2"} <= ids, ids


def _check_no_semantic_filter_all_past_floor_is_empty(update: dict) -> None:
    assert update["retrieved_context"] == [], update["retrieved_context"]
    assert update["out_of_catalog"] is True, update["out_of_catalog"]


def _check_duplicate_id_keeps_last_occurrence(update: dict) -> None:
    ids = [i["id"] for i in update["retrieved_context"]]
    assert ids == ["shoe-run-0", "shoe-run-1"], ids
    dup = next(i for i in update["retrieved_context"] if i["id"] == "shoe-run-0")
    assert dup["score"] == 0.20, dup["score"]


def _check_pinned_product_ranks_first(update: dict) -> None:
    ids = [i["id"] for i in update["retrieved_context"]]
    assert ids[0] == "shoe-run-0", ids


def _check_faq_and_shop_info_exempt_from_floor(update: dict) -> None:
    types = {i["type"] for i in update["retrieved_context"]}
    assert types == {"faq", "shop_info"}, types


def _check_explore_trims_to_the_limit(update: dict) -> None:
    assert len(update["retrieved_context"]) == EXPLORE_CONTEXT_LIMIT, update["retrieved_context"]


def _check_product_trims_to_6(update: dict) -> None:
    assert len(update["retrieved_context"]) == 6, update["retrieved_context"]


def _check_brand_only_semantic_filter_skips_the_floor(update: dict) -> None:
    ids = {i["id"] for i in update["retrieved_context"]}
    assert ids == {"shoe-run-0", "shoe-run-2"}, ids


RETRIEVAL_RANKING_CASES: list[DeterministicNodeCase] = [
    DeterministicNodeCase(
        id="shoe_query_across_the_full_40_product_catalog_surfaces_only_relevant_shoes",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=pool_with_scores(
                base_score=0.85,
                overrides={s["id"]: 0.30 + i * 0.02 for i, s in enumerate(RUNNING_SHOES)},
            ),
            intent="search_product",
        ),
        expected="of all 40 catalog products, only the top EXPLORE_CONTEXT_LIMIT most relevant running shoes come back, in relevance order",
        check=_check_shoe_query_surfaces_only_relevant_shoes,
    ),
    DeterministicNodeCase(
        id="laptop_query_across_the_full_40_product_catalog_surfaces_only_relevant_laptops",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=pool_with_scores(
                base_score=0.85,
                overrides={l["id"]: 0.33 + i * 0.02 for i, l in enumerate(OFFICE_LAPTOPS)},
            ),
            intent="search_product",
        ),
        expected="of all 40 catalog products, only the top EXPLORE_CONTEXT_LIMIT most relevant laptops come back, in relevance order",
        check=_check_laptop_query_surfaces_only_relevant_laptops,
    ),
    DeterministicNodeCase(
        id="semantic_filter_applied_skips_the_relevance_floor",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=pool_with_scores(
                base_score=0.85,
                overrides={"shoe-run-0": 0.72, "shoe-run-1": 0.75, "shoe-run-2": 0.78},
            ),
            filter_effective={"category": "کفش ورزشی"},
            intent="search_product",
        ),
        expected="SQL already proved these are on-topic, so 3 genuine matches past the 0.70 floor still make the cut",
        check=_check_semantic_filter_skips_the_floor,
    ),
    DeterministicNodeCase(
        id="without_semantic_filter_the_same_scores_are_all_dropped",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=pool_with_scores(
                base_score=0.85,
                overrides={"shoe-run-0": 0.72, "shoe-run-1": 0.75, "shoe-run-2": 0.78},
            ),
            filter_effective={},
            intent="search_product",
        ),
        expected="same scores, no SQL proof this time -> every product is past the 0.70 floor, result is empty and out_of_catalog flips True",
        check=_check_no_semantic_filter_all_past_floor_is_empty,
    ),
    DeterministicNodeCase(
        id="exact_duplicate_id_keeps_only_the_last_occurrence",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=[
                {**RUNNING_SHOES[0], "score": 0.60},
                {**RUNNING_SHOES[1], "score": 0.40},
                {**RUNNING_SHOES[0], "score": 0.20},  # same id, later in the list, better score
            ],
        ),
        expected="shoe-run-0 appears once (the later/better-scored copy wins), ranked ahead of shoe-run-1",
        check=_check_duplicate_id_keeps_last_occurrence,
    ),
    DeterministicNodeCase(
        id="pinned_product_always_ranks_first_even_with_a_mediocre_score",
        node="fuse_context_product",
        state=_base_state(
            retrieved_raw=[
                {**RUNNING_SHOES[0], "score": 0.65},
                {**RUNNING_SHOES[1], "score": 0.30},
                {**RUNNING_SHOES[2], "score": 0.35},
            ],
            product_id="shoe-run-0",
        ),
        expected="shoe-run-0 is pinned (product_id), so it ranks first despite 0.65 being worse than the other two",
        check=_check_pinned_product_ranks_first,
    ),
    DeterministicNodeCase(
        id="faq_and_shop_info_are_exempt_from_the_relevance_floor",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=[
                {**RUNNING_SHOES[0], "score": 0.85},
                {**RUNNING_SHOES[1], "score": 0.85},
                _faq("faq-1", 0.90),
                _shop_info("info-1", 0.95),
            ],
        ),
        expected="both products get dropped (score > 0.70, no semantic filter), the faq/shop_info rows survive regardless of score",
        check=_check_faq_and_shop_info_exempt_from_floor,
    ),
    DeterministicNodeCase(
        id="explore_trims_the_same_oversupply_to_the_limit",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=pool_with_scores(
                base_score=0.85, overrides={s["id"]: 0.30 + i * 0.02 for i, s in enumerate(RUNNING_SHOES)}
            ),
            intent="search_product",
        ),
        expected=f"EXPLORE_CONTEXT_LIMIT={EXPLORE_CONTEXT_LIMIT} - only that many of the 10 relevant shoes come back",
        check=_check_explore_trims_to_the_limit,
    ),
    DeterministicNodeCase(
        id="product_mode_trims_the_same_oversupply_to_6",
        node="fuse_context_product",
        state=_base_state(
            retrieved_raw=pool_with_scores(
                base_score=0.85, overrides={s["id"]: 0.30 + i * 0.02 for i, s in enumerate(RUNNING_SHOES)}
            ),
        ),
        expected="PRODUCT_CONTEXT_LIMIT=6 - only 6 of the same 10 relevant shoes come back",
        check=_check_product_trims_to_6,
    ),
    DeterministicNodeCase(
        id="brand_only_semantic_filter_also_skips_the_relevance_floor",
        node="fuse_results_explore",
        state=_base_state(
            retrieved_raw=[
                {**RUNNING_SHOES[0], "score": 0.74},  # نایک
                {**RUNNING_SHOES[2], "score": 0.77},  # نایک
            ],
            filter_effective={"brand": "نایک"},
            intent="search_product",
        ),
        expected="a brand-only SQL match (no category) also counts as proof - both نایک shoes survive past 0.70",
        check=_check_brand_only_semantic_filter_skips_the_floor,
    ),
]
