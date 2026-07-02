import os
from typing import Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel

from .db import db
from .prompts import (
    build_explore_prompt,
    build_intent_analysis_prompt,
    build_product_prompt,
    build_system_prompt,
)
from .state import RESET_CONTEXT, RetrievedItem, SalesAgentState, SetContext

# ── LLM / Embeddings ──────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    temperature=0.7,
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL"),
)

embeddings = OpenAIEmbeddings(
    model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL"),
)

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def to_fa_number(n) -> str:
    grouped = f"{int(round(float(n))):,}".replace(",", "٬")
    return "".join(PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in grouped)


def last_message_text(state: SalesAgentState) -> str:
    if not state["messages"]:
        return ""
    last = state["messages"][-1]
    content = last.content if isinstance(last, BaseMessage) else last.get("content")
    return content if isinstance(content, str) else ""


# ── Retrieval helpers ─────────────────────────────────────────────────────────


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vec) + "]"


def _product_content(row: dict) -> str:
    parts = [f"محصول: {row['name']} | قیمت: {to_fa_number(row['price'])} تومان"]
    if row.get("description"):
        parts.append(row["description"])
    if row.get("category"):
        parts.append(f"دسته: {row['category']}")
    return " | ".join(parts)


async def vector_search(
    shop_id: str, table: str, query_text: str, k: int = 5
) -> list[RetrievedItem]:
    vec = await embeddings.aembed_query(query_text)
    vec_str = _vector_literal(vec)

    if table == "products":
        rows = await db.query_raw(
            """SELECT id, name, price, description, category, brand, stock,
                      "productUrl", "imageUrl",
                      embedding <=> $1::vector AS score
               FROM products
               WHERE "shopId" = $2 AND "isActive" = true AND embedding IS NOT NULL
               ORDER BY score ASC
               LIMIT $3""",
            vec_str,
            shop_id,
            k,
        )
        return [
            RetrievedItem(
                id=str(r["id"]),
                type="product",
                content=_product_content(r),
                score=float(r["score"]),
                metadata={
                    "name": r["name"],
                    "productUrl": r.get("productUrl"),
                    "imageUrl": r.get("imageUrl"),
                    "price": r["price"],
                    "stock": r.get("stock"),
                },
            )
            for r in rows
        ]

    if table == "faq_items":
        rows = await db.query_raw(
            """SELECT id, question, answer,
                      embedding <=> $1::vector AS score
               FROM faq_items
               WHERE "shopId" = $2 AND embedding IS NOT NULL
               ORDER BY score ASC
               LIMIT $3""",
            vec_str,
            shop_id,
            k,
        )
        return [
            RetrievedItem(
                id=str(r["id"]),
                type="faq",
                content=f"سوال: {r['question']}\nپاسخ: {r['answer']}",
                score=float(r["score"]),
            )
            for r in rows
        ]

    # shop_info_chunks
    rows = await db.query_raw(
        """SELECT id, content,
                  embedding <=> $1::vector AS score
           FROM shop_info_chunks
           WHERE "shopId" = $2 AND embedding IS NOT NULL
           ORDER BY score ASC
           LIMIT $3""",
        vec_str,
        shop_id,
        k,
    )
    return [
        RetrievedItem(id=str(r["id"]), type="shop_info", content=str(r["content"]), score=float(r["score"]))
        for r in rows
    ]


