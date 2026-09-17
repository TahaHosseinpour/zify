"""Judge node cases: generation nodes, called with the real conversational
LLM, graded by the jury against a rubric (checklist) and an `ideal` reply
description, because their output is prose - no plain assertion can check it.

Products/FAQs come from cases/catalog.py, whose `content` is built the same
way app/graph.py's own `_product_content` builds it in production - the real
text the LLM sees in its prompt, not a placeholder.

Add a scenario by appending a JudgeNodeCase; remove one by deleting its
entry. test_node_judge.py just iterates this list.
"""

from __future__ import annotations

from helpers import user_says

from . import catalog
from .types import JudgeNodeCase


def _base_state(**overrides) -> dict:
    state = {
        "shop_id": "shop-1",
        "mode": "explore",
        "stage": "browsing",
        "value_driver": None,
        "objection": None,
        "filters_dropped": [],
        "out_of_catalog": False,
        "summary": None,
    }
    state.update(overrides)
    return state


NODE_JUDGE_CASES: list[JudgeNodeCase] = [
    JudgeNodeCase(
        id="suggest_products_mentions_only_the_retrieved_products",
        node="suggest_products",
        state=_base_state(
            messages=user_says("کفش ورزشی می‌خوام، چی دارید؟"),
            retrieved_context=[catalog.NIKE_RUNNING, catalog.ADIDAS_RUNNING, catalog.PUMA_CASUAL],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply refers to at least one of the three retrieved shoes "
            "(نایک ایرزوم, آدیداس اولترابوست, or پوما اسمش) by name or price.\n"
            "- The reply does not mention any product, brand, or price that "
            "isn't one of these three - inventing a fourth product is an "
            "automatic fail.\n"
        ),
        ideal=(
            "A short, friendly Persian message that lists the three shoes "
            "(نایک ایرزوم ۱٬۴۵۰٬۰۰۰, آدیداس اولترابوست ۱٬۶۵۰٬۰۰۰, پوما اسمش "
            "۹۸۰٬۰۰۰) with their prices, maybe a one-line differentiator each "
            "(e.g. running vs. casual), and asks which one interests the "
            "customer or what matters most to them (price/brand/use)."
        ),
    ),
    JudgeNodeCase(
        id="suggest_products_out_of_catalog_declines_honestly",
        node="suggest_products",
        state=_base_state(
            messages=user_says("کیف چرم مردونه دارید؟"),
            retrieved_context=[],
            out_of_catalog=True,
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply clearly states the shop does not carry this "
            "product, without a long apology.\n"
            "- The reply does not invent or describe any specific product, "
            "since none was given in context - doing so is an automatic "
            "fail.\n"
        ),
        ideal=(
            "A short, honest Persian message: 'این محصول رو نداریم' (or "
            "equivalent), with no invented product filling the gap. It may "
            "ask what else the customer is looking for."
        ),
    ),
    JudgeNodeCase(
        id="suggest_products_explains_the_dropped_budget_honestly",
        node="suggest_products",
        state=_base_state(
            messages=user_says("لپ‌تاپ اداری زیر ۱۵ میلیون دارید؟"),
            retrieved_context=[catalog.LENOVO_OFFICE_LAPTOP],
            filters_dropped=["maxPrice"],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply is upfront that nothing matched the stated ۱۵ "
            "میلیون budget before presenting لپ‌تاپ اداری لنوو ثینک‌پد "
            "(۲۱٬۵۰۰٬۰۰۰) as the closest alternative.\n"
            "- The reply does not claim the Lenovo laptop is under ۱۵ "
            "میلیون, and does not invent a cheaper product.\n"
        ),
        ideal=(
            "A short, honest Persian reply: says nothing matched the ۱۵ "
            "میلیون budget, then offers لپ‌تاپ اداری لنوو ثینک‌پد at its "
            "real price (۲۱٬۵۰۰٬۰۰۰ تومان) as the nearest option, framed as "
            "'closest we have', not as a match to the stated budget."
        ),
    ),
    JudgeNodeCase(
        id="ask_question_clarifies_instead_of_answering",
        node="ask_question",
        state=_base_state(
            messages=user_says("یک چیزی برای هدیه می‌خوام"),
            intent="needs_clarification",
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply asks a short clarifying question (e.g. who the gift "
            "is for, or a budget) rather than presenting a finished answer or "
            "a list of products.\n"
            "- The reply is short (a clarifying question, not a paragraph).\n"
        ),
        ideal=(
            "One short Persian question, e.g. 'این هدیه برای چه کسیه و "
            "بودجه‌تون حدوداً چقدره؟' - no product list, no long preamble."
        ),
    ),
    JudgeNodeCase(
        id="ask_question_answers_a_complete_question_from_faq_context",
        node="ask_question",
        state=_base_state(messages=user_says("ارسال چطوریه؟"), intent="browse"),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply directly answers the shipping question using the "
            "FAQ content given (پست پیشتاز، ۲ تا ۴ روز کاری).\n"
            "- The reply does not ask a clarifying question back - the "
            "request was already complete.\n"
        ),
        ideal=(
            "A short direct Persian answer restating the FAQ: shipping is by "
            "پست پیشتاز and takes ۲ تا ۴ روز کاری, with no follow-up "
            "question."
        ),
        faq=[catalog.SHIPPING_FAQ],
    ),
    JudgeNodeCase(
        id="ask_question_out_of_catalog_states_unavailability_not_a_question",
        node="ask_question",
        state=_base_state(
            messages=user_says("کیف چرم مردونه دارید؟"),
            intent="search_product",
            out_of_catalog=True,
            shop_categories=catalog.SHOP_CATEGORIES,
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply states plainly the shop doesn't carry this product, "
            "without asking the customer a clarifying question about it.\n"
            "- The reply may mention the shop's real categories "
            "(کفش ورزشی، کفش رسمی، لپ‌تاپ) as what's available instead.\n"
        ),
        ideal=(
            "A short Persian statement: 'کیف چرم نداریم' (or equivalent), "
            "optionally followed by 'ولی کفش ورزشی، کفش رسمی و لپ‌تاپ داریم' "
            "- never a question asking what kind of bag they want."
        ),
    ),
    JudgeNodeCase(
        id="product_agent_stays_on_the_pinned_product",
        node="product_agent",
        state=_base_state(
            mode="product",
            messages=user_says("این محصول چند تومنه؟"),
            retrieved_context=[catalog.NIKE_RUNNING],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply answers about نایک ایرزوم, including its price "
            "(۱٬۴۵۰٬۰۰۰ تومان).\n"
            "- The reply does not introduce a second, different product.\n"
        ),
        ideal="A short Persian reply stating نایک ایرزوم costs ۱٬۴۵۰٬۰۰۰ تومان, nothing else offered.",
    ),
    JudgeNodeCase(
        id="product_agent_addresses_an_embedded_objection",
        node="product_agent",
        state=_base_state(
            mode="product",
            messages=user_says("قیمتش یکم بالاست به نظرم"),
            retrieved_context=[catalog.ASUS_GAMING_LAPTOP],
            objection="price",
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply addresses the price concern with a concrete reason "
            "grounded in لپ‌تاپ گیمینگ ایسوس TUF's given specs (i7, RTX "
            "4060, ۱۶ گیگ رم), not a generic 'quality costs more'.\n"
            "- The reply does not suggest a different, cheaper product.\n"
        ),
        ideal=(
            "A short Persian reply that justifies the ۴۲٬۰۰۰٬۰۰۰ تومان "
            "price using the laptop's real specs (RTX 4060 GPU, i7, ۱۶ گیگ "
            "رم) rather than deflecting or offering something else."
        ),
    ),
    JudgeNodeCase(
        id="smalltalk_reply_is_warm_and_sells_nothing",
        node="smalltalk_reply",
        state=_base_state(messages=user_says("سلام خوبی؟")),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply is a short, warm greeting that asks what the customer "
            "is looking for.\n"
            "- The reply does not list or recommend any product.\n"
        ),
        ideal="A short warm Persian greeting back, e.g. 'سلام! ممنون، شما چطورید؟ دنبال چی می‌گردید؟' - no product mentioned.",
    ),
    JudgeNodeCase(
        id="smalltalk_reply_to_a_thank_you_stays_short",
        node="smalltalk_reply",
        state=_base_state(messages=user_says("ممنون از راهنمایی‌تون")),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply is a short, warm acknowledgement (you're welcome, "
            "happy to help), not a new sales pitch.\n"
            "- The reply does not list or recommend any product.\n"
        ),
        ideal="A short Persian 'خواهش می‌کنم' style reply, optionally asking if there's anything else they need - no product list.",
    ),
    JudgeNodeCase(
        id="smalltalk_reply_to_a_bare_reaction_asks_what_they_need",
        node="smalltalk_reply",
        state=_base_state(messages=user_says("چه جالب")),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply is short and asks what the customer is looking for, "
            "since their message carried no actual request.\n"
            "- The reply does not list or recommend any product.\n"
        ),
        ideal="A short Persian reply that invites the customer to say what they need - no product list, no assumptions about what they want.",
    ),
    JudgeNodeCase(
        id="handle_purchase_buy_move_gives_the_link",
        node="handle_purchase",
        state=_base_state(
            intent="buy_intent",
            messages=user_says("همینو میخوام، لینک بده"),
            shown_products=[catalog.NIKE_RUNNING],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply includes نایک ایرزوم's purchase link "
            f"({catalog.NIKE_RUNNING['metadata']['productUrl']}) or clearly "
            "hands it over.\n"
            "- The reply does not mention any product other than نایک "
            "ایرزوم.\n"
        ),
        ideal=(
            "A short, encouraging Persian reply confirming نایک ایرزوم and "
            f"giving the link {catalog.NIKE_RUNNING['metadata']['productUrl']}, "
            "nothing else offered."
        ),
    ),
    JudgeNodeCase(
        id="handle_purchase_delay_objection_gives_space",
        node="handle_purchase",
        state=_base_state(
            intent="objection",
            objection="delay",
            messages=user_says("بذار یکم فکر کنم"),
            shown_products=[catalog.NIKE_RUNNING],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply gives the customer space to think and applies no "
            "pressure to buy right now.\n"
            "- The reply does not suggest a new, different product.\n"
        ),
        ideal=(
            "A short, relaxed Persian reply: takes no as an answer for now, "
            "invites questions later, no pressure and no new product "
            "suggested."
        ),
    ),
    JudgeNodeCase(
        id="handle_purchase_uncertainty_objection_uses_only_given_facts",
        node="handle_purchase",
        state=_base_state(
            intent="objection",
            objection="uncertainty",
            messages=user_says("مطمئن نیستم این برام مناسبه"),
            shown_products=[catalog.NIKE_RUNNING],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply responds to the uncertainty using only facts "
            "already given about نایک ایرزوم (description, price), not "
            "invented specs or guarantees.\n"
            "- The reply does not suggest a different product.\n"
        ),
        ideal=(
            "A short Persian reply addressing the uncertainty with نایک "
            "ایرزوم's real description (light running shoe with air "
            "cushioning), possibly asking what specifically makes them "
            "unsure - no invented claims, no other product offered."
        ),
    ),
    JudgeNodeCase(
        id="product_agent_answers_a_stock_availability_question",
        node="product_agent",
        state=_base_state(
            mode="product",
            messages=user_says("این موجوده؟"),
            retrieved_context=[catalog.PUMA_CASUAL],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply is about پوما اسمش specifically, not a generic "
            "'yes it's available' with no product reference.\n"
            "- The reply does not introduce a second, different product.\n"
        ),
        ideal="A short Persian reply confirming پوما اسمش is what's being discussed, answering the availability question directly.",
    ),
    JudgeNodeCase(
        id="suggest_products_nudges_a_ready_to_buy_customer",
        node="suggest_products",
        state=_base_state(
            messages=user_says("لپ‌تاپ اداری سبک می‌خوام"),
            retrieved_context=[catalog.LENOVO_OFFICE_LAPTOP],
            stage="ready_to_buy",
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply presents لپ‌تاپ اداری لنوو ثینک‌پد and nudges "
            "toward taking action (buying/next step) rather than staying "
            "purely informational.\n"
            "- The reply does not invent a second product.\n"
        ),
        ideal=(
            "A short Persian reply presenting لپ‌تاپ اداری لنوو ثینک‌پد "
            "(۲۱٬۵۰۰٬۰۰۰ تومان) and encouraging the customer toward buying "
            "it, since they're already ready to buy."
        ),
    ),
    JudgeNodeCase(
        id="suggest_products_for_a_quality_driven_customer_leads_with_the_premium_option",
        node="suggest_products",
        state=_base_state(
            messages=user_says("بهترین و باکیفیت‌ترین کفش دویدنی که دارید رو می‌خوام، قیمت مهم نیست"),
            retrieved_context=[catalog.PUMA_CASUAL, catalog.ADIDAS_RUNNING],
            value_driver="high_quality",
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- Given the customer explicitly said quality matters most and "
            "price doesn't, the reply leads with آدیداس اولترابوست (the "
            "higher-quality running shoe) and its real features, not پوما "
            "اسمش (the cheaper casual one) as if it were the top pick.\n"
            "- The reply does not lecture the customer about saving money or "
            "push the cheaper option unprompted.\n"
        ),
        ideal=(
            "A short Persian reply presenting آدیداس اولترابوست first, "
            "highlighting its real quality feature (boost midsole cushioning) "
            "over its price - not opening with 'پوما ارزون‌تره' or similar."
        ),
    ),
    JudgeNodeCase(
        id="product_agent_for_a_brand_conscious_customer_emphasizes_quality_not_price",
        node="product_agent",
        state=_base_state(
            mode="product",
            messages=user_says("این لپ‌تاپ گیمینگ واقعاً بهترینشونه؟"),
            retrieved_context=[catalog.ASUS_GAMING_LAPTOP],
            value_driver="high_quality",
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply answers using لپ‌تاپ گیمینگ ایسوس TUF's real specs "
            "(RTX 4060, i7, ۱۶ گیگ رم) to back up why it's a strong choice.\n"
            "- The reply does not unpromptedly suggest a cheaper alternative "
            "or undercut the purchase with 'اگه بودجه‌تون کمتره...'.\n"
        ),
        ideal=(
            "A short confident Persian reply affirming the laptop's quality "
            "using its real specs, without introducing price as a concern the "
            "customer didn't raise."
        ),
    ),
    JudgeNodeCase(
        id="suggest_products_for_a_browsing_stage_customer_stays_exploratory",
        node="suggest_products",
        state=_base_state(
            messages=user_says("یه چیزی برای دویدن می‌خوام، هنوز مطمئن نیستم چی"),
            retrieved_context=[catalog.NIKE_RUNNING, catalog.ADIDAS_RUNNING],
            stage="browsing",
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply presents both options as things to explore (invites "
            "the customer to compare or ask more), rather than pushing for a "
            "decision right now.\n"
            "- The reply does not apply closing pressure ('همین الان بخرید') "
            "- the customer is still just browsing.\n"
        ),
        ideal=(
            "A short Persian reply presenting both shoes with their real "
            "differences and inviting the customer to say what matters more "
            "to them - no pressure to decide immediately."
        ),
    ),
    JudgeNodeCase(
        id="suggest_products_for_a_considering_stage_customer_reinforces_value",
        node="suggest_products",
        state=_base_state(
            messages=user_says("بین این و چندتا جای دیگه که دیدم مردد موندم"),
            retrieved_context=[catalog.NIKE_RUNNING],
            stage="considering",
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply reinforces نایک ایرزوم's real value (from its given "
            "description/price) to help the customer decide, since they're "
            "actively weighing it against other options.\n"
            "- The reply does not repeat a plain product listing with no "
            "added reasoning - the customer has already seen it.\n"
        ),
        ideal=(
            "A short Persian reply that gives the customer one concrete "
            "reason (grounded in نایک ایرزوم's real description) to feel "
            "good about this option specifically, helping them move past "
            "indecision - not just re-listing the product."
        ),
    ),
    JudgeNodeCase(
        id="handle_purchase_compare_move_uses_only_the_shown_products",
        node="handle_purchase",
        state=_base_state(
            intent="compare",
            messages=user_says("بین این دوتا کدوم بهتره؟"),
            shown_products=[catalog.NIKE_RUNNING, catalog.ADIDAS_RUNNING],
        ),
        rubric=(
            "- The reply is written in Persian.\n"
            "- The reply compares نایک ایرزوم and آدیداس اولترابوست using "
            "only the facts given (price, brand, description) and "
            "recommends one.\n"
            "- The reply does not invent a third option or specs that "
            "weren't given.\n"
        ),
        ideal=(
            "A short Persian comparison mentioning both shoes' real prices "
            "(۱٬۴۵۰٬۰۰۰ vs ۱٬۶۵۰٬۰۰۰) and a real differentiator from their "
            "descriptions (air cushioning vs. boost midsole), ending with a "
            "recommendation for one of the two."
        ),
    ),
]
