"""Run the comparison scenarios against the real agent.

    apps\\agent\\.venv\\Scripts\\python.exe tests/comparison-eval/run_comparison.py
    ... run_comparison.py --list            # show the scenarios, call nothing
    ... run_comparison.py --only S03,S09    # run just these

Each scenario is a whole conversation through the production graph - the real
classifier, the real SQL filter and vector search over the sample shop seeded
into the local database (store.py), the real reply model. Only the last reply
is scored: by a check in code, or by the two-judge jury (judging.py).

Scenarios run one after another, never concurrently, so the timings are not
skewed by them competing for the same rate limit. Results are written after
every scenario to reports/comparison-eval/<timestamp>/results.json (gitignored),
so an interrupted run keeps what it finished.

This makes real, billed model calls: about two per customer message, plus two
judge calls per judged scenario.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "agent"))
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from scenarios import ORIGINAL_TWENTY, SCENARIOS, Outcome, Scenario  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    parser.add_argument("--only", default="", help="comma-separated scenario ids to run")
    return parser.parse_args()


def _list() -> None:
    for s in SCENARIOS:
        print(f"{s.id}  {s.kind:9s}  {s.group:28s}  {s.title}  ({len(s.messages)} نوبت)")


async def _run_scenario(graph, shop_id: str, scenario: Scenario) -> dict:
    """Play one conversation; return its record (not yet judged)."""
    from langchain_core.messages import HumanMessage

    from app.server import _build_chat_payload
    from app.usage import TokenUsageCallback

    usage = TokenUsageCallback()
    config = {"configurable": {"thread_id": f"{shop_id}:cmp:{scenario.id}:{time.time_ns()}"}, "callbacks": [usage]}
    mode, product_id = "explore", None
    turns, payload, final_state = [], {}, {}

    for message in scenario.messages:
        started = time.perf_counter()
        final_state = await graph.ainvoke(
            {"messages": [HumanMessage(content=message)], "shop_id": shop_id, "mode": mode, "product_id": product_id},
            config,
        )
        seconds = time.perf_counter() - started
        payload = _build_chat_payload(final_state)
        # What a client does between turns: send back the mode and pinned
        # product the agent settled on.
        mode, product_id = payload.get("mode") or "explore", payload.get("productId")
        turns.append({"customer": message, "assistant": payload["reply"], "seconds": round(seconds, 2)})

    return {
        "id": scenario.id,
        "title": scenario.title,
        "group": scenario.group,
        "kind": scenario.kind,
        "turns": turns,
        "reply": payload["reply"],
        "cards": [
            {"id": p["id"], "name": p["name"], "price": p["price"], "productUrl": p["productUrl"]}
            for p in payload["products"]
        ],
        "purchaseUrl": payload["purchaseUrl"],
        "showBuyActions": payload["showBuyActions"],
        "intent": final_state.get("intent"),
        "filters": {k: v for k, v in (final_state.get("explore_filters") or {}).items() if k != "query"},
        "filtersDropped": final_state.get("filters_dropped") or [],
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
    }


def _attachments(record: dict) -> str:
    lines = []
    for card in record["cards"]:
        price = f"{int(card['price']):,} تومان" if card["price"] is not None else "بدون قیمت"
        button = f" | دکمه خرید: {card['productUrl']}" if record["showBuyActions"] and card["productUrl"] else ""
        lines.append(f"- کارت محصول: {card['name']} | {price}{button}")
    if record["showBuyActions"] and record["purchaseUrl"]:
        lines.append(f"- دکمه «خرید محصول» زیر پیام: {record['purchaseUrl']}")
    return "\n".join(lines)


async def _score(scenario: Scenario, record: dict, catalog: str) -> None:
    outcome = Outcome(record["reply"], record["cards"], record["purchaseUrl"], record["showBuyActions"])
    if scenario.check:
        try:
            scenario.check(outcome)
            record.update(passed=True, reason="شرط تابع بررسی برقرار است")
        except AssertionError as exc:
            record.update(passed=False, reason=str(exc))
        return

    from judging import deliberate

    transcript = "\n".join(
        line
        for turn in record["turns"][:-1]
        for line in (f"مشتری: {turn['customer']}", f"فروشنده: {turn['assistant']}")
    )
    transcript = (transcript + "\n" if transcript else "") + f"مشتری: {record['turns'][-1]['customer']}"
    jury = await deliberate(catalog, transcript, record["reply"], _attachments(record), scenario.rubric, scenario.ideal)
    record.update(
        passed=jury.passed,
        judgeError=jury.errored,
        votes=[{"model": v.model, "passed": v.passed, "reasoning": v.reasoning} for v in jury.votes],
        reason=" | ".join(
            f"{v.model}: {'خطا' if v.passed is None else 'قبول' if v.passed else 'رد'} - {v.reasoning}"
            for v in jury.votes
        ),
    )


def _report(records: list[dict]) -> None:
    print("\n" + "=" * 100)
    for r in records:
        mark = "قبول" if r["passed"] else "رد  "
        cards = f"{len(r['cards'])} کارت"
        print(f"{r['id']}  {mark}  {r['kind']:9s}  {cards:7s}  {r['title']}")
        if not r["passed"]:
            print(f"      ↳ {r['reason']}")

    by_id = {r["id"]: r for r in records}
    twenty = [by_id[s.id] for s in ORIGINAL_TWENTY if s.id in by_id]
    extra = [r for r in records if not r["id"].startswith("S")]
    if twenty:
        coded = [r for r in twenty if r["kind"] == "قطعی"]
        judged = [r for r in twenty if r["kind"] != "قطعی"]
        print("\n" + "-" * 100)
        print(
            f"بیست سناریوی اصلی: {sum(r['passed'] for r in twenty)} از {len(twenty)} "
            f"(قطعی {sum(r['passed'] for r in coded)} از {len(coded)}، "
            f"داوری‌شده {sum(r['passed'] for r in judged)} از {len(judged)})"
        )
    if extra:
        print(f"سناریوهای ربط خروجی: {sum(r['passed'] for r in extra)} از {len(extra)}")
    seconds = [t["seconds"] for r in records for t in r["turns"]]
    if seconds:
        ordered = sorted(seconds)
        print(
            f"زمان هر پیام: میانگین {sum(seconds) / len(seconds):.2f}s، میانه {ordered[len(ordered) // 2]:.2f}s، "
            f"کندترین {ordered[-1]:.2f}s | توکن LLM هر گفت‌وگو: ورودی "
            f"{sum(r['inputTokens'] for r in records) // len(records)}، خروجی "
            f"{sum(r['outputTokens'] for r in records) // len(records)}"
        )
    split = [r["id"] for r in records if len({v["passed"] for v in r.get("votes", [])}) > 1]
    if split:
        print(f"اختلاف نظر داوران در: {', '.join(split)}")


async def main() -> int:
    args = _parse_args()
    if args.list:
        _list()
        return 0

    wanted = {s.strip().upper() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if not wanted or s.id in wanted]
    if not scenarios:
        print(f"no scenario matches {sorted(wanted)}")
        return 2

    # The comparison is defined on the hosted models; a laptop left on the
    # local-Ollama switch would silently measure something else.
    os.environ["USE_LOCAL_MODELS"] = "false"
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    from langgraph.checkpoint.memory import InMemorySaver

    from app import graph as G
    from app.db import db

    import store
    from dataset import catalog_as_text

    await db.connect()
    try:
        print("seeding the sample shop into the local database ...")
        shop_id = await store.seed()
        graph = G.build_graph(InMemorySaver())
        catalog = catalog_as_text()

        out_dir = REPO_ROOT / "reports" / "comparison-eval" / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        out_dir.mkdir(parents=True, exist_ok=True)
        records: list[dict] = []
        for scenario in scenarios:
            print(f"running {scenario.id}  {scenario.title} ...", flush=True)
            try:
                record = await _run_scenario(graph, shop_id, scenario)
                await _score(scenario, record, catalog)
            except Exception as exc:  # noqa: BLE001 - one broken scenario must not lose the rest
                record = {
                    "id": scenario.id, "title": scenario.title, "group": scenario.group, "kind": scenario.kind,
                    "turns": [], "reply": "", "cards": [], "purchaseUrl": None, "showBuyActions": False,
                    "inputTokens": 0, "outputTokens": 0, "passed": False,
                    "reason": f"اجرا خطا داد: {type(exc).__name__}: {exc}",
                }
            records.append(record)
            (out_dir / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

        _report(records)
        print(f"\nresults: {out_dir / 'results.json'}")
        return 0 if all(r["passed"] for r in records) else 1
    finally:
        await store.clear()
        await db.disconnect()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
