"""Search requests with the products that answer them, for the retrieval
evaluation.

The right answer of every request is derived from the sample shop's own data
(comparison-eval/dataset.py) - by product key, or by a condition on category,
brand and price - so nothing here is a matter of opinion, and a change to the
catalog changes the answers with it.

Six kinds of request:

    name     one product, called by its name
    brand    everything of a brand or a kind
    price    a kind of product inside a price bound
    need     a need described without naming the product that meets it
    sort     the cheapest or the dearest of a kind: exactly one right answer,
             and it has to come first
    absent   something the shop does not sell: the right answer is nothing
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "comparison-eval"))

from dataset import ACCESSORY, BY_KEY, FORMAL, LAPTOP, PRODUCTS, RUNNING  # noqa: E402

KINDS = ["name", "brand", "price", "need", "sort", "absent"]
KIND_LABELS_FA = {
    "name": "نام محصول",
    "brand": "برند یا نوع کالا",
    "price": "قید قیمت",
    "need": "توصیف نیاز",
    "sort": "ارزان‌ترین / گران‌ترین",
    "absent": "کالای ناموجود",
}

M = 1_000_000


@dataclass
class Query:
    id: str
    kind: str
    text: str
    relevant: frozenset[str]  # product keys


def _where(condition) -> frozenset[str]:
    return frozenset(p.key for p in PRODUCTS if condition(p))


def _keys(*keys: str) -> frozenset[str]:
    assert all(k in BY_KEY for k in keys)
    return frozenset(keys)


def _extreme(condition, dearest: bool = False) -> frozenset[str]:
    pick = max if dearest else min
    return frozenset({pick((p for p in PRODUCTS if condition(p)), key=lambda p: p.price).key})


QUERIES: list[Query] = [
    Query("N01", "name", "نایک پگاسوس دارید؟", _keys("shoe-run-2")),
    Query("N02", "name", "لپ‌تاپ لنوو لیجن", _keys("laptop-5")),
    Query("N03", "name", "آسیکس کایانو موجوده؟", _keys("shoe-run-8")),
    Query("N04", "name", "کوله پشتی سفری", _keys("acc-1")),
    Query("N05", "name", "ایسوس زنبوک رو می‌خوام", _keys("laptop-7")),
    Query("N06", "name", "کفش لوفر چرم", _keys("shoe-casual-3")),
    Query("N07", "name", "هدفون بی‌سیم سونی", _keys("acc-9")),
    Query("N08", "name", "asus tuf", _keys("laptop-4")),
    Query("B01", "brand", "کفش دویدن نایک", _where(lambda p: p.brand == "نایک" and p.category == RUNNING)),
    Query("B02", "brand", "لپ‌تاپ ایسوس چی دارید؟", _where(lambda p: p.brand == "ایسوس" and p.category == LAPTOP)),
    Query("B03", "brand", "کفش‌های آدیداس", _where(lambda p: p.brand == "آدیداس" and p.category == RUNNING)),
    Query("B04", "brand", "لپ‌تاپ گیمینگ", _where(lambda p: "گیمینگ" in p.name)),
    Query("B05", "brand", "کفش رسمی", _where(lambda p: p.category == FORMAL)),
    Query("B06", "brand", "لپ‌تاپ اداری", _where(lambda p: "اداری" in p.name)),
    Query("B07", "brand", "از برند بلوط چی دارید؟", _where(lambda p: p.brand == "بلوط")),
    Query("B08", "brand", "کفش دویدن آسیکس", _where(lambda p: p.brand == "آسیکس")),
    Query("P01", "price", "لپ‌تاپ زیر ۲۰ میلیون", _where(lambda p: p.category == LAPTOP and p.price <= 20 * M)),
    Query("P02", "price", "کفش دویدن تا یک و نیم میلیون", _where(lambda p: p.category == RUNNING and p.price <= 1.5 * M)),
    Query("P03", "price", "لپ‌تاپ بالای ۴۰ میلیون", _where(lambda p: p.category == LAPTOP and p.price >= 40 * M)),
    Query("P04", "price", "کفش دویدن بین یک و نیم تا دو میلیون تومان",
          _where(lambda p: p.category == RUNNING and 1.5 * M <= p.price <= 2 * M)),
    Query("P05", "price", "لوازم جانبی زیر ۳۰۰ هزار تومان", _where(lambda p: p.category == ACCESSORY and p.price <= 300_000)),
    Query("P06", "price", "لپ‌تاپ لنوو زیر ۲۵ میلیون",
          _where(lambda p: p.category == LAPTOP and p.brand == "لنوو" and p.price <= 25 * M)),
    Query("P07", "price", "کفش رسمی حداکثر یک میلیون و صد", _where(lambda p: p.category == FORMAL and p.price <= 1_100_000)),
    Query("P08", "price", "لپ‌تاپ بین ۲۰ تا ۳۰ میلیون", _where(lambda p: p.category == LAPTOP and 20 * M <= p.price <= 30 * M)),
    Query("D01", "need", "یه چیزی می‌خوام که تو سفر گوشیم رو شارژ کنه", _keys("acc-8")),
    Query("D02", "need", "کفش برای کسی که کف پاش صافه", _keys("shoe-run-8")),
    Query("D03", "need", "برای دویدن تو کوه و مسیر خاکی کفش می‌خوام", _keys("shoe-run-9")),
    Query("D04", "need", "لپ‌تاپ سبک که راحت جابه‌جاش کنم", _keys("laptop-7", "laptop-1", "laptop-3")),
    Query("D05", "need", "کفشی که برای ایستادن طولانی سر کار مناسب باشه", _keys("shoe-casual-9")),
    Query("D06", "need", "یه چیزی برای محافظت از آفتاب", _keys("acc-3", "acc-6")),
    Query("D07", "need", "برای زمستون یه کفش گرم می‌خوام", _keys("shoe-casual-6")),
    Query("D08", "need", "کیفی که لپ‌تاپ توش جا بشه", _keys("acc-0")),
    Query("T01", "sort", "ارزون‌ترین لپ‌تاپتون کدومه؟", _extreme(lambda p: p.category == LAPTOP)),
    Query("T02", "sort", "گرون‌ترین کفش دویدن", _extreme(lambda p: p.category == RUNNING, dearest=True)),
    Query("T03", "sort", "ارزون‌ترین کفش دویدن نایک", _extreme(lambda p: p.category == RUNNING and p.brand == "نایک")),
    Query("T04", "sort", "گرون‌ترین لپ‌تاپ ایسوس", _extreme(lambda p: p.category == LAPTOP and p.brand == "ایسوس", dearest=True)),
    Query("T05", "sort", "ارزون‌ترین کفش رسمی", _extreme(lambda p: p.category == FORMAL)),
    Query("A01", "absent", "موتور سیکلت برقی دارید؟", frozenset()),
    Query("A02", "absent", "گوشی آیفون می‌خوام", frozenset()),
    Query("A03", "absent", "تلویزیون ۵۵ اینچ", frozenset()),
    Query("A04", "absent", "ماشین لباسشویی دارید؟", frozenset()),
    Query("A05", "absent", "دوچرخه کوهستان", frozenset()),
]  # fmt: skip

assert len({q.id for q in QUERIES}) == len(QUERIES)
assert all(q.relevant or q.kind == "absent" for q in QUERIES)
