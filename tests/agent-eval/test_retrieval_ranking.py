"""Pure ranking/trimming logic (fuse_results_explore, fuse_context_product) -
no LLM call, no DB, so no skip-on-error wrapper: a failure here is a real bug
in the ranking code or in the test data, not an infrastructure hiccup. See
cases/retrieval_ranking_cases.py to add or remove a scenario.
"""

import pytest
from app import graph as G

from cases.retrieval_ranking_cases import RETRIEVAL_RANKING_CASES


@pytest.mark.parametrize("case", RETRIEVAL_RANKING_CASES, ids=[c.id for c in RETRIEVAL_RANKING_CASES])
async def test_retrieval_ranking(case):
    node = getattr(G, case.node)
    update = await node(case.state)
    try:
        case.check(update)
    except AssertionError as exc:
        raise AssertionError(f"expected: {case.expected}\n{exc}") from exc
