import asyncio
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
from pydantic import BaseModel

from .db import db
from .prompts import (
    build_explore_prompt,
    build_intent_analysis_prompt,
    build_product_prompt,
    build_system_prompt,
)
from .state import RESET_CONTEXT, RetrievedItem, SalesAgentState

# ── LLM / Embeddings ──────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    temperature=0.3,
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL"),
)

# Classification must be (near-)deterministic: the same message should always
# take the same route through the graph. A separate low-temperature instance is
# used for intent analysis, distinct from the creative conversational `llm`.
intent_llm = ChatOpenAI(
    model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    temperature=0,
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


# The retrieval pipeline runs in two ordered steps, never in parallel:
#
#   1. `filter_candidate_ids` applies the customer's *hard* constraints
#      (category / brand / price) in SQL. This is cheap, exact, and needs no
#      embedding at all.
#   2. `vector_search_products` ranks by semantic similarity, but only over the
#      rows step 1 allowed through.
#
# Running them in this order (rather than side by side and merging afterwards)
# means the vector search can never surface a product that violates a stated
# budget or category, and the two result sets no longer have to be reconciled
# on incompatible score scales.

# Upper bound on the id list handed from step 1 to step 2. Past this point
# enumerating ids is pointless and would bloat the checkpointed state, so the
# vector query re-applies the same predicates inline instead — same semantics,
# no truncation.
CANDIDATE_POOL_LIMIT = 500

MEANINGFUL_FILTER_KEYS = ("category", "brand", "minPrice", "maxPrice")


def has_meaningful_filters(filters: Optional[dict]) -> bool:
    """True when the customer stated a constraint worth filtering on.

    `query` is deliberately excluded: it is free text for the embedding, not a
    SQL predicate.
    """
    f = filters or {}
    return any(f.get(k) is not None and f.get(k) != "" for k in MEANINGFUL_FILTER_KEYS)


def _product_where(
    shop_id: str,
    filters: Optional[dict],
    exclude_ids: Optional[list[str]],
    first_param: int,
) -> tuple[str, list, int]:
    """Build the product WHERE clause shared by both retrieval steps.

    `first_param` is the 1-based index of the next free placeholder, so the
    same predicates can start a plain filter query ($1...) or follow the
    embedding parameter of a vector query ($2...). Returns the clause, its
    parameters, and the next free placeholder index.
    """
    f = filters or {}
    clauses = [
        f'"shopId" = ${first_param}',
        '"isActive" = true',
        # Rows without an embedding can never come back from step 2, so they
        # must not be counted as matches in step 1 either.
        "embedding IS NOT NULL",
    ]
    params: list = [shop_id]
    n = first_param + 1

    if f.get("category"):
        clauses.append(f"category ILIKE ${n}")
        params.append(f"%{f['category']}%")
        n += 1
    if f.get("brand"):
        clauses.append(f"brand ILIKE ${n}")
        params.append(f"%{f['brand']}%")
        n += 1
    # price is numeric(10,2); bind as text and cast so no float rounding can
    # creep into the comparison.
    if f.get("minPrice") is not None:
        clauses.append(f"price >= ${n}::numeric")
        params.append(str(f["minPrice"]))
        n += 1
    if f.get("maxPrice") is not None:
        clauses.append(f"price <= ${n}::numeric")
        params.append(str(f["maxPrice"]))
        n += 1
    if exclude_ids:
        clauses.append(f"NOT (id = ANY(${n}))")
        params.append(exclude_ids)
        n += 1

    return " AND ".join(clauses), params, n


async def filter_candidate_ids(
    shop_id: str,
    filters: Optional[dict],
    exclude_ids: Optional[list[str]] = None,
) -> tuple[list[str], bool]:
    """Step 1 — narrow the catalog with SQL before any embedding work.

    Returns `(ids, overflowed)`. `overflowed` means the match set is larger
    than CANDIDATE_POOL_LIMIT, so `ids` is not a complete answer and the caller
    should let step 2 re-apply the filters itself.
    """
    where, params, n = _product_where(shop_id, filters, exclude_ids, 1)
    rows = await db.query_raw(
        f"SELECT id FROM products WHERE {where} LIMIT ${n}",
        *params,
        CANDIDATE_POOL_LIMIT + 1,
    )
    ids = [str(r["id"]) for r in rows]
    if len(ids) > CANDIDATE_POOL_LIMIT:
        return [], True
    return ids, False


_PRODUCT_COLUMNS = (
    'id, name, price, description, category, brand, stock, "productUrl", "imageUrl"'
)


async def embed(text: str) -> list[float]:
    """One embedding call. Callers reuse the result across every vector query
    of the same turn instead of re-embedding the identical text per table."""
    return await embeddings.aembed_query(text)


async def vector_search_products(
    shop_id: str,
    query_vec: list[float],
    k: int,
    candidate_ids: Optional[list[str]] = None,
    filters: Optional[dict] = None,
    exclude_ids: Optional[list[str]] = None,
) -> list[RetrievedItem]:
    """Step 2 — rank by embedding distance *within* the filtered set.

    `candidate_ids` is the explicit output of step 1. When it is None the same
    predicates are applied inline instead: either the match set overflowed the
    pool, or there were no hard constraints to begin with.
    """
    params: list = [_vector_literal(query_vec)]

    if candidate_ids is not None:
        if not candidate_ids:
            return []
        where = (
            '"shopId" = $2 AND "isActive" = true '
            "AND embedding IS NOT NULL AND id = ANY($3)"
        )
        params += [shop_id, candidate_ids]
        n = 4
    else:
        where, extra, n = _product_where(shop_id, filters, exclude_ids, 2)
        params += extra

    rows = await db.query_raw(
        f"""SELECT {_PRODUCT_COLUMNS},
                   embedding <=> $1::vector AS score
            FROM products
            WHERE {where}
            ORDER BY score ASC
            LIMIT ${n}""",
        *params,
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


async def vector_search_faq(
    shop_id: str, query_vec: list[float], k: int = 3
) -> list[RetrievedItem]:
    rows = await db.query_raw(
        """SELECT id, question, answer,
                  embedding <=> $1::vector AS score
           FROM faq_items
           WHERE "shopId" = $2 AND embedding IS NOT NULL
           ORDER BY score ASC
           LIMIT $3""",
        _vector_literal(query_vec),
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
    # Customer rejected the current suggestions and wants different options
    rejected_current: bool = False
    # Customer accepted/dropped their previous objection ("ok", "fair enough")
    objection_resolved: bool = False


structured_llm = intent_llm.with_structured_output(IntentResult)

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


def derive_mode(intent: Optional[str], prev_mode: str) -> str:
    """Derive the graph mode from the intent so the two can't contradict.

    A new product search or a comparison is always broad exploration, never a
    single pinned product; anything else keeps the previous mode.
    """
    if intent in ("search_product", "compare"):
        return "explore"
    return prev_mode


async def analyze_intent(state: SalesAgentState) -> dict:
    # Give the classifier a short window of recent turns, not just the last
    # message, so filters/intent are read in context ("cheaper than that one").
    recent = state["messages"][-INTENT_HISTORY_WINDOW:]

    result: IntentResult = await structured_llm.ainvoke(
        [SystemMessage(content=build_intent_analysis_prompt()), *recent]
    )

    prev_mode = state.get("mode", "explore")
    # Single source of truth: derive mode from intent rather than trusting a
    # separate model field that may disagree with it.
    new_mode = derive_mode(result.intent, prev_mode)

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

    # objection is sticky across turns, but must clear once the customer drops it.
    if result.objection_resolved:
        new_objection = None
    else:
        new_objection = result.objection or state.get("objection")

    updates: dict = {
        "intent": result.intent,
        # stage / value_driver describe the customer over the whole
        # conversation, so keep the previous value when this turn says nothing.
        "stage": result.stage or state.get("stage", "browsing"),
        "value_driver": result.value_driver or state.get("value_driver"),
        "objection": new_objection,
        "explore_filters": merged_filters,
        # Wipe both retrieval buffers from the previous turn so nothing freezes:
        # retrieved_raw is reset via the None sentinel, retrieved_context via [].
        "retrieved_raw": RESET_CONTEXT,
        "retrieved_context": [],
        # Per-turn scratch from the SQL filter step; stale values must never
        # leak into a path that doesn't re-run it.
        "candidate_ids": [],
        "filter_status": FILTER_NONE,
        "filter_effective": {},
    }

    # Resolve an ordinal reference ("the second one") to a concrete product id.
    # Always resolve against shown_products, which is the last explore list the
    # customer actually browsed (product mode never overwrites it). Pinning a
    # product also switches to product mode so routing hits sql_query_product.
    if result.selected_index is not None:
        shown = [p for p in (state.get("shown_products") or []) if p.get("type") == "product"]
        idx = result.selected_index - 1
        if 0 <= idx < len(shown):
            updates["product_id"] = shown[idx]["id"]
            new_mode = "product"

    updates["mode"] = new_mode

    # Forget the pinned product when the customer leaves product mode.
    if new_mode == "explore" and prev_mode == "product":
        updates["product_id"] = None

    # Reject-and-retry: on a new topic clear the exclusion list; when the
    # customer rejects the current options, exclude them so the next search
    # returns something different.
    excluded = list(state.get("excluded_product_ids") or [])
    if result.new_topic:
        excluded = []
    elif result.rejected_current:
        rejected_ids = [p["id"] for p in (state.get("shown_products") or [])]
        excluded = list(dict.fromkeys(excluded + rejected_ids))
    updates["excluded_product_ids"] = excluded

    return updates


def router_after_intent(state: SalesAgentState) -> str:
    intent = state.get("intent")
    if intent == "buy_intent":
        return "handle_purchase"
    if intent in ("ask_question", "needs_clarification"):
        return "ask_question"
    # Objections and comparisons are about products already on the table — answer
    # from what we've shown instead of running a fresh (and misleading) search
    # whose query would be the objection/comparison text itself.
    if intent in ("objection", "compare") and state.get("shown_products"):
        return "answer_from_memory"
    if state.get("mode") == "product":
        return "sql_query_product"
    return "sql_filter_explore"


# ── Retrieval nodes: SQL filter → vector search ───────────────────────────────

# What the filter step concluded. The vector step reads this to decide how to
# scope itself, and the prompt reads it to know whether the constraints were
# actually satisfiable.
FILTER_NONE = "none"  # no hard constraints — vector sees the whole catalog
FILTER_IDS = "ids"  # vector is scoped to the ids the filter returned
FILTER_INLINE = "inline"  # too many matches to enumerate — filters re-applied in SQL
FILTER_RELAXED = "relaxed"  # filters matched nothing — vector runs unscoped

# Vector `k` per path. These are lower than the old fan-out's combined budget
# because every row now satisfies the customer's constraints: there is no
# off-budget noise left to over-fetch and discard, so fewer rows reach the
# prompt for the same answer quality.
EXPLORE_PRODUCT_K = 6
PRODUCT_RELATED_K = 5
FAQ_K = 3

EXPLORE_CONTEXT_LIMIT = 8
PRODUCT_CONTEXT_LIMIT = 6


# Order in which predicates are dropped when nothing matches — most negotiable
# first. `category` and `brand` are free text the classifier inferred from the
# message, so they routinely miss a column that is sparse, NULL, or worded
# differently ("لپ تاپ گیمینگ" vs a NULL category) — and the embedding already
# carries that meaning, which is precisely what step 2 is for. A stated budget
# is the opposite: it is exact, the customer means it literally, and breaking it
# is the worst failure this agent can have. So price is never dropped.
#
# The invariant this buys us: either the customer's price range is honoured, or
# `filter_status` is RELAXED and the prompt says so outright.
FILTER_RELAXATION_ORDER = ("category", "brand")


def _active_filters(filters: dict) -> dict:
    return {
        k: v for k, v in filters.items() if k in MEANINGFUL_FILTER_KEYS and v not in (None, "")
    }


async def _filter_step(state: SalesAgentState) -> dict:
    """Step 1, shared by both paths: turn the customer's stated constraints
    into a concrete candidate set (or a reason why there isn't one).

    Filters are tried as a whole first, then progressively relaxed. Each retry
    is one indexed SQL query with no embedding or LLM involved, and only runs
    when the previous attempt matched nothing.
    """
    filters = state.get("explore_filters") or {}
    if not has_meaningful_filters(filters):
        return {"candidate_ids": [], "filter_status": FILTER_NONE, "filter_effective": {}}

    exclude_ids = state.get("excluded_product_ids")
    attempt = _active_filters(filters)

    while True:
        ids, overflowed = await filter_candidate_ids(state["shop_id"], attempt, exclude_ids)
        if overflowed:
            return {
                "candidate_ids": [],
                "filter_status": FILTER_INLINE,
                "filter_effective": attempt,
            }
        if ids:
            return {
                "candidate_ids": ids,
                "filter_status": FILTER_IDS,
                "filter_effective": attempt,
            }

        # Nothing matched — give up the most negotiable predicate and retry.
        droppable = next((k for k in FILTER_RELAXATION_ORDER if k in attempt), None)
        if droppable is None:
            break
        attempt.pop(droppable)
        if not attempt:
            break

    # Even the hard constraints alone match nothing. Rather than dead-ending,
    # let step 2 run unscoped so the agent has the closest alternatives to
    # offer — build_explore_prompt tells it to be upfront about that.
    return {"candidate_ids": [], "filter_status": FILTER_RELAXED, "filter_effective": {}}


def _vector_scope(
    state: SalesAgentState,
) -> tuple[Optional[list[str]], Optional[dict], Optional[list[str]]]:
    """Translate the filter step's verdict into vector-query scoping."""
    status = state.get("filter_status", FILTER_NONE)
    if status == FILTER_IDS:
        return list(state.get("candidate_ids") or []), None, None
    if status == FILTER_INLINE:
        # Re-apply the predicates that actually survived relaxation, not the
        # raw ones the classifier produced.
        return None, state.get("filter_effective"), state.get("excluded_product_ids")
    # NONE / RELAXED: no id list to honour; only rejected products still apply.
    return None, None, state.get("excluded_product_ids")


async def sql_filter_explore(state: SalesAgentState) -> dict:
    """Explore, step 1: narrow the catalog by category / brand / price."""
    return await _filter_step(state)


async def vector_search_explore(state: SalesAgentState) -> dict:
    """Explore, step 2: embed once, then search the filtered set."""
    query = (state.get("explore_filters") or {}).get("query") or last_message_text(state)
    query_vec = await embed(query)
    candidate_ids, filters, exclude_ids = _vector_scope(state)

    tasks = [
        vector_search_products(
            state["shop_id"],
            query_vec,
            EXPLORE_PRODUCT_K,
            candidate_ids,
            filters,
            exclude_ids,
        )
    ]
    # A pure product search gains nothing from FAQ chunks, and they cost both a
    # query and prompt tokens. Other explore intents (browse: shipping, hours,
    # returns) are exactly what the FAQ table is for, so they keep it.
    if state.get("intent") != "search_product":
        tasks.append(vector_search_faq(state["shop_id"], query_vec, FAQ_K))

    groups = await asyncio.gather(*tasks)
    return {"retrieved_raw": [item for group in groups for item in group]}


async def sql_query_product(state: SalesAgentState) -> dict:
    """Product, step 1: load the pinned product, then narrow the catalog the
    same way explore does so related suggestions stay inside the constraints."""
    items: list[RetrievedItem] = []

    product_id = state.get("product_id")
    if product_id:
        # Scope by shopId so one shop can never pull another shop's product.
        product = await db.product.find_first(
            where={"id": product_id, "shopId": state["shop_id"]}
        )
        if product:
            items.append(
                RetrievedItem(
                    id=product.id,
                    type="product",
                    content=_product_content(
                        {
                            "name": product.name,
                            "price": product.price,
                            "description": product.description,
                        }
                    ),
                    metadata={
                        "name": product.name,
                        "productUrl": product.productUrl,
                        "imageUrl": product.imageUrl,
                        "price": product.price,
                        "stock": product.stock,
                    },
                )
            )

    return {"retrieved_raw": items, **(await _filter_step(state))}


async def vector_search_product(state: SalesAgentState) -> dict:
    """Product, step 2: related products + FAQ, sharing one embedding."""
    query_vec = await embed(last_message_text(state))
    candidate_ids, filters, exclude_ids = _vector_scope(state)

    products, faqs = await asyncio.gather(
        vector_search_products(
            state["shop_id"],
            query_vec,
            PRODUCT_RELATED_K,
            candidate_ids,
            filters,
            exclude_ids,
        ),
        vector_search_faq(state["shop_id"], query_vec, FAQ_K),
    )
    return {"retrieved_raw": products + faqs}


def fuse_and_rank_context(
    items: list[RetrievedItem], state: SalesAgentState
) -> list[RetrievedItem]:
    deduped = list({item["id"]: item for item in items}.values())
    pinned_id = state.get("product_id")

    def sort_key(item: RetrievedItem) -> float:
        # The product the customer is actively discussing must rank first.
        if pinned_id and item.get("id") == pinned_id:
            return -1.0
        # Every retrieved row now carries a real cosine distance from the same
        # query vector, so these are directly comparable; the default only
        # covers the pinned product, which is fetched by id rather than search.
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
    ranked = fuse_and_rank_context(state.get("retrieved_raw", []), state)
    top = ranked[:EXPLORE_CONTEXT_LIMIT]
    # Only the explore path updates shown_products — it is the list the customer
    # numbers ("the second one"). Product mode must NOT overwrite it, or later
    # ordinal references would resolve against a single pinned product.
    # candidate_ids is per-turn scratch; drop it so it isn't checkpointed.
    return {
        "retrieved_context": top,
        "shown_products": _shown_products(top),
        "candidate_ids": [],
    }


async def fuse_context_product(state: SalesAgentState) -> dict:
    ranked = fuse_and_rank_context(state.get("retrieved_raw", []), state)
    top = ranked[:PRODUCT_CONTEXT_LIMIT]
    return {"retrieved_context": top, "candidate_ids": []}


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
        state.get("retrieved_context", []), state.get("stage"), state.get("value_driver"), state.get("objection"),
        filters_relaxed=state.get("filter_status") == FILTER_RELAXED,
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
        state.get("retrieved_context", []), state.get("stage"), state.get("value_driver"), state.get("objection"),
        filters_relaxed=state.get("filter_status") == FILTER_RELAXED,
    )

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_prompt, state.get("summary"))
    )

    return {"messages": [reply]}


