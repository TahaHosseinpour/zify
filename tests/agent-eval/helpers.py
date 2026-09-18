"""Shared plumbing for the agent-eval suite.

Every test here calls the *real* `app.graph.llm` / `structured_llm` (no
`fake_llm` stub) — that is the whole point of an eval suite. Only the layers
that would otherwise need a live Postgres/pgvector instance (shop lookup,
product/FAQ/shop-info retrieval) are stubbed, with canned rows supplied by
each test case. See /tests/conftest.py for `fake_shop_db`, reused here as-is.
"""

from __future__ import annotations

from typing import Awaitable, TypeVar

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app import graph as G

# Not a relative import: tests/agent-eval has a hyphen in its name, so it
# can't be a dotted Python package. pytest's default "prepend" import mode
# puts this directory on sys.path when it collects any test_*.py file here,
# which is what makes plain top-level imports like this one resolve.
from judge.jury import deliberate

T = TypeVar("T")


def user_says(*texts: str) -> list[BaseMessage]:
    """Build an alternating transcript ending on the customer's turn - the
    shape every node expects `state["messages"]` to be in."""
    messages: list[BaseMessage] = []
    for i, text in enumerate(texts):
        messages.append(HumanMessage(content=text) if i % 2 == 0 else AIMessage(content=text))
    return messages


def transcript(messages: list[BaseMessage]) -> str:
    """Render a message list as plain text for a judge prompt."""
    lines = []
    for m in messages:
        role = "مشتری" if isinstance(m, HumanMessage) else "فروشنده"
        lines.append(f"{role}: {m.content}")
    return "\n".join(lines)


async def call_or_skip(coro: Awaitable[T]) -> T:
    """Await a coroutine that makes a real LLM call; skip (not fail) the test
    if the call itself errors out - an expired quota or a network hiccup is an
    infrastructure problem, not evidence the agent behaves incorrectly."""
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live LLM call failed - {type(exc).__name__}: {exc}")


def stub_retrieval_nodes(monkeypatch, **rows: list) -> None:
    """Patch every seam that would otherwise hit Postgres/pgvector to return
    canned rows instead, while leaving analyze_intent's classifier and every
    generation node's `llm` call real.

    This covers both ways a turn can reach retrieval: the fan-out nodes
    (explore/product) *and* ask_question's direct FAQ/shop-info lookup - a
    full-graph test can't know in advance which one the real classifier's
    intent will route it through, so both must always be safe to hit.

    Keyword names match the retrieval node/function being stubbed:
    sql_filter_explore, vector_search_explore, vector_faq, vector_shop_info,
    sql_query_product, vector_search_product (fan-out), or faq/shop_info (the
    two ask_question pulls directly). Any name not passed defaults to
    returning no rows.
    """
    names = (
        "sql_filter_explore",
        "vector_search_explore",
        "vector_faq",
        "vector_shop_info",
        "sql_query_product",
        "vector_search_product",
    )
    for name in names:
        result = list(rows.get(name, []))

        async def node(state, _result=result):
            return {"retrieved_raw": _result}

        monkeypatch.setattr(G, name, node)

    stub_ask_question_retrieval(monkeypatch, faq=rows.get("faq"), shop_info=rows.get("shop_info"))


def stub_ask_question_retrieval(monkeypatch, faq: list | None = None, shop_info: list | None = None) -> None:
    """`ask_question` pulls FAQ/shop-info directly (it never fans out through
    the graph's retrieval nodes), so it needs its own seam stubbed."""

    async def fake_embed(text):
        return [0.0]

    async def fake_vector_search_faq(shop_id, query_vec, k=3):
        return list(faq or [])

    async def fake_vector_search_shop_info(shop_id, query_vec, k=2):
        return list(shop_info or [])

    monkeypatch.setattr(G, "embed", fake_embed)
    monkeypatch.setattr(G, "vector_search_faq", fake_vector_search_faq)
    monkeypatch.setattr(G, "vector_search_shop_info", fake_vector_search_shop_info)


def grounding(*item_lists: list | None) -> str:
    """Render the rows a turn was given - products, FAQ entries, shop info -
    as the judge's record of what the agent was allowed to say.

    Each row's `content` is the exact text the node put in its prompt (see
    cases/catalog.py), so this is the agent's evidence, verbatim. Without it a
    judge only sees the visible transcript and reads every correctly-quoted
    price as a hallucination; see judge/jury.py's `_judge_prompt`.
    """
    seen: dict[str, str] = {}
    for items in item_lists:
        for row in items or []:
            content = row.get("content")
            if content:
                seen.setdefault(row.get("id", content), content)
    return "\n".join(f"- {content}" for content in seen.values())


async def assert_jury_passes(
    rubric: str, ideal: str, transcript_text: str, reply: str, context: str = ""
) -> None:
    """Put `reply` to the configured jury (judge/config.py) and fail loudly -
    with every judge's reasoning attached - if it doesn't pass. `ideal` is a
    concrete description of what a great reply looks like here, given to
    every judge alongside the rubric checklist so it has a standard to
    compare against, and `context` is what the agent was handed to answer
    from (see `grounding`). Skips (rather than fails) if every judge in the
    jury errored out, since that means the jury itself is unavailable, not
    that the reply is bad."""
    verdict = await deliberate(rubric, ideal, transcript_text, reply, context)
    if verdict.all_errored:
        pytest.skip(f"every judge errored:\n{verdict.explain()}")
    assert verdict.passed, f"jury rejected the reply:\n{verdict.explain()}\n\n--- reply ---\n{reply}"
