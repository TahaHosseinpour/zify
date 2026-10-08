"""The sample shop every comparison scenario runs against.

40 products in 5 categories and 19 brands, two FAQ entries and two shop-info
chunks - the catalog described in EVALUATION_FA.md. It is also what the judges
are handed as ground truth: any name or price in a reply that is not in this
file counts as invented.

The shop's knowledge is incomplete on purpose. Nothing here says anything about
instalments or discount codes, and the scenarios built on that expect the agent
to say it doesn't know rather than make a policy up.
"""

from __future__ import annotations

from dataclasses import dataclass

SHOP_NAME = "فروشگاه تست"
SHOP_SLUG = "comparison-eval-shop"
# Ids are namespaced so seeding can never collide with (or delete) a real row.
ID_PREFIX = "cmpeval-"


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    brand: str
    category: str
    price: int
    description: str

    @property
    def id(self) -> str:
        return ID_PREFIX + self.key

    @property
    def url(self) -> str:
        return f"https://shop.test/{self.key}"


RUNNING = "کفش ورزشی"
LAPTOP = "لپ‌تاپ"
ACCESSORY = "لوازم جانبی"
CASUAL = "کفش روزمره"
FORMAL = "کفش رسمی"

PRODUCTS: list[Product] = [
    # ── کفش ورزشی (running shoes) ────────────────────────────────────────────
    Product("shoe-run-5", "کفش دویدن پوما ولوسیتی", "پوما", RUNNING, 1_250_000, "کفش سبک و اقتصادی، مناسب شروع دویدن"),
    Product("shoe-run-0", "کفش دویدن نایک ایرزوم", "نایک", RUNNING, 1_450_000, "کفش سبک با کفی هوا، مناسب مسافت طولانی"),
    Product("shoe-run-7", "کفش دویدن آدیداس سولار گلاید", "آدیداس", RUNNING, 1_500_000, "کفش پایدار و راحت، مناسب دویدن روزانه"),
    Product("shoe-run-2", "کفش دویدن نایک پگاسوس", "نایک", RUNNING, 1_550_000, "مناسب تمرین روزانه با زیره واکنش‌گرا"),
    Product("shoe-run-1", "کفش دویدن آدیداس اولترابوست", "آدیداس", RUNNING, 1_650_000, "میان‌کفی بوست با برگشت انرژی بالا"),
    Product("shoe-run-4", "کفش دویدن نیوبالانس فرش", "نیوبالانس", RUNNING, 1_700_000, "میان‌کفی نرم و راحت، مناسب مسافت‌های متوسط"),
    Product("shoe-run-3", "کفش دویدن آسیکس جل نیمبوس", "آسیکس", RUNNING, 1_800_000, "جذب ضربه بالا با فناوری ژل"),
    Product("shoe-run-8", "کفش دویدن آسیکس گل کایانو", "آسیکس", RUNNING, 1_900_000, "پشتیبانی بالا برای کف پای صاف"),
    Product("shoe-run-6", "کفش دویدن نایک زوم فلای", "نایک", RUNNING, 2_100_000, "مناسب تمرین سرعت و مسابقه با صفحه کربنی"),
    Product("shoe-run-9", "کفش دویدن سالامون سنس", "سالامون", RUNNING, 2_300_000, "مناسب مسیرهای طبیعی و کوهستانی"),
    # ── لپ‌تاپ ────────────────────────────────────────────────────────────────
    Product("laptop-8", "لپ‌تاپ دانشجویی لنوو آیدیاپد", "لنوو", LAPTOP, 15_200_000, "لپ‌تاپ اقتصادی برای کارهای درسی و اداری سبک"),
    Product("laptop-3", "لپ‌تاپ دانشجویی ایسوس ویووبوک", "ایسوس", LAPTOP, 16_500_000, "لپ‌تاپ سبک با قیمت مناسب، مناسب کارهای درسی و وب"),
    Product("laptop-1", "لپ‌تاپ اداری ایسوس ExpertBook", "ایسوس", LAPTOP, 19_800_000, "لپ‌تاپ سبک و بادوام، مناسب کار روزمره و ارائه"),
    Product("laptop-0", "لپ‌تاپ اداری لنوو ثینک‌پد", "لنوو", LAPTOP, 21_500_000, "صفحه‌کلید راحت و بدنه مقاوم، مناسب کار اداری سنگین"),
    Product("laptop-2", "لپ‌تاپ اداری اچ‌پی پروبوک", "اچ‌پی", LAPTOP, 22_300_000, "امنیت سازمانی و باتری بادوام برای کار اداری"),
    Product("laptop-6", "لپ‌تاپ اداری دل لتیتود", "دل", LAPTOP, 24_000_000, "لپ‌تاپ سازمانی با پشتیبانی طولانی و عمر باتری بالا"),
    Product("laptop-7", "لپ‌تاپ اولترابوک ایسوس زنبوک", "ایسوس", LAPTOP, 28_500_000, "بسیار سبک و باریک با صفحه‌نمایش OLED"),
    Product("laptop-9", "لپ‌تاپ گیمینگ اچ‌پی امن", "اچ‌پی", LAPTOP, 38_000_000, "پردازنده i5، کارت گرافیک RTX 4050، رم ۱۶ گیگ"),
    Product("laptop-4", "لپ‌تاپ گیمینگ ایسوس TUF", "ایسوس", LAPTOP, 42_000_000, "پردازنده i7، کارت گرافیک RTX 4060، رم ۱۶ گیگ"),
    Product("laptop-5", "لپ‌تاپ گیمینگ لنوو لیجن", "لنوو", LAPTOP, 45_000_000, "پردازنده i7، کارت گرافیک RTX 4070، رم ۳۲ گیگ"),
    # ── لوازم جانبی ───────────────────────────────────────────────────────────
    Product("acc-5", "جوراب ورزشی بسته ۳تایی", "نایک", ACCESSORY, 180_000, "جوراب نخی تنفس‌پذیر"),
    Product("acc-6", "کلاه آفتابی", "پوما", ACCESSORY, 220_000, "کلاه سبک با لبه بلند"),
    Product("acc-7", "دستکش ورزشی", "آدیداس", ACCESSORY, 260_000, "دستکش بدنسازی با کف ضد لغزش"),
    Product("acc-4", "کمربند چرم", "بلوط", ACCESSORY, 320_000, "کمربند چرم طبیعی با سگک فلزی"),
    Product("acc-3", "عینک آفتابی", "ری‌بن", ACCESSORY, 750_000, "عینک با لنز پلاریزه و محافظ UV"),
    Product("acc-0", "کیف چرم مردانه", "بلوط", ACCESSORY, 890_000, "کیف اداری چرم طبیعی با جای لپ‌تاپ"),
    Product("acc-8", "پاوربانک ۲۰۰۰۰", "انکر", ACCESSORY, 890_000, "ظرفیت ۲۰۰۰۰ میلی‌آمپر با شارژ سریع"),
    Product("acc-1", "کوله پشتی سفری", "دیوتر", ACCESSORY, 1_200_000, "کوله ۴۰ لیتری ضدآب برای سفر و کوهنوردی"),
    Product("acc-9", "هدفون بی‌سیم", "سونی", ACCESSORY, 1_450_000, "هدفون بلوتوثی با حذف نویز"),
    Product("acc-2", "ساعت مچی کلاسیک", "کاسیو", ACCESSORY, 3_400_000, "ساعت مچی استیل ضدآب"),
    # ── کفش روزمره ───────────────────────────────────────────────────────────
    Product("shoe-casual-7", "کفش راحتی خانگی", "ایگل", CASUAL, 350_000, "نرم و راحت برای استفاده در خانه"),
    Product("shoe-casual-5", "کفش صندل تابستانی", "ایگل", CASUAL, 450_000, "سبک و خنک برای تابستان"),
    Product("shoe-casual-4", "کفش کتانی روزمره ریباک", "ریباک", CASUAL, 890_000, "سبک و راحت برای پیاده‌روی روزانه"),
    Product("shoe-casual-1", "کفش کژوال پوما اسمش", "پوما", CASUAL, 980_000, "رویه چرم مصنوعی، مناسب استفاده روزمره"),
    Product("shoe-casual-9", "کفش طبی راحتی", "ریباک", CASUAL, 1_400_000, "کفی طبی، مناسب ایستادن طولانی"),
    Product("shoe-casual-6", "کفش بوت زمستانی", "کاترپیلار", CASUAL, 1_600_000, "ضدآب و گرم برای زمستان"),
    # ── کفش رسمی ─────────────────────────────────────────────────────────────
    Product("shoe-casual-8", "کفش مجلسی زنانه", "بلوط", FORMAL, 1_050_000, "پاشنه متوسط با رویه چرم"),
    Product("shoe-casual-0", "کفش رسمی چرم مردانه", "بلوط", FORMAL, 1_100_000, "چرم طبیعی، مناسب محیط اداری"),
    Product("shoe-casual-3", "کفش لوفر چرم", "بلوط", FORMAL, 1_150_000, "بدون بند، چرم طبیعی"),
    Product("shoe-casual-2", "کفش کلاسیک آکسفورد", "بلوط", FORMAL, 1_300_000, "طرح کلاسیک بندی برای مراسم رسمی"),
]