async def sql_filter_products(shop_id: str, filters: dict) -> list[RetrievedItem]:
    where: dict = {"shopId": shop_id, "isActive": True}
    if filters.get("category"):
        where["category"] = {"contains": filters["category"], "mode": "insensitive"}
    if filters.get("brand"):
        where["brand"] = {"contains": filters["brand"], "mode": "insensitive"}
    if filters.get("minPrice") is not None or filters.get("maxPrice") is not None:
        price_filter: dict = {}
        if filters.get("minPrice") is not None:
            price_filter["gte"] = filters["minPrice"]
        if filters.get("maxPrice") is not None:
            price_filter["lte"] = filters["maxPrice"]
        where["price"] = price_filter

    products = await db.product.find_many(where=where, take=8)

    return [
        RetrievedItem(
            id=p.id,
            type="product",
            content=_product_content(
                {
                    "name": p.name,
                    "price": p.price,
                    "description": p.description,
                    "category": p.category,
                }
            ),
            metadata={
                "name": p.name,
                "productUrl": p.productUrl,
                "imageUrl": p.imageUrl,
                "price": p.price,
                "stock": p.stock,
            },
        )
        for p in products
    ]


# ── Intent Analysis Schema ────────────────────────────────────────────────────


class ExploreFiltersModel(BaseModel):
    category: Optional[str] = None
    maxPrice: Optional[float] = None
    minPrice: Optional[float] = None
    brand: Optional[str] = None
    query: Optional[str] = None


class IntentResult(BaseModel):
    intent: str
    mode: str
    stage: str
    value_driver: Optional[str] = None
    objection: Optional[str] = None
    explore_filters: Optional[ExploreFiltersModel] = None


structured_llm = llm.with_structured_output(IntentResult)

# ── Nodes ─────────────────────────────────────────────────────────────────────


async def analyze_intent(state: SalesAgentState) -> dict:
    user_text = last_message_text(state)

    result: IntentResult = await structured_llm.ainvoke(
        [
            SystemMessage(content=build_intent_analysis_prompt()),
            HumanMessage(content=user_text),
        ]
    )

    return {
        "intent": result.intent,
        "mode": result.mode or state.get("mode", "explore"),
        "stage": result.stage or state.get("stage", "browsing"),
        "value_driver": result.value_driver,
        "objection": result.objection,
        "explore_filters": result.explore_filters.model_dump(exclude_none=True)
        if result.explore_filters
        else {},
        # Wipe retrieval from the previous turn so context never freezes.
        "retrieved_context": RESET_CONTEXT,
    }


def router_after_intent(state: SalesAgentState) -> str:
    if state.get("intent") == "buy_intent":
        return "handle_purchase"
    if state.get("intent") in ("ask_question", "needs_clarification"):
        return "ask_question"
    if state.get("mode") == "product":
        return "fan_out_product"
    return "fan_out_explore"


async def fan_out_explore(_state: SalesAgentState) -> dict:
    return {}


async def fan_out_product(_state: SalesAgentState) -> dict:
    return {}


def route_fan_out_explore(state: SalesAgentState) -> list[Send]:
    text = state.get("explore_filters", {}).get("query") or last_message_text(state)
    return [
        Send("vector_search_explore", {**state, "_query": text}),
        Send("sql_filter_explore", {**state}),
        Send("vector_faq_explore", {**state, "_query": text}),
    ]


def route_fan_out_product(state: SalesAgentState) -> list[Send]:
    text = last_message_text(state)
    return [
        Send("vector_search_product", {**state, "_query": text}),
        Send("sql_query_product", {**state}),
        Send("vector_faq_product", {**state, "_query": text}),
    ]


async def vector_search_explore(state: dict) -> dict:
    items = await vector_search(state["shop_id"], "products", state.get("_query", ""), 5)
    return {"retrieved_context": items}


async def sql_filter_explore(state: SalesAgentState) -> dict:
    items = await sql_filter_products(state["shop_id"], state.get("explore_filters") or {})
    return {"retrieved_context": items}


async def vector_search_product(state: dict) -> dict:
    items = await vector_search(state["shop_id"], "products", state.get("_query", ""), 5)
    return {"retrieved_context": items}


