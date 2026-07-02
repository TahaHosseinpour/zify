from contextlib import asynccontextmanager
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .db import db
from .graph import build_graph
from .state import RetrievedItem


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()

    async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as checkpointer:
        await checkpointer.setup()
        app.state.graph = build_graph(checkpointer)
        yield

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


@app.post("/chat")
async def chat(request: Request):
    try:
        body = await request.json()
        shop_id = body.get("shopId")
        thread_id = body.get("threadId")
        message = body.get("message")
        mode = body.get("mode") or "explore"
        product_id = body.get("productId")

        if not shop_id or not thread_id or not message:
            return JSONResponse(
                {"error": "shopId, threadId, message are required"}, status_code=400
            )

        graph = request.app.state.graph
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=message)],
                "shop_id": shop_id,
                "mode": mode,
                "product_id": product_id,
            },
            {"configurable": {"thread_id": thread_id}},
        )

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

        purchase_url = next(
            (p["productUrl"] for p in products if p["productUrl"]),
            None,
        )

        return {
            "reply": reply,
            "mode": result.get("mode"),
            "stage": result.get("stage"),
            "intent": result.get("intent"),
            "valueDriver": result.get("value_driver"),
            "objection": result.get("objection"),
            "suggestedProductIds": product_ids,
            "products": products,
            "purchaseUrl": purchase_url,
        }
    except Exception as err:  # noqa: BLE001
        print(f"[agent] error: {err}")
        traceback.print_exc()
        return JSONResponse({"error": "internal error"}, status_code=500)
