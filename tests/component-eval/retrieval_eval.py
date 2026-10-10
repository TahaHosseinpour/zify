"""Retrieval on its own: which products each system puts in front of the reply
model, per kind of request and per embedding model.

    apps\\agent\\.venv\\Scripts\\python.exe tests/component-eval/retrieval_eval.py

    --list                 show the requests and their right answers, call nothing
    --only N01,P03         run just these requests
    --retrievers vector    run just these (vector, rule_sql, graph_llm, graph_jev)
    --spaces gemini        run just these embedding models (openai, gemini)
    --out <dir>            where to write the CSVs

Every request of retrieval_set.py is given to four retrievers, and what comes
back is compared with the products that answer it:

    vector     the six nearest rows to the message (simple RAG)
    rule_sql   price and brand read off the message by text rules, applied as
               a SQL filter, then the six nearest rows (RAG with a SQL filter)
    graph_llm  the production graph up to the point where the reply would be
    graph_jev  written, with the LLM classifier and with Jev

The graph is run with its reply nodes replaced by empty ones, so the cost of a
graph row is one classification and one search; no reply is generated and no
judge is involved. Each retriever is run once per embedding model, with the
other model switched off for the duration.

Written:

    retrieval_results.csv   one row per request per retriever per embedding model
    retrieval_by_kind.csv   the measures per kind of request
    retrieval_summary.csv   the measures over all requests
    run.log                 everything printed, without colour

Every row also carries the time the retrieval took and what it cost in dollars
(embedding, plus the classification for the two graph retrievers).

Measures, each averaged over requests: first result right (hit@1), a right
result among the first three (hit@3), share of the right products found
(recall, out of at most six), share of the returned products that are right
(precision), reciprocal rank of the first right result (MRR), and, for
requests the shop has nothing for, how often nothing was returned.

About 170 Jev requests, 85 LLM calls and a few hundred embedding calls; five to
eight minutes.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from statistics import mean

import common
from retrieval_set import KIND_LABELS_FA, KINDS, QUERIES, Query

RETRIEVERS = ["vector", "rule_sql", "graph_llm", "graph_jev"]
RETRIEVER_LABELS = {
    "vector": "RAG ساده",
    "rule_sql": "RAG با فیلتر SQL",
    "graph_llm": "گراف با طبقه‌بند LLM",
    "graph_jev": "گراف با Jev",
}
SPACES = ["openai", "gemini"]
K = 6
ATTEMPTS = 3
# The nodes that write a reply. Replaced by empty ones: this evaluation stops
# at what the reply model would have been shown.
REPLY_NODES = ["suggest_products", "product_agent", "ask_question", "handle_purchase", "smalltalk_reply", "decline_reply"]

MEASURES = ["hit_at_1", "hit_at_3", "recall", "precision", "mrr"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--retrievers", default="")
    parser.add_argument("--spaces", default="")
    parser.add_argument("--out", default="")
    return parser.parse_args()


def _key(product_id: str) -> str:
    from dataset import ID_PREFIX

    return product_id.removeprefix(ID_PREFIX)


async def _silent(_state) -> dict:
    return {}


class Retrievers:
    def __init__(self, shop_id: str) -> None:
        import systems

        self.shop_id = shop_id
        self.rule_sql_system = systems.RagWithSql(shop_id)
        # Set per request by the caller: counts the LLM classifier's tokens.
        self.callbacks: list = []

    async def vector(self, query: Query) -> tuple[list[str], str]:
        from app import graph as G

        rows = await G.vector_search_products(self.shop_id, await G.embed(query.text), K)
        return [_key(r["id"]) for r in rows], ""

    async def rule_sql(self, query: Query) -> tuple[list[str], str]:
        from app import graph as G

        state = await self.rule_sql_system.start()
        rows = await self.rule_sql_system.retrieve_products(state, query.text, await G.embed(query.text))
        return [_key(r["id"]) for r in rows], str(state["filters"] or "")

    async def _graph(self, query: Query, classifier: str) -> tuple[list[str], str]:
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import InMemorySaver

        from app import graph as G

        os.environ["INTENT_CLASSIFIER"] = classifier
        originals = {name: getattr(G, name) for name in REPLY_NODES}
        for name in REPLY_NODES:
            setattr(G, name, _silent)
        try:
            final = await G.build_graph(InMemorySaver()).ainvoke(
                {"messages": [HumanMessage(content=query.text)], "shop_id": self.shop_id, "mode": "explore", "product_id": None},
                {
                    "configurable": {"thread_id": f"{self.shop_id}:retrieval:{classifier}:{time.time_ns()}"},
                    "callbacks": self.callbacks,
                },
            )
        finally:
            for name, node in originals.items():
                setattr(G, name, node)
        products = [i for i in final.get("retrieved_context") or [] if i["type"] == "product"]
        filters = {k: v for k, v in (final.get("explore_filters") or {}).items() if k != "query"}
        return [_key(p["id"]) for p in products], f"{final.get('intent')} {filters or ''}".strip()

    async def graph_llm(self, query: Query) -> tuple[list[str], str]:
        return await self._graph(query, "llm")

    async def graph_jev(self, query: Query) -> tuple[list[str], str]:
        return await self._graph(query, "jev")


def _score(query: Query, returned: list[str]) -> dict:
    if not query.relevant:
        return {"abstained": int(not returned)}
    right = [key in query.relevant for key in returned]
    first = next((rank for rank, ok in enumerate(right, 1) if ok), None)
    return {
        "hit_at_1": int(bool(right[:1]) and right[0]),
        "hit_at_3": int(any(right[:3])),
        "recall": round(min(1.0, len(query.relevant & set(returned)) / min(len(query.relevant), K)), 3),
        "precision": round(sum(right) / len(returned), 3) if returned else 0.0,
        "mrr": round(1 / first, 3) if first else 0.0,
    }


def _aggregate(rows: list[dict], space: str, retriever: str, kind: str | None) -> dict | None:
    mine = [r for r in rows if r["space"] == space and r["retriever"] == retriever and (kind is None or r["kind"] == kind)]
    if not mine:
        return None
    answerable = [r for r in mine if r["kind"] != "absent"]
    absent = [r for r in mine if r["kind"] == "absent"]
    return {
        "embedding_model": space,
        "retriever": retriever,
        "retriever_fa": RETRIEVER_LABELS[retriever],
        **({} if kind is None else {"kind": kind, "kind_fa": KIND_LABELS_FA[kind]}),
        "requests": len(mine),
        **{f"{m}_percent": round(100 * mean(r[m] for r in answerable), 1) if answerable else "" for m in MEASURES},
        "avg_returned": round(mean(r["returned_count"] for r in mine), 2),
        "nothing_returned_when_absent_percent": common.percent(sum(r["abstained"] for r in absent), len(absent)),
        "avg_seconds": round(mean(r["seconds"] for r in mine), 3),
        "avg_cost_usd": round(mean(r["cost_usd"] for r in mine), 7),
        "total_cost_usd": round(sum(r["cost_usd"] for r in mine), 6),
    }


async def main() -> int:
    args = _parse_args()
    wanted = {s.strip().upper() for s in args.only.split(",") if s.strip()}
    queries = [q for q in QUERIES if not wanted or q.id in wanted]
    retrievers = [r.strip() for r in args.retrievers.split(",") if r.strip()] or RETRIEVERS
    spaces = [s.strip() for s in args.spaces.split(",") if s.strip()] or SPACES
    if args.list:
        for q in QUERIES:
            print(f"  {q.id}  {q.kind:7s} {q.text}  ->  {sorted(q.relevant) or 'nothing'}")
        print(f"\n{len(QUERIES)} requests: " + ", ".join(f"{k} {sum(1 for q in QUERIES if q.kind == k)}" for k in KINDS))
        return 0
    if not queries or any(r not in RETRIEVERS for r in retrievers) or any(s not in SPACES for s in spaces):
        print("nothing to run: check --only, --retrievers and --spaces")
        return 2

    common.load_environment()
    import console as c

    out = common.out_dir(args.out, "retrieval")
    c.log_to(out / "run.log")
    classifier_before = os.environ.get("INTENT_CLASSIFIER")
    if not await common.providers_ready():
        return 3

    import store
    from app import graph as G
    from app.db import db

    by_name = {space.name: space for space, _client in G._embedding_chain()}
    up = [name for name in spaces if name in by_name and G._embedding_breaker(by_name[name]).available()]
    for name in spaces:
        if name not in up:
            print(f"  embedding model {name} is not configured or not answering - left out")
    if not up:
        return 3

    from app import metering
    from systems import Usage, _LLMUsage

    await db.connect()
    rows: list[dict] = []
    try:
        print("seeding the sample shop into the local database ...", flush=True)
        shop_id = await store.seed()
        run = Retrievers(shop_id)
        for space in up:
            # One embedding model at a time: the others are switched off, so
            # every query of this pass is embedded by this one.
            for name in by_name:
                (common.switch_on if name == space else common.switch_off)(f"{name}-embedding")
            for index, query in enumerate(queries, 1):
                for retriever in retrievers:
                    G.clear_embed_caches()
                    for attempt in range(1, ATTEMPTS + 1):
                        # Time and cost are those of the attempt that answered.
                        usage, meter = Usage(), metering.start_turn()
                        run.callbacks = [_LLMUsage(usage)]
                        started = time.perf_counter()
                        try:
                            returned, note = await getattr(run, retriever)(query)
                            break
                        except Exception as exc:  # noqa: BLE001 - retried, then recorded
                            if attempt == ATTEMPTS:
                                returned, note = [], f"error: {type(exc).__name__}: {exc}"
                            else:
                                common.switch_on(f"{space}-embedding")
                                await asyncio.sleep(3 * attempt)
                    seconds = round(time.perf_counter() - started, 3)
                    usage.jev_tokens = meter.jev_tokens
                    usage.embedding_tokens = meter.embedding_tokens
                    usage.fallback_embedding_tokens = meter.fallback_embedding_tokens
                    rows.append({
                        "space": space, "retriever": retriever, "query_id": query.id, "kind": query.kind,
                        "query": query.text, "relevant": " ".join(sorted(query.relevant)),
                        "returned": " ".join(returned), "returned_count": len(returned), "note": note,
                        "seconds": seconds, "cost_usd": round(usage.cost_usd, 7),
                        **{m: 0 for m in MEASURES}, "abstained": 0, **_score(query, returned),
                    })  # fmt: skip
                    row = rows[-1]
                    if note.startswith("error"):
                        outcome = c.red(note[:90])
                    elif not query.relevant:
                        outcome = c.verdict(not returned, "NONE  ", "SHOWN ") + c.grey(" (nothing should be returned)")
                    else:
                        outcome = c.verdict(bool(row["hit_at_1"]), "TOP-1 ", "MISS-1") + f" recall {row['recall']:.2f} precision {row['precision']:.2f}"
                    print(
                        f"{c.grey(f'[{space:6s} {index:>2d}/{len(queries)}]')} {query.id:4s} {retriever:9s} "
                        f"{seconds:>7.3f}s {c.money(row['cost_usd']):>12s}  {outcome}  {c.grey(' '.join(returned) or '-')}",
                        flush=True,
                    )
                common.write_csv(
                    out / "retrieval_results.csv",
                    ["space", "retriever", "query_id", "kind", "query", "relevant", "returned", "returned_count",
                     *MEASURES, "abstained", "seconds", "cost_usd", "note"],
                    rows,
                )  # fmt: skip
    finally:
        if classifier_before is None:
            os.environ.pop("INTENT_CLASSIFIER", None)
        else:
            os.environ["INTENT_CLASSIFIER"] = classifier_before
        await store.clear()
        await db.disconnect()

    summary = [a for s in up for r in retrievers if (a := _aggregate(rows, s, r, None))]
    by_kind = [a for s in up for r in retrievers for k in KINDS if (a := _aggregate(rows, s, r, k))]
    common.write_csv(out / "retrieval_summary.csv", list(summary[0]), summary)
    common.write_csv(out / "retrieval_by_kind.csv", list(by_kind[0]), by_kind)

    c.heading("RETRIEVAL  -  averages over all requests, per embedding model and retriever")
    print(
        f"{'embedding':10s}{'retriever':11s}{'hit@1':>8s}{'hit@3':>8s}{'recall':>8s}{'prec.':>8s}{'MRR':>8s}"
        f"{'none-if-absent':>16s}{'returned':>10s}{'avg s':>9s}{'avg $':>13s}{'total $':>13s}"
    )

    def cell(value, width: int) -> str:
        text = "-" if value == "" else f"{value:.1f}%"
        return " " * max(0, width - len(text)) + c.rate(value)

    for row in summary:
        print(
            f"{row['embedding_model']:10s}{row['retriever']:11s}"
            + "".join(cell(row[f"{m}_percent"], 8) for m in MEASURES)
            + cell(row["nothing_returned_when_absent_percent"], 16)
            + f"{row['avg_returned']:>10.2f}{row['avg_seconds']:>9.3f}{c.money(row['avg_cost_usd']):>13s}{c.money(row['total_cost_usd']):>13s}"
        )

    c.heading("RETRIEVAL  -  first result right (hit@1) per kind of request")
    print(f"{'embedding':10s}{'retriever':11s}" + "".join(f"{k:>9s}" for k in KINDS if k != "absent"))
    for space in up:
        for retriever in retrievers:
            cells = "".join(
                cell(next((r["hit_at_1_percent"] for r in by_kind if (r["embedding_model"], r["retriever"], r["kind"]) == (space, retriever, k)), ""), 9)
                for k in KINDS if k != "absent"
            )
            print(f"{space:10s}{retriever:11s}{cells}")
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
