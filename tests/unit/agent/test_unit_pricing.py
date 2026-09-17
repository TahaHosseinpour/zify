"""Unit tests for the relative-price-bound logic (the "ارزون‌ترش رو دارید؟" fix).

This is the highest-value test in the suite: the original bug shipped silently
for a while — "cheaper" returned a *different* product that could easily cost
more, because nothing ever compared the new candidate's price to what was on
screen.
"""

from tests.conftest import item

from app import graph as G


SHOWN = [
    item("p1", price=3_000_000),
    item("p2", price=1_500_000),
    item("p3", price=2_400_000),
]


class TestRelativePriceBound:
    def test_cheaper_bounds_below_the_shown_minimum(self):
        key, value = G._relative_price_bound("cheaper", SHOWN)
        assert key == "maxPrice"
        assert value < 1_500_000
        assert value == 1_500_000 - G.PRICE_EPSILON

    def test_pricier_bounds_above_the_shown_maximum(self):
        key, value = G._relative_price_bound("pricier", SHOWN)
        assert key == "minPrice"
        assert value > 3_000_000
        assert value == 3_000_000 + G.PRICE_EPSILON

    def test_bound_is_strictly_exclusive(self):
        """The cheapest shown product must not itself qualify as 'cheaper'."""
        _, cheaper_max = G._relative_price_bound("cheaper", SHOWN)
        assert cheaper_max < 1_500_000  # the boundary product is excluded

        _, pricier_min = G._relative_price_bound("pricier", SHOWN)
        assert pricier_min > 3_000_000

    def test_none_relative_returns_none(self):
        assert G._relative_price_bound(None, SHOWN) is None

    def test_unrecognized_value_returns_none(self):
        assert G._relative_price_bound("cheapest", SHOWN) is None

    def test_no_shown_products_invents_nothing(self):
        assert G._relative_price_bound("cheaper", []) is None
        assert G._relative_price_bound("cheaper", None) is None

    def test_non_product_items_are_ignored(self):
        shown = [item("f1", typ="faq"), item("s1", typ="shop_info")]
        assert G._relative_price_bound("cheaper", shown) is None

    def test_products_without_a_price_are_ignored(self):
        no_price = [{"id": "x", "type": "product", "metadata": {}}]
        assert G._relative_price_bound("cheaper", no_price) is None

    def test_mixed_priced_and_unpriced_uses_only_priced_ones(self):
        mixed = [item("a", price=1000), {"id": "b", "type": "product", "metadata": {}}]
        key, value = G._relative_price_bound("cheaper", mixed)
        assert key == "maxPrice"
        assert value == 1000 - G.PRICE_EPSILON

    def test_single_shown_product(self):
        one = [item("solo", price=500_000)]
        key, value = G._relative_price_bound("cheaper", one)
        assert (key, value) == ("maxPrice", 500_000 - G.PRICE_EPSILON)


class TestDeriveMode:
    def test_search_product_forces_explore(self):
        assert G.derive_mode("search_product", "product") == "explore"

    def test_compare_forces_explore(self):
        assert G.derive_mode("compare", "product") == "explore"

    def test_other_intents_keep_previous_mode(self):
        assert G.derive_mode("objection", "product") == "product"
        assert G.derive_mode("objection", "explore") == "explore"
        assert G.derive_mode("buy_intent", "product") == "product"

    def test_none_intent_keeps_previous_mode(self):
        assert G.derive_mode(None, "explore") == "explore"
