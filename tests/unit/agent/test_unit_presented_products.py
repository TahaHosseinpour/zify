"""What the customer is shown must match what the reply said.

The search returns its top-k whether or not k things answer the request, so a
shop with one Nike shoe used to answer "کفش نایک می‌خوام" with that shoe, a
formal leather shoe and four bags. Two things stop that now, both pure Python
and tested here without a model: rows that trail the best match are dropped
before the prompt, and after the reply only the products it actually named
become cards.
"""

from tests.conftest import item

from app import graph as G


def product(id_, name, score=0.5, price=1000):
    row = item(id_, score=score, price=price, url=f"https://shop.test/{id_}")
    row["metadata"]["name"] = name
    return row


class TestWithinGap:
    def test_rows_trailing_the_best_match_are_dropped(self):
        rows = [product("nike", "کفش نایک", 0.42), product("formal", "کفش چرم رسمی", 0.61),
                product("bag", "کیف", 0.74)]
        assert [r["id"] for r in G._within_gap(rows)] == ["nike"]

    def test_comparably_good_matches_all_stay(self):
        rows = [product(f"p{i}", f"کفش {i}", 0.50 + 0.01 * i) for i in range(6)]
        assert len(G._within_gap(rows)) == 6

    def test_a_single_result_is_never_judged_against_itself(self):
        rows = [product("only", "کفش", 0.69)]
        assert G._within_gap(rows) == rows

    def test_price_sorted_rows_are_exact_answers_and_never_dropped(self):
        # Their "scores" are ranks written by the sort, not distances.
        rows = [product(f"p{i}", f"کفش {i}", i * 1e-6) for i in range(5)]
        assert len(G._within_gap(rows)) == 5

    def test_the_pinned_product_and_non_products_are_exempt(self):
        rows = [product("best", "الف", 0.30), product("pinned", "ب", 0.80),
                item("faq", typ="faq", score=0.9)]
        kept = [r["id"] for r in G._within_gap(rows, pinned_id="pinned")]
        assert kept == ["best", "pinned", "faq"]


class TestMentionedProducts:
    CANDIDATES = [
        product("pegasus", "کفش دویدن نایک پگاسوس"),
        product("zoomfly", "کفش دویدن نایک زوم فلای"),
        product("oxford", "کفش کلاسیک آکسفورد"),
        product("bag", "کوله پشتی سفری"),
    ]

    def test_only_products_the_reply_names_are_returned(self):
        reply = "بله، کفش دویدن نایک پگاسوس با قیمت ۱٬۵۵۰٬۰۰۰ تومان موجود است."
        assert [p["id"] for p in G._mentioned_products(reply, self.CANDIDATES)] == ["pegasus"]

    def test_a_shortened_name_still_counts(self):
        # Replies drop the generic words; the word no other candidate has is enough.
        reply = "پیشنهاد من پگاسوس است."
        assert [p["id"] for p in G._mentioned_products(reply, self.CANDIDATES)] == ["pegasus"]

    def test_words_shared_by_several_candidates_identify_none_of_them(self):
        reply = "چند مدل کفش دویدن نایک داریم."
        assert G._mentioned_products(reply, self.CANDIDATES) == []

    def test_order_follows_the_reply_not_the_search(self):
        reply = "۱. کوله پشتی سفری ۲. کفش کلاسیک آکسفورد"
        assert [p["id"] for p in G._mentioned_products(reply, self.CANDIDATES)] == ["bag", "oxford"]

    def test_half_space_and_arabic_letter_variants_match(self):
        candidates = [product("p", "لپ‌تاپ گیمینگ ایسوس"), product("q", "کیف چرم")]
        reply = "لپ تاپ گیمینگ ايسوس را پیشنهاد می‌کنم."
        assert [p["id"] for p in G._mentioned_products(reply, candidates)] == ["p"]

    def test_a_reply_that_names_nothing_returns_nothing(self):
        assert G._mentioned_products("متأسفانه این محصول را نداریم.", self.CANDIDATES) == []


class TestPresentedContext:
    def state(self, context, **extra):
        return {"retrieved_context": context, **extra}

    def test_cards_follow_the_reply(self):
        nike, formal, bag = (product("nike", "کفش نایک ایرزوم"), product("formal", "کفش چرم رسمی"),
                             product("bag", "کوله پشتی"))
        faq = item("f1", typ="faq")
        updates = G._presented_context(self.state([nike, formal, bag, faq]), "کفش نایک ایرزوم را داریم.")
        assert [i["id"] for i in updates["retrieved_context"]] == ["nike", "f1"]
        assert updates["buy_actions"] is True

    def test_the_numbered_list_becomes_what_the_reply_listed(self):
        # "the second one" on the next turn must count through what was shown.
        a, b, c = product("a", "آلفا"), product("b", "بتا"), product("c", "گاما")
        updates = G._presented_context(self.state([a, b, c]), "۱. گاما ۲. آلفا")
        assert [p["id"] for p in updates["shown_products"]] == ["c", "a"]

    def test_several_results_and_none_named_shows_no_cards(self):
        rows = [product("a", "آلفا"), product("b", "بتا")]
        updates = G._presented_context(self.state(rows), "چه نوع کفشی مد نظرتان است؟")
        assert [i for i in updates["retrieved_context"] if i["type"] == "product"] == []
        assert updates["buy_actions"] is False
        assert "shown_products" not in updates  # the earlier list still stands

    def test_a_single_result_keeps_its_card_even_unnamed(self):
        only = product("a", "آلفا")
        updates = G._presented_context(
            self.state([only], intent="search_product"), "بله، موجود است."
        )
        assert [i["id"] for i in updates["retrieved_context"]] == ["a"]
        assert updates["buy_actions"] is True

    def test_a_lone_row_under_a_non_product_question_is_not_an_answer(self):
        # "کد تخفیف بده" retrieves whatever is nearest; that is not a result.
        only = product("a", "پاوربانک")
        updates = G._presented_context(
            self.state([only], intent="other"), "اطلاعاتی درباره کد تخفیف ندارم."
        )
        assert updates["buy_actions"] is False
        assert [i for i in updates["retrieved_context"] if i["type"] == "product"] == []

    def test_a_single_unrelated_result_is_not_shown_when_we_dont_stock_the_request(self):
        only = product("a", "آلفا")
        updates = G._presented_context(
            self.state([only], out_of_catalog=True, intent="search_product"), "این را نداریم."
        )
        assert updates["buy_actions"] is False

    def test_the_pinned_product_stays_even_when_the_reply_says_this_one(self):
        pinned, related = product("pin", "آلفا"), product("rel", "بتا")
        updates = G._presented_context(
            self.state([pinned, related], product_id="pin"), "این کفش برای دویدن مناسب است."
        )
        assert [i["id"] for i in updates["retrieved_context"]] == ["pin"]

    def test_no_products_in_context_means_no_buttons(self):
        assert G._presented_context(self.state([item("f1", typ="faq")]), "متن") == {"buy_actions": False}
