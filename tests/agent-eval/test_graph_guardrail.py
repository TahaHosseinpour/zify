"""Adversarial/off-topic messages through the real compiled graph - the
customer tries to pull the agent off its sales-assistant role, and the graph
must not follow along. See cases/guardrail_cases.py to add or remove a
scenario.
"""

import pytest

from cases.guardrail_cases import GUARDRAIL_DETERMINISTIC_CASES, GUARDRAIL_JUDGE_CASES
from helpers import assert_jury_passes, call_or_skip, stub_retrieval_nodes, transcript


@pytest.mark.parametrize("case", GUARDRAIL_DETERMINISTIC_CASES, ids=[c.id for c in GUARDRAIL_DETERMINISTIC_CASES])
async def test_graph_guardrail_deterministic(case, graph, fake_shop_db, monkeypatch):
    stub_retrieval_nodes(monkeypatch, **case.retrieval)
    result = await call_or_skip(graph.ainvoke(case.input_state, {}))
    try:
        case.check(result)
    except AssertionError as exc:
        raise AssertionError(f"expected: {case.expected}\n{exc}") from exc


@pytest.mark.parametrize("case", GUARDRAIL_JUDGE_CASES, ids=[c.id for c in GUARDRAIL_JUDGE_CASES])
async def test_graph_guardrail_judge(case, graph, fake_shop_db, monkeypatch):
    stub_retrieval_nodes(monkeypatch, **case.retrieval)
    result = await call_or_skip(graph.ainvoke(case.input_state, {}))
    reply = result["messages"][-1].content

    await assert_jury_passes(case.rubric, case.ideal, transcript(case.input_state["messages"]), reply)
