"""Intent classification on its own: Jev against the LLM classifier, per intent.

    apps\\agent\\.venv\\Scripts\\python.exe tests/component-eval/intent_eval.py

    --list                 show the labelled turns, call nothing
    --only SP01,OB03       run just these turns
    --classifiers jev      run just these classifiers (jev, llm)
    --out <dir>            where to write the CSVs
    --from <dir>           rebuild every table from the intent_predictions.csv
                           of an earlier run, calling nothing
    --merge <dir>[,<dir>]  with --from: take the rows of these later runs in
                           place of the same turns (a call that failed and was
                           repeated on its own); the first file is kept as
                           intent_predictions.original.csv

The comparison benchmark scores whole conversations, so it cannot say where a
classifier is better - a wrong intent and a weak reply both end as "failed".
Here the classifier is the only thing running: each labelled turn of
intent_set.py is handed to both classifiers exactly as the graph hands it over
(graph.classify_intent), and the answer is compared with the label. Nothing is
retrieved and no reply is generated.

Written:

    intent_predictions.csv  one row per turn per classifier
    intent_per_class.csv    precision, recall and F1 of every intent
    intent_confusion.csv    labelled intent against predicted intent
    intent_slots.csv        how often each stated constraint was read correctly
    intent_summary.csv      accuracy, macro F1, latency and cost per classifier
    run.log                 everything printed, without colour

Time and dollar cost are recorded for every single call (intent_predictions.csv),
averaged per intent (intent_per_class.csv) and totalled per classifier.

About 100 Jev requests and 100 LLM calls; three to five minutes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from statistics import mean, median

import common
from intent_set import INTENT_LABELS_FA, INTENTS, ROUTE, TURNS, Turn, seller_reply, shown_products

CLASSIFIERS = ["jev", "llm"]
CLASSIFIER_LABELS = {"jev": "Jev", "llm": "LLM"}
SLOTS = ["brand", "category", "maxPrice", "minPrice", "sort", "relative_price", "selected_index", "objection"]
ATTEMPTS = 3

# The two classifiers name a few things differently; the graph treats each
# pair alike (graph.router_after_intent).
SAME_AS = {"ask_question": "needs_clarification", "off_script": "other"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--classifiers", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--from", dest="rebuild", default="", help="rebuild the tables of an earlier run; calls nothing")
    parser.add_argument("--merge", default="", help="with --from: folders of later runs whose rows replace the same turns")
    return parser.parse_args()


def _messages(turn: Turn) -> list:
    from langchain_core.messages import AIMessage, HumanMessage

    earlier = [HumanMessage(content=turn.asked_before), AIMessage(content=seller_reply(turn.shown))] if turn.shown else []
    return [*earlier, HumanMessage(content=turn.message)]


async def _ask_jev(turn: Turn, categories: list[str], brands: list[str]):
    from app import intent as jev

    return await jev.classify(
        _messages(turn),
        categories=categories,
        brands=brands,
        shown_products=shown_products(turn.shown),
        filters={},
        objection=None,
        allow_uncertain=True,
    )


async def _ask_llm(turn: Turn, categories: list[str], brands: list[str]):
    from langchain_core.messages import SystemMessage

    from app import graph as G
    from app.prompts import build_intent_analysis_prompt

    return await G.structured_llm.ainvoke(
        [SystemMessage(content=build_intent_analysis_prompt(categories)), *_messages(turn)]
    )


def _read(result) -> tuple[str, dict]:
    """The intent and constraints a classifier's answer carries."""
    filters = result.explore_filters.model_dump(exclude_none=True) if result.explore_filters else {}
    # Jev resolves the category against the shop's list itself and may return
    # several plausible ones; the LLM classifier names at most one.
    categories = result.categories if result.categories is not None else [filters.get("category")]
    return SAME_AS.get(result.intent, result.intent), {
        "brand": filters.get("brand"),
        "category": [c for c in categories if c],
        "maxPrice": filters.get("maxPrice"),
        "minPrice": filters.get("minPrice"),
        "sort": result.sort,
        "relative_price": result.relative_price,
        "selected_index": result.selected_index,
        "objection": result.objection,
    }


def _slot_matches(slot: str, wanted, got) -> bool:
    from scenarios import fold

    if slot == "category":
        return wanted in got
    if slot in ("maxPrice", "minPrice"):
        return got is not None and abs(float(got) - float(wanted)) <= 0.01 * float(wanted)
    if slot == "brand":
        return got is not None and fold(str(got)) == fold(str(wanted))
    return got == wanted


