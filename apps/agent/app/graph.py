import os
from typing import Optional

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
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
    # Customer started a genuinely new topic/category unrelated to the prior search
    new_topic: bool = False
    # Ordinal reference to an already-shown product ("the second one") — 1-based
    selected_index: Optional[int] = None


structured_llm = llm.with_structured_output(IntentResult)

# ── Nodes ─────────────────────────────────────────────────────────────────────

# When the running transcript exceeds SUMMARY_TRIGGER messages, collapse
# everything except the last KEEP_RECENT into a text summary. This caps the
# tokens sent to the model on every turn instead of resending the whole history.
SUMMARY_TRIGGER = 20
KEEP_RECENT = 6

SUMMARY_INSTRUCTION = (
    "خلاصه‌ای فشرده از این بخش مکالمه بنویس و فقط نکات مهم برای ادامه فروش را نگه دار: "
    "نیاز و خواسته مشتری، محصولاتی که دیده، بودجه و ترجیحاتش، اعتراض‌ها و تصمیم‌هایش. "
    "کوتاه و به فارسی بنویس."
)


async def maybe_summarize(state: SalesAgentState) -> dict:
    messages = state["messages"]
    if len(messages) <= SUMMARY_TRIGGER:
        return {}

    old = messages[:-KEEP_RECENT]
    previous = state.get("summary")
    preface = f"خلاصه قبلی:\n{previous}\n\n" if previous else ""

    summary = await llm.ainvoke(
        [SystemMessage(content=preface + SUMMARY_INSTRUCTION), *old]
    )

    # Keep the summary in its own state field and drop the summarized messages
    # from the transcript. Storing it separately (rather than splicing a message
    # back in) avoids ordering issues with the add_messages reducer.
    removals = [RemoveMessage(id=m.id) for m in old if getattr(m, "id", None)]
    return {"summary": summary.content, "messages": removals}


INTENT_HISTORY_WINDOW = 6


async def analyze_intent(state: SalesAgentState) -> dict:
    # Give the classifier a short window of recent turns, not just the last
    # message, so filters/intent are read in context ("cheaper than that one").
    recent = state["messages"][-INTENT_HISTORY_WINDOW:]

    result: IntentResult = await structured_llm.ainvoke(
        [SystemMessage(content=build_intent_analysis_prompt()), *recent]
    )

    prev_mode = state.get("mode", "explore")
    new_mode = result.mode or prev_mode

    # Merge new filters onto the existing ones so earlier constraints (budget,
    # brand, ...) survive; wipe them only when the topic genuinely changed.
    new_filters = (
        result.explore_filters.model_dump(exclude_none=True)
        if result.explore_filters
        else {}
    )
    merged_filters = (
        new_filters if result.new_topic else {**(state.get("explore_filters") or {}), **new_filters}
    )

    updates: dict = {
        "intent": result.intent,
        "mode": new_mode,
        # stage / value_driver / objection describe the customer over the whole
        # conversation, so keep the previous value when this turn says nothing.
        "stage": result.stage or state.get("stage", "browsing"),
        "value_driver": result.value_driver or state.get("value_driver"),
        "objection": result.objection or state.get("objection"),
        "explore_filters": merged_filters,
        # Wipe retrieval from the previous turn so context never freezes.
        "retrieved_context": RESET_CONTEXT,
    }

    # Forget the pinned product when the customer leaves product mode.
    if new_mode == "explore" and prev_mode == "product":
        updates["product_id"] = None

    # Resolve an ordinal reference ("the second one") to a concrete product id.
    if result.selected_index is not None:
        shown = [p for p in (state.get("shown_products") or []) if p.get("type") == "product"]
        idx = result.selected_index - 1
        if 0 <= idx < len(shown):
            updates["product_id"] = shown[idx]["id"]

    return updates


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
    # Scope by shopId so one shop can never pull another shop's product.
    product = await db.product.find_first(
        where={"id": product_id, "shopId": state["shop_id"]}
    )
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


def _shown_products(items: list[RetrievedItem]) -> list[RetrievedItem]:
    return [i for i in items if i["type"] == "product"]


async def fuse_results_explore(state: SalesAgentState) -> dict:
    ranked = fuse_and_rank_context(state.get("retrieved_context", []), state)
    top = ranked[:8]
    return {"retrieved_context": SetContext(top), "shown_products": _shown_products(top)}


