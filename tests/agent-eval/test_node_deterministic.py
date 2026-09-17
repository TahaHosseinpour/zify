"""Each node, called directly, tested against an exact expected output using
the real classifier LLM. See cases/node_deterministic_cases.py to add or
remove a scenario - nothing here depends on how many there are.
"""

import pytest
from app import graph as G

from cases.node_deterministic_cases import NODE_DETERMINISTIC_CASES
from helpers import call_or_skip


@pytest.mark.parametrize("case", NODE_DETERMINISTIC_CASES, ids=[c.id for c in NODE_DETERMINISTIC_CASES])
async def test_node_deterministic(case, fake_shop_db):
    node = getattr(G, case.node)
    update = await call_or_skip(node(case.state))
    try:
        case.check(update)
    except AssertionError as exc:
        raise AssertionError(f"expected: {case.expected}\n{exc}") from exc