async def sql_query_product(state: SalesAgentState) -> dict:
    product_id = state.get("product_id")
    if not product_id:
        return {"retrieved_context": []}
    product = await db.product.find_unique(where={"id": product_id})
    if not product:
        return {"retrieved_context": []}
    return {
        "retrieved_context": [
            RetrievedItem(
                id=product.id,
                type="product",
                content=_product_content(
                    {"name": product.name, "price": product.price, "description": product.description}
                ),
                metadata={
                    "name": product.name,
                    "productUrl": product.productUrl,
                    "imageUrl": product.imageUrl,
                    "price": product.price,
                    "stock": product.stock,
                },
            )
        ]
    }


async def vector_faq(state: dict) -> dict:
    items = await vector_search(state["shop_id"], "faq_items", state.get("_query", ""), 3)
    return {"retrieved_context": items}


def fuse_and_rank_context(items: list[RetrievedItem], state: SalesAgentState) -> list[RetrievedItem]:
    deduped = list({item["id"]: item for item in items}.values())

    def sort_key(item: RetrievedItem) -> float:
        score = item.get("score", 0.5)
        value_driver = state.get("value_driver")
        if value_driver in ("low_price", "best_price_in_quality"):
            if item["type"] == "product" and item.get("metadata", {}).get("price") is not None:
                score -= 0.1
        return score

    return sorted(deduped, key=sort_key)


async def fuse_results_explore(state: SalesAgentState) -> dict:
    ranked = fuse_and_rank_context(state.get("retrieved_context", []), state)
    return {"retrieved_context": SetContext(ranked[:8])}


async def fuse_context_product(state: SalesAgentState) -> dict:
    ranked = fuse_and_rank_context(state.get("retrieved_context", []), state)
    return {"retrieved_context": SetContext(ranked[:6])}


def build_llm_messages(
    system_prompt: str,
    conversation: list[BaseMessage],
    context_prompt: str = "",
) -> list[BaseMessage]:
    """Order messages for OpenAI prefix-caching.

    Stable, static content (persona + business info in `system_prompt`) goes
    first so it forms a cacheable prefix that never changes between requests.
    Dynamic per-turn content (retrieved products/FAQs) goes *last*, after the
    conversation, so it can't invalidate the cached prefix.
    """
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    messages.extend(conversation)
    if context_prompt.strip():
        messages.append(SystemMessage(content=context_prompt))
    return messages


