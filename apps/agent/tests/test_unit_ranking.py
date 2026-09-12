"""Unit tests for fusing/ranking/relevance-filtering retrieved items, and for
the pure routing decision after intent classification."""

from tests.conftest import item

from app import graph as G


class TestFuseAndRankContext:
    def test_sorts_by_score_ascending(self):
        items = [item("a", score=0.6), item("b", score=0.2), item("c", score=0.4)]
        ranked = G.fuse_and_rank_context(items, {})
        assert [i["id"] for i in ranked] == ["b", "c", "a"]

    def test_deduplicates_by_id_keeping_the_last(self):
        # dict-comprehension dedup keeps the *last* occurrence for a given id —
        # the vector step's row overwrites a stale one from an earlier branch.
        stale = item("a", score=0.9)
        fresh = item("a", score=0.1)
        ranked = G.fuse_and_rank_context([stale, fresh], {})
        assert len(ranked) == 1
        assert ranked[0]["score"] == 0.1

    def test_pinned_product_always_ranks_first(self):
        items = [item("a", score=0.1), item("pinned", score=0.9)]
        ranked = G.fuse_and_rank_context(items, {"product_id": "pinned"})
        assert ranked[0]["id"] == "pinned"

    def test_missing_score_defaults_to_midpoint(self):
        no_score = {"id": "x", "type": "product", "metadata": {}}
        ranked = G.fuse_and_rank_context([no_score, item("y", score=0.1)], {})
        assert [i["id"] for i in ranked] == ["y", "x"]

    def test_empty_input(self):
        assert G.fuse_and_rank_context([], {}) == []


class TestDropIrrelevant:
    def test_drops_products_beyond_the_relevance_threshold(self):
        close = item("close", score=0.5)
        far = item("far", score=0.9)
        kept = G._drop_irrelevant([close, far], pinned_id=None)
        assert [i["id"] for i in kept] == ["close"]

    def test_keeps_faq_and_shop_info_regardless_of_score(self):
        far_faq = item("f", typ="faq", score=0.99)
        far_info = item("s", typ="shop_info", score=0.99)
        kept = G._drop_irrelevant([far_faq, far_info], pinned_id=None)
        assert {i["id"] for i in kept} == {"f", "s"}

    def test_pinned_product_survives_even_if_far(self):
        far_pinned = item("pinned", score=0.99)
        kept = G._drop_irrelevant([far_pinned], pinned_id="pinned")
        assert len(kept) == 1

    def test_boundary_score_is_kept(self):
        boundary = item("b", score=G.RELEVANCE_MAX_DISTANCE)
        assert G._drop_irrelevant([boundary], pinned_id=None) == [boundary]

    def test_just_over_boundary_is_dropped(self):
        just_over = item("b", score=G.RELEVANCE_MAX_DISTANCE + 0.001)
        assert G._drop_irrelevant([just_over], pinned_id=None) == []


class TestRouterAfterIntent:
    def test_smalltalk_skips_retrieval_entirely(self):
        assert G.router_after_intent({"intent": "smalltalk"}) == "smalltalk_reply"

    def test_ask_question_and_needs_clarification(self):
        assert G.router_after_intent({"intent": "ask_question"}) == "ask_question"
        assert G.router_after_intent({"intent": "needs_clarification"}) == "ask_question"

    def test_buy_intent_always_goes_to_handle_purchase(self):
        assert G.router_after_intent({"intent": "buy_intent"}) == "handle_purchase"
        # Even with nothing shown yet — handle_purchase itself asks instead of
        # guessing when there is nothing on the table.
        assert G.router_after_intent({"intent": "buy_intent", "shown_products": []}) == "handle_purchase"

    def test_objection_with_shown_products_closes_without_retrieval(self):
        state = {"intent": "objection", "shown_products": [item("p1")]}
        assert G.router_after_intent(state) == "handle_purchase"

    def test_compare_with_shown_products_closes_without_retrieval(self):
        state = {"intent": "compare", "shown_products": [item("p1")]}
        assert G.router_after_intent(state) == "handle_purchase"

    def test_objection_with_nothing_shown_falls_through_to_search(self):
        # No products on the table yet — there is nothing to close on, so a
        # real search must run instead of a no-op closing turn.
        state = {"intent": "objection", "shown_products": []}
        assert G.router_after_intent(state) == "fan_out_explore"

    def test_compare_with_no_shown_key_at_all(self):
        assert G.router_after_intent({"intent": "compare"}) == "fan_out_explore"

    def test_product_mode_routes_to_product_fan_out(self):
        state = {"intent": "search_product", "mode": "product"}
        assert G.router_after_intent(state) == "fan_out_product"

    def test_default_routes_to_explore_fan_out(self):
        assert G.router_after_intent({"intent": "search_product", "mode": "explore"}) == "fan_out_explore"
        assert G.router_after_intent({"intent": "browse"}) == "fan_out_explore"


class TestRouteFanOut:
    def test_explore_skips_faq_for_pure_product_search(self):
        sends = G.route_fan_out_explore({"intent": "search_product"})
        nodes = {s.node for s in sends}
        assert nodes == {"sql_filter_explore", "vector_shop_info_explore"}

    def test_explore_includes_faq_for_browse(self):
        sends = G.route_fan_out_explore({"intent": "browse"})
        nodes = {s.node for s in sends}
        assert nodes == {"sql_filter_explore", "vector_shop_info_explore", "vector_faq_explore"}

    def test_product_fan_out_always_has_three_branches(self):
        sends = G.route_fan_out_product({"intent": "search_product"})
        nodes = {s.node for s in sends}
        assert nodes == {"sql_query_product", "vector_faq_product", "vector_shop_info_product"}