async def fuse_context_product(state: SalesAgentState) -> dict:
    ranked = fuse_and_rank_context(state.get("retrieved_context", []), state)
    top = ranked[:6]
    return {"retrieved_context": SetContext(top), "shown_products": _shown_products(top)}


def build_llm_messages(
    system_prompt: str,
    conversation: list[BaseMessage],
    context_prompt: str = "",
    summary: Optional[str] = None,
) -> list[BaseMessage]:
    """Order messages for OpenAI prefix-caching.

    Stable, static content (persona + business info in `system_prompt`) goes
    first so it forms a cacheable prefix that never changes between requests.
    The conversation summary (if any) follows, then the live conversation, and
    finally the dynamic per-turn content (retrieved products/FAQs) goes *last*
    so it can't invalidate the cached prefix.
    """
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    if summary:
        messages.append(SystemMessage(content=f"خلاصه گفتگوی قبلی:\n{summary}"))
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

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_prompt, state.get("summary"))
    )

    return {"messages": [reply]}


async def product_agent(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    if not shop:
        return {"messages": [HumanMessage(content="فروشگاه یافت نشد")]}

    system_prompt = build_system_prompt(shop)
    context_prompt = build_product_prompt(
        state.get("retrieved_context", []), state.get("stage"), state.get("value_driver"), state.get("objection")
    )

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_prompt, state.get("summary"))
    )

    return {"messages": [reply]}


async def ask_question(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    query = last_message_text(state)
    faq_items = await vector_search(state["shop_id"], "faq_items", query, 3)

    context = "\n\n".join(i["content"] for i in faq_items)
    context_block = f"## اطلاعات مرتبط:\n{context}\n\n" if context else ""

    # Only nudge the model to ask a clarifying question when the request is
    # actually ambiguous; a clear question should just be answered.
    clarify_instruction = (
        "درخواست مشتری ناقص یا مبهم است. به‌جای پاسخ کامل، فقط یک سوال کوتاه و مشخص بپرس "
        "تا نیازش روشن شود (مثلاً نوع، کاربرد، بودجه یا سایز). از اطلاعات بالا فقط برای هدفمندتر "
        "کردن سوالت استفاده کن، نه برای دادن پاسخ کامل."
    )
    extra = clarify_instruction if state.get("intent") == "needs_clarification" else ""

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_block + extra, state.get("summary"))
    )

    return {"messages": [reply]}


async def handle_purchase(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    # 1) An explicitly selected product (ordinal reference or product mode).
    if state.get("product_id"):
        product = await db.product.find_first(
            where={"id": state["product_id"], "shopId": state["shop_id"]}
        )
        if product and product.productUrl:
            reply = await llm.ainvoke(
                build_llm_messages(
                    system_prompt or "تو دستیار فروش هستی. مشتری آماده خرید است. لینک خرید را ارائه بده و او را تشویق کن.",
                    state["messages"],
                    f"مشتری آماده خرید است. لینک خرید را ارائه بده:\n🛒 {product.productUrl}",
                    state.get("summary"),
                )
            )
            return {"messages": [reply]}

    # 2) Otherwise fall back to the products we most recently showed the customer.
    products = [
        p
        for p in state.get("shown_products", [])
        if p.get("metadata", {}).get("productUrl")
    ]

    if products:
        links_text = "\n\n".join(
            f"{p['content']}\n🛒 لینک خرید: {p.get('metadata', {}).get('productUrl')}" for p in products[:3]
        )
        context_prompt = "مشتری آماده خرید است. لینک‌های زیر را ارائه بده:\n" + links_text
    else:
        # 3) Nothing to link to yet — ask which product instead of guessing.
        context_prompt = (
            "مشتری قصد خرید دارد اما هنوز محصول مشخصی انتخاب نشده است. "
            "کوتاه بپرس کدام محصول را می‌خواهد یا یک محصول مرتبط پیشنهاد بده."
        )

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_prompt, state.get("summary"))
    )

    return {"messages": [reply]}


# ── Graph ─────────────────────────────────────────────────────────────────────


def build_graph(checkpointer: Optional[AsyncPostgresSaver] = None):
    graph = (
        StateGraph(SalesAgentState)
        # nodes
        .add_node("maybe_summarize", maybe_summarize)
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
        .add_edge(START, "maybe_summarize")
        .add_edge("maybe_summarize", "analyze_intent")
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