async def answer_from_memory(state: SalesAgentState) -> dict:
    """Handle objections / comparisons using already-shown products, no search."""
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    shown = state.get("shown_products", [])
    context_prompt = build_explore_prompt(
        shown, state.get("stage"), state.get("value_driver"), state.get("objection")
    )

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_prompt, state.get("summary"))
    )

    # Re-surface the same products in the response (images / buy buttons) since
    # analyze_intent cleared retrieved_context at the start of the turn.
    return {"messages": [reply], "retrieved_context": list(shown)}


async def ask_question(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    query = last_message_text(state)
    faq_items = await vector_search_faq(state["shop_id"], await embed(query), FAQ_K)

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
        .add_node("sql_filter_explore", sql_filter_explore)
        .add_node("vector_search_explore", vector_search_explore)
        .add_node("sql_query_product", sql_query_product)
        .add_node("vector_search_product", vector_search_product)
        .add_node("fuse_results_explore", fuse_results_explore)
        .add_node("fuse_context_product", fuse_context_product)
        .add_node("suggest_products", suggest_products)
        .add_node("product_agent", product_agent)
        .add_node("answer_from_memory", answer_from_memory)
        .add_node("ask_question", ask_question)
        .add_node("handle_purchase", handle_purchase)
        # edges
        .add_edge(START, "maybe_summarize")
        .add_edge("maybe_summarize", "analyze_intent")
        .add_conditional_edges(
            "analyze_intent",
            router_after_intent,
            ["sql_filter_explore", "sql_query_product", "ask_question", "handle_purchase", "answer_from_memory"],
        )
        # explore path: SQL filter narrows the catalog, then the vector search
        # ranks *within* that result — strictly sequential, never side by side.
        .add_edge("sql_filter_explore", "vector_search_explore")
        .add_edge("vector_search_explore", "fuse_results_explore")
        .add_edge("fuse_results_explore", "suggest_products")
        .add_edge("suggest_products", END)
        # product path: same two steps, plus the pinned product itself
        .add_edge("sql_query_product", "vector_search_product")
        .add_edge("vector_search_product", "fuse_context_product")
        .add_edge("fuse_context_product", "product_agent")
        .add_edge("product_agent", END)
        # terminal nodes
        .add_edge("answer_from_memory", END)
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
