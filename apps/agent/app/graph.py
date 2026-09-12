import asyncio
import os
from collections import OrderedDict
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
from pydantic import BaseModel, Field

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
    if row.get("brand"):
        parts.append(f"برند: {row['brand']}")
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

# The subset that establishes *topical* relevance. `category` and `brand` come
# from the shop's own vocabulary and are matched exactly, so a row satisfying
# one is on-topic by construction. A price range says nothing about topic:
# "under 2M" is satisfied just as well by a power bank as by a running shoe.
# Used both to steer the embedding (_search_text) and to decide whether the
# distance floor may run at all (_rank_and_trim).
SEMANTIC_FILTER_KEYS = ("category", "brand")


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

    # Exact, case-insensitive match — not a substring one. The classifier picks
    # `category` from the shop's own vocabulary (see analyze_intent), so the
    # value is known to exist. A `%…%` pattern was worse than useless here: it
    # required the *stored* category to contain the classifier's phrase, so a
    # customer being more specific than the taxonomy ("کفش ورزشی مردانه" against
    # a stored "کفش ورزشی") matched nothing and silently relaxed the filter.
    if f.get("category"):
        clauses.append(f"lower(category) = lower(${n})")
        params.append(str(f["category"]).strip())
        n += 1
    if f.get("brand"):
        clauses.append(f"lower(brand) = lower(${n})")
        params.append(str(f["brand"]).strip())
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


# The fan-out branches all embed the *same* query text concurrently, so the
# vector is memoised process-wide (an embedding depends only on the text, never
# on the shop or the turn). A plain cache is not enough: three concurrent misses
# would still fire three requests, so in-flight calls are shared through one
# task per text and only the winner pays.
_EMBED_CACHE_MAX = 32
_embed_cache: "OrderedDict[str, list[float]]" = OrderedDict()
_embed_inflight: dict[str, "asyncio.Task[list[float]]"] = {}


async def embed(text: str) -> list[float]:
    """Embed `text`, sharing one API call across every branch of the turn."""
    cached = _embed_cache.get(text)
    if cached is not None:
        _embed_cache.move_to_end(text)
        return cached

    running = _embed_inflight.get(text)
    if running is not None:
        # Another branch is already embedding this exact text — wait on it
        # rather than paying for a second identical call.
        return await running

    task = asyncio.create_task(embeddings.aembed_query(text))
    _embed_inflight[text] = task
    try:
        vec = await task
    finally:
        # Pop on failure too, or one transient error would poison the text for
        # the lifetime of the process.
        _embed_inflight.pop(text, None)

    _embed_cache[text] = vec
    if len(_embed_cache) > _EMBED_CACHE_MAX:
        _embed_cache.popitem(last=False)
    return vec


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


