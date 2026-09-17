"""Judge full-graph cases: one turn through the real compiled graph, graded
by the jury (checklist rubric + an `ideal` reply description) on the final
reply the customer would actually see (the last message in the returned
state). Retrieval is stubbed (see helpers.stub_retrieval_nodes); analyze_intent
and every generation node's LLM call are real.

Add a scenario by appending a JudgeGraphCase; remove one by deleting its
entry. test_graph_judge.py just iterates this list.
"""

from __future__ import annotations

from helpers import user_says

from . import catalog
from .types import JudgeGraphCase


def _base_input(**overrides) -> dict:
    state = {
        "shop_id": "shop-1",
        "mode": "explore",
        "shop_categories": catalog.SHOP_CATEGORIES,
        "shop_brands": catalog.SHOP_BRANDS,
        "shown_products": [],
        "explore_filters": {},
        "excluded_product_ids": [],
    }
    state.update(overrides)
    return state


GRAPH_JUDGE_CASES: list[JudgeGraphCase] = [
    JudgeGraphCase(
        id="search_flow_reply_mentions_the_real_retrieved_products",
        input_state=_base_input(messages=user_says("کفش ورزشی چی دارید؟")),
        retrieval={"vector_search_explore": [catalog.NIKE_RUNNING, catalog.ADIDAS_RUNNING]},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply refers to نایک ایرزوم and/or آدیداس اولترابوست "
            "rather than a generic or invented shoe.\n"
            "- The reply does not invent a product, price or link that "
            "wasn't given in context.\n"
        ),
        ideal=(
            "A short Persian reply presenting both نایک ایرزوم "
            "(۱٬۴۵۰٬۰۰۰) and آدیداس اولترابوست (۱٬۶۵۰٬۰۰۰), asking which "
            "one the customer prefers or what matters most to them."
        ),
    ),
    JudgeGraphCase(
        id="buy_intent_closing_reply_hands_over_the_link",
        input_state=_base_input(
            messages=user_says("این کفش رو نشونم دادید", "بله", "همینو میخوام، لینک بده"),
            shown_products=[catalog.NIKE_RUNNING],
        ),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply includes or clearly hands over نایک ایرزوم's "
            f"purchase link ({catalog.NIKE_RUNNING['metadata']['productUrl']}).\n"
            "- The reply does not mention any product other than the one "
            "already on the table.\n"
        ),
        ideal=(
            "A short, encouraging Persian reply confirming نایک ایرزوم and "
            f"giving the link {catalog.NIKE_RUNNING['metadata']['productUrl']}."
        ),
    ),
    JudgeGraphCase(
        id="out_of_catalog_request_is_declined_honestly",
        input_state=_base_input(messages=user_says("موتور سیکلت برقی دارید؟")),
        retrieval={"vector_search_explore": []},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply does not claim to have, show, or recommend a "
            "specific motorcycle product - there is none in context, so doing "
            "so would be a hallucination and an automatic fail.\n"
            "- The reply states or implies the shop doesn't carry this, "
            "optionally mentioning what the shop does carry instead "
            "(کفش ورزشی، کفش رسمی، لپ‌تاپ).\n"
        ),
        ideal=(
            "A short honest Persian reply: 'موتور سیکلت نداریم' (or "
            "equivalent), optionally adding what the shop does sell instead "
            "- no invented motorcycle product or price."
        ),
    ),
    JudgeGraphCase(
        id="compare_reply_uses_only_the_two_shown_products",
        input_state=_base_input(
            messages=user_says("بین این دوتا کدوم بهتره؟"),
            shown_products=[catalog.NIKE_RUNNING, catalog.ADIDAS_RUNNING],
        ),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply compares نایک ایرزوم and آدیداس اولترابوست using "
            "only their given prices/descriptions and recommends one.\n"
            "- The reply does not introduce a third product or invented "
            "specs.\n"
        ),
        ideal=(
            "A short Persian comparison of the two real shoes by price "
            "(۱٬۴۵۰٬۰۰۰ vs ۱٬۶۵۰٬۰۰۰) and description, ending with a pick."
        ),
    ),
    JudgeGraphCase(
        id="price_objection_reply_justifies_value_without_new_product",
        input_state=_base_input(
            messages=user_says(
                "لپ‌تاپ گیمینگ نشونم دادید", "بله", "قیمتش خیلی بالاست به نظرم"
            ),
            shown_products=[catalog.ASUS_GAMING_LAPTOP],
        ),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply addresses the price concern using لپ‌تاپ گیمینگ "
            "ایسوس TUF's real specs (i7, RTX 4060, ۱۶ گیگ رم) rather than a "
            "generic 'good things cost more'.\n"
            "- The reply does not suggest a cheaper, different product.\n"
        ),
        ideal=(
            "A short Persian reply justifying the ۴۲٬۰۰۰٬۰۰۰ تومان price "
            "with the laptop's real specs, applying no sales pressure."
        ),
    ),
    JudgeGraphCase(
        id="vague_request_reply_is_a_short_clarifying_question",
        input_state=_base_input(messages=user_says("یک کفش می‌خوام")),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply is a short clarifying question (type/use/budget), "
            "not a finished answer or product list - nothing was retrieved "
            "for this vague a request.\n"
            "- The reply does not name any specific product.\n"
        ),
        ideal="A single short Persian question asking what kind of shoe or what it's for, no product mentioned.",
    ),
    JudgeGraphCase(
        id="faq_question_reply_answers_directly_from_context",
        input_state=_base_input(messages=user_says("ارسال چطوریه؟")),
        retrieval={"vector_faq": [catalog.SHIPPING_FAQ], "vector_search_explore": []},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply directly answers using the given shipping FAQ "
            "(پست پیشتاز، ۲ تا ۴ روز کاری), not a clarifying question back.\n"
            "- The reply does not invent shipping details not in the FAQ.\n"
        ),
        ideal="A short direct Persian answer: shipping is by پست پیشتاز, ۲ تا ۴ روز کاری - no follow-up question.",
    ),
    JudgeGraphCase(
        id="smalltalk_reply_is_warm_and_sells_nothing",
        input_state=_base_input(messages=user_says("سلام")),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply is a short, warm greeting.\n"
            "- The reply does not list or recommend any product.\n"
        ),
        ideal="A short warm Persian greeting, asking what the customer is looking for - no product mentioned.",
    ),
    JudgeGraphCase(
        id="delay_objection_reply_gives_space_without_a_new_product",
        input_state=_base_input(
            messages=user_says("این کفش رو نشونم دادید", "بله", "بذار یکم فکر کنم"),
            shown_products=[catalog.NIKE_RUNNING],
        ),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply gives the customer space to think, applying no "
            "pressure.\n"
            "- The reply does not suggest a new, different product.\n"
        ),
        ideal="A short, relaxed Persian reply that takes 'let me think' as fine, invites questions later, no pressure and no new product.",
    ),
    JudgeGraphCase(
        id="uncertainty_objection_reply_addresses_the_concern_honestly",
        input_state=_base_input(
            messages=user_says("این کفش رو نشونم دادید", "بله", "مطمئن نیستم این برام مناسبه"),
            shown_products=[catalog.NIKE_RUNNING],
        ),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply responds to the uncertainty using نایک ایرزوم's "
            "real description/price, not invented reassurances.\n"
            "- The reply does not suggest a different product.\n"
        ),
        ideal="A short Persian reply addressing the uncertainty with نایک ایرزوم's real description, maybe asking what specifically worries them - no other product offered.",
    ),
    JudgeGraphCase(
        id="quality_driven_customer_reply_leads_with_the_premium_option",
        input_state=_base_input(messages=user_says("بهترین و باکیفیت‌ترین کفش دویدن رو می‌خوام، قیمت مهم نیست")),
        retrieval={"vector_search_explore": [catalog.PUMA_CASUAL, catalog.ADIDAS_RUNNING]},
        rubric=(
            "- The reply is written in Persian.\n"
            "- Given the customer said quality matters most, the reply leads "
            "with آدیداس اولترابوست (the higher-quality running shoe) and "
            "its real features, not پوما اسمش (the cheaper casual one).\n"
            "- The reply does not push the cheaper option or lecture about "
            "saving money.\n"
        ),
        ideal="A short Persian reply presenting آدیداس اولترابوست first with a real quality feature (boost midsole), not opening with the cheaper alternative.",
    ),
    JudgeGraphCase(
        id="considering_stage_reply_reinforces_value_without_pressure",
        input_state=_base_input(
            messages=user_says("این کفش رو نشونم دادید", "بله", "بین این و چندتا جای دیگه که دیدم مردد موندم"),
            shown_products=[catalog.NIKE_RUNNING],
        ),
        retrieval={},
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply gives one concrete reason (grounded in نایک ایرزوم's "
            "real description) to help the customer decide, rather than "
            "re-listing the product with no added reasoning.\n"
            "- The reply does not apply closing pressure or urgency tactics.\n"
        ),
        ideal="A short Persian reply reinforcing نایک ایرزوم's real value to help resolve the customer's indecision, calmly, without pressure.",
    ),
]
