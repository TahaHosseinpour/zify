"""Unit tests for the SQL-filter-building helpers in graph.py.

These are pure functions — no DB connection, no mocking needed — but they are
exactly where a wrong placeholder index or a wrong operator silently returns
the wrong products, so they're worth pinning down explicitly.
"""

from app import graph as G


class TestHasMeaningfulFilters:
    def test_none_filters(self):
        assert G.has_meaningful_filters(None) is False

    def test_empty_dict(self):
        assert G.has_meaningful_filters({}) is False

    def test_query_only_is_not_meaningful(self):
        # `query` is free text for the embedding, never a SQL predicate.
        assert G.has_meaningful_filters({"query": "لپ تاپ گیمینگ"}) is False

    def test_category_is_meaningful(self):
        assert G.has_meaningful_filters({"category": "کفش"}) is True

    def test_price_zero_is_meaningful(self):
        # 0 is a valid, meaningful bound — must not be treated as falsy/absent.
        assert G.has_meaningful_filters({"minPrice": 0}) is True

    def test_empty_string_is_not_meaningful(self):
        assert G.has_meaningful_filters({"category": ""}) is False


class TestProductWhere:
    def test_base_clause_shape(self):
        where, params, n = G._product_where("shop1", None, None, 1)
        assert where == '"shopId" = $1 AND "isActive" = true AND embedding IS NOT NULL'
        assert params == ["shop1"]
        assert n == 2

    def test_placeholder_indices_are_sequential(self):
        where, params, n = G._product_where(
            "shop1",
            {"category": "کفش", "brand": "نایک", "minPrice": 100, "maxPrice": 200},
            ["ex1", "ex2"],
            1,
        )
        # $1..$6 in order: shopId, category, brand, minPrice, maxPrice, exclude
        assert "$1" in where and "$6" in where
        assert params == ["shop1", "کفش", "نایک", "100", "200", ["ex1", "ex2"]]
        assert n == 7

    def test_first_param_offset_for_vector_queries(self):
        # vector_search_products starts filters at $2 because $1 is the vector.
        where, params, n = G._product_where("shop1", {"category": "کفش"}, None, 2)
        assert "$2" in where  # shopId
        assert "$3" in where  # category
        assert n == 4

    def test_category_is_case_insensitive_exact_match(self):
        where, params, _ = G._product_where("s", {"category": "کفش ورزشی"}, None, 1)
        assert "lower(category) = lower($2)" in where
        assert params[1] == "کفش ورزشی"

    def test_category_is_not_a_substring_match(self):
        # A %...% pattern would require the *stored* value to contain the
        # classifier's phrase — the opposite of what a customer being more
        # specific than the taxonomy needs.
        where, _, _ = G._product_where("s", {"category": "کفش"}, None, 1)
        assert "%" not in where

    def test_price_bounds_use_numeric_cast(self):
        where, params, _ = G._product_where(
            "s", {"minPrice": 1_000_000, "maxPrice": 2_000_000}, None, 1
        )
        assert "price >= $2::numeric" in where
        assert "price <= $3::numeric" in where
        # Bound as text, not float, so no float rounding creeps into the SQL.
        assert params[1] == "1000000"
        assert params[2] == "2000000"

    def test_exclude_ids_uses_not_any(self):
        where, params, _ = G._product_where("s", None, ["a", "b"], 1)
        assert "NOT (id = ANY($2))" in where
        assert params[1] == ["a", "b"]

    def test_empty_exclude_list_omits_clause(self):
        where, _, n = G._product_where("s", None, [], 1)
        assert "ANY" not in where
        assert n == 2

    def test_no_filters_at_all_is_just_the_base_clause(self):
        where, params, n = G._product_where("s", {}, None, 1)
        assert where.count("AND") == 2  # isActive + embedding, nothing else
        assert params == ["s"]
        assert n == 2

    def test_whitespace_in_category_is_trimmed(self):
        _, params, _ = G._product_where("s", {"category": "  کفش  "}, None, 1)
        assert params[1] == "کفش"


class TestActiveFilters:
    def test_drops_non_meaningful_keys(self):
        got = G._active_filters({"category": "کفش", "query": "چیزی", "minPrice": None})
        assert got == {"category": "کفش"}

    def test_drops_empty_strings(self):
        got = G._active_filters({"category": "", "brand": "نایک"})
        assert got == {"brand": "نایک"}