async def vector_search_shop_info(
    shop_id: str, query_vec: list[float], k: int = 2
) -> list[RetrievedItem]:
    """Business facts (history, payment methods, sizing guidance, support).

    The admin panel rebuilds these chunks from the shop's description, support
    info and prompt extra whenever the catalog is re-embedded, so this is the
    live copy — the system prompt no longer repeats it (see prompts.py).
    """
    rows = await db.query_raw(
        """SELECT id, content,
                  embedding <=> $1::vector AS score
           FROM shop_info_chunks
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
            type="shop_info",
            content=str(r["content"]),
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
    # Optional, same as value_driver/objection: the prompt tells the model to
    # leave it null when the current message doesn't make it clear, so the
    # merge logic below can keep the previous turn's value. A bare `str` made
    # that instruction impossible to follow — with_structured_output turns the
    # schema into a hard constraint, so the model was forced to guess a stage
    # on every turn no matter what the wording asked for.
    stage: Optional[str] = None
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
    # The customer named a product type this shop's category vocabulary does
    # not contain. Set instead of guessing a category that cannot match.
    out_of_catalog: bool = False
    # Constraints the customer explicitly took back or corrected. Merging alone
    # could never remove a filter, so a wrong budget stuck for the whole
    # conversation no matter how often the customer objected to it.
    cleared_filters: list[str] = Field(default_factory=list)
    # "price_asc" for cheapest-first, "price_desc" for most-expensive-first.
    sort: Optional[str] = None
    # A comparative aimed at what was just shown ("ارزون‌تر", "گرون‌ترش رو
    # دارید؟"). Unlike `sort`, which only orders whatever the filters allow,
    # this has to become a hard bound derived from the shown prices — otherwise
    # "cheaper" returned a *different* product that cost more.
    # "cheaper" | "pricier".
    relative_price: Optional[str] = None


structured_llm = intent_llm.with_structured_output(IntentResult)

# ── Nodes ─────────────────────────────────────────────────────────────────────

# When the running transcript exceeds SUMMARY_TRIGGER messages, collapse
# everything except the last KEEP_RECENT into a text summary. This caps the
# tokens sent to the model on every turn instead of resending the whole history.
SUMMARY_TRIGGER = 20
KEEP_RECENT = 6

SUMMARY_INSTRUCTION = (
    "متن بالا رونوشت بخشی از یک مکالمه است. از آن یک خلاصه بنویس.\n"
    "فقط این‌ها را نگه دار: نیاز و خواسته مشتری، محصولاتی که دیده، بودجه و "
    "ترجیحاتش، اعتراض‌ها و تصمیم‌هایش. کوتاه و به فارسی بنویس.\n\n"
    "⚠️ تو در حال گفتگو با مشتری نیستی و نباید به او پاسخ بدهی. فقط گزارش بنویس.\n"
    "⚠️ هیچ نام محصول، قیمت یا مشخصه‌ای که در متن بالا نیامده ننویس. چیزی از خودت "
    "اضافه نکن و پیشنهاد جدید نده."
)


def _transcript(messages: list[BaseMessage]) -> str:
    """Render messages as plain text for the summarizer."""
    lines = []
    for m in messages:
        role = "مشتری" if isinstance(m, HumanMessage) else "فروشنده"
        content = m.content if isinstance(m.content, str) else str(m.content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def maybe_summarize(state: SalesAgentState) -> dict:
    messages = state["messages"]
    if len(messages) <= SUMMARY_TRIGGER:
        return {}

    old = messages[:-KEEP_RECENT]
    previous = state.get("summary")
    preface = f"خلاصه قبلی:\n{previous}\n\n" if previous else ""

    # The old turns go in as *quoted text*, not as live conversation, and the
    # instruction goes last. Passing them as real messages made the model
    # continue the dialogue instead of summarizing it — it answered as the
    # salesperson and invented products and prices that were never in the
    # catalog, which then got injected into every later turn as trusted
    # "conversation summary" context.
    summary = await llm.ainvoke(
        [
            HumanMessage(
                content=(
                    f"{preface}--- رونوشت مکالمه ---\n"
                    f"{_transcript(old)}\n"
                    f"--- پایان رونوشت ---\n\n{SUMMARY_INSTRUCTION}"
                )
            )
        ]
    )

    # Keep the summary in its own state field and drop the summarized messages
    # from the transcript. Storing it separately (rather than splicing a message
    # back in) avoids ordering issues with the add_messages reducer.
    removals = [RemoveMessage(id=m.id) for m in old if getattr(m, "id", None)]
    return {"summary": summary.content, "messages": removals}


INTENT_HISTORY_WINDOW = 6


# products.price is numeric(10,2), so one step of its scale turns an
# inclusive bound into a strictly exclusive one.
PRICE_EPSILON = 0.01


def _relative_price_bound(
    relative: Optional[str], shown: Optional[list[RetrievedItem]]
) -> Optional[tuple[str, float]]:
    """Turn "cheaper"/"pricier" into a price bound taken from the shown list.

    Cheaper is measured against the *lowest* price on the table (and pricier
    against the highest): anything else would return a product the customer can
    already see and has implicitly passed over.
    """
    if relative not in ("cheaper", "pricier"):
        return None

    prices = []
    for item in shown or []:
        if item.get("type") != "product":
            continue
        price = (item.get("metadata") or {}).get("price")
        if price is None:
            continue
        try:
            prices.append(float(price))
        except (TypeError, ValueError):
            continue
    if not prices:
        return None

    # _product_where compares with <= / >=, so the bound is nudged by one step
    # of the column's own scale (numeric(10,2)) to make it strictly exclusive.
    # Landing *on* the boundary is not "cheaper" — it is the same price as
    # something the customer just turned down.
    if relative == "cheaper":
        return "maxPrice", min(prices) - PRICE_EPSILON
    return "minPrice", max(prices) + PRICE_EPSILON


def derive_mode(intent: Optional[str], prev_mode: str) -> str:
    """Derive the graph mode from the intent so the two can't contradict.

    A new product search or a comparison is always broad exploration, never a
    single pinned product; anything else keeps the previous mode.
    """
    if intent in ("search_product", "compare"):
        return "explore"
    return prev_mode


async def shop_categories(shop_id: str) -> list[str]:
    """The categories this shop actually stocks.

    This is the vocabulary the classifier must choose from. Reading it from the
    products themselves (rather than the aspirational free-text list on the
    shop) guarantees any category it returns can match a row.
    """
    rows = await db.query_raw(
        """SELECT DISTINCT category FROM products
           WHERE "shopId" = $1 AND "isActive" = true
             AND category IS NOT NULL AND category <> ''
           ORDER BY category""",
        shop_id,
    )
    return [str(r["category"]) for r in rows]


async def analyze_intent(state: SalesAgentState) -> dict:
    # Give the classifier a short window of recent turns, not just the last
    # message, so filters/intent are read in context ("cheaper than that one").
    recent = state["messages"][-INTENT_HISTORY_WINDOW:]
    categories = await shop_categories(state["shop_id"])

    result: IntentResult = await structured_llm.ainvoke(
        [SystemMessage(content=build_intent_analysis_prompt(categories)), *recent]
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
    # A merge can only ever add constraints. Without this, a filter the model
    # invented once (a budget read into "ارزون") survived every correction the
    # customer made for the rest of the conversation.
    for key in result.cleared_filters:
        merged_filters.pop(key, None)
    # Guard the same failure from the other side: never keep a category the
    # shop does not stock, it can only match zero rows and force a relaxation.
    # (The mirror-image guard — a wrong `out_of_catalog` guess overturned by a
    # real SQL match — lives in fuse_results_explore.)
    if merged_filters.get("category") and categories:
        if not any(
            str(merged_filters["category"]).strip().lower() == c.strip().lower()
            for c in categories
        ):
            merged_filters.pop("category", None)

    # "cheaper" / "pricier" is only meaningful against what the customer is
    # looking at, so turn it into a hard bound taken from those prices. Without
    # this the request was honoured only by luck: `rejected_current` excluded the
    # shown ids, so the next search returned *different* products — which could
    # perfectly well cost more than the ones the customer just called expensive.
    bound = _relative_price_bound(result.relative_price, state.get("shown_products"))
    if bound:
        key, value = bound
        merged_filters[key] = value
        # A cheaper-than bound replaces any floor left over from earlier turns
        # (and vice versa), or the two can cross and match nothing.
        merged_filters.pop("minPrice" if key == "maxPrice" else "maxPrice", None)

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
        "filters_dropped": [],
        # Both are per-turn verdicts; a stale "we don't stock this" must never
        # leak into the next question.
        "out_of_catalog": result.out_of_catalog,
        "sort": result.sort,
        # Search turns show buy buttons; only handle_purchase turns it off.
        "buy_actions": True,
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
    # Greetings, thanks and acknowledgements ("جالبه") need no catalog at all.
    # Routing them through retrieval attached six unrelated products to a
    # "سلام" and burned an embedding call plus two SQL queries per turn.
    if intent == "smalltalk":
        return "smalltalk_reply"
    if intent in ("ask_question", "needs_clarification"):
        return "ask_question"
    # Buying, objecting and comparing are the same turn: the customer is engaged
    # with the products already on the table and wants nothing new retrieved.
    # Searching here would embed the objection text itself ("قیمتش بالاست"),
    # return different products, and overwrite the numbered list the customer is
    # referring to. handle_purchase picks the closing move for each.
    if intent == "buy_intent":
        return "handle_purchase"
    if intent in ("objection", "compare") and state.get("shown_products"):
        return "handle_purchase"
    if state.get("mode") == "product":
        return "fan_out_product"
    return "fan_out_explore"


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
# Business facts are few and short; two chunks cover a question without
# crowding products out of the context budget.
SHOP_INFO_K = 2

EXPLORE_CONTEXT_LIMIT = 8
PRODUCT_CONTEXT_LIMIT = 6


# Order in which predicates are dropped when nothing matches — most negotiable
# first. A stated budget is a preference, not an identity: a customer who asked
# for football boots under 8M would rather see the same boots for more than see
# an unrelated product that merely happens to fit the price — which is exactly
# what dropping category first produced (a yoga mat "answering" a shoe search,
# because it was cheap enough). So price gives way before anything else, and
# `filters_dropped` tells the prompt precisely that, so the reply says "not at
# this budget, but here's what we have" instead of "we don't have this at all".
#
# `category`/`brand` are the shop's own vocabulary the classifier guessed at,
# so they can still miss on a wording/NULL mismatch ("لپ تاپ گیمینگ" vs a NULL
# category) — but that is the last resort, tried only once dropping price
# alone still finds nothing.
FILTER_RELAXATION_ORDER = ("maxPrice", "minPrice", "category", "brand")


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
        return {
            "candidate_ids": [],
            "filter_status": FILTER_NONE,
            "filter_effective": {},
            "filters_dropped": [],
        }

    exclude_ids = state.get("excluded_product_ids")
    requested = _active_filters(filters)
    attempt = dict(requested)

    def dropped(surviving: dict) -> list[str]:
        return [k for k in requested if k not in surviving]

    while True:
        ids, overflowed = await filter_candidate_ids(state["shop_id"], attempt, exclude_ids)
        if overflowed:
            return {
                "candidate_ids": [],
                "filter_status": FILTER_INLINE,
                "filter_effective": attempt,
                "filters_dropped": dropped(attempt),
            }
        if ids:
            return {
                "candidate_ids": ids,
                "filter_status": FILTER_IDS,
                "filter_effective": attempt,
                "filters_dropped": dropped(attempt),
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
    return {
        "candidate_ids": [],
        "filter_status": FILTER_RELAXED,
        "filter_effective": {},
        "filters_dropped": list(requested),
    }


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


SORT_DIRECTIONS = {"price_asc": "ASC", "price_desc": "DESC"}
SORT_LIMIT = 5


async def sorted_products(
    shop_id: str,
    sort: str,
    filters: Optional[dict],
    exclude_ids: Optional[list[str]],
) -> list[RetrievedItem]:
    """Answer a superlative ("the cheapest one") with SQL, not similarity.

    Embedding distance cannot rank by price, so "ارزان‌ترین گوشی" used to come
    back as whatever happened to be nearest in the filtered set. This orders
    the same constrained set by price instead.
    """
    direction = SORT_DIRECTIONS.get(sort)
    if direction is None:
        return []

    where, params, n = _product_where(shop_id, filters, exclude_ids, 1)
    rows = await db.query_raw(
        f"""SELECT {_PRODUCT_COLUMNS}
            FROM products WHERE {where}
            ORDER BY price {direction} LIMIT ${n}""",
        *params,
        SORT_LIMIT,
    )
    return [
        RetrievedItem(
            id=str(r["id"]),
            type="product",
            content=_product_content(r),
            # Sorted rows are exact answers to the stated constraint, so they
            # must clear the relevance floor that similarity results face.
            score=0.0,
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


def _search_text(state: SalesAgentState) -> str:
    """The text to embed for this turn.

    The customer's current message always leads. `explore_filters["query"]` is
    merged across turns, so relying on it first meant a turn that produced no
    new filters silently re-embedded an *older* query — the same vector, the
    same rows, and the model then repeated its previous answer verbatim.

    The resolved category/brand follow. A needs-shaped message ("برای
    برادرزاده‌ام دختر ۱۶ ساله") shares almost no vocabulary with the rows it
    should match, so on its own it ranks an already-correct candidate set
    close to arbitrarily. These come from `explore_filters`, i.e. what the
    customer asked for — unlike the floor's gate, which reads `filter_effective`
    because it asks a different question (what SQL *proved*, not what was
    *wanted*). When the category matched nothing, steering the embedding toward
    it is exactly right: the unscoped search should then surface the nearest
    alternatives to what was asked for.
    """
    text = last_message_text(state)
    filters = state.get("explore_filters") or {}

    extras = [filters.get("query"), *(filters.get(k) for k in SEMANTIC_FILTER_KEYS)]
    for extra in extras:
        if extra and str(extra) not in text:
            text = f"{text} {extra}"
    return text


# ── Fan-out ───────────────────────────────────────────────────────────────────
#
# The product lookup is a *chain*: the SQL filter must finish before the vector
# search can be scoped to its result. The FAQ and shop-info lookups depend on
# neither, so they run alongside that chain rather than behind it. Each branch
# writes into `retrieved_raw` (see accumulate_retrieved) and the fuse node joins
# them once every branch has finished.
#
# The three branches embed the same query text, so `embed` shares one API call
# between them — the fan-out costs extra queries, never extra embeddings.


async def fan_out_explore(_state: SalesAgentState) -> dict:
    return {}


async def fan_out_product(_state: SalesAgentState) -> dict:
    return {}


def route_fan_out_explore(state: SalesAgentState) -> list[Send]:
    sends = [
        Send("sql_filter_explore", dict(state)),
        Send("vector_shop_info_explore", dict(state)),
    ]
    # A pure product search gains nothing from FAQ chunks, and they cost both a
    # query and prompt tokens. Other explore intents (browse: shipping, hours,
    # returns) are exactly what the FAQ table is for, so they keep it.
    if state.get("intent") != "search_product":
        sends.append(Send("vector_faq_explore", dict(state)))
    return sends


def route_fan_out_product(state: SalesAgentState) -> list[Send]:
    return [
        Send("sql_query_product", dict(state)),
        Send("vector_faq_product", dict(state)),
        Send("vector_shop_info_product", dict(state)),
    ]


async def vector_faq(state: SalesAgentState) -> dict:
    query_vec = await embed(_search_text(state))
    return {"retrieved_raw": await vector_search_faq(state["shop_id"], query_vec, FAQ_K)}


async def vector_shop_info(state: SalesAgentState) -> dict:
    query_vec = await embed(_search_text(state))
    return {
        "retrieved_raw": await vector_search_shop_info(
            state["shop_id"], query_vec, SHOP_INFO_K
        )
    }


async def vector_search_explore(state: SalesAgentState) -> dict:
    """Explore, step 2: rank the filtered set. Ranking and truncation happen in
    fuse_results_explore, once the parallel branches have landed too."""
    # A superlative is answered by ordering, not by similarity. Reuse the same
    # constrained set the filter step produced so the budget still holds.
    sort = state.get("sort")
    if sort in SORT_DIRECTIONS:
        status = state.get("filter_status", FILTER_NONE)
        scope_filters = (
            state.get("filter_effective")
            if status in (FILTER_IDS, FILTER_INLINE)
            else None
        )
        ranked = await sorted_products(
            state["shop_id"],
            sort,
            scope_filters,
            state.get("excluded_product_ids"),
        )
        if ranked:
            return {"retrieved_raw": ranked, "candidate_ids": []}

    query_vec = await embed(_search_text(state))
    candidate_ids, filters, exclude_ids = _vector_scope(state)
    items = await vector_search_products(
        state["shop_id"],
        query_vec,
        EXPLORE_PRODUCT_K,
        candidate_ids,
        filters,
        exclude_ids,
    )
    # candidate_ids is per-turn scratch, already consumed by _vector_scope above.
    return {"retrieved_raw": items, "candidate_ids": []}


def _item_from_product(product) -> RetrievedItem:
    """A catalog row fetched by id, rendered exactly as the vector path renders
    it — dropping any of these made the same product read differently depending
    on how it had been found."""
    return RetrievedItem(
        id=product.id,
        type="product",
        content=_product_content(
            {
                "name": product.name,
                "price": product.price,
                "description": product.description,
                "category": product.category,
                "brand": product.brand,
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


async def _pinned_product(state: SalesAgentState) -> Optional[RetrievedItem]:
    """The product the customer pinned, if any. Scoped by shopId so one shop can
    never pull another shop's product."""
    product_id = state.get("product_id")
    if not product_id:
        return None
    product = await db.product.find_first(
        where={"id": product_id, "shopId": state["shop_id"]}
    )
    return _item_from_product(product) if product else None


async def sql_query_product(state: SalesAgentState) -> dict:
    """Product, step 1: load the pinned product, then narrow the catalog the
    same way explore does so related suggestions stay inside the constraints."""
    items: list[RetrievedItem] = []

    pinned = await _pinned_product(state)
    if pinned:
        items.append(pinned)

    return {"retrieved_raw": items, **(await _filter_step(state))}


async def vector_search_product(state: SalesAgentState) -> dict:
    """Product, step 2: related products, scoped to what step 1 allowed.

    FAQ and shop info arrive on their own branches; fuse_context_product joins
    all three.
    """
    query_vec = await embed(_search_text(state))
    candidate_ids, filters, exclude_ids = _vector_scope(state)
    products = await vector_search_products(
        state["shop_id"],
        query_vec,
        PRODUCT_RELATED_K,
        candidate_ids,
        filters,
        exclude_ids,
    )
    # candidate_ids is per-turn scratch, already consumed by _vector_scope above.
    return {"retrieved_raw": products, "candidate_ids": []}


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
        #
        # No value_driver adjustment here: subtracting a constant from every
        # product with a price changed nothing about their order relative to
        # each other, which is the only thing this function decides. A stated
        # preference for cheap is honoured by `sort` (SQL ORDER BY) instead.
        return item.get("score", 0.5)

    return sorted(deduped, key=sort_key)


# Cosine distance above which a product is not a real answer to the query, just
# the nearest row in a small catalog. Calibrated on product-shaped queries
# ("لپتاپ برای دانشگاه" against "لپ تاپ HP ..."), where genuine matches land at
# 0.50–0.65 and unrelated rows cluster at 0.74–0.82.
#
# A needs-shaped query does not obey that calibration. "برای برادرزاده‌ام دختر
# ۱۶ ساله" describes the *recipient*; the rows describe *garments*, so a
# perfectly correct match still sits at 0.75+. That is why the floor below is
# conditional — see _drop_irrelevant.
RELEVANCE_MAX_DISTANCE = 0.70

def _semantic_filter_applied(state: SalesAgentState) -> bool:
    """True when the SQL step already proved the candidates are on-topic.

    Reads `filter_effective` — what actually survived progressive relaxation —
    not the classifier's original guess. A category that was dropped because it
    matched nothing proves nothing.
    """
    effective = state.get("filter_effective") or {}
    return any(effective.get(key) for key in SEMANTIC_FILTER_KEYS)


def _drop_irrelevant(
    items: list[RetrievedItem], pinned_id: Optional[str]
) -> list[RetrievedItem]:
    """Remove products too far from the query to be worth showing.

    Without this every search returns its top-k regardless of distance, and the
    prompt presents them under "محصولات پیدا شده" — which is how a power bank
    became the answer to a request for running shoes. FAQs and the pinned
    product are exempt: they are fetched deliberately, not by similarity.

    Only ever called when no semantic predicate survived (see _rank_and_trim):
    embedding distance is evidence of last resort, not a veto over an exact
    category match.
    """
    return [
        i
        for i in items
        if i["type"] != "product"
        or i.get("id") == pinned_id
        or float(i.get("score", 0.0)) <= RELEVANCE_MAX_DISTANCE
    ]


def _shown_products(items: list[RetrievedItem]) -> list[RetrievedItem]:
    return [i for i in items if i["type"] == "product"]


def _rank_and_trim(state: SalesAgentState, limit: int) -> list[RetrievedItem]:
    """Join point: every branch has landed in `retrieved_raw` by now, so rank
    them together, drop the too-distant products, and cut to the prompt budget.

    The distance floor applies only when the SQL step established nothing about
    topic. When a category/brand predicate survived, these rows *are* the
    answer and the vector step's only job was to order them — applying the
    floor there let a weak signal (how close the customer's phrasing embeds to
    the product text) overrule a strong one (an exact category match), and the
    agent told a customer it had nothing while stocking four matching items.
    """
    ranked = fuse_and_rank_context(state.get("retrieved_raw") or [], state)
    if _semantic_filter_applied(state):
        return ranked[:limit]
    relevant = _drop_irrelevant(ranked, state.get("product_id"))
    return relevant[:limit]


async def fuse_results_explore(state: SalesAgentState) -> dict:
    """Barrier for the explore fan-out: the SQL→vector chain plus the FAQ and
    shop-info branches. Runs only once all of them have finished."""
    top = _rank_and_trim(state, EXPLORE_CONTEXT_LIMIT)

    # The customer asked for products and nothing we hold is close enough. Say
    # so rather than presenting the nearest rows as if they were the answer.
    #
    # Only a genuine product request can conclude this. An informational
    # question ("do you offer a warranty?") also retrieves no products, but
    # that means "answer from the business info", not "we don't stock it".
    product_request = state.get("intent") in ("search_product", "compare")
    no_product_answer = not any(i["type"] == "product" for i in top)

    # The classifier's `out_of_catalog` guess is just that — a guess made
    # before any retrieval ran. Guard the same failure as the `category`
    # guard in analyze_intent, from the other side: a category/brand
    # predicate that survived to `filter_status == FILTER_IDS` means SQL
    # matched real rows in that exact shop vocabulary, and if any of them
    # made it through ranking, the request is proven in-catalog. That proof
    # must overturn the guess, not just fail to reinforce it — without this
    # the flag was monotonic (only ever OR'd in), so a wrong "we don't stock
    # this" from turn N survived even after turn N+1 retrieved the real
    # products, and the prompt told the model to disown its own results.
    proven_in_catalog = _semantic_filter_applied(state) and not no_product_answer
    out_of_catalog = (
        False
        if proven_in_catalog
        else bool(state.get("out_of_catalog")) or (product_request and no_product_answer)
    )

    updates: dict = {
        "retrieved_context": top,
        "candidate_ids": [],
        "out_of_catalog": out_of_catalog,
    }
    # Only the explore path updates shown_products — it is the list the customer
    # numbers ("the second one"). Product mode must NOT overwrite it, or later
    # ordinal references would resolve against a single pinned product. Keep the
    # previous list when this turn produced nothing to number, so an ordinal
    # reference still resolves against what the customer last browsed.
    shown = _shown_products(top)
    if shown:
        updates["shown_products"] = shown
    return updates


async def fuse_context_product(state: SalesAgentState) -> dict:
    """Barrier for the product fan-out. shown_products and out_of_catalog stay
    untouched: only the explore path may set them.

    Not an oversight: fuse_results_explore can *revoke* a wrong out_of_catalog
    guess because a category/brand match there is proof the request matches
    real rows in the shop's own vocabulary. This path has no equivalent proof
    to offer — the pinned product was already fetched by id, not by category —
    so there is nothing here that could correct the classifier's guess either
    way, and leaving it alone is the correct (not merely convenient) choice.
    """
    return {
        "retrieved_context": _rank_and_trim(state, PRODUCT_CONTEXT_LIMIT),
        "candidate_ids": [],
    }


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
        filters_dropped=state.get("filters_dropped") or [],
        out_of_catalog=bool(state.get("out_of_catalog")),
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
        filters_dropped=state.get("filters_dropped") or [],
        out_of_catalog=bool(state.get("out_of_catalog")),
    )

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_prompt, state.get("summary"))
    )

    return {"messages": [reply]}


