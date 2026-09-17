"""Unit tests for the SQL-filter-building helpers in graph.py.

Mostly pure functions — no DB connection needed — that are exactly where a
wrong placeholder index or a wrong operator silently returns the wrong
products, so they're worth pinning down explicitly. `embed` is stubbed for
the category-resolution tests, same convention as the rest of the suite.
"""

import pytest

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

    def test_a_list_category_uses_any_instead_of_equals(self):
        # _resolve_category_candidates can hand back several plausible
        # categories when it isn't confident about just one.
        where, params, n = G._product_where(
            "s", {"category": ["کفش ورزشی", "پوشاک ورزشی"]}, None, 1
        )
        assert "lower(category) = ANY($2)" in where
        assert params[1] == ["کفش ورزشی", "پوشاک ورزشی"]
        assert n == 3

    def test_a_single_item_list_still_uses_equals(self):
        # One candidate behaves exactly like the plain-string case — same
        # clause shape, same placeholder count.
        where, params, _ = G._product_where("s", {"category": ["کفش ورزشی"]}, None, 1)
        assert "lower(category) = lower($2)" in where
        assert params[1] == "کفش ورزشی"


class TestCosineDistance:
    def test_identical_vectors_have_zero_distance(self):
        assert G._cosine_distance([1, 0], [1, 0]) == pytest.approx(0.0)

    def test_orthogonal_vectors_have_distance_one(self):
        assert G._cosine_distance([1, 0], [0, 1]) == pytest.approx(1.0)

    def test_opposite_vectors_have_distance_two(self):
        assert G._cosine_distance([1, 0], [-1, 0]) == pytest.approx(2.0)

    def test_a_zero_vector_is_treated_as_maximally_distant_not_a_crash(self):
        assert G._cosine_distance([0, 0], [1, 0]) == 1.0


class TestResolveCategoryCandidates:
    """_filter_step's embedding-similarity fallback for a `category` the
    classifier's exact-vocabulary match left null — see the "سایر لوازم
    ورزشی" incident this replaces (a lexical guess in the classifier prompt,
    proven wrong for "شلوار ورزشی" once a real shop test hit it)."""

    def _install_embed(self, monkeypatch, vectors: dict):
        async def fake_embed(text):
            return vectors[text]

        monkeypatch.setattr(G, "embed", fake_embed)

    def _state(self, message: str, categories: list[str]):
        return {
            "messages": [{"content": message}],
            "explore_filters": {},
            "shop_categories": categories,
        }

    async def test_no_categories_at_all_short_circuits(self, monkeypatch):
        # Must not even try to embed when there's nothing to compare against —
        # this is what keeps every pre-existing test (no shop_categories in
        # its state) from suddenly needing an embed stub.
        state = self._state("شلوار ورزشی می‌خوام", [])
        assert await G._resolve_category_candidates(state) == []

    async def test_a_close_match_is_returned_alone(self, monkeypatch):
        self._install_embed(monkeypatch, {
            "شلوار ورزشی می‌خوام": [1, 0],
            "پوشاک ورزشی": [1, 0],       # identical → distance 0, confident
            "لوازم برقی": [0, 1],         # orthogonal → distance 1, rejected
        })
        state = self._state("شلوار ورزشی می‌خوام", ["پوشاک ورزشی", "لوازم برقی"])
        assert await G._resolve_category_candidates(state) == ["پوشاک ورزشی"]

    async def test_an_uncertain_match_widens_to_every_plausible_category(self, monkeypatch):
        self._install_embed(monkeypatch, {
            "شلوار ورزشی می‌خوام": [1, 0],
            "پوشاک ورزشی": [0.55, 0.8352],   # distance 0.45 — uncertain band
            "لوازم ورزشی": [0.55, -0.8352],  # distance 0.45 — uncertain band
            "دیجیتال": [0, 1],                # distance 1.0 — rejected
        })
        state = self._state(
            "شلوار ورزشی می‌خوام", ["پوشاک ورزشی", "لوازم ورزشی", "دیجیتال"]
        )
        result = await G._resolve_category_candidates(state)
        assert set(result) == {"پوشاک ورزشی", "لوازم ورزشی"}

    async def test_nothing_plausible_returns_empty_not_a_bad_guess(self, monkeypatch):
        # This is the regression guard for today's bug: when nothing genuinely
        # matches, stay unscoped rather than latching onto the least-bad
        # option — a catch-all "سایر" category included.
        self._install_embed(monkeypatch, {
            "شلوار می‌خوام": [1, 0],
            "سایر لوازم ورزشی": [0, 1],  # orthogonal — nowhere close
        })
        state = self._state("شلوار می‌خوام", ["سایر لوازم ورزشی"])
        assert await G._resolve_category_candidates(state) == []

    async def test_a_catchall_category_is_never_resolved_even_as_the_closest_match(
        self, monkeypatch
    ):
        # The real regression this guards: a bare, ambiguous word ("توپ") sits
        # closer to a catch-all bucket than to any specific real category,
        # *because* the bucket describes nothing in particular — so it must be
        # excluded from the contest entirely, not just lose a fair one. Here
        # it's given the closest possible vector (identical to the query) and
        # must still be ignored, falling through to the specific category.
        self._install_embed(monkeypatch, {
            "توپ می‌خوام": [1, 0],
            "سایر لوازم ورزشی": [1, 0],   # would win on distance alone — excluded anyway
            "توپ والیبال": [0.55, 0.8352],  # uncertain band once the bucket is gone
        })
        state = self._state("توپ می‌خوام", ["سایر لوازم ورزشی", "توپ والیبال"])
        assert await G._resolve_category_candidates(state) == ["توپ والیبال"]

    async def test_only_catchall_categories_available_resolves_to_nothing(self, monkeypatch):
        state = self._state("توپ می‌خوام", ["سایر لوازم ورزشی", "متفرقه"])
        # No fake_embed installed — every category is filtered out before any
        # embedding would happen.
        assert await G._resolve_category_candidates(state) == []

    async def test_empty_message_short_circuits_without_embedding(self, monkeypatch):
        state = self._state("", ["کفش ورزشی"])
        # No fake_embed installed — a call here would raise KeyError/AttributeError.
        assert await G._resolve_category_candidates(state) == []


