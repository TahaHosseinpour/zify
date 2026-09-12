"""Integration tests against the real Postgres/pgvector instance.

These exercise exactly the behaviour a mock cannot verify: whether the raw SQL
graph.py builds actually does what its Python-side logic assumes — parameter
binding, case folding, numeric bounds, shop isolation, and vector-search
scoping to a candidate-id set. Every OpenAI call is still avoided: vector
queries take a hand-built fixed-length vector instead of a real embedding, so
what's under test is the SQL, not embedding quality.

Skipped automatically (via the `real_db`/`shop_id` fixtures) when Postgres is
unreachable or has no embedded fixture data — see conftest.py.
"""

import pytest

from app import graph as G

# products.embedding is vector(1536); pgvector's <=> operator requires the
# query vector to match that dimension exactly or it errors, not just returns
# a meaningless score.
FIXED_VEC = [0.01] * 1536


class TestFilterCandidateIdsAgainstRealData:
    async def test_budget_is_never_exceeded(self, shop_id):
        ids, overflowed = await G.filter_candidate_ids(shop_id, {"maxPrice": 5_000_000})
        assert overflowed is False
        assert ids, "expected at least one product under 5,000,000 in fixture data"

        rows = await G.db.query_raw(
            "SELECT price FROM products WHERE id = ANY($1)", ids
        )
        assert all(float(r["price"]) <= 5_000_000 for r in rows)

    async def test_min_and_max_price_combined(self, shop_id):
        ids, _ = await G.filter_candidate_ids(
            shop_id, {"minPrice": 1_000_000, "maxPrice": 3_000_000}
        )
        rows = await G.db.query_raw("SELECT price FROM products WHERE id = ANY($1)", ids)
        assert all(1_000_000 <= float(r["price"]) <= 3_000_000 for r in rows)

    async def test_shop_isolation_never_leaks_another_shops_products(self, real_db):
        shops = await real_db.query_raw(
            'SELECT DISTINCT "shopId" FROM products WHERE embedding IS NOT NULL'
        )
        if len(shops) < 2:
            pytest.skip("fixture data has only one shop with embedded products")
        shop_a, shop_b = str(shops[0]["shopId"]), str(shops[1]["shopId"])

        ids_a, _ = await G.filter_candidate_ids(shop_a, {"minPrice": 0})
        rows = await real_db.query_raw(
            'SELECT "shopId" FROM products WHERE id = ANY($1)', ids_a
        )
        assert all(str(r["shopId"]) == shop_a for r in rows)

    async def test_category_filter_is_case_insensitive_against_real_rows(self, shop_id):
        rows = await G.db.query_raw(
            'SELECT DISTINCT category FROM products '
            'WHERE "shopId" = $1 AND category IS NOT NULL LIMIT 1',
            shop_id,
        )
        if not rows:
            pytest.skip("no categorized products for this shop")
        real_category = str(rows[0]["category"])

        ids_exact, _ = await G.filter_candidate_ids(shop_id, {"category": real_category})
        ids_upper, _ = await G.filter_candidate_ids(
            shop_id, {"category": real_category.upper()}
        )
        ids_padded, _ = await G.filter_candidate_ids(
            shop_id, {"category": f"  {real_category}  "}
        )
        assert ids_exact
        assert set(ids_exact) == set(ids_padded)
        # Persian has no case, but the comparison must not accidentally be
        # bytewise-sensitive to something in the string either.
        assert set(ids_exact) == set(ids_upper)

    async def test_unknown_category_matches_nothing(self, shop_id):
        ids, overflowed = await G.filter_candidate_ids(
            shop_id, {"category": "دسته‌ای که قطعاً وجود ندارد xyz123"}
        )
        assert ids == []
        assert overflowed is False

    async def test_excluded_ids_are_never_returned(self, shop_id):
        first_ids, _ = await G.filter_candidate_ids(shop_id, {"minPrice": 0})
        assert first_ids
        excluded = first_ids[:1]
        remaining, _ = await G.filter_candidate_ids(
            shop_id, {"minPrice": 0}, exclude_ids=excluded
        )
        assert excluded[0] not in remaining

    async def test_products_without_embeddings_are_never_candidates(self, real_db, shop_id):
        no_embedding = await real_db.query_raw(
            'SELECT id FROM products WHERE "shopId" = $1 AND embedding IS NULL LIMIT 5',
            shop_id,
        )
        if not no_embedding:
            pytest.skip("every product in fixture data already has an embedding")
        ids, _ = await G.filter_candidate_ids(shop_id, {"minPrice": 0})
        excluded_ids = {str(r["id"]) for r in no_embedding}
        assert not (excluded_ids & set(ids))