async def ask_question(state: SalesAgentState) -> dict:
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    # This node never fans out, so it pulls both sources itself. Business facts
    # no longer ride along in the system prompt (see prompts._business_info_block),
    # and the shared embedding makes the second lookup effectively free.
    query_vec = await embed(last_message_text(state))
    faq_items, info_items = await asyncio.gather(
        vector_search_faq(state["shop_id"], query_vec, FAQ_K),
        vector_search_shop_info(state["shop_id"], query_vec, SHOP_INFO_K),
    )

    context = "\n\n".join(i["content"] for i in faq_items + info_items)
    context_block = f"## اطلاعات مرتبط:\n{context}\n\n" if context else ""

    # Only nudge the model to ask a clarifying question when the request is
    # actually ambiguous; a clear question should just be answered.
    clarify_instruction = (
        "درخواست مشتری ناقص یا مبهم است. به‌جای پاسخ کامل، فقط یک سوال کوتاه و مشخص بپرس "
        "تا نیازش روشن شود (مثلاً نوع، کاربرد، بودجه یا سایز). از اطلاعات بالا فقط برای هدفمندتر "
        "کردن سوالت استفاده کن، نه برای دادن پاسخ کامل."
    )
    if state.get("out_of_catalog"):
        # Never interrogate a customer about a category we don't stock. The
        # agent used to say "we have no flashlights" and then ask what kind of
        # flashlight they wanted.
        categories = await shop_categories(state["shop_id"])
        available = "، ".join(categories) if categories else ""
        extra = (
            "فروشگاه این نوع محصول را ندارد. صریح و کوتاه بگو که موجود نیست و "
            "هیچ سوال تکمیلی درباره همان محصول نپرس."
            + (f" دسته‌های موجود فروشگاه: {available}. یکی از این‌ها را پیشنهاد بده."
               if available else "")
        )
    elif state.get("intent") == "needs_clarification":
        extra = clarify_instruction
    else:
        extra = ""

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_block + extra, state.get("summary"))
    )

    return {"messages": [reply]}


