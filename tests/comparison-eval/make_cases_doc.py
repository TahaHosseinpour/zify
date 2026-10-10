"""Write the Persian documents that list every benchmark scenario.

    apps\\agent\\.venv\\Scripts\\python.exe tests/comparison-eval/make_cases_doc.py

Produces CASES_FA.md (the first shop) and CASES_BEAUTY_FA.md (the second) from
scenarios.py and scenarios_beauty.py, so the documents cannot drift from what is
run. Calls no model.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "apps" / "agent"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def described(check) -> list[str]:
    """The labels a code check was built with (its `what` arguments), read out
    of its closure - the checks are small factories."""
    found: list[str] = []

    def walk(fn, depth=0):
        if depth > 4 or not getattr(fn, "__closure__", None):
            return
        for name, cell in zip(fn.__code__.co_freevars, fn.__closure__):
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(value, str) and name in ("what", "label", "why", "message"):
                found.append(value)
            elif callable(value):
                walk(value, depth + 1)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if callable(item):
                        walk(item, depth + 1)

    walk(check)
    return list(dict.fromkeys(found))


def document(scenarios, shop_line: str, judge_line: str, results_dir: str) -> str:
    lines = [
        "# سناریوهای ارزیابی مقایسه‌ای زیفای",
        "",
        "این سند از روی کد سناریوها ساخته شده (`tests/comparison-eval/make_cases_doc.py`) و هر سناریویی را که "
        "چهار رویکرد (RAG ساده، RAG با فیلتر SQL، گراف زیفای با طبقه‌بند LLM، گراف زیفای با Jev) روی آن "
        "سنجیده می‌شوند فهرست می‌کند.",
        "",
        shop_line,
        "- **سناریوی قطعی:** پاسخ نهایی با یک شرط برنامه‌نویسی‌شده سنجیده می‌شود.",
        judge_line,
        "- در گفت‌وگوهای چندنوبتی فقط پاسخ آخر سنجیده می‌شود؛ نوبت‌های قبلی زمینه‌اند.",
        f"- نتایج نهایی: [`{results_dir}/comparison.csv`]({results_dir}/comparison.csv) (قبول/رد هر سناریو برای هر "
        f"چهار رویکرد) و [`{results_dir}/results.csv`]({results_dir}/results.csv) (پاسخ، هزینه، تاخیر و دلیل داور).",
        "",
        f"تعداد: {len(scenarios)} سناریو، {sum(len(s.messages) for s in scenarios)} نوبت گفت‌وگو، "
        f"{sum(1 for s in scenarios if s.check)} قطعی و {sum(1 for s in scenarios if not s.check)} داوری‌شده.",
        "",
    ]
    group = None
    for s in scenarios:
        if s.group != group:
            group = s.group
            lines += [f"## {group}", ""]
        lines += [f"### {s.id} — {s.title}", "", f"نوع سنجش: {s.kind}", "", "پیام‌های مشتری:", ""]
        lines += [f"{i}. «{m}»" for i, m in enumerate(s.messages, 1)]
        lines.append("")
        if s.check:
            labels = described(s.check)
            if labels:
                lines += ["شرط قبولی (بررسی با کد):", ""] + [f"- {label}" for label in labels]
            else:
                lines.append("شرط قبولی: با کد بررسی می‌شود (تابع `check` همین سناریو در کد سناریوها).")
            lines.append("")
        else:
            lines += ["معیارهای قبولی (داوری):", ""]
            lines += [row.strip() for row in s.rubric.split("\n") if row.strip()]
            lines.append("")
            if s.ideal:
                lines += [f"نمونه پاسخ مطلوب: {s.ideal}", ""]
            if s.reference:
                lines += ["اطلاعاتی که به داور داده می‌شود (نه کل کاتالوگ):", "", "```", s.reference, "```", ""]
    return "\n".join(lines)


def main() -> None:
    import scenarios
    import scenarios_beauty

    (HERE / "CASES_FA.md").write_text(
        document(
            scenarios.SCENARIOS,
            "- **فروشگاه نمونه:** ۴۰ محصول از ۱۹ برند در ۵ دسته، ۲ پرسش متداول و ۲ قطعه اطلاعات فروشگاه "
            "(`tests/comparison-eval/dataset.py`).",
            "- **سناریوی داوری‌شده:** یک مدل داور (DeepSeek v4.1 flash) پاسخ نهایی را با معیارهای همان سناریو و "
            "کل کاتالوگ فروشگاه می‌سنجد (`tests/comparison-eval/judging.py`).",
            "results/sports-shop",
        ),
        encoding="utf-8",
    )
    (HERE / "CASES_BEAUTY_FA.md").write_text(
        document(
            scenarios_beauty.SCENARIOS,
            "- **فروشگاه نمونه:** ۳۰۰ محصول از ۱۱۹ برند در ۵ دسته و ۳۰ نوع کالا، از هر نوع ده محصول با قیمت "
            "متفاوت؛ ۳ پرسش متداول و ۲ قطعه اطلاعات فروشگاه (`tests/comparison-eval/dataset_beauty.py`).",
            "- **سناریوی داوری‌شده:** یک مدل داور (DeepSeek v4.1 flash) پاسخ نهایی را با معیارهای همان سناریو می‌سنجد. "
            "داور کاتالوگ را نمی‌بیند: فقط محصولات همان سناریو (پاسخ درست و آنچه نباید جایگزین شود) و "
            "سیاست‌های فروشگاه را دریافت می‌کند و معیار قبولی می‌گوید کدام محصول باید معرفی شود.",
            "results/beauty-shop",
        ),
        encoding="utf-8",
    )
    print("written CASES_FA.md and CASES_BEAUTY_FA.md")


if __name__ == "__main__":
    main()
