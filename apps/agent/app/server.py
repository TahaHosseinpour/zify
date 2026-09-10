from contextlib import asynccontextmanager
from collections import Counter
import os
import time
import traceback
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .db import db
from .graph import build_graph
from .state import RetrievedItem
from .tracing import chat_config, flush as flush_tracing


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


@app.post("/chat")
async def chat(request: Request):
    try:
        body = await request.json()
        shop_id = body.get("shopId")
        thread_id = body.get("threadId")
        message = body.get("message")
        mode = body.get("mode") or "explore"
        product_id = body.get("productId")
        want_debug = bool(body.get("debug"))

        if not shop_id or not thread_id or not message:
            return JSONResponse(
                {"error": "shopId, threadId, message are required"}, status_code=400
            )

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
            chat_config(thread_id, shop_id, mode, product_id),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        messages = result.get("messages") or []
        last = messages[-1] if messages else None
        reply = last.content if last is not None and isinstance(last.content, str) else ""

        context: list[RetrievedItem] = result.get("retrieved_context", [])
        product_items = [i for i in context if i["type"] == "product"]
        product_ids = [i["id"] for i in product_items]

        def _to_float(v):
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

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

        response = {
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

        if want_debug:
            response["debug"] = build_debug(result, path, node_updates, latency_ms)

        return response
    except Exception as err:  # noqa: BLE001
        print(f"[agent] error: {err}")
        traceback.print_exc()
        return JSONResponse({"error": "internal error"}, status_code=500)