class TestVectorSearchScoping:
    async def test_scoping_to_candidate_ids_never_returns_an_id_outside_the_set(self, shop_id):
        candidate_ids, _ = await G.filter_candidate_ids(shop_id, {"maxPrice": 3_000_000})
        if not candidate_ids:
            pytest.skip("no products under 3,000,000 in fixture data")

        results = await G.vector_search_products(
            shop_id, FIXED_VEC, k=50, candidate_ids=candidate_ids
        )
        assert set(i["id"] for i in results) <= set(candidate_ids)

    async def test_empty_candidate_list_returns_nothing_without_querying(self, shop_id):
        # An empty (but non-None) candidate list means the filter step found
        # zero matches — vector search must not silently fall back to the
        # whole catalog.
        results = await G.vector_search_products(
            shop_id, FIXED_VEC, k=10, candidate_ids=[]
        )
        assert results == []

    async def test_inline_mode_still_respects_the_price_bound(self, shop_id):
        # candidate_ids=None means "apply filters inline in the vector query
        # itself" (the FILTER_INLINE path, used when the candidate set
        # overflowed CANDIDATE_POOL_LIMIT).
        results = await G.vector_search_products(
            shop_id, FIXED_VEC, k=50, candidate_ids=None, filters={"maxPrice": 2_000_000}
        )
        assert all(float(r["metadata"]["price"]) <= 2_000_000 for r in results)

    async def test_k_limits_the_result_count(self, shop_id):
        results = await G.vector_search_products(shop_id, FIXED_VEC, k=2, candidate_ids=None)
        assert len(results) <= 2


class TestRelativePriceBoundEndToEnd:
    """The exact scenario the "cheaper" bug was about, on real fixture data:
    request cheaper-than-shown, verify every candidate is strictly cheaper."""

    async def test_cheaper_candidates_are_all_strictly_below_the_shown_minimum(self, shop_id):
        rows = await G.db.query_raw(
            'SELECT id, name, price FROM products '
            'WHERE "shopId" = $1 AND "isActive" = true AND embedding IS NOT NULL '
            'ORDER BY price DESC LIMIT 4',
            shop_id,
        )
        if len(rows) < 2:
            pytest.skip("not enough fixture products for this shop")

        shown = [
            {"id": str(r["id"]), "type": "product", "metadata": {"price": float(r["price"])}}
            for r in rows
        ]
        cheapest_shown = min(float(r["price"]) for r in rows)

        key, value = G._relative_price_bound("cheaper", shown)
        assert key == "maxPrice"

        ids, _ = await G.filter_candidate_ids(shop_id, {"maxPrice": value})
        if not ids:
            pytest.skip("nothing in this shop is cheaper than the shown minimum")

        candidate_rows = await G.db.query_raw(
            "SELECT price FROM products WHERE id = ANY($1)", ids
        )
        assert all(float(r["price"]) < cheapest_shown for r in candidate_rows)

    async def test_pricier_candidates_are_all_strictly_above_the_shown_maximum(self, shop_id):
        rows = await G.db.query_raw(
            'SELECT id, price FROM products '
            'WHERE "shopId" = $1 AND "isActive" = true AND embedding IS NOT NULL '
            'ORDER BY price ASC LIMIT 4',
            shop_id,
        )
        if len(rows) < 2:
            pytest.skip("not enough fixture products for this shop")

        shown = [
            {"id": str(r["id"]), "type": "product", "metadata": {"price": float(r["price"])}}
            for r in rows
        ]
        most_expensive_shown = max(float(r["price"]) for r in rows)

        key, value = G._relative_price_bound("pricier", shown)
        assert key == "minPrice"

        ids, _ = await G.filter_candidate_ids(shop_id, {"minPrice": value})
        if not ids:
            pytest.skip("nothing in this shop is pricier than the shown maximum")

        candidate_rows = await G.db.query_raw(
            "SELECT price FROM products WHERE id = ANY($1)", ids
        )
        assert all(float(r["price"]) > most_expensive_shown for r in candidate_rows)