async def smalltalk_reply(state: SalesAgentState) -> dict:
    """Greetings and acknowledgements: answer from the persona alone."""
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    reply = await llm.ainvoke(
        build_llm_messages(
            system_prompt,
            state["messages"],
            "مشتری فقط احوال‌پرسی یا تعارف کرده است. کوتاه و گرم پاسخ بده و "
            "بپرس دنبال چه چیزی است. هیچ محصولی پیشنهاد نده و لیست نساز.",
            state.get("summary"),
        )
    )
    # No retrieval ran, so nothing new was shown; leave shown_products intact.
    return {"messages": [reply], "retrieved_context": []}


# The closing move for each way a customer can be engaged with what is already
# on the table. Buying, objecting and comparing are one turn shape — no
# retrieval, same product list, one LLM call — and differ only in what the
# agent should do next, so they share a node and pick an instruction here.
CLOSING_MOVES = {
    "buy": (
        "مشتری آماده خرید است. لینک خرید را بده و او را تشویق کن."
    ),
    "compare": (
        "مشتری می‌خواهد بین همین گزینه‌ها انتخاب کند. تفاوت‌های واقعی آن‌ها را فقط بر اساس "
        "همین اطلاعات کوتاه و روشن بگو و با توجه به نیازی که تا حالا گفته یکی را پیشنهاد کن. "
        "لینک خرید را فقط وقتی بده که خودش خواسته باشد."
    ),
    "price": (
        "مشتری قیمت را بالا می‌داند. اول ارزش همین محصول را با دلیل مشخص توضیح بده. "
        "محصول دیگری پیشنهاد نده مگر خودش بخواهد، و برای فروش فشار نیاور."
    ),
    "uncertainty": (
        "مشتری مطمئن نیست این گزینه مناسبش است. فقط بر اساس همین اطلاعات به تردیدش پاسخ بده. "
        "اگر چیزی لازم است که در اطلاعات بالا نیست، از خودت نساز و کوتاه بپرس."
    ),
    "delay": (
        "مشتری می‌خواهد فکر کند. به او فرصت بده، هیچ فشاری برای خرید نیاور و محصول جدیدی "
        "پیشنهاد نده. کوتاه بگو برای هر سوالی در خدمتی."
    ),
}