async def _classify(classifier: str, turn: Turn, categories: list[str], brands: list[str]) -> dict:
    from langchain_core.runnables.config import var_child_runnable_config

    from app import metering
    from systems import Usage, _LLMUsage

    ask = _ask_jev if classifier == "jev" else _ask_llm
    row = {
        "turn_id": turn.id, "classifier": classifier, "message": turn.message,
        "has_context": bool(turn.shown), "expected": turn.intent,
    }  # fmt: skip
    for attempt in range(1, ATTEMPTS + 1):
        usage = Usage()
        meter = metering.start_turn()
        # The LLM's token counts reach the usage handler through the run
        # config (app/failover.py merges it into every call).
        token = var_child_runnable_config.set({"callbacks": [_LLMUsage(usage)]})
        started = time.perf_counter()
        try:
            result = await ask(turn, categories, brands)
            seconds = time.perf_counter() - started
            break
        except Exception as exc:  # noqa: BLE001 - retried, then recorded as an error
            if attempt == ATTEMPTS:
                return {**row, "predicted": "error", "correct": False, "route_correct": False,
                        "seconds": "", "cost_usd": "", "error": f"{type(exc).__name__}: {exc}", "slots": {}}  # fmt: skip
            await asyncio.sleep(2 * attempt)
        finally:
            var_child_runnable_config.reset(token)

    predicted, slots = _read(result)
    usage.jev_tokens = meter.jev_tokens
    return {
        **row,
        "predicted": predicted,
        "correct": predicted == turn.intent,
        "route_correct": ROUTE.get(predicted) == ROUTE[turn.intent],
        "seconds": round(seconds, 3),
        "cost_usd": round(usage.cost_usd, 7),
        "input_tokens": usage.input_tokens + usage.jev_tokens,
        "output_tokens": usage.output_tokens,
        "error": "",
        "slots": slots,
        **{f"got_{slot}": slots[slot] for slot in SLOTS},
    }


def _avg(values: list[float], digits: int) -> float | str:
    return round(mean(values), digits) if values else ""


def _unsupported(slot: str, value, turn: Turn) -> bool:
    """True when a classifier returned a constraint that neither the message
    nor the conversation before it supports.

    A customer who says "همین رو برمی‌دارم" about the one shoe on the table
    has named neither its brand nor its position, and a classifier that
    returns both has read the conversation, not made something up.
    """
    from dataset import BY_KEY
    from scenarios import fold

    if value in (None, [], ""):
        return False
    if slot == "brand":
        on_the_table = {fold(BY_KEY[k].brand) for k in turn.shown}
        return fold(str(value)) not in on_the_table and fold(str(value)) not in fold(turn.message)
    if slot == "selected_index":
        return not 1 <= int(value) <= len(turn.shown)
    return True


def _per_class(rows: list[dict], classifier: str) -> list[dict]:
    mine = [r for r in rows if r["classifier"] == classifier]
    out = []
    for intent in INTENTS:
        of_class = [r for r in mine if r["expected"] == intent]
        support = len(of_class)
        predicted = sum(1 for r in mine if r["predicted"] == intent)
        hit = sum(1 for r in of_class if r["predicted"] == intent)
        precision = hit / predicted if predicted else 0.0
        recall = hit / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out.append({
            "classifier": classifier, "intent": intent, "intent_fa": INTENT_LABELS_FA[intent],
            "turns": support, "correct": hit, "predicted_as_this": predicted,
            "precision_percent": round(100 * precision, 1), "recall_percent": round(100 * recall, 1),
            "f1_percent": round(100 * f1, 1),
            # What classifying a turn of this intent took and cost.
            "avg_seconds": _avg([r["seconds"] for r in of_class if r["seconds"] != ""], 3),
            "avg_cost_usd": _avg([r["cost_usd"] for r in of_class if r["cost_usd"] != ""], 7),
        })  # fmt: skip
    return out


def _confusion(rows: list[dict], classifier: str) -> list[dict]:
    mine = [r for r in rows if r["classifier"] == classifier]
    columns = [*INTENTS, "error"]
    return [
        {"classifier": classifier, "expected": intent,
         **{c: sum(1 for r in mine if r["expected"] == intent and r["predicted"] == c) for c in columns}}
        for intent in INTENTS
    ]  # fmt: skip