class TestSortedProducts:
    """The superlative path ("ارزان‌ترین گوشی") — SQL ORDER BY, not similarity.
    Never exercised anywhere else in the suite before this."""

    async def test_price_asc_is_actually_ascending(self, shop_id):
        results = await G.sorted_products(shop_id, "price_asc", None, None)
        prices = [float(r["metadata"]["price"]) for r in results]
        assert prices == sorted(prices)
        assert prices  # fixture data has priced products

    async def test_price_desc_is_actually_descending(self, shop_id):
        results = await G.sorted_products(shop_id, "price_desc", None, None)
        prices = [float(r["metadata"]["price"]) for r in results]
        assert prices == sorted(prices, reverse=True)

    async def test_unknown_sort_key_returns_nothing(self, shop_id):
        assert await G.sorted_products(shop_id, "relevance", None, None) == []

    async def test_respects_a_combined_price_filter(self, shop_id):
        results = await G.sorted_products(
            shop_id, "price_asc", {"maxPrice": 5_000_000}, None
        )
        assert all(float(r["metadata"]["price"]) <= 5_000_000 for r in results)

    async def test_sorted_rows_get_a_zero_relevance_score(self, shop_id):
        # They're exact answers to a stated constraint, not similarity matches,
        # so they must clear _drop_irrelevant's threshold unconditionally.
        results = await G.sorted_products(shop_id, "price_asc", None, None)
        assert results and all(r["score"] == 0.0 for r in results)

    async def test_result_count_is_capped_at_sort_limit(self, shop_id):
        results = await G.sorted_products(shop_id, "price_asc", None, None)
        assert len(results) <= G.SORT_LIMIT

    async def test_excluded_ids_are_honoured(self, shop_id):
        first = await G.sorted_products(shop_id, "price_asc", None, None)
        if not first:
            pytest.skip("no products to exclude")
        excluded = [first[0]["id"]]
        again = await G.sorted_products(shop_id, "price_asc", None, excluded)
        assert excluded[0] not in {r["id"] for r in again}


class TestFaqAndShopInfoVectorSearch:
    """These ride the FAQ/shop-info fan-out branches on every explore turn
    that isn't a pure product search."""

    async def test_faq_search_returns_shop_scoped_rows(self, shop_id):
        results = await G.vector_search_faq(shop_id, FIXED_VEC, k=5)
        assert all(r["type"] == "faq" for r in results)
        assert all(0.0 <= r["score"] <= 2.0 for r in results)  # cosine distance range

    async def test_faq_k_limits_the_count(self, shop_id):
        results = await G.vector_search_faq(shop_id, FIXED_VEC, k=1)
        assert len(results) <= 1

    async def test_shop_info_search_returns_shop_scoped_rows(self, shop_id):
        results = await G.vector_search_shop_info(shop_id, FIXED_VEC, k=5)
        assert all(r["type"] == "shop_info" for r in results)

    async def test_shop_info_content_is_non_empty_text(self, shop_id):
        results = await G.vector_search_shop_info(shop_id, FIXED_VEC, k=5)
        if not results:
            pytest.skip("no shop_info_chunks for this shop")
        assert all(r["content"].strip() for r in results)


