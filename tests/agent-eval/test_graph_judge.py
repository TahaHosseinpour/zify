"""One turn through the real compiled graph, with the final reply the
customer would see graded by the jury against a rubric. See
cases/graph_judge_cases.py to add or remove a scenario.
"""

import pytest

from cases.graph_judge_cases import GRAPH_JUDGE_CASES
from helpers import assert_jury_passes, call_or_skip, grounding, stub_retrieval_nodes, transcript


@pytest.mark.parametrize("case", GRAPH_JUDGE_CASES, ids=[c.id for c in GRAPH_JUDGE_CASES])
async def test_graph_judge(case, graph, fake_shop_db, monkeypatch):
    stub_retrieval_nodes(monkeypatch, **case.retrieval)
    result = await call_or_skip(graph.ainvoke(case.input_state, {}))
    reply = result["messages"][-1].content

    # Whatever the stubs would hand back, plus the products already on the
    # table - a compare or objection turn closes from those and retrieves
    # nothing, so they are its only facts.
    context = grounding(*case.retrieval.values(), case.input_state.get("shown_products"))
    await assert_jury_passes(
        case.rubric, case.ideal, transcript(case.input_state["messages"]), reply, context
    )