def _slots(rows: list[dict], classifier: str, turns: dict[str, Turn]) -> list[dict]:
    mine = [r for r in rows if r["classifier"] == classifier and r["slots"]]
    out = []
    for slot in SLOTS:
        stated = [r for r in mine if slot in turns[r["turn_id"]].slots]
        right = sum(1 for r in stated if _slot_matches(slot, turns[r["turn_id"]].slots[slot], r["slots"][slot]))
        # A constraint read into a message that states none, and that the
        # conversation does not supply either (_unsupported). An objection may
        # quote the price of the product it is about, which is not an invented
        # budget, so objections are left out of this count.
        silent = [r for r in mine if slot not in turns[r["turn_id"]].slots and r["expected"] != "objection"]
        invented = sum(1 for r in silent if _unsupported(slot, r["slots"][slot], turns[r["turn_id"]]))
        out.append({
            "classifier": classifier, "slot": slot, "turns_stating_it": len(stated), "read_correctly": right,
            "read_correctly_percent": common.percent(right, len(stated)),
            "turns_not_stating_it": len(silent), "unsupported": "" if slot == "category" else invented,
        })  # fmt: skip
    return out


def _summary(rows: list[dict], classifier: str, per_class: list[dict]) -> dict:
    mine = [r for r in rows if r["classifier"] == classifier]
    timed = sorted(r["seconds"] for r in mine if r["seconds"] != "")
    costs = [r["cost_usd"] for r in mine if r["cost_usd"] != ""]
    return {
        "classifier": classifier,
        "turns": len(mine),
        "correct": sum(1 for r in mine if r["correct"]),
        "accuracy_percent": common.percent(sum(1 for r in mine if r["correct"]), len(mine)),
        "macro_f1_percent": round(mean(c["f1_percent"] for c in per_class), 1),
        "route_accuracy_percent": common.percent(sum(1 for r in mine if r["route_correct"]), len(mine)),
        "accuracy_without_context_percent": common.percent(
            sum(1 for r in mine if r["correct"] and not r["has_context"]), sum(1 for r in mine if not r["has_context"])
        ),
        "accuracy_with_context_percent": common.percent(
            sum(1 for r in mine if r["correct"] and r["has_context"]), sum(1 for r in mine if r["has_context"])
        ),
        "errors": sum(1 for r in mine if r["predicted"] == "error"),
        "avg_seconds": round(mean(timed), 3) if timed else "",
        "median_seconds": round(median(timed), 3) if timed else "",
        "p95_seconds": round(timed[min(len(timed) - 1, int(0.95 * len(timed)))], 3) if timed else "",
        "max_seconds": round(timed[-1], 3) if timed else "",
        "total_seconds": round(sum(timed), 2) if timed else "",
        "avg_cost_usd": round(mean(costs), 7) if costs else "",
        "total_cost_usd": round(sum(costs), 6) if costs else "",
        "cost_per_1000_turns_usd": round(1000 * mean(costs), 4) if costs else "",
        "avg_input_tokens": round(mean(r.get("input_tokens", 0) for r in mine), 1) if mine else "",
        "avg_output_tokens": round(mean(r.get("output_tokens", 0) for r in mine), 1) if mine else "",
    }


def _rate_cell(c, value, width: int) -> str:
    """A coloured percentage, right-aligned (padding counted without colour codes)."""
    text = "-" if value == "" else f"{value:.1f}%"
    return " " * max(0, width - len(text)) + c.rate(value)