FAQS: list[tuple[str, str]] = [
    ("ارسال چطوریه؟", "ارسال به سراسر کشور با پست پیشتاز انجام می‌شود و ۲ تا ۴ روز کاری زمان می‌برد."),
    ("گارانتی دارید؟", "همه محصولات ۷ روز ضمانت بازگشت و ۶ ماه گارانتی تعویض دارند."),
]

SHOP_INFO: list[str] = [
    "فروشگاه ما از سال ۱۴۰۰ فعالیت می‌کند و نماد اعتماد الکترونیکی دارد.",
    "پشتیبانی فروشگاه هر روز از ساعت ۹ صبح تا ۹ شب پاسخگوی مشتریان است.",
]

CATEGORIES = [RUNNING, LAPTOP, ACCESSORY, CASUAL, FORMAL]

BY_KEY = {p.key: p for p in PRODUCTS}
BY_ID = {p.id: p for p in PRODUCTS}

assert len(PRODUCTS) == 40 and len({p.brand for p in PRODUCTS}) == 19


def fa_number(n: int) -> str:
    grouped = f"{n:,}".replace(",", "٬")
    return "".join("۰۱۲۳۴۵۶۷۸۹"[int(ch)] if ch.isdigit() else ch for ch in grouped)


def catalog_as_text() -> str:
    """The whole shop as plain text - the judges' ground truth."""
    lines = ["## محصولات فروشگاه (نام | برند | دسته | قیمت | توضیح | لینک)"]
    for p in PRODUCTS:
        lines.append(
            f"- {p.name} | {p.brand} | {p.category} | {fa_number(p.price)} تومان | {p.description} | {p.url}"
        )
    lines.append("\n## سوالات متداول")
    lines += [f"- {q} — {a}" for q, a in FAQS]
    lines.append("\n## اطلاعات فروشگاه")
    lines += [f"- {text}" for text in SHOP_INFO]
    lines.append("\nهیچ اطلاعات دیگری (پرداخت اقساطی، کد تخفیف، شعبه و ...) درباره این فروشگاه وجود ندارد.")
    return "\n".join(lines)
