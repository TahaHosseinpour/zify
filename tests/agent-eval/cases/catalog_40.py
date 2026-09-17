"""A 40-product pool for testing fuse_results_explore / fuse_context_product's
ranking and trimming logic deterministically - no LLM call, no real
embeddings, no live DB.

`score` on a RetrievedItem stands in for the cosine distance a real vector
search would have produced. app/graph.py's own ranking code (fuse_and_rank_context,
_rank_and_trim, _drop_irrelevant, RELEVANCE_MAX_DISTANCE=0.70) is pure Python
over that number - so picking scores by hand, instead of computing them from
real embeddings, is what makes "which products should come back" a known,
checkable answer instead of something only a live DB could tell us. That's
the "gold answer" retrieval_ranking_cases.py's checks are written against.

Four buckets, 10 items each = 40 products, spanning two real query topics
(running shoes, office/gaming laptops) plus two topics a shoe or laptop query
should never surface (casual shoes, accessories) - close enough to be a
believable 40-row catalog, far enough apart to make "which ones are actually
relevant" unambiguous.
"""

from __future__ import annotations

from app.state import RetrievedItem


def product(id_: str, name: str, price: int, brand: str) -> RetrievedItem:
    """Score defaults to 0.5 - every scenario overrides it via
    pool_with_scores() to simulate that scenario's query, since real
    relevance is query-dependent and these 40 identities are reused across
    many different simulated queries."""
    return RetrievedItem(
        id=id_,
        type="product",
        score=0.5,
        content=f"محصول: {name} | قیمت: {price:,} تومان | برند: {brand}",
        metadata={"name": name, "price": price, "brand": brand, "productUrl": f"https://shop.test/{id_}"},
    )


RUNNING_SHOES = [
    product(f"shoe-run-{i}", name, price, brand)
    for i, (name, price, brand) in enumerate(
        [
            ("کفش دویدن نایک ایرزوم", 1_450_000, "نایک"),
            ("کفش دویدن آدیداس اولترابوست", 1_650_000, "آدیداس"),
            ("کفش دویدن نایک پگاسوس", 1_550_000, "نایک"),
            ("کفش دویدن آسیکس جل نیمبوس", 1_800_000, "آسیکس"),
            ("کفش دویدن نیوبالانس فرش", 1_700_000, "نیوبالانس"),
            ("کفش دویدن پوما ولوسیتی", 1_250_000, "پوما"),
            ("کفش دویدن نایک زوم فلای", 2_100_000, "نایک"),
            ("کفش دویدن آدیداس سولار گلاید", 1_500_000, "آدیداس"),
            ("کفش دویدن آسیکس گل کایانو", 1_900_000, "آسیکس"),
            ("کفش دویدن سالامون سنس", 2_300_000, "سالامون"),
        ]
    )
]

CASUAL_SHOES = [
    product(f"shoe-casual-{i}", name, price, brand)
    for i, (name, price, brand) in enumerate(
        [
            ("کفش رسمی چرم مردانه", 1_100_000, "بلوط"),
            ("کفش کژوال پوما اسمش", 980_000, "پوما"),
            ("کفش کلاسیک آکسفورد", 1_300_000, "بلوط"),
            ("کفش لوفر چرم", 1_150_000, "بلوط"),
            ("کفش کتانی روزمره ریباک", 890_000, "ریباک"),
            ("کفش صندل تابستانی", 450_000, "ایگل"),
            ("کفش بوت زمستانی", 1_600_000, "کاترپیلار"),
            ("کفش راحتی خانگی", 350_000, "ایگل"),
            ("کفش مجلسی زنانه", 1_050_000, "بلوط"),
            ("کفش طبی راحتی", 1_400_000, "ریباک"),
        ]
    )
]

OFFICE_LAPTOPS = [
    product(f"laptop-{i}", name, price, brand)
    for i, (name, price, brand) in enumerate(
        [
            ("لپ‌تاپ اداری لنوو ثینک‌پد", 21_500_000, "لنوو"),
            ("لپ‌تاپ اداری ایسوس ExpertBook", 19_800_000, "ایسوس"),
            ("لپ‌تاپ اداری اچ‌پی پروبوک", 22_300_000, "اچ‌پی"),
            ("لپ‌تاپ دانشجویی ایسوس ویووبوک", 16_500_000, "ایسوس"),
            ("لپ‌تاپ گیمینگ ایسوس TUF", 42_000_000, "ایسوس"),
            ("لپ‌تاپ گیمینگ لنوو لیجن", 45_000_000, "لنوو"),
            ("لپ‌تاپ اداری دل لتیتود", 24_000_000, "دل"),
            ("لپ‌تاپ اولترابوک ایسوس زنبوک", 28_500_000, "ایسوس"),
            ("لپ‌تاپ دانشجویی لنوو آیدیاپد", 15_200_000, "لنوو"),
            ("لپ‌تاپ گیمینگ اچ‌پی امن", 38_000_000, "اچ‌پی"),
        ]
    )
]

ACCESSORIES = [
    product(f"acc-{i}", name, price, brand)
    for i, (name, price, brand) in enumerate(
        [
            ("کیف چرم مردانه", 890_000, "بلوط"),
            ("کوله پشتی سفری", 1_200_000, "دیوتر"),
            ("ساعت مچی کلاسیک", 3_400_000, "کاسیو"),
            ("عینک آفتابی", 750_000, "ری‌بن"),
            ("کمربند چرم", 320_000, "بلوط"),
            ("جوراب ورزشی بسته ۳تایی", 180_000, "نایک"),
            ("کلاه آفتابی", 220_000, "پوما"),
            ("دستکش ورزشی", 260_000, "آدیداس"),
            ("پاوربانک ۲۰۰۰۰", 890_000, "انکر"),
            ("هدفون بی‌سیم", 1_450_000, "سونی"),
        ]
    )
]

ALL_40 = RUNNING_SHOES + CASUAL_SHOES + OFFICE_LAPTOPS + ACCESSORIES
assert len(ALL_40) == 40


def pool_with_scores(base_score: float, overrides: dict[str, float]) -> list[RetrievedItem]:
    """Every item in ALL_40 gets `base_score` as its simulated distance for
    this scenario's query, except the ids in `overrides` - lets a scenario
    say "these specific products are relevant to this query, the other ~35
    in the 40-item catalog are not" without hand-scoring all 40 every time."""
    return [{**item, "score": overrides.get(item["id"], base_score)} for item in ALL_40]