async def suggest_products(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    if not shop:
        return {"messages": [HumanMessage(content="فروشگاه یافت نشد")]}

    system_prompt = build_system_prompt(shop)
    context_prompt = build_explore_prompt(
        state.get("retrieved_context", []), state.get("stage"), state.get("value_driver"), state.get("objection")
    )

    reply = await llm.ainvoke(build_llm_messages(system_prompt, state["messages"], context_prompt))

    return {"messages": [reply]}


async def product_agent(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    if not shop:
        return {"messages": [HumanMessage(content="فروشگاه یافت نشد")]}

    system_prompt = build_system_prompt(shop)
    context_prompt = build_product_prompt(
        state.get("retrieved_context", []), state.get("stage"), state.get("value_driver"), state.get("objection")
    )

    reply = await llm.ainvoke(build_llm_messages(system_prompt, state["messages"], context_prompt))

    return {"messages": [reply]}


async def ask_question(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    query = last_message_text(state)
    faq_items = await vector_search(state["shop_id"], "faq_items", query, 3)

    context = "\n\n".join(i["content"] for i in faq_items)
    context_block = f"## اطلاعات مرتبط:\n{context}\n\n" if context else ""
    clarify_instruction = (
        "درخواست مشتری ناقص یا مبهم است. به‌جای پاسخ کامل، فقط یک سوال کوتاه و مشخص بپرس "
        "تا نیازش روشن شود (مثلاً نوع، کاربرد، بودجه یا سایز). از اطلاعات بالا فقط برای هدفمندتر "
        "کردن سوالت استفاده کن، نه برای دادن پاسخ کامل."
    )

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_block + clarify_instruction)
    )

    return {"messages": [reply]}


async def handle_purchase(state: SalesAgentState) -> dict:
    products = [
        c
        for c in state.get("retrieved_context", [])
        if c["type"] == "product" and c.get("metadata", {}).get("productUrl")
    ]

    if not products and state.get("product_id"):
        product = await db.product.find_unique(where={"id": state["product_id"]})
        if product and product.productUrl:
            reply = await llm.ainvoke(
                build_llm_messages(
                    "تو دستیار فروش هستی. مشتری آماده خرید است. لینک خرید را ارائه بده و او را تشویق کن.",
                    state["messages"],
                    f"لینک خرید: {product.productUrl}",
                )
            )
            return {"messages": [reply]}

    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    links_text = "\n\n".join(
        f"{p['content']}\n🛒 لینک خرید: {p.get('metadata', {}).get('productUrl')}" for p in products[:3]
    )

    reply = await llm.ainvoke(
        build_llm_messages(
            system_prompt,
            state["messages"],
            "مشتری آماده خرید است. لینک‌های زیر را ارائه بده:\n" + links_text,
        )
    )

    return {"messages": [reply]}


# ── Graph ─────────────────────────────────────────────────────────────────────


def build_graph(checkpointer: Optional[AsyncPostgresSaver] = None):
    graph = (
        StateGraph(SalesAgentState)
        # nodes
        .add_node("analyze_intent", analyze_intent)
        .add_node("fan_out_explore", fan_out_explore)
        .add_node("fan_out_product", fan_out_product)
        .add_node("vector_search_explore", vector_search_explore)
        .add_node("sql_filter_explore", sql_filter_explore)
        .add_node("vector_search_product", vector_search_product)
        .add_node("sql_query_product", sql_query_product)
        .add_node("vector_faq_explore", vector_faq)
        .add_node("vector_faq_product", vector_faq)
        .add_node("fuse_results_explore", fuse_results_explore)
        .add_node("fuse_context_product", fuse_context_product)
        .add_node("suggest_products", suggest_products)
        .add_node("product_agent", product_agent)
        .add_node("ask_question", ask_question)
        .add_node("handle_purchase", handle_purchase)
        # edges
        .add_edge(START, "analyze_intent")
        .add_conditional_edges(
            "analyze_intent",
            router_after_intent,
            ["fan_out_explore", "fan_out_product", "ask_question", "handle_purchase"],
        )
        # explore fan-out
        .add_conditional_edges(
            "fan_out_explore",
            route_fan_out_explore,
            ["vector_search_explore", "sql_filter_explore", "vector_faq_explore"],
        )
        # product fan-out
        .add_conditional_edges(
            "fan_out_product",
            route_fan_out_product,
            ["vector_search_product", "sql_query_product", "vector_faq_product"],
        )
        # explore path
        .add_edge("vector_search_explore", "fuse_results_explore")
        .add_edge("sql_filter_explore", "fuse_results_explore")
        .add_edge("vector_faq_explore", "fuse_results_explore")
        .add_edge("fuse_results_explore", "suggest_products")
        .add_edge("suggest_products", END)
        # product path
        .add_edge("vector_search_product", "fuse_context_product")
        .add_edge("sql_query_product", "fuse_context_product")
        .add_edge("vector_faq_product", "fuse_context_product")
        .add_edge("fuse_context_product", "product_agent")
        .add_edge("product_agent", END)
        # terminal nodes
        .add_edge("ask_question", END)
        .add_edge("handle_purchase", END)
        .compile(checkpointer=checkpointer)
    )

    return graph


async def make_graph():
    """Entry point for `langgraph dev` / LangGraph Studio.

    Unlike `build_graph`, this connects the Prisma client itself (normally
    done by the FastAPI app's lifespan hook) and compiles without a custom
    checkpointer so the LangGraph dev server can manage persistence.
    """
    if not db.is_connected():
        await db.connect()
    return build_graph()
