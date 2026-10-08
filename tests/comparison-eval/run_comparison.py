"""Benchmark four ways of answering a shop's customers, on the same scenarios.

    apps\\agent\\.venv\\Scripts\\python.exe tests/comparison-eval/run_comparison.py

    --list                     show the scenarios and systems, call nothing
    --only S03,D08             run just these scenarios
    --systems graph_jev        run just these systems (comma-separated keys)
    --out <dir>                where to write the CSVs (default: a timestamped
                               folder under reports/comparison-eval/)

Every scenario (scenarios.py) is played as a whole conversation through each
system (systems.py): simple RAG, RAG with a SQL filter, the production graph
without Jev, and the production graph with Jev. All four use the same sample
shop, seeded into the local database for the run and removed afterwards, the
same reply model and the same embedding model. The last reply of each
conversation is scored - in code, or by a two-judge jury that must agree.

Written as the run goes, so an interrupted run keeps what it finished:

    results.csv   one row per scenario per system: passed or not, latency,
                  cost in dollars, tokens, and the reply itself
    summary.csv   one row per system: pass rate, average latency, average cost
    results.json  the same rows with full transcripts and each judge's reasoning

Everything runs one conversation at a time, never concurrently, so no system's
timings are skewed by another competing for the same rate limit. The embedding
cache is emptied before every conversation for the same reason: otherwise the
second system to ask a question would get its embedding free.

This makes real, billed model calls - roughly 600 for a full run, which takes
around twenty minutes. Judge calls are part of the test, not of any system, and
are not counted in a system's cost.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "agent"))
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from scenarios import SCENARIOS, Outcome, Scenario  # noqa: E402

SYSTEM_KEYS = ["simple_rag", "rag_sql", "graph_llm", "graph_jev"]
SYSTEM_LABELS = {
    "simple_rag": "رگ ساده",
    "rag_sql": "رگ با وکتور و SQL",
    "graph_llm": "گراف زیفای بدون JEV",
    "graph_jev": "گراف زیفای با JEV",
}

RESULT_COLUMNS = [
    "case_id", "title", "group", "kind", "turns", "system", "system_label", "passed",
    "latency_total_s", "latency_per_message_s", "cost_usd", "input_tokens", "output_tokens",
    "jev_tokens", "embedding_tokens", "llm_calls", "cards", "reason", "reply",
]  # fmt: skip
SUMMARY_COLUMNS = [
    "system", "system_label", "cases", "passed", "pass_rate_percent", "avg_latency_per_message_s",
    "median_latency_per_message_s", "max_latency_per_message_s", "avg_latency_per_conversation_s",
    "avg_cost_per_conversation_usd", "avg_cost_per_message_usd", "total_cost_usd",
    "avg_llm_calls_per_message",
]  # fmt: skip


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="list scenarios and systems, then exit")
    parser.add_argument("--only", default="", help="comma-separated scenario ids")
    parser.add_argument("--systems", default="", help=f"comma-separated system keys ({', '.join(SYSTEM_KEYS)})")
    parser.add_argument("--out", default="", help="output directory")
    parser.add_argument(
        "--second-providers",
        action="store_true",
        help="run on the second chat and embedding providers (DEEPSEEK_BASE_URL / GEMINI_BASE_URL) "
        "even when the first ones are up - to compare with a run that was made on them",
    )
    return parser.parse_args()


def _list() -> None:
    print("systems:")
    for key in SYSTEM_KEYS:
        print(f"  {key:11s} {SYSTEM_LABELS[key]}")
    print(f"\n{len(SCENARIOS)} scenarios:")
    for s in SCENARIOS:
        print(f"  {s.id}  {s.kind:9s}  {len(s.messages)} نوبت  {s.group:26s}  {s.title}")


def _attachments(outcome: Outcome) -> str:
    lines = []
    for card in outcome.cards:
        price = f"{int(card['price']):,} تومان" if card["price"] is not None else "بدون قیمت"
        button = f" | دکمه خرید: {card['productUrl']}" if outcome.show_buy_actions and card["productUrl"] else ""
        lines.append(f"- کارت محصول: {card['name']} | {price}{button}")
    if outcome.show_buy_actions and outcome.purchase_url:
        lines.append(f"- دکمه «خرید محصول» زیر پیام: {outcome.purchase_url}")
    return "\n".join(lines)


async def _score(scenario: Scenario, outcome: Outcome, transcript: list[dict], catalog: str) -> dict:
    if scenario.check:
        try:
            scenario.check(outcome)
            return {"passed": True, "reason": "شرط تابع بررسی برقرار است", "votes": []}
        except AssertionError as exc:
            return {"passed": False, "reason": str(exc), "votes": []}

    from judging import deliberate

    earlier = "\n".join(
        line for turn in transcript[:-1] for line in (f"مشتری: {turn['customer']}", f"فروشنده: {turn['assistant']}")
    )
    conversation = (earlier + "\n" if earlier else "") + f"مشتری: {transcript[-1]['customer']}"
    jury = await deliberate(
        catalog, conversation, outcome.reply, _attachments(outcome), scenario.rubric, scenario.ideal
    )
    return {
        "passed": jury.passed,
        "votes": [{"model": v.model, "passed": v.passed, "reasoning": v.reasoning} for v in jury.votes],
        "reason": " | ".join(
            f"{v.model}: {'خطا' if v.passed is None else 'قبول' if v.passed else 'رد'} - {v.reasoning}"
            for v in jury.votes
        ),
    }


# A gateway timeout or a dropped connection says nothing about how well a
# system answers, so the conversation is simply played again from the start -
# with a fresh state, and timings and cost taken from the attempt that
# completed. Anything else (a bug, a bad response) is not retried.
TRANSIENT_ERRORS = ("InternalServerError", "APITimeoutError", "APIConnectionError", "RateLimitError",
                    "ReadTimeout", "ConnectTimeout", "ConnectError", "RemoteProtocolError")  # fmt: skip
CONVERSATION_ATTEMPTS = 3


async def _converse_with_retries(system, scenario: Scenario):
    from app import graph as G

    for attempt in range(1, CONVERSATION_ATTEMPTS + 1):
        try:
            return await system.converse(scenario.messages)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ not in TRANSIENT_ERRORS or attempt == CONVERSATION_ATTEMPTS:
                raise
            print(f"(خطای موقت {type(exc).__name__}، تلاش دوباره) ", end="", flush=True)
            await asyncio.sleep(5 * attempt)
            G._embed_cache.clear()


async def _run_one(system, scenario: Scenario, catalog: str) -> dict:
    """One scenario through one system: the CSV row, plus the full record."""
    from app import graph as G

    # No system inherits another's embeddings (see the module docstring).
    G._embed_cache.clear()
    base = {
        "case_id": scenario.id, "title": scenario.title, "group": scenario.group, "kind": scenario.kind,
        "turns": len(scenario.messages), "system": system.key, "system_label": system.label,
    }  # fmt: skip
    try:
        outcome, transcript, usage = await _converse_with_retries(system, scenario)
        verdict = await _score(scenario, outcome, transcript, catalog)
    except Exception as exc:  # noqa: BLE001 - one broken run must not lose the rest
        return {
            **base, "passed": False, "latency_total_s": "", "latency_per_message_s": "", "cost_usd": "",
            "input_tokens": 0, "output_tokens": 0, "jev_tokens": 0, "embedding_tokens": 0, "llm_calls": 0,
            "cards": 0, "reason": f"اجرا خطا داد: {type(exc).__name__}: {exc}", "reply": "",
            "transcript": [], "votes": [], "errored": True,
        }  # fmt: skip

    return {
        **base,
        "passed": verdict["passed"],
        "latency_total_s": round(sum(usage.seconds), 3),
        "latency_per_message_s": round(mean(usage.seconds), 3),
        "cost_usd": round(usage.cost_usd, 6),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "jev_tokens": usage.jev_tokens,
        "embedding_tokens": usage.embedding_tokens,
        "llm_calls": usage.llm_calls,
        "cards": len(outcome.cards),
        "reason": verdict["reason"],
        "reply": outcome.reply,
        "transcript": transcript,
        "votes": verdict["votes"],
        "message_seconds": [round(s, 3) for s in usage.seconds],
        "errored": False,
    }


def _summarise(records: list[dict], system_keys: list[str]) -> list[dict]:
    rows = []
    for key in system_keys:
        mine = [r for r in records if r["system"] == key]
        ok = [r for r in mine if not r.get("errored")]
        if not mine:
            continue
        per_message = [s for r in ok for s in r.get("message_seconds", [])]
        messages = sum(r["turns"] for r in ok)
        total_cost = sum(r["cost_usd"] for r in ok)
        rows.append(
            {
                "system": key,
                "system_label": SYSTEM_LABELS[key],
                "cases": len(mine),
                "passed": sum(1 for r in mine if r["passed"]),
                "pass_rate_percent": round(100 * sum(1 for r in mine if r["passed"]) / len(mine), 1),
                "avg_latency_per_message_s": round(mean(per_message), 3) if per_message else "",
                "median_latency_per_message_s": round(median(per_message), 3) if per_message else "",
                "max_latency_per_message_s": round(max(per_message), 3) if per_message else "",
                "avg_latency_per_conversation_s": round(mean(r["latency_total_s"] for r in ok), 3) if ok else "",
                "avg_cost_per_conversation_usd": round(total_cost / len(ok), 6) if ok else "",
                "avg_cost_per_message_usd": round(total_cost / messages, 6) if messages else "",
                "total_cost_usd": round(total_cost, 6),
                "avg_llm_calls_per_message": round(sum(r["llm_calls"] for r in ok) / messages, 2) if messages else "",
            }
        )
    return rows


def _write(out_dir: Path, records: list[dict], system_keys: list[str]) -> None:
    # utf-8-sig so Excel opens the Persian columns correctly.
    with open(out_dir / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(_summarise(records, system_keys))
    (out_dir / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_summary(records: list[dict], system_keys: list[str]) -> None:
    by_case: dict[str, dict[str, dict]] = {}
    for r in records:
        by_case.setdefault(r["case_id"], {})[r["system"]] = r

    print("\n" + "=" * 110)
    print(f"{'':6s}" + "".join(f"{key:>14s}" for key in system_keys) + "   سناریو")
    for case_id, per_system in by_case.items():
        cells = "".join(
            f"{('قبول' if per_system[k]['passed'] else 'رد') if k in per_system else '-':>14s}" for k in system_keys
        )
        print(f"{case_id:6s}{cells}   {next(iter(per_system.values()))['title']}")

    print("\n" + "-" * 110)
    for row in _summarise(records, system_keys):
        print(
            f"{row['system']:11s} قبولی {row['passed']}/{row['cases']} ({row['pass_rate_percent']}%)"
            f" | تاخیر هر پیام: میانگین {row['avg_latency_per_message_s']}s، میانه "
            f"{row['median_latency_per_message_s']}s، بیشینه {row['max_latency_per_message_s']}s"
            f" | هزینه هر گفت‌وگو: ${row['avg_cost_per_conversation_usd']}"
            f" | فراخوانی LLM هر پیام: {row['avg_llm_calls_per_message']}"
        )


PREFLIGHT_TIMEOUT_SECONDS = 25


async def _provider_is_up(second_providers: bool = False) -> bool:
    """One tiny request to each endpoint the run can use, with a short
    timeout. The model client retries and the failover waits out a timeout
    per provider, so without this an outage looks like the run crawling
    through its first steps rather than like what it is.

    Each kind of call (chat, embedding) has a first provider and, when its
    base URL is configured, a second one (app/graph.py). The run goes ahead
    when at least one of the two answers. A first provider found down here is
    switched off for the whole run - otherwise the agent would probe it again
    every half minute and a few messages would each carry a timeout, which is
    noise in a latency comparison. The run then measures the second provider
    from start to finish, and says so.

    `second_providers` switches the first provider off without asking it, so a
    run can be repeated on the same models as an earlier one that was made
    during an outage. It refuses to start unless both second providers are
    configured: silently measuring the first ones instead would defeat it.
    """
    import httpx

    from app import breaker

    key = os.environ.get("OPENAI_API_KEY", "")
    bearer = {"Authorization": f"Bearer {key}"}
    openai = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    deepseek = (os.environ.get("DEEPSEEK_BASE_URL") or "").rstrip("/")
    gemini = (os.environ.get("GEMINI_BASE_URL") or "").rstrip("/")
    chat_model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    deepseek_model = os.environ.get("DEEPSEEK_CHAT_MODEL", "deepseek-v4-flash")
    gemini_model = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    hi = [{"role": "user", "content": "hi"}]

    # kind -> [(provider, model, url, headers, body)], first provider first.
    chains: dict[str, list[tuple]] = {
        "embedding": [("openai", embedding_model, f"{openai}/embeddings", bearer, {"model": embedding_model, "input": "سلام"})],
        "chat": [("openai", chat_model, f"{openai}/chat/completions", bearer, {"model": chat_model, "messages": hi, "max_tokens": 3})],
    }  # fmt: skip
    if gemini:
        chains["embedding"].append((
            "gemini", gemini_model, f"{gemini}/models/{gemini_model}:embedContent",
            {"x-goog-api-key": os.environ.get("GEMINI_API_KEY") or key},
            {"model": f"models/{gemini_model}", "content": {"parts": [{"text": "سلام"}]}, "outputDimensionality": 8},
        ))  # fmt: skip
    if deepseek:
        chains["chat"].append((
            "deepseek", deepseek_model, f"{deepseek}/chat/completions",
            {"Authorization": f"Bearer {os.environ.get('DEEPSEEK_API_KEY') or key}"},
            {"model": deepseek_model, "messages": hi, "max_tokens": 3, "thinking": {"type": "disabled"}},
        ))  # fmt: skip

    if second_providers:
        missing = [name for name, url in (("DEEPSEEK_BASE_URL", deepseek), ("GEMINI_BASE_URL", gemini)) if not url]
        if missing:
            print(f"--second-providers needs {' and '.join(missing)} to be set. Nothing was run.")
            return False

    print("checking the model providers ...", flush=True)
    ok = True
    async with httpx.AsyncClient(timeout=PREFLIGHT_TIMEOUT_SECONDS) as client:
        for kind, chain in chains.items():
            serving = None
            for position, (provider, model, url, headers, body) in enumerate(chain):
                if second_providers and position == 0:
                    problem = None
                    print(f"  {kind}: {provider} switched off for this run (--second-providers)")
                else:
                    try:
                        response = await client.post(url, json=body, headers=headers)
                        problem = None if response.status_code == 200 else f"HTTP {response.status_code}"
                    except httpx.HTTPError as exc:
                        problem = f"no answer within {PREFLIGHT_TIMEOUT_SECONDS}s ({type(exc).__name__})"
                    if problem is None:
                        serving = (provider, model)
                        break
                    print(f"  {kind}: {provider} is down - {problem} from {url}")
                gate = breaker.breaker(f"{provider}-{kind}")
                gate.reset_seconds = float("inf")
                for _ in range(gate.failure_threshold):
                    gate.record_failure()
            if serving is None:
                ok = False
            else:
                note = "" if serving[0] == chain[0][0] else "  <- SECOND provider, not the benchmark's usual model"
                print(f"  {kind}: this run uses {serving[0]} ({serving[1]}){note}")
    if not ok:
        print("\nNo model provider is answering for one kind of call, so nothing was run. Try again in a few minutes.")
    return ok


async def main() -> int:
    args = _parse_args()
    if args.list:
        _list()
        return 0

    wanted = {s.strip().upper() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if not wanted or s.id in wanted]
    system_keys = [k.strip() for k in args.systems.split(",") if k.strip()] or SYSTEM_KEYS
    unknown = [k for k in system_keys if k not in SYSTEM_KEYS]
    if unknown or not scenarios:
        print(f"unknown system {unknown}" if unknown else f"no scenario matches {sorted(wanted)}")
        return 2

    # The benchmark is defined on the hosted models; a laptop left on the
    # local-Ollama switch would silently measure something else.
    os.environ["USE_LOCAL_MODELS"] = "false"
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    classifier_before = os.environ.get("INTENT_CLASSIFIER")

    from app.db import db

    import store
    import systems
    from dataset import catalog_as_text

    out_dir = Path(args.out) if args.out else (
        REPO_ROOT / "reports" / "comparison-eval" / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    if not await _provider_is_up(args.second_providers):
        return 3

    await db.connect()
    try:
        print("seeding the sample shop into the local database ...", flush=True)
        shop_id = await store.seed()
        catalog = catalog_as_text()
        runners = [systems.BY_KEY[key](shop_id) for key in system_keys]

        records: list[dict] = []
        for index, scenario in enumerate(scenarios, 1):
            for system in runners:
                print(f"[{index}/{len(scenarios)}] {scenario.id}  {system.key:11s} ...", end=" ", flush=True)
                record = await _run_one(system, scenario, catalog)
                records.append(record)
                _write(out_dir, records, system_keys)
                latency = record["latency_per_message_s"]
                print(
                    f"{'قبول' if record['passed'] else 'رد'}"
                    + (f"  {latency}s/پیام  ${record['cost_usd']}" if latency != "" else f"  {record['reason']}"),
                    flush=True,
                )

        _print_summary(records, system_keys)
        print(f"\nresults.csv : {out_dir / 'results.csv'}")
        print(f"summary.csv : {out_dir / 'summary.csv'}")
        print(f"results.json: {out_dir / 'results.json'}")
        return 0
    finally:
        if classifier_before is None:
            os.environ.pop("INTENT_CLASSIFIER", None)
        else:
            os.environ["INTENT_CLASSIFIER"] = classifier_before
        await store.clear()
        await db.disconnect()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