def _print_report(classifiers: list[str], per_class: dict, slots: list[dict], summary: list[dict]) -> None:
    import console as c

    c.heading("PER INTENT  -  recall / precision / F1, and the time and cost of classifying one turn")
    print(f"{'':27s}" + "".join(f"  | {CLASSIFIER_LABELS[k]:<45s}" for k in classifiers))
    print(
        f"{'intent':21s}{'turns':>6s}"
        + "".join(f"  | {'recall':>7s}{'prec.':>8s}{'F1':>8s}{'avg s':>9s}{'avg $':>13s}" for _ in classifiers)
    )
    for i, intent in enumerate(INTENTS):
        line = f"{intent:21s}{per_class[classifiers[0]][i]['turns']:>6d}"
        for k in classifiers:
            row = per_class[k][i]
            seconds = "-" if row["avg_seconds"] == "" else f"{row['avg_seconds']:.3f}"
            line += (
                "  | "
                + _rate_cell(c, row["recall_percent"], 7)
                + _rate_cell(c, row["precision_percent"], 8)
                + _rate_cell(c, row["f1_percent"], 8)
                + f"{seconds:>9s}{c.money(row['avg_cost_usd']):>13s}"
            )
        print(line)

    c.heading("CONSTRAINTS  -  read correctly when stated; returned with nothing in the conversation to support it")
    print(f"{'constraint':17s}" + "".join(f"  | {CLASSIFIER_LABELS[k] + ' correct':>22s}{'unsupported':>13s}" for k in classifiers))
    for slot in SLOTS:
        line = f"{slot:17s}"
        for k in classifiers:
            row = next(r for r in slots if r["classifier"] == k and r["slot"] == slot)
            share = f"{row['read_correctly']}/{row['turns_stating_it']}"
            unsupported = "-" if row["unsupported"] == "" else str(row["unsupported"])
            line += f"  | {share:>13s}" + _rate_cell(c, row["read_correctly_percent"], 9) + f"{unsupported:>13s}"
        print(line)

    c.heading("SUMMARY")
    labels = [
        ("accuracy", "accuracy_percent", "rate"), ("macro F1", "macro_f1_percent", "rate"),
        ("right graph path", "route_accuracy_percent", "rate"),
        ("accuracy, first message", "accuracy_without_context_percent", "rate"),
        ("accuracy, follow-up message", "accuracy_with_context_percent", "rate"),
        ("failed calls", "errors", "plain"),
        ("avg time per turn (s)", "avg_seconds", "plain"), ("median time (s)", "median_seconds", "plain"),
        ("p95 time (s)", "p95_seconds", "plain"), ("slowest (s)", "max_seconds", "plain"),
        ("total time (s)", "total_seconds", "plain"),
        ("avg cost per turn", "avg_cost_usd", "money"), ("cost per 1000 turns", "cost_per_1000_turns_usd", "money4"),
        ("total cost of this run", "total_cost_usd", "money"),
        ("avg input tokens", "avg_input_tokens", "plain"), ("avg output tokens", "avg_output_tokens", "plain"),
    ]  # fmt: skip
    print(f"{'':30s}" + "".join(f"{CLASSIFIER_LABELS[s['classifier']]:>16s}" for s in summary))
    for label, key, kind in labels:
        line = f"{label:30s}"
        for s in summary:
            value = s[key]
            if kind == "rate":
                line += _rate_cell(c, value, 16)
            elif kind == "money":
                line += f"{c.money(value):>16s}"
            elif kind == "money4":
                line += f"{'-' if value == '' else f'${value:.4f}':>16s}"
            else:
                line += f"{str(value):>16s}"
        print(line)
    if len(summary) == 2 and all(s["avg_seconds"] not in ("", 0) and s["avg_cost_usd"] not in ("", 0) for s in summary):
        a, b = summary
        print(
            c.bold(
                f"\n{CLASSIFIER_LABELS[a['classifier']]} against {CLASSIFIER_LABELS[b['classifier']]}: "
                f"{b['avg_seconds'] / a['avg_seconds']:.1f}x as fast, "
                f"{b['avg_cost_usd'] / a['avg_cost_usd']:.1f}x as cheap per turn, "
                f"{a['accuracy_percent'] - b['accuracy_percent']:+.1f} points of accuracy"
            )
        )


PREDICTION_COLUMNS = [
    "turn_id", "classifier", "expected", "predicted", "correct", "route_correct", "has_context", "message",
    "seconds", "cost_usd", "input_tokens", "output_tokens", *[f"got_{s}" for s in SLOTS], "error",
]  # fmt: skip


def _write_tables(out, rows: list[dict], classifiers: list[str]) -> None:
    by_id = {t.id: t for t in TURNS}
    per_class = {k: _per_class(rows, k) for k in classifiers}
    common.write_csv(out / "intent_per_class.csv", list(per_class[classifiers[0]][0]), [r for k in classifiers for r in per_class[k]])
    confusion = [r for k in classifiers for r in _confusion(rows, k)]
    common.write_csv(out / "intent_confusion.csv", list(confusion[0]), confusion)
    slots = [r for k in classifiers for r in _slots(rows, k, by_id)]
    common.write_csv(out / "intent_slots.csv", list(slots[0]), slots)
    summary = [_summary(rows, k, per_class[k]) for k in classifiers]
    common.write_csv(out / "intent_summary.csv", list(summary[0]), summary)
    _print_report(classifiers, per_class, slots, summary)


