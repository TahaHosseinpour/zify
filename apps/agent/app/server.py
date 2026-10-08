from contextlib import asynccontextmanager
from collections import Counter
import json
import os
import time
import traceback
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from . import metering
from .db import db
from .graph import build_graph
from .state import RetrievedItem
from .tracing import chat_config, flush as flush_tracing
from .usage import (
    WEEKLY_INPUT_TOKEN_LIMIT,
    TokenUsageCallback,
    UsageStatus,
    increment_input_tokens,
    usage_status,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()

    async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as checkpointer:
        await checkpointer.setup()
        app.state.graph = build_graph(checkpointer)
        yield

    flush_tracing()
    await db.disconnect()


app = FastAPI(lifespan=lifespan)

# Every model call the platform pays for runs behind this service, so only our
# own services may call it. They share this key (packages: apps/admin/lib/
# agent.ts, apps/telegram-bot). Unset means "local development": no check, and
# a loud line at startup so it is never unset in production by accident.
INTERNAL_KEY = os.environ.get("AGENT_INTERNAL_KEY")
if not INTERNAL_KEY:
    print("[agent] WARNING: AGENT_INTERNAL_KEY is not set - the API accepts any caller")

# Mirrors MAX_MESSAGE_CHARS in packages/db/src/billing.ts, which refuses longer
# messages with a friendly reply before they get here. Enforced again because
# this is where the tokens are spent.
MAX_MESSAGE_CHARS = 300


@app.middleware("http")
async def require_internal_key(request: Request, call_next):
    if INTERNAL_KEY and request.url.path != "/health":
        if request.headers.get("x-agent-key") != INTERNAL_KEY:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/health")
async def health():
    return {"ok": True}


# LangGraph's Postgres checkpointer stores conversation memory keyed by
# thread_id. Our thread ids look like "<shopId>:<endUserId>", so we can wipe
# a whole shop's conversation memory by matching that prefix.
_CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


@app.post("/admin/reset-memory")
async def reset_memory(request: Request):
    """Clear persisted conversation memory so agents re-retrieve fresh data."""
    body = await request.json()
    shop_id = body.get("shopId")
    if not shop_id:
        return JSONResponse({"error": "shopId is required"}, status_code=400)

    pattern = f"{shop_id}:%"
    deleted = 0
    for table in _CHECKPOINT_TABLES:
        try:
            deleted += await db.execute_raw(
                f'DELETE FROM {table} WHERE thread_id LIKE $1', pattern
            )
        except Exception as err:  # noqa: BLE001 — table may not exist yet
            print(f"[agent] reset-memory: skipped {table}: {err}")

    return {"ok": True, "deletedRows": deleted}


def _to_float(v) -> Optional[float]:
    """Prisma's Decimal (or a malformed value) coerced to a plain float for
    JSON, or None rather than a 500 if it isn't numeric at all."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def single_purchase_url(products: list[dict], pinned_id: Optional[str]) -> Optional[str]:
    """The one link a top-level buy button can point at, or None.

    Taking the first product that happened to have a URL meant a six-product
    answer got a "🛒 خرید محصول" button silently pointing at whichever one
    ranked first. A single link is only unambiguous when the customer pinned a
    product, or when there is only one on the table.
    """
    if pinned_id:
        return next((p["productUrl"] for p in products if p["id"] == pinned_id), None)
    if len(products) == 1:
        return products[0]["productUrl"]
    return None


async def run_graph(
    graph, input_state: dict, config: dict
) -> tuple[dict, list[str], dict]:
    """Run the graph, returning the final state, the nodes it ran, and their updates.

    Equivalent to `ainvoke` (which is itself a "values" stream), but the
    interleaved "updates" stream also tells us which branch of the graph the
    turn took — the single most useful thing when debugging routing — and lets
    us keep per-turn scratch fields (`candidate_ids`) that a later node clears
    before they ever reach the final state.
    """
    path: list[str] = []
    node_updates: dict = {}
    final: dict = {}

    async for stream_mode, chunk in graph.astream(
        input_state, config, stream_mode=["updates", "values"]
    ):
        if stream_mode == "updates":
            for node, update in chunk.items():
                if node.startswith("__"):
                    continue
                path.append(node)
                if isinstance(update, dict):
                    node_updates[node] = update
        else:
            final = chunk

    return final, path, node_updates


def build_debug(
    result: dict, path: list[str], node_updates: dict, latency_ms: int
) -> dict:
    """State-only snapshot of a turn: features and counts, never the text.

    Used by the admin playground to explain *why* the agent answered the way it
    did. Retrieved documents are reported as counts and ids so the payload
    stays small and free of catalog content.
    """
    context: list[RetrievedItem] = result.get("retrieved_context") or []
    raw: list[RetrievedItem] = result.get("retrieved_raw") or []
    shown: list[RetrievedItem] = result.get("shown_products") or []
    summary = result.get("summary")

    # The SQL pre-filter's own output: how many products cleared the customer's
    # hard constraints. A later node in the same path clears candidate_ids
    # (the step-2 node of either path), so it is gone from the
    # final state — read it off the filter node's own update instead.
    # Either path can be the one that ran the filter step — explore goes through
    # sql_filter_explore, product mode through sql_query_product.
    filter_update = (
        node_updates.get("sql_filter_explore")
        or node_updates.get("sql_query_product")
        or {}
    )

    return {
        "path": path,
        "filterStatus": result.get("filter_status"),
        "filterEffective": result.get("filter_effective") or {},
        "filtersDropped": result.get("filters_dropped") or [],
        "outOfCatalog": bool(result.get("out_of_catalog")),
        "sort": result.get("sort"),
        "candidateCount": len(filter_update.get("candidate_ids") or []),
        "intent": result.get("intent"),
        "mode": result.get("mode"),
        "stage": result.get("stage"),
        "valueDriver": result.get("value_driver"),
        "objection": result.get("objection"),
        "productId": result.get("product_id"),
        "exploreFilters": result.get("explore_filters") or {},
        "excludedProductIds": result.get("excluded_product_ids") or [],
        "shownProducts": [
            {"id": p["id"], "name": (p.get("metadata") or {}).get("name")}
            for p in shown
        ],
        "retrieved": {
            "rawCount": len(raw),
            "contextCount": len(context),
            "byType": dict(Counter(i.get("type") for i in context)),
            "scores": [round(float(i.get("score") or 0), 3) for i in context],
        },
        "messageCount": len(result.get("messages") or []),
        "hasSummary": bool(summary),
        "summaryChars": len(summary) if summary else 0,
        "latencyMs": latency_ms,
    }


def _limit_reached_reply(status: UsageStatus) -> str:
    """Which cap was hit decides which reset date to quote - a customer who
    blew through the weekly cap needs to know when *that* resets, not the
    (later) monthly one, even though both are technically true."""
    if status.weekly_used >= WEEKLY_INPUT_TOKEN_LIMIT:
        window, reset_at = "هفتگی", status.weekly_reset_at
    else:
        window, reset_at = "ماهانه", status.monthly_reset_at
    return (
        f"به سقف مصرف {window} خودتون رسیدید. "
        f"از {reset_at.strftime('%Y/%m/%d')} دوباره می‌تونید پیام بدید."
    )


def _limit_reached_response(status: UsageStatus, mode: str, product_id) -> dict:
    return {
        "reply": _limit_reached_reply(status),
        "mode": mode,
        "productId": product_id,
        "stage": None,
        "intent": None,
        "valueDriver": None,
        "objection": None,
        "suggestedProductIds": [],
        "products": [],
        "purchaseUrl": None,
        "showBuyActions": False,
    }


def _build_chat_payload(result: dict) -> dict:
    """The response shape both /chat and /chat/stream's final event share -
    everything derived from the graph's finished state. /chat/stream's
    "reply" duplicates text already delivered token-by-token via "answer"
    events; harmless, but the client should prefer the streamed text."""
    messages = result.get("messages") or []
    last = messages[-1] if messages else None
    reply = last.content if last is not None and isinstance(last.content, str) else ""

    context: list[RetrievedItem] = result.get("retrieved_context", [])
    product_items = [i for i in context if i["type"] == "product"]
    product_ids = [i["id"] for i in product_items]

    products = [
        {
            "id": i["id"],
            "name": i.get("metadata", {}).get("name"),
            "price": _to_float(i.get("metadata", {}).get("price")),
            "imageUrl": i.get("metadata", {}).get("imageUrl"),
            "productUrl": i.get("metadata", {}).get("productUrl"),
        }
        for i in product_items
    ]

    pinned_id = result.get("product_id")
    purchase_url = single_purchase_url(products, pinned_id)

    # Clients render buy buttons from this rather than guessing: a turn that
    # tells the customer to take their time must not sprout purchase buttons.
    buy_actions = result.get("buy_actions")

    return {
        "reply": reply,
        "mode": result.get("mode"),
        "productId": pinned_id,
        "stage": result.get("stage"),
        "intent": result.get("intent"),
        "valueDriver": result.get("value_driver"),
        "objection": result.get("objection"),
        "suggestedProductIds": product_ids,
        "products": products,
        "purchaseUrl": purchase_url,
        "showBuyActions": True if buy_actions is None else bool(buy_actions),
    }


@app.post("/chat")
async def chat(request: Request):
    try:
        body = await request.json()
        shop_id = body.get("shopId")
        thread_id = body.get("threadId")
        message = body.get("message")
        mode = body.get("mode") or "explore"
        product_id = body.get("productId")
        # Absent for the admin playground (shop owners testing their own bot
        # aren't a real customer and have no EndUser row) - the quota gate and
        # usage tracking below both simply skip when this is missing.
        end_user_id = body.get("endUserId")
        want_debug = bool(body.get("debug"))

        if not shop_id or not thread_id or not message:
            return JSONResponse(
                {"error": "shopId, threadId, message are required"}, status_code=400
            )
        if len(message) > MAX_MESSAGE_CHARS:
            return JSONResponse({"error": "message too long"}, status_code=413)

        if end_user_id:
            status = await usage_status(end_user_id)
            if status.over_limit:
                # Refused before spending a single token on a request we're
                # about to turn away - no graph run, no LLM call at all.
                return _limit_reached_response(status, mode, product_id)
        # Always attached: the customer quota only needs it when there is a
        # customer, but every turn is metered (metering.record_turn).
        usage_cb = TokenUsageCallback()
        meter = metering.start_turn()

        graph = request.app.state.graph
        started = time.perf_counter()
        result, path, node_updates = await run_graph(
            graph,
            {
                "messages": [HumanMessage(content=message)],
                "shop_id": shop_id,
                "mode": mode,
                "product_id": product_id,
            },
            chat_config(
                thread_id,
                shop_id,
                mode,
                product_id,
                extra_callbacks=[usage_cb],
            ),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        await metering.record_turn(
            shop_id, thread_id, usage_cb.input_tokens, usage_cb.output_tokens, meter
        )
        if end_user_id:
            await increment_input_tokens(end_user_id, usage_cb.input_tokens)

        response = _build_chat_payload(result)

        if want_debug:
            response["debug"] = build_debug(result, path, node_updates, latency_ms)

        return response
    except Exception as err:  # noqa: BLE001
        print(f"[agent] error: {err}")
        traceback.print_exc()
        return JSONResponse({"error": "internal error"}, status_code=500)


# Node names whose LLM call actually produces customer-facing text - the only
# ones /chat/stream relays token-by-token. analyze_intent's structured-output
# call and maybe_summarize's summary are real LLM calls too (same `llm`
# instance, in maybe_summarize's case), but neither is something a customer
# should see appearing token-by-token in the reply box.
_REPLY_NODES = {
    "suggest_products",
    "product_agent",
    "ask_question",
    "smalltalk_reply",
    "handle_purchase",
    "decline_reply",
}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(request: Request):
    """Same contract as /chat, but the reply streams token-by-token as
    Server-Sent Events instead of arriving as one JSON blob - built for the
    storefront's chat UI (and, with `debug: true`, the admin playground).
    `event: answer` chunks carry `{"text": "..."}` as they're generated; a
    final `event: done` carries everything /chat returns except `reply`
    (already delivered) - products, purchaseUrl, mode, etc., plus `debug`
    when requested. `event: error` on failure, same message shape as /chat's
    own error body.

    LangGraph's `stream_mode="messages"` streams token deltas from *every*
    LLM call a node makes without any change to how the nodes themselves call
    the model (they still just `await llm.ainvoke(...)`) - filtered here to
    _REPLY_NODES so the customer only ever sees the actual reply forming, not
    the intent classifier's or the summarizer's internal calls. `updates` rides
    alongside only to build `debug` (same path/node_updates run_graph tracks
    for /chat) - skipped entirely when want_debug is false, so the storefront
    pays nothing extra for it.
    """
    body = await request.json()
    shop_id = body.get("shopId")
    thread_id = body.get("threadId")
    message = body.get("message")
    mode = body.get("mode") or "explore"
    product_id = body.get("productId")
    end_user_id = body.get("endUserId")
    want_debug = bool(body.get("debug"))

    if not shop_id or not thread_id or not message:
        return JSONResponse(
            {"error": "shopId, threadId, message are required"}, status_code=400
        )
    if len(message) > MAX_MESSAGE_CHARS:
        return JSONResponse({"error": "message too long"}, status_code=413)

    async def event_stream():
        try:
            if end_user_id:
                status = await usage_status(end_user_id)
                if status.over_limit:
                    # Refused before spending a single token - no graph run.
                    yield _sse("answer", {"text": _limit_reached_reply(status)})
                    done = _limit_reached_response(status, mode, product_id)
                    done.pop("reply", None)
                    yield _sse("done", done)
                    return

            usage_cb = TokenUsageCallback()
            meter = metering.start_turn()
            graph = request.app.state.graph
            config = chat_config(
                thread_id,
                shop_id,
                mode,
                product_id,
                extra_callbacks=[usage_cb],
            )
            input_state = {
                "messages": [HumanMessage(content=message)],
                "shop_id": shop_id,
                "mode": mode,
                "product_id": product_id,
            }

            started = time.perf_counter()
            result: dict = {}
            path: list[str] = []
            node_updates: dict = {}
            stream_modes = ["messages", "values", "updates"] if want_debug else ["messages", "values"]
            async for stream_mode, chunk in graph.astream(
                input_state, config, stream_mode=stream_modes
            ):
                if stream_mode == "messages":
                    message_chunk, metadata = chunk
                    if metadata.get("langgraph_node") not in _REPLY_NODES:
                        continue
                    text = message_chunk.content
                    if text:
                        yield _sse("answer", {"text": text})
                elif stream_mode == "values":
                    result = chunk
                elif stream_mode == "updates":
                    for node, update in chunk.items():
                        if node.startswith("__"):
                            continue
                        path.append(node)
                        if isinstance(update, dict):
                            node_updates[node] = update

            await metering.record_turn(
                shop_id, thread_id, usage_cb.input_tokens, usage_cb.output_tokens, meter
            )
            if end_user_id:
                await increment_input_tokens(end_user_id, usage_cb.input_tokens)

            done = _build_chat_payload(result)
            done.pop("reply", None)
            if want_debug:
                latency_ms = int((time.perf_counter() - started) * 1000)
                done["debug"] = build_debug(result, path, node_updates, latency_ms)
            yield _sse("done", done)
        except Exception as err:  # noqa: BLE001
            print(f"[agent] stream error: {err}")
            traceback.print_exc()
            yield _sse("error", {"message": "internal error"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
