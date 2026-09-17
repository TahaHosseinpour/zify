"""Fixtures local to the agent-eval suite.

Unlike the rest of the agent test suite, every test collected here makes a
real call to the configured LLM (the graph's own `llm`/`structured_llm` for
the thing under test, plus the jury's judge models for anything graded - see
judge/config.py). `skip_if_no_llm_key` below keeps that from turning into a
hard failure when OPENAI_API_KEY isn't configured, mirroring how
/tests/conftest.py's `real_db` fixture skips DB-marked tests instead of
failing the run when Postgres is unreachable.
"""

from __future__ import annotations

import os

import pytest

from app import graph as G


# test_retrieval_ranking.py calls fuse_results_explore/fuse_context_product
# directly - pure Python over a `score` number, no LLM call - so it needs no
# key and must never skip just because one is missing.
_NO_LLM_NEEDED_MODULES = {"test_retrieval_ranking"}


@pytest.fixture(autouse=True)
def skip_if_no_llm_key(request):
    if request.module.__name__ in _NO_LLM_NEEDED_MODULES:
        return
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - agent-eval tests need a live LLM")


@pytest.fixture
def graph():
    """The real compiled graph, no checkpointer - one ainvoke per case."""
    return G.build_graph()
