"""Unit tests covering the handle_purchase closing-move logic and the
single_purchase_url rule — the two client-facing fixes from this project:
buy buttons must never appear on a turn that just told the customer to take
their time, and a purchase link must never point ambiguously at "whichever
product happened to rank first"."""

from tests.conftest import item

from app import graph as G
from app.server import single_purchase_url


class TestClosingMove:
    def test_buy_intent_is_the_buy_move(self):
        assert G._closing_move({"intent": "buy_intent"}) == "buy"

    def test_compare_is_the_compare_move(self):
        assert G._closing_move({"intent": "compare"}) == "compare"

    def test_objection_uses_the_specific_objection(self):
        for objection in ("price", "uncertainty", "delay"):
            assert G._closing_move({"intent": "objection", "objection": objection}) == objection

    def test_objection_without_a_specific_reason_defaults_to_uncertainty(self):
        assert G._closing_move({"intent": "objection", "objection": None}) == "uncertainty"

    def test_every_closing_move_has_an_instruction(self):
        for move in ("buy", "compare", "price", "uncertainty", "delay"):
            assert move in G.CLOSING_MOVES
            assert G.CLOSING_MOVES[move].strip()


class TestBuyActionsFlag:
    """buy_actions gates whether a client renders purchase buttons at all."""

    def test_only_buy_move_wants_buy_actions(self):
        assert G.BUY_ACTION_MOVES == {"buy"}

    def test_delay_and_uncertainty_are_not_buy_actions(self):
        assert "delay" not in G.BUY_ACTION_MOVES
        assert "uncertainty" not in G.BUY_ACTION_MOVES
        assert "price" not in G.BUY_ACTION_MOVES
        assert "compare" not in G.BUY_ACTION_MOVES


class TestProductListing:
    def test_numbers_products_starting_at_one(self):
        text = G._product_listing([item("a"), item("b")])
        assert text.startswith("1.")
        assert "2." in text

    def test_includes_buy_link_when_present(self):
        text = G._product_listing([item("a", url="https://shop/a")])
        assert "https://shop/a" in text
        assert "🛒" in text

    def test_products_without_a_url_are_still_listed(self):
        # Regression: these used to be filtered out entirely, so an objection
        # about a linkless product made it vanish from the conversation.
        text = G._product_listing([item("a", url=None)])
        assert "content-a" in text
        assert "🛒" not in text

    def test_empty_list(self):
        assert G._product_listing([]) == ""


class TestSinglePurchaseUrl:
    SIX = [
        {"id": f"p{i}", "productUrl": f"https://shop/{i}" if i != 4 else None}
        for i in range(1, 7)
    ]

    def test_no_pin_multiple_products_is_ambiguous(self):
        assert single_purchase_url(self.SIX, None) is None

    def test_pinned_product_resolves_unambiguously(self):
        assert single_purchase_url(self.SIX, "p3") == "https://shop/3"

    def test_pinned_product_without_a_url_is_none_not_a_wrong_guess(self):
        assert single_purchase_url(self.SIX, "p4") is None

    def test_pinned_id_not_in_the_list(self):
        assert single_purchase_url(self.SIX, "does-not-exist") is None

    def test_single_product_no_pin_needed(self):
        one = [{"id": "p1", "productUrl": "https://shop/1"}]
        assert single_purchase_url(one, None) == "https://shop/1"

    def test_no_products_at_all(self):
        assert single_purchase_url([], None) is None
