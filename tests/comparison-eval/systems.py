"""The four systems the benchmark compares, behind one interface.

    simple_rag   embed the message, take the nearest rows, one model call.
    rag_sql      the same, with price and brand pulled out of the message by
                 text rules and applied as a SQL filter before the vector search.
    graph_llm    the production graph with the LLM intent classifier
                 (INTENT_CLASSIFIER=llm) - what ran before Jev.
    graph_jev    the production graph as deployed: Jev classifies, the LLM is
                 only the fallback.

All four answer from the same shop in the same database with the same reply
model and the same embedding model, and all four carry a conversation across
turns. What differs is only what happens between the customer's message and the
reply model's prompt - which is the thing being measured.

The two baselines get the same persona prompt as the graph and show cards for
the products their reply names, the same rule the graph uses, so the comparison
is of how each system decides what to say, not of how it formats the result.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import LLMResult
from langgraph.checkpoint.memory import InMemorySaver

from app import graph as G
from app import intent as jev
from app import metering
from app.db import db
from app.prompts import build_system_prompt
from app.server import _build_chat_payload

from scenarios import Outcome


@dataclass
class Usage:
    """Everything a conversation spent, in the units it is billed in."""

    input_tokens: int = 0
    output_tokens: int = 0
    jev_tokens: int = 0
    embedding_tokens: int = 0
    # The part of embedding_tokens the fallback embedding provider handled,
    # and the LLM calls priced one by one at the rates of whichever model
    # answered - a run can be served by the second providers (app/failover.py).
    fallback_embedding_tokens: int = 0
    llm_usd: float = 0.0
    llm_calls: int = 0
    seconds: list[float] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return metering.turn_cost_usd(
            self.input_tokens,
            self.output_tokens,
            metering.TurnMeter(self.jev_tokens, self.embedding_tokens, self.fallback_embedding_tokens),
            self.llm_usd,
        )


class _LLMUsage(BaseCallbackHandler):
    """Counts the tokens and the number of model calls inside a graph run."""

    def __init__(self, usage: Usage) -> None:
        self.usage = usage

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        self.usage.llm_calls += 1
        for generations in response.generations:
            for gen in generations:
                message = getattr(gen, "message", None)
                meta = getattr(message, "usage_metadata", None) or {}
                input_tokens = meta.get("input_tokens", 0) or 0
                output_tokens = meta.get("output_tokens", 0) or 0
                self.usage.input_tokens += input_tokens
                self.usage.output_tokens += output_tokens
                model = (getattr(message, "response_metadata", None) or {}).get("model_name")
                self.usage.llm_usd += metering.llm_cost_usd(model, input_tokens, output_tokens)


class System:
    key = ""
    label = ""

    def __init__(self, shop_id: str) -> None:
        self.shop_id = shop_id

    async def converse(self, messages: list[str]) -> tuple[Outcome, list[dict], Usage]:
        """Play a whole conversation. Returns the last reply's outcome, the
        transcript, and what it cost."""
        usage = Usage()
        state = await self.start()
        transcript: list[dict] = []
        outcome = Outcome("", [], None, False)
        for message in messages:
            # A fresh meter per turn collects what LangChain's callbacks never
            # see: Jev's tokens and the text sent for embedding.
            meter = metering.start_turn()
            started = time.perf_counter()
            outcome = await self.turn(state, message, usage)
            usage.seconds.append(time.perf_counter() - started)
            usage.jev_tokens += meter.jev_tokens
            usage.embedding_tokens += meter.embedding_tokens
            usage.fallback_embedding_tokens += meter.fallback_embedding_tokens
            transcript.append({"customer": message, "assistant": outcome.reply})
        outcome.earlier_replies = [turn["assistant"] for turn in transcript[:-1]]
        return outcome, transcript, usage

    async def start(self) -> dict:
        return {}

    async def turn(self, state: dict, message: str, usage: Usage) -> Outcome:
        raise NotImplementedError


# ── The production graph, with either classifier ─────────────────────────────


class GraphSystem(System):
    classifier = "jev"

    async def start(self) -> dict:
        return {
            "graph": G.build_graph(InMemorySaver()),
            "thread": f"{self.shop_id}:bench:{self.key}:{time.time_ns()}",
            "mode": "explore",
            "product_id": None,
        }

    async def turn(self, state: dict, message: str, usage: Usage) -> Outcome:
        # Read by intent.enabled() on every call, so this switches the
        # classifier for exactly this system's turns.
        os.environ["INTENT_CLASSIFIER"] = self.classifier
        final = await state["graph"].ainvoke(
            {
                "messages": [HumanMessage(content=message)],
                "shop_id": self.shop_id,
                "mode": state["mode"],
                "product_id": state["product_id"],
            },
            {"configurable": {"thread_id": state["thread"]}, "callbacks": [_LLMUsage(usage)]},
        )
        payload = _build_chat_payload(final)
        # What a client does between turns: send back the mode and pinned
        # product the agent settled on.
        state["mode"], state["product_id"] = payload.get("mode") or "explore", payload.get("productId")
        return Outcome(
            reply=payload["reply"],
            cards=[
                {"id": p["id"], "name": p["name"], "price": p["price"], "productUrl": p["productUrl"]}
                for p in payload["products"]
            ],
            purchase_url=payload["purchaseUrl"],
            show_buy_actions=payload["showBuyActions"],
        )


class GraphWithJev(GraphSystem):
    key, label, classifier = "graph_jev", "گراف زیفای با JEV", "jev"


class GraphWithoutJev(GraphSystem):
    key, label, classifier = "graph_llm", "گراف زیفای بدون JEV", "llm"


# ── The two retrieval baselines ──────────────────────────────────────────────

BASELINE_PRODUCT_K = 6

BASELINE_INSTRUCTION = (
    "با استفاده از اطلاعات زیر به آخرین پیام مشتری پاسخ بده. فقط از همین اطلاعات استفاده کن و "
    "چیزی از خودت نساز. اگر پاسخ در این اطلاعات نیست، بگو اطلاعاتی نداری."
)


def _context_block(products: list[dict], faqs: list[dict], info: list[dict]) -> str:
    parts = [BASELINE_INSTRUCTION]
    if products:
        parts.append("## محصولات بازیابی‌شده:")
        for i, p in enumerate(products, 1):
            url = (p.get("metadata") or {}).get("productUrl")
            parts.append(f"{i}. {p['content']}" + (f" | لینک خرید: {url}" if url else ""))
    if faqs:
        parts.append("## سوالات متداول:")
        parts += [f["content"] for f in faqs]
    if info:
        parts.append("## اطلاعات کسب‌وکار:")
        parts += [i["content"] for i in info]
    return "\n".join(parts)


class _RetrievalBaseline(System):
    """One retrieval, one model call, per customer message."""

    async def start(self) -> dict:
        shop = await db.shop.find_unique(where={"id": self.shop_id})
        return {"history": [], "system_prompt": build_system_prompt(shop), "filters": {}}

    async def retrieve_products(self, state: dict, message: str, query_vec: list[float]) -> list[dict]:
        raise NotImplementedError

    async def turn(self, state: dict, message: str, usage: Usage) -> Outcome:
        history: list[BaseMessage] = state["history"]
        history.append(HumanMessage(content=message))

        query_vec = await G.embed(message)
        products = await self.retrieve_products(state, message, query_vec)
        faqs = await G.vector_search_faq(self.shop_id, query_vec, G.FAQ_K)
        info = await G.vector_search_shop_info(self.shop_id, query_vec, G.SHOP_INFO_K)

        reply: AIMessage = await G.llm.ainvoke(
            G.build_llm_messages(state["system_prompt"], history, _context_block(products, faqs, info))
        )
        usage.llm_calls += 1
        meta = reply.usage_metadata or {}
        usage.input_tokens += meta.get("input_tokens", 0) or 0
        usage.output_tokens += meta.get("output_tokens", 0) or 0
        usage.llm_usd += metering.llm_cost_usd(
            (reply.response_metadata or {}).get("model_name"),
            meta.get("input_tokens", 0) or 0,
            meta.get("output_tokens", 0) or 0,
        )
        history.append(reply)

        text = reply.content if isinstance(reply.content, str) else str(reply.content)
        named = G._mentioned_products(text, products)
        cards = [
            {
                "id": p["id"],
                "name": p["metadata"].get("name"),
                "price": float(p["metadata"]["price"]) if p["metadata"].get("price") is not None else None,
                "productUrl": p["metadata"].get("productUrl"),
            }
            for p in named
        ]
        return Outcome(
            reply=text,
            cards=cards,
            purchase_url=cards[0]["productUrl"] if len(cards) == 1 else None,
            show_buy_actions=bool(cards),
        )


class SimpleRag(_RetrievalBaseline):
    key, label = "simple_rag", "رگ ساده"

    async def retrieve_products(self, state: dict, message: str, query_vec: list[float]) -> list[dict]:
        return await G.vector_search_products(self.shop_id, query_vec, BASELINE_PRODUCT_K)


# Text rules standing in for intent analysis: what "RAG with a SQL filter" can
# know about a message without asking a model.
# Whole words only: «تا» is also the middle of «لپ‌تاپ».
_MAX_CUES = re.compile(r"(?<!\w)(?:زیر|تا|کمتر از|حداکثر|نهایت\w*|بودجه|نمی\s*تونم|نمیتونم)(?!\w)")
_MIN_CUES = re.compile(r"(?<!\w)(?:بالای|بالاتر از|بیشتر از|حداقل|به بالا)(?!\w)")
_RANGE_CUE = re.compile(r"(?<!\w)بین(?!\w)")


def extract_rule_filters(message: str, brands: list[str]) -> dict:
    """Price bounds and brand, read off the message by pattern."""
    text = message.replace("‌", " ")
    filters: dict = {}

    amounts = [a.value for a in jev.extract_amounts(message)]
    if len(amounts) >= 2 and _RANGE_CUE.search(text):
        filters["minPrice"], filters["maxPrice"] = min(amounts), max(amounts)
    elif amounts:
        # "بیشتر از ۴۰ میلیون نمی‌تونم بدم" is a ceiling: a max cue anywhere
        # in the message outranks the min cue next to the number.
        if _MAX_CUES.search(text):
            filters["maxPrice"] = amounts[-1]
        elif _MIN_CUES.search(text):
            filters["minPrice"] = amounts[-1]

    for brand in brands:
        if brand.replace("‌", " ") in text:
            filters["brand"] = brand
            break
    return filters


class RagWithSql(_RetrievalBaseline):
    key, label = "rag_sql", "رگ با وکتور و SQL"

    async def start(self) -> dict:
        state = await super().start()
        state["brands"] = await G.shop_brands(self.shop_id)
        return state

    async def retrieve_products(self, state: dict, message: str, query_vec: list[float]) -> list[dict]:
        # Constraints accumulate over the conversation, as the graph's do.
        state["filters"].update(extract_rule_filters(message, state["brands"]))
        filters = state["filters"]
        if G.has_meaningful_filters(filters):
            ids, overflowed = await G.filter_candidate_ids(self.shop_id, filters)
            if ids and not overflowed:
                return await G.vector_search_products(self.shop_id, query_vec, BASELINE_PRODUCT_K, ids)
            if not ids and not overflowed:
                return []  # the filter is exact: nothing satisfies it
        return await G.vector_search_products(self.shop_id, query_vec, BASELINE_PRODUCT_K)


SYSTEMS: list[type[System]] = [SimpleRag, RagWithSql, GraphWithoutJev, GraphWithJev]
BY_KEY = {cls.key: cls for cls in SYSTEMS}
