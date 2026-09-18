"""Each node, called directly, whose output is free text - graded by the
jury against a rubric instead of an exact-match assertion. See
cases/node_judge_cases.py to add or remove a scenario.
"""

import pytest
from app import graph as G

from cases.node_judge_cases import NODE_JUDGE_CASES
from helpers import assert_jury_passes, call_or_skip, grounding, stub_ask_question_retrieval, transcript


@pytest.mark.parametrize("case", NODE_JUDGE_CASES, ids=[c.id for c in NODE_JUDGE_CASES])
async def test_node_judge(case, fake_shop_db, monkeypatch):
    if case.node == "ask_question":
        stub_ask_question_retrieval(monkeypatch, faq=case.faq, shop_info=case.shop_info)

    node = getattr(G, case.node)
    update = await call_or_skip(node(case.state))
    reply = update["messages"][-1].content

    # Every way a node can be handed facts: retrieval output for the
    # suggest/product paths, the table being closed on for handle_purchase,
    # and ask_question's own FAQ/shop-info pulls.
    context = grounding(
        case.state.get("retrieved_context"),
        case.state.get("shown_products"),
        case.faq,
        case.shop_info,
    )
    await assert_jury_passes(
        case.rubric, case.ideal, transcript(case.state["messages"]), reply, context
    )