class TestActiveFilters:
    def test_drops_non_meaningful_keys(self):
        got = G._active_filters({"category": "کفش", "query": "چیزی", "minPrice": None})
        assert got == {"category": "کفش"}

    def test_drops_empty_strings(self):
        got = G._active_filters({"category": "", "brand": "نایک"})
        assert got == {"brand": "نایک"}


class TestFilterStepCategoryOverride:
    """_filter_step must run embedding resolution even when analyze_intent's
    classifier already picked a real, in-vocabulary category — the exact
    regression this covers: the classifier chose "ست ورزشی زنانه" ("women's
    sports set") for "شلوار ورزشی زنانه" ("women's sports pants") over the
    product's real category "لباس ورزشی زنانه" ("women's sportswear"), a
    valid-but-wrong pick that the old null-only gate could never catch.

    _resolve_category_candidates always returns a list (of 0, 1, or several
    categories — see its own tests), so `filter_effective["category"]` is a
    single-item list even on a confident match; _product_where already treats
    a one-item list the same as a bare string.
    """

    async def _run(self, monkeypatch, message, classifier_category, categories, vectors, ids_by_category):
        async def fake_embed(text):
            return vectors[text]

        async def fake_filter_candidate_ids(shop_id, filters, exclude_ids=None):
            cats = filters.get("category") or []
            cats = cats if isinstance(cats, list) else [cats]
            found = [pid for c in cats for pid in ids_by_category.get(c, [])]
            return found, False

        monkeypatch.setattr(G, "embed", fake_embed)
        monkeypatch.setattr(G, "filter_candidate_ids", fake_filter_candidate_ids)

        state = {
            "shop_id": "s1",
            "messages": [{"content": message}],
            "explore_filters": {"category": classifier_category} if classifier_category else {},
            "excluded_product_ids": [],
            "shop_categories": categories,
        }
        return await G._filter_step(state)

    async def test_embedding_evidence_overrides_the_classifiers_own_pick(self, monkeypatch):
        result = await self._run(
            monkeypatch,
            message="شلوار ورزشی زنانه می‌خوام",
            classifier_category="ست ورزشی زنانه",
            categories=["ست ورزشی زنانه", "لباس ورزشی زنانه"],
            vectors={
                # _search_text appends explore_filters["category"] when it
                # isn't already a substring of the message.
                "شلوار ورزشی زنانه می‌خوام ست ورزشی زنانه": [1, 0],
                "ست ورزشی زنانه": [0, 1],        # far — the classifier's wrong pick
                "لباس ورزشی زنانه": [1, 0],       # identical — the real match
            },
            ids_by_category={"لباس ورزشی زنانه": ["p1", "p2"]},
        )
        assert result["filter_effective"]["category"] == ["لباس ورزشی زنانه"]
        assert result["candidate_ids"] == ["p1", "p2"]

    async def test_agreement_leaves_the_classifiers_pick_in_effect(self, monkeypatch):
        result = await self._run(
            monkeypatch,
            message="توپ فوتبال می‌خوام",
            classifier_category="توپ فوتبال",
            categories=["توپ فوتبال", "توپ والیبال"],
            vectors={
                "توپ فوتبال می‌خوام": [1, 0],
                "توپ فوتبال": [1, 0],   # identical — confirms the classifier's pick
                "توپ والیبال": [0, 1],
            },
            ids_by_category={"توپ فوتبال": ["p1"]},
        )
        assert result["filter_effective"]["category"] == ["توپ فوتبال"]
        assert result["candidate_ids"] == ["p1"]

    async def test_an_embedding_hiccup_never_erases_an_already_valid_pick(self, monkeypatch):
        # Nothing is even plausible by embedding distance (every vector is
        # orthogonal to the query) — resolution returns [], and the
        # classifier's own real, in-vocabulary category must survive rather
        # than being wiped down to an unscoped search.
        result = await self._run(
            monkeypatch,
            message="چیزی می‌خوام",
            classifier_category="توپ فوتبال",
            categories=["توپ فوتبال"],
            vectors={
                # _search_text appends the classifier's category here too.
                "چیزی می‌خوام توپ فوتبال": [1, 0],
                "توپ فوتبال": [0, 1],
            },
            ids_by_category={"توپ فوتبال": ["p1"]},
        )
        assert result["filter_effective"]["category"] == "توپ فوتبال"
        assert result["candidate_ids"] == ["p1"]
