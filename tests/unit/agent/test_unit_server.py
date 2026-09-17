"""Unit tests for server.py's pure helpers: build_debug (the admin playground's
state panel) and the request-shaping logic single_purchase_url already covers
in test_unit_closing.py."""

from tests.conftest import item

from app.server import build_debug


def result(**overrides):
    base = {
        "retrieved_context": [],
        "retrieved_raw": [],
        "shown_products": [],
        "messages": [],
        "filter_status": None,
        "filter_effective": {},
        "filters_dropped": [],
        "out_of_catalog": False,
        "sort": None,
        "intent": None,
        "mode": None,
        "stage": None,
        "value_driver": None,
        "objection": None,
        "product_id": None,
        "explore_filters": {},
        "excluded_product_ids": [],
        "summary": None,
    }
    base.update(overrides)
    return base


class TestBuildDebug:
    def test_candidate_count_reads_the_explore_filter_node(self):
        node_updates = {"sql_filter_explore": {"candidate_ids": ["a", "b", "c"]}}
        debug = build_debug(result(), ["sql_filter_explore"], node_updates, 10)
        assert debug["candidateCount"] == 3

    def test_candidate_count_reads_the_product_filter_node(self):
        """Regression: candidateCount used to only read sql_filter_explore, so
        product-mode turns always reported 0 candidates even when the filter
        step actually ran and found some."""
        node_updates = {"sql_query_product": {"candidate_ids": ["a", "b"]}}
        debug = build_debug(result(), ["sql_query_product"], node_updates, 10)
        assert debug["candidateCount"] == 2

    def test_candidate_count_is_zero_when_no_filter_node_ran(self):
        debug = build_debug(result(), ["ask_question"], {"ask_question": {}}, 10)
        assert debug["candidateCount"] == 0

    def test_retrieved_counts_and_by_type(self):
        ctx = [item("a", typ="product"), item("b", typ="product"), item("c", typ="faq")]
        debug = build_debug(
            result(retrieved_context=ctx, retrieved_raw=ctx + [item("d")]), [], {}, 5
        )
        assert debug["retrieved"]["contextCount"] == 3
        assert debug["retrieved"]["rawCount"] == 4
        assert debug["retrieved"]["byType"] == {"product": 2, "faq": 1}

    def test_scores_are_rounded_to_three_decimals(self):
        ctx = [item("a", score=0.123456789)]
        debug = build_debug(result(retrieved_context=ctx), [], {}, 1)
        assert debug["retrieved"]["scores"] == [0.123]

    def test_shown_products_are_reduced_to_id_and_name(self):
        shown = [item("p1"), item("p2")]
        debug = build_debug(result(shown_products=shown), [], {}, 1)
        assert debug["shownProducts"] == [
            {"id": "p1", "name": "name-p1"},
            {"id": "p2", "name": "name-p2"},
        ]

    def test_has_summary_and_summary_chars(self):
        debug = build_debug(result(summary="خلاصه کوتاه"), [], {}, 1)
        assert debug["hasSummary"] is True
        assert debug["summaryChars"] == len("خلاصه کوتاه")

    def test_no_summary(self):
        debug = build_debug(result(summary=None), [], {}, 1)
        assert debug["hasSummary"] is False
        assert debug["summaryChars"] == 0

    def test_latency_and_path_pass_through_unchanged(self):
        debug = build_debug(result(), ["a", "b", "c"], {}, 987)
        assert debug["path"] == ["a", "b", "c"]
        assert debug["latencyMs"] == 987

    def test_missing_optional_fields_default_safely(self):
        # A turn that ended in an error path might hand back a nearly-empty
        # result dict — build_debug must not KeyError on any of it.
        debug = build_debug({}, [], {}, 0)
        assert debug["filterEffective"] == {}
        assert debug["filtersDropped"] == []
        assert debug["excludedProductIds"] == []
        assert debug["exploreFilters"] == {}
        assert debug["shownProducts"] == []
        assert debug["messageCount"] == 0