def _closing_move(state: SalesAgentState) -> str:
    if state.get("intent") == "compare":
        return "compare"
    if state.get("intent") == "objection":
        return state.get("objection") or "uncertainty"
    return "buy"


# Only the "buy" move wants the client to render buy buttons. Telling the model
# to give the customer space to think and then attaching five purchase buttons
# under the reply is the same pressure the instruction just forbade.
BUY_ACTION_MOVES = {"buy"}


def _product_listing(items: list[RetrievedItem]) -> str:
    """Number the products and attach a buy link where there is one.

    Products without a `productUrl` are listed too. They used to be filtered
    out, which meant a customer objecting to the price of a product that has no
    link watched it vanish from the conversation.
    """
    lines = []
    for i, p in enumerate(items, 1):
        url = (p.get("metadata") or {}).get("productUrl")
        line = f"{i}. {p['content']}"
        if url:
            line += f"\n   🛒 لینک خرید: {url}"
        lines.append(line)
    return "\n\n".join(lines)


async def handle_purchase(state: SalesAgentState) -> dict:
    """Close from the products already on the table.

    Buying, objecting and comparing all mean the same thing structurally: the
    customer is engaged with what was shown, wants nothing new retrieved, and
    needs one more thing before deciding. Only the closing move differs.
    """
    shop = await db.shop.find_unique(where={"id": state["shop_id"]})
    system_prompt = build_system_prompt(shop) if shop else ""

    # A pinned product is what the turn is about; otherwise it is the whole list
    # the customer is looking at. The list is already capped upstream by
    # EXPLORE_CONTEXT_LIMIT, so it is not truncated again here — cutting it to
    # three made a comparison silently ignore half the options on screen.
    pinned = await _pinned_product(state)
    items = [pinned] if pinned else list(state.get("shown_products") or [])
    move = _closing_move(state)

    if items:
        context_prompt = (
            f"{CLOSING_MOVES[move]}\n\n"
            "محصولاتی که مشتری درباره‌شان صحبت می‌کند:\n"
            f"{_product_listing(items)}\n\n"
            "⚠️ هیچ محصول یا لینک دیگری ننویس — حتی محصولی که قبلاً در گفتگو نام برده شده "
            "ولی اینجا نیست. اگر مطمئن نیستی مشتری کدام‌یک را می‌خواهد، کوتاه بپرس."
        )
    else:
        # Nothing on the table yet — ask instead of guessing.
        context_prompt = (
            "مشتری قصد خرید دارد اما هنوز محصول مشخصی انتخاب نشده است. "
            "کوتاه بپرس کدام محصول را می‌خواهد یا یک محصول مرتبط پیشنهاد بده."
        )

    reply = await llm.ainvoke(
        build_llm_messages(system_prompt, state["messages"], context_prompt, state.get("summary"))
    )

    # Without retrieved_context the API returned no products and no purchaseUrl
    # on the single most commercially important turn: analyze_intent clears it at
    # the start of every turn, and this node never put anything back, so the
    # Telegram bot's "🛒 خرید محصول" button and product cards never rendered.
    # shown_products is deliberately left alone — only the explore path sets it.
    return {
        "messages": [reply],
        "retrieved_context": items,
        "buy_actions": move in BUY_ACTION_MOVES,
    }


