"""One turn through the real compiled graph, checked against an exact
expected final state. See cases/graph_deterministic_cases.py to add or
remove a scenario.
"""

import pytest

from cases.graph_deterministic_cases import GRAPH_DETERMINISTIC_CASES
from helpers import call_or_skip, stub_retrieval_nodes


@pytest.mark.parametrize("case", GRAPH_DETERMINISTIC_CASES, ids=[c.id for c in GRAPH_DETERMINISTIC_CASES])
async def test_graph_deterministic(case, graph, fake_shop_db, monkeypatch):
    stub_retrieval_nodes(monkeypatch, **case.retrieval)
    result = await call_or_skip(graph.ainvoke(case.input_state, {}))
    try:
        case.check(result)
    except AssertionError as exc:
        raise AssertionError(f"expected: {case.expected}\n{exc}") from exc