class TestPinnedProductLookup:
    """_pinned_product backs both sql_query_product and handle_purchase — the
    shop-scoping here is a real isolation boundary, not a convenience."""

    async def test_pinned_product_renders_with_full_metadata(self, real_db, shop_id):
        row = await real_db.query_raw(
            'SELECT id FROM products WHERE "shopId" = $1 AND embedding IS NOT NULL LIMIT 1',
            shop_id,
        )
        if not row:
            pytest.skip("no products for this shop")
        product_id = str(row[0]["id"])

        result = await G._pinned_product({"shop_id": shop_id, "product_id": product_id})
        assert result is not None
        assert result["id"] == product_id
        assert result["type"] == "product"
        assert "name" in result["metadata"]
        assert "price" in result["metadata"]

    async def test_a_product_id_from_another_shop_resolves_to_nothing(self, real_db):
        shops = await real_db.query_raw(
            'SELECT DISTINCT "shopId" FROM products WHERE embedding IS NOT NULL'
        )
        if len(shops) < 2:
            pytest.skip("fixture data has only one shop with embedded products")
        shop_a, shop_b = str(shops[0]["shopId"]), str(shops[1]["shopId"])

        row_b = await real_db.query_raw(
            'SELECT id FROM products WHERE "shopId" = $1 LIMIT 1', shop_b
        )
        if not row_b:
            pytest.skip("second shop has no products")
        product_from_b = str(row_b[0]["id"])

        # Asking shop A to resolve shop B's product id must return nothing —
        # this is the boundary that stops one shop's customer from ever
        # pinning, viewing, or buying another shop's product by id.
        result = await G._pinned_product({"shop_id": shop_a, "product_id": product_from_b})
        assert result is None

    async def test_no_product_id_returns_none_without_querying(self):
        result = await G._pinned_product({"shop_id": "irrelevant", "product_id": None})
        assert result is None


class TestShopCategories:
    """This is the vocabulary analyze_intent's category guard checks the
    classifier's guess against — must reflect the actual catalog, not the
    shop's aspirational category list."""

    async def test_returns_only_categories_with_active_products(self, shop_id):
        categories = await G.shop_categories(shop_id)
        assert isinstance(categories, list)
        if categories:
            assert all(isinstance(c, str) and c for c in categories)

    async def test_a_category_unique_to_one_shop_never_leaks_into_another(self, real_db):
        rows = await real_db.query_raw(
            'SELECT "shopId", category FROM products '
            'WHERE category IS NOT NULL AND "isActive" = true GROUP BY "shopId", category'
        )
        owners: dict[str, set[str]] = {}
        for r in rows:
            owners.setdefault(str(r["category"]), set()).add(str(r["shopId"]))
        all_shops = {str(r["shopId"]) for r in rows}

        unique = [(cat, next(iter(shops))) for cat, shops in owners.items() if len(shops) == 1]
        if not unique or len(all_shops) < 2:
            pytest.skip("fixture data has no category unique to a single shop")
        category, owning_shop = unique[0]
        other_shop = next(iter(all_shops - {owning_shop}))

        assert category in await G.shop_categories(owning_shop)
        assert category not in await G.shop_categories(other_shop)