# ── Graph ─────────────────────────────────────────────────────────────────────


def build_graph(checkpointer: Optional[AsyncPostgresSaver] = None):
    graph = (
        StateGraph(SalesAgentState)
        # nodes
        .add_node("maybe_summarize", maybe_summarize)
        .add_node("analyze_intent", analyze_intent)
        .add_node("fan_out_explore", fan_out_explore)
        .add_node("fan_out_product", fan_out_product)
        .add_node("sql_filter_explore", sql_filter_explore)
        .add_node("vector_search_explore", vector_search_explore)
        .add_node("vector_faq_explore", vector_faq)
        .add_node("vector_shop_info_explore", vector_shop_info)
        .add_node("sql_query_product", sql_query_product)
        .add_node("vector_search_product", vector_search_product)
        .add_node("vector_faq_product", vector_faq)
        .add_node("vector_shop_info_product", vector_shop_info)
        # defer=True is load-bearing, not a tuning knob. The branches have
        # unequal depth (the SQL→vector chain is two nodes, FAQ and shop-info
        # are one), and a plain multi-edge join only waits for the branches that
        # finished in the *same* superstep. Without defer the fuse node ran
        # twice — once on the shallow branches, again when the chain landed —
        # and so did the generation node after it, costing a second LLM call
        # per turn and answering from half the context the first time.
        .add_node("fuse_results_explore", fuse_results_explore, defer=True)
        .add_node("fuse_context_product", fuse_context_product, defer=True)
        .add_node("suggest_products", suggest_products)
        .add_node("product_agent", product_agent)
        .add_node("ask_question", ask_question)
        .add_node("handle_purchase", handle_purchase)
        .add_node("smalltalk_reply", smalltalk_reply)
        # edges
        .add_edge(START, "maybe_summarize")
        .add_edge("maybe_summarize", "analyze_intent")
        .add_conditional_edges(
            "analyze_intent",
            router_after_intent,
            [
                "fan_out_explore",
                "fan_out_product",
                "ask_question",
                "handle_purchase",
                "smalltalk_reply",
            ],
        )
        # Explore fan-out. The product lookup stays a two-step chain — the SQL
        # filter must finish before the vector search can be scoped to its
        # result — but runs *alongside* the FAQ and shop-info lookups, which
        # depend on neither. fuse_results_explore is the barrier: three incoming
        # edges, so it waits for the deepest branch.
        .add_conditional_edges(
            "fan_out_explore",
            route_fan_out_explore,
            ["sql_filter_explore", "vector_faq_explore", "vector_shop_info_explore"],
        )
        .add_edge("sql_filter_explore", "vector_search_explore")
        .add_edge("vector_search_explore", "fuse_results_explore")
        .add_edge("vector_faq_explore", "fuse_results_explore")
        .add_edge("vector_shop_info_explore", "fuse_results_explore")
        .add_edge("fuse_results_explore", "suggest_products")
        .add_edge("suggest_products", END)
        # Product fan-out: the same shape, with the pinned product loaded by
        # step 1 of the chain.
        .add_conditional_edges(
            "fan_out_product",
            route_fan_out_product,
            ["sql_query_product", "vector_faq_product", "vector_shop_info_product"],
        )
        .add_edge("sql_query_product", "vector_search_product")
        .add_edge("vector_search_product", "fuse_context_product")
        .add_edge("vector_faq_product", "fuse_context_product")
        .add_edge("vector_shop_info_product", "fuse_context_product")
        .add_edge("fuse_context_product", "product_agent")
        .add_edge("product_agent", END)
        # terminal nodes
        .add_edge("ask_question", END)
        .add_edge("handle_purchase", END)
        .add_edge("smalltalk_reply", END)
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