def _load(path) -> list[dict]:
    """The rows of an intent_predictions.csv, with their types back."""
    import ast
    import csv

    def value(slot: str, text: str):
        if text in ("", "None"):
            return [] if slot == "category" else None
        if slot == "category":
            return ast.literal_eval(text)
        if slot in ("maxPrice", "minPrice"):
            return float(text)
        return int(text) if slot == "selected_index" else text

    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            failed = r["predicted"] == "error"
            rows.append({
                **r,
                "correct": r["correct"] == "True", "route_correct": r["route_correct"] == "True",
                "has_context": r["has_context"] == "True",
                "seconds": "" if r["seconds"] == "" else float(r["seconds"]),
                "cost_usd": "" if r["cost_usd"] == "" else float(r["cost_usd"]),
                "input_tokens": int(r["input_tokens"] or 0), "output_tokens": int(r["output_tokens"] or 0),
                "slots": {} if failed else {slot: value(slot, r[f"got_{slot}"]) for slot in SLOTS},
            })  # fmt: skip
    return rows


def _rebuild(folder: str, merge: str) -> int:
    """Rebuild the tables of an earlier run from its predictions file."""
    import shutil
    from pathlib import Path

    import console as c

    out = Path(folder)
    predictions = out / "intent_predictions.csv"
    rows = _load(predictions)
    for later in [m.strip() for m in merge.split(",") if m.strip()]:
        fresh = {(r["turn_id"], r["classifier"]): r for r in _load(Path(later) / "intent_predictions.csv")}
        replaced = [key for key in fresh if any((r["turn_id"], r["classifier"]) == key for r in rows)]
        rows = [fresh.get((r["turn_id"], r["classifier"]), r) for r in rows]
        print(f"merged {len(replaced)} row(s) from {later}: " + ", ".join(f"{t} {k}" for t, k in replaced))
    if merge:
        original = out / "intent_predictions.original.csv"
        if not original.exists():
            shutil.copyfile(predictions, original)
        common.write_csv(predictions, PREDICTION_COLUMNS, rows)
    classifiers = [k for k in CLASSIFIERS if any(r["classifier"] == k for r in rows)]
    _write_tables(out, rows, classifiers)
    print(f"\nresults: {out}")
    return 0


async def main() -> int:
    import console as c

    args = _parse_args()
    if args.rebuild:
        return _rebuild(args.rebuild, args.merge)
    wanted = {s.strip().upper() for s in args.only.split(",") if s.strip()}
    turns = [t for t in TURNS if not wanted or t.id in wanted]
    classifiers = [k.strip() for k in args.classifiers.split(",") if k.strip()] or CLASSIFIERS
    if args.list:
        for t in TURNS:
            print(f"  {t.id}  {t.intent:20s} {'follow-up' if t.shown else '         '}  {t.message}  {t.slots or ''}")
        print(f"\n{len(TURNS)} turns: " + ", ".join(f"{i} {sum(1 for t in TURNS if t.intent == i)}" for i in INTENTS))
        return 0
    if not turns or any(k not in CLASSIFIERS for k in classifiers):
        print(c.red("nothing to run: check --only and --classifiers"))
        return 2

    common.load_environment()
    from dataset import CATEGORIES, PRODUCTS

    out = common.out_dir(args.out, "intent")
    c.log_to(out / "run.log")
    if not await common.providers_ready():
        return 3
    brands = sorted({p.brand for p in PRODUCTS})

    c.heading(f"INTENT CLASSIFICATION  -  {len(turns)} turns x {len(classifiers)} classifiers")
    rows: list[dict] = []
    for index, turn in enumerate(turns, 1):
        for classifier in classifiers:
            row = await _classify(classifier, turn, CATEGORIES, brands)
            rows.append(row)
            if row["predicted"] == "error":
                outcome = c.red(f"ERROR  {row['error'][:90]}")
            elif row["correct"]:
                outcome = c.green(f"OK     {row['predicted']}")
            else:
                outcome = c.red(f"WRONG  expected {turn.intent}, got {row['predicted']}")
            seconds = "-" if row["seconds"] == "" else f"{row['seconds']:.3f}s"
            print(
                f"{c.grey(f'[{index:>3d}/{len(turns)}]')} {turn.id:5s} {CLASSIFIER_LABELS[classifier]:4s} "
                f"{seconds:>8s} {c.money(row['cost_usd']):>12s}  {outcome}",
                flush=True,
            )
        common.write_csv(out / "intent_predictions.csv", PREDICTION_COLUMNS, rows)

    _write_tables(out, rows, classifiers)
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