class TestFanOutNodesAgainstRealData:
    """The full node functions (not just their SQL helpers), still with a
    fixed vector instead of a real embedding, exercised end to end."""

    @pytest.fixture(autouse=True)
    def fixed_embed(self, monkeypatch):
        async def fake_embed(text):
            return FIXED_VEC

        monkeypatch.setattr(G, "embed", fake_embed)

    async def test_vector_search_explore_after_a_real_filter_step(self, shop_id):
        state = {
            "shop_id": shop_id,
            "messages": [],
            "explore_filters": {"maxPrice": 5_000_000, "query": "کفش"},
            "excluded_product_ids": [],
            "intent": "search_product",
            "sort": None,
        }
        step1 = await G.sql_filter_explore(state)
        state.update(step1)
        step2 = await G.vector_search_explore(state)
        raw = step2["retrieved_raw"]
        assert all(float(r["metadata"]["price"]) <= 5_000_000 for r in raw)
        assert step2["candidate_ids"] == []  # cleared once consumed

    async def test_vector_search_explore_with_no_filters_searches_the_whole_catalog(self, shop_id):
        # The FILTER_NONE / _vector_scope "nothing to scope to" path: a pure
        # browse turn with no stated constraints at all.
        state = {
            "shop_id": shop_id,
            "messages": [],
            "explore_filters": {},
            "excluded_product_ids": [],
            "intent": "browse",
            "sort": None,
        }
        step1 = await G.sql_filter_explore(state)
        assert step1["filter_status"] == G.FILTER_NONE
        state.update(step1)
        step2 = await G.vector_search_explore(state)
        assert step2["retrieved_raw"]  # the unscoped catalog search finds something

    async def test_vector_search_explore_honours_a_sort_request(self, shop_id):
        state = {
            "shop_id": shop_id,
            "messages": [],
            "explore_filters": {},
            "excluded_product_ids": [],
            "intent": "search_product",
            "sort": "price_asc",
        }
        step1 = await G.sql_filter_explore(state)
        state.update(step1)
        step2 = await G.vector_search_explore(state)
        prices = [float(r["metadata"]["price"]) for r in step2["retrieved_raw"]]
        assert prices == sorted(prices)

    async def test_sql_query_product_loads_the_pinned_row_and_runs_the_filter(self, real_db, shop_id):
        row = await real_db.query_raw(
            'SELECT id FROM products WHERE "shopId" = $1 AND embedding IS NOT NULL LIMIT 1',
            shop_id,
        )
        if not row:
            pytest.skip("no products for this shop")
        product_id = str(row[0]["id"])

        state = {
            "shop_id": shop_id,
            "product_id": product_id,
            "explore_filters": {},
            "excluded_product_ids": [],
        }
        result = await G.sql_query_product(state)
        assert result["retrieved_raw"][0]["id"] == product_id
        assert result["filter_status"] == G.FILTER_NONE  # no meaningful filters set

    async def test_vector_search_product_scopes_to_the_filter_step(self, shop_id):
        state = {
            "shop_id": shop_id,
            "messages": [],
            "product_id": None,
            "explore_filters": {"maxPrice": 5_000_000},
            "excluded_product_ids": [],
        }
        step1 = await G.sql_query_product(state)
        state.update(step1)
        step2 = await G.vector_search_product(state)
        assert all(
            float(r["metadata"]["price"]) <= 5_000_000 for r in step2["retrieved_raw"]
        )

    async def test_vector_faq_node_returns_faq_typed_rows(self, shop_id):
        state = {"shop_id": shop_id, "messages": [], "explore_filters": {}}
        result = await G.vector_faq(state)
        assert all(r["type"] == "faq" for r in result["retrieved_raw"])

    async def test_vector_shop_info_node_returns_shop_info_typed_rows(self, shop_id):
        state = {"shop_id": shop_id, "messages": [], "explore_filters": {}}
        result = await G.vector_shop_info(state)
        assert all(r["type"] == "shop_info" for r in result["retrieved_raw"])


