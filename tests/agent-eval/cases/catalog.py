"""A small, realistic product catalog shared by every judge case.

Judge cases put these straight into `retrieved_context`/`shown_products`, and
the generation nodes render exactly `content` into the prompt the real LLM
sees (see app/prompts.py's build_explore_prompt: `f"{i+1}. {p['content']}"`)
- so `content` here is built the same way app/graph.py's own
`_product_content` builds it in production, not a debug placeholder. That's
what makes a judge rubric like "mentions the retrieved running shoe" a
meaningful check instead of one that references text the model never saw.

For cases that only need a *structural* stand-in (analyze_intent doesn't read
`content` at all, only `metadata.price`/`type`), tests/conftest.py's `item()`
is still the simpler choice - see node_deterministic_cases.py /
graph_deterministic_cases.py.
"""

from __future__ import annotations

from typing import Optional

from app.state import RetrievedItem


def product(
    id_: str,
    name: str,
    price: int,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    url: Optional[str] = None,
) -> RetrievedItem:
    parts = [f"محصول: {name} | قیمت: {price:,} تومان"]
    if description:
        parts.append(description)
    if brand:
        parts.append(f"برند: {brand}")
    if category:
        parts.append(f"دسته: {category}")
    content = " | ".join(parts)
    return RetrievedItem(
        id=id_,
        type="product",
        content=content,
        score=0.5,
        metadata={
            "name": name,
            "price": price,
            "productUrl": url,
            "brand": brand,
            "category": category,
        },
    )


def faq(id_: str, question: str, answer: str) -> RetrievedItem:
    return RetrievedItem(
        id=id_,
        type="faq",
        content=f"سوال: {question}\nپاسخ: {answer}",
        score=0.4,
    )


def shop_info(id_: str, content: str) -> RetrievedItem:
    return RetrievedItem(id=id_, type="shop_info", content=content, score=0.3)


SHOP_CATEGORIES = ["کفش ورزشی", "کفش رسمی", "لپ‌تاپ"]
SHOP_BRANDS = ["نایک", "آدیداس", "پوما", "ایسوس", "لنوو"]

NIKE_RUNNING = product(
    "p-nike-run",
    "کفش دویدن نایک ایرزوم",
    1_450_000,
    brand="نایک",
    category="کفش ورزشی",
    description="کفش دویدن سبک با کفی هوا، مناسب مسافت طولانی",
    url="https://shop.test/p-nike-run",
)
ADIDAS_RUNNING = product(
    "p-adidas-run",
    "کفش دویدن آدیداس اولترابوست",
    1_650_000,
    brand="آدیداس",
    category="کفش ورزشی",
    description="کفش دویدن با میان‌کفی بوست، برگشت انرژی بالا",
    url="https://shop.test/p-adidas-run",
)
PUMA_CASUAL = product(
    "p-puma-casual",
    "کفش کژوال پوما اسمش",
    980_000,
    brand="پوما",
    category="کفش رسمی",
    description="کفش کژوال روزمره، چرم مصنوعی",
    url="https://shop.test/p-puma-casual",
)
ASUS_GAMING_LAPTOP = product(
    "p-asus-gaming",
    "لپ‌تاپ گیمینگ ایسوس TUF",
    42_000_000,
    brand="ایسوس",
    category="لپ‌تاپ",
    description="پردازنده i7، کارت گرافیک RTX 4060، رم ۱۶ گیگ",
    url="https://shop.test/p-asus-gaming",
)
LENOVO_OFFICE_LAPTOP = product(
    "p-lenovo-office",
    "لپ‌تاپ اداری لنوو ثینک‌پد",
    21_500_000,
    brand="لنوو",
    category="لپ‌تاپ",
    description="سبک، باتری بلندمدت، مناسب کار اداری",
    url="https://shop.test/p-lenovo-office",
)

# A running-shoe pair (same category, different brand/price) - good for
# ranking/comparison scenarios.
RUNNING_SHOES = [NIKE_RUNNING, ADIDAS_RUNNING]
# The fuller catalog a "what do you have" browse turn would realistically
# retrieve across categories.
FULL_CATALOG = [NIKE_RUNNING, ADIDAS_RUNNING, PUMA_CASUAL, ASUS_GAMING_LAPTOP, LENOVO_OFFICE_LAPTOP]

SHIPPING_FAQ = faq(
    "faq-shipping",
    "ارسال چطوریه؟",
    "ارسال به سراسر کشور با پست پیشتاز انجام می‌شود و ۲ تا ۴ روز کاری زمان می‌برد.",
)
WARRANTY_FAQ = faq(
    "faq-warranty",
    "گارانتی دارید؟",
    "همه محصولات ۷ روز ضمانت بازگشت و ۶ ماه گارانتی تعویض دارند.",
)
ABOUT_SHOP_INFO = shop_info(
    "info-about",
    "فروشگاه ما از سال ۱۴۰۰ فعالیت می‌کند و نماد اعتماد الکترونیکی دارد.",
)