class TestFilterStepOverflow:
    """The candidate-pool-overflow path — CANDIDATE_POOL_LIMIT is 500, far more
    than any fixture catalog, so this is tested by shrinking the limit rather
    than growing the catalog."""

    async def test_overflow_switches_to_inline_filtering(self, monkeypatch, shop_id):
        monkeypatch.setattr(G, "CANDIDATE_POOL_LIMIT", 1)
        state = {
            "shop_id": shop_id,
            "explore_filters": {"minPrice": 0},  # matches every product
            "excluded_product_ids": [],
        }
        result = await G._filter_step(state)
        assert result["filter_status"] == G.FILTER_INLINE
        assert result["candidate_ids"] == []
        assert result["filter_effective"] == {"minPrice": 0}

    async def test_inline_status_makes_vector_search_apply_filters_directly(self, monkeypatch, shop_id):
        monkeypatch.setattr(G, "CANDIDATE_POOL_LIMIT", 1)

        async def fake_embed(text):
            return FIXED_VEC

        monkeypatch.setattr(G, "embed", fake_embed)

        state = {
            "shop_id": shop_id,
            "messages": [],
            "explore_filters": {"maxPrice": 5_000_000},
            "excluded_product_ids": [],
            "intent": "search_product",
            "sort": None,
        }
        step1 = await G.sql_filter_explore(state)
        assert step1["filter_status"] == G.FILTER_INLINE
        state.update(step1)
        step2 = await G.vector_search_explore(state)
        assert all(
            float(r["metadata"]["price"]) <= 5_000_000 for r in step2["retrieved_raw"]
        )


class TestFilterStepProgressiveRelaxation:
    """_filter_step must always honour category/brand once real and only ever
    relax price first — showing the right product at a higher price beats
    showing an unrelated one that merely fits the budget."""

    async def test_impossible_price_relaxes_first_but_keeps_the_category(self, shop_id):
        rows = await G.db.query_raw(
            'SELECT DISTINCT category FROM products '
            'WHERE "shopId" = $1 AND category IS NOT NULL LIMIT 1',
            shop_id,
        )
        if not rows:
            pytest.skip("no categorized products for this shop")
        real_category = str(rows[0]["category"])

        state = {
            "shop_id": shop_id,
            "explore_filters": {
                "category": real_category,
                "maxPrice": 1,  # nothing in this category costs 1 toman
            },
            "excluded_product_ids": [],
        }
        result = await G._filter_step(state)
        assert result["filter_status"] in (G.FILTER_IDS, G.FILTER_RELAXED)
        if result["filter_status"] == G.FILTER_IDS:
            assert result["filters_dropped"] == ["maxPrice"]
            assert result["filter_effective"].get("category") == real_category
            rows = await G.db.query_raw(
                "SELECT category FROM products WHERE id = ANY($1)", result["candidate_ids"]
            )
            assert all(r["category"].lower() == real_category.lower() for r in rows)

    async def test_impossible_price_alone_is_reported_as_relaxed_never_silently_dropped(self, shop_id):
        state = {
            "shop_id": shop_id,
            "explore_filters": {"maxPrice": 1},  # nothing costs 1 toman
            "excluded_product_ids": [],
        }
        result = await G._filter_step(state)
        assert result["filter_status"] == G.FILTER_RELAXED
        assert result["candidate_ids"] == []
        assert "maxPrice" in result["filters_dropped"]

    async def test_category_and_brand_both_invalid_with_no_price_fully_relaxes(self, shop_id):
        # Neither predicate is in FILTER_RELAXATION_ORDER's fallback chain once
        # both are exhausted, and there is no price to fall back to at all —
        # this is the one path where the loop drops its last predicate and the
        # attempt dict itself goes empty.
        state = {
            "shop_id": shop_id,
            "explore_filters": {
                "category": "دسته‌ای که قطعاً وجود ندارد",
                "brand": "برندی که قطعاً وجود ندارد",
            },
            "excluded_product_ids": [],
        }
        result = await G._filter_step(state)
        assert result["filter_status"] == G.FILTER_RELAXED
        assert result["candidate_ids"] == []
        assert set(result["filters_dropped"]) == {"category", "brand"}

    async def test_satisfiable_filters_return_ids_with_no_drops(self, shop_id):
        state = {
            "shop_id": shop_id,
            "explore_filters": {"minPrice": 0},
            "excluded_product_ids": [],
        }
        result = await G._filter_step(state)
        assert result["filter_status"] == G.FILTER_IDS
        assert result["filters_dropped"] == []
        assert result["candidate_ids"]
