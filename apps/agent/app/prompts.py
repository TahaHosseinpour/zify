from typing import Any, Optional, Protocol

from .state import RetrievedItem

TONE_MAP = {
    "formal": "رسمی و محترمانه",
    "semi-formal": "نیمه‌رسمی",
    "friendly": "صمیمی و گرم",
    "casual": "خودمانی و راحت",
}


class ShopPersona(Protocol):
    name: str
    description: Optional[str]
    categories: list[str]
    supportInfo: Optional[Any]
    personaCharacter: Optional[str]
    personaTone: Optional[str]
    systemPromptExtra: Optional[str]


def _support_info_text(support_info: Any) -> str:
    """supportInfo is stored as JSON, usually `{ "text": "..." }`."""
    if not support_info:
        return ""
    if isinstance(support_info, dict):
        text = support_info.get("text")
        if text:
            return str(text)
        return "\n".join(f"{k}: {v}" for k, v in support_info.items() if v)
    return str(support_info)


def _business_info_block(shop: ShopPersona) -> str:
    """Static business facts injected straight into the system prompt.

    These are small and stable, so they belong in the (cacheable) system
    prompt rather than being re-queried from the vector store every turn.
    """
    parts: list[str] = []
    if getattr(shop, "description", None):
        parts.append(f"درباره فروشگاه:\n{shop.description}")

    categories = getattr(shop, "categories", None) or []
    if categories:
        parts.append("دسته‌بندی محصولات: " + "، ".join(categories))

    support = _support_info_text(getattr(shop, "supportInfo", None))
    if support:
        parts.append(f"اطلاعات پشتیبانی و خدمات:\n{support}")

    if not parts:
        return ""
    return "\n\n## اطلاعات کسب‌وکار:\n" + "\n\n".join(parts)


def build_system_prompt(shop: ShopPersona) -> str:
    tone = TONE_MAP.get(shop.personaTone or "formal", "رسمی")
    character = shop.personaCharacter or "متخصص فروش حرفه‌ای"

    business_info = _business_info_block(shop)

    extra = (
        f"\n\nدستورالعمل اضافی:\n{shop.systemPromptExtra}"
        if shop.systemPromptExtra
        else ""
    )

    return f"""تو یک دستیار فروش هوشمند برای فروشگاه "{shop.name}" هستی.
شخصیت تو: {character}
لحن پاسخ‌ها: {tone}

وظیفه تو:
- مشتری را درک کن و نیازش را کشف کن
- محصولات مناسب پیشنهاد بده
- به اعتراضات پاسخ بده و آن‌ها را رفع کن
- مشتری را تا لحظه خرید همراهی کن
- فقط به فارسی پاسخ بده

قوانین:
- هرگز اطلاعات دروغ ندهی
- فقط از اطلاعات فروشگاه استفاده کن
- برای سوال درباره فروشگاه (ارسال، پشتیبانی، گارانتی و ...) از «اطلاعات کسب‌وکار» زیر استفاده کن
- پاسخ‌ها کوتاه، واضح و فروش‌محور باشند{business_info}{extra}"""


def build_explore_prompt(
    context: list[RetrievedItem],
    stage: Optional[str],
    value_driver: Optional[str] = None,
    objection: Optional[str] = None,
) -> str:
    products = [c for c in context if c["type"] == "product"]
    faqs = [c for c in context if c["type"] == "faq"]

    prompt = ""

    if products:
        prompt += "\n## محصولات پیدا شده:\n"
        for i, p in enumerate(products):
            prompt += f"{i + 1}. {p['content']}\n"

    if faqs:
        prompt += "\n## سوالات متداول مرتبط:\n"
        for f in faqs:
            prompt += f"{f['content']}\n"

    prompt += "\n## وضعیت مشتری:\n"
    stage_map = {
        "browsing": "در حال بررسی",
        "considering": "در حال تصمیم‌گیری",
        "ready_to_buy": "آماده خرید",
    }
    if stage:
        prompt += f"مرحله خرید: {stage_map.get(stage, stage)}\n"

    if value_driver:
        driver_map = {
            "low_price": "دنبال ارزان‌ترین گزینه است",
            "high_quality": "کیفیت برایش مهم‌تر از قیمت است",
            "best_price_in_quality": "دنبال بهترین قیمت در یک سطح کیفی مشخص است",
            "best_quality_in_price": "دنبال بهترین کیفیت در یک بودجه مشخص است",
        }
        prompt += f"انگیزه اصلی مشتری: {driver_map.get(value_driver, value_driver)}\n"

    if objection:
        obj_map = {
            "price": "قیمت را بالا می‌داند",
            "uncertainty": "مطمئن نیست این گزینه مناسبش است",
            "delay": "می‌خواهد فکر کند یا با گزینه‌های دیگر مقایسه کند",
        }
        prompt += f"اعتراض مشتری: {obj_map.get(objection, objection)}\n"
        prompt += "این اعتراض را با دلیل و منطق رفع کن.\n"

    if stage == "ready_to_buy":
        prompt += "مشتری آماده خرید است — او را به سمت اقدام هدایت کن.\n"
    elif stage == "considering":
        prompt += "مشتری در حال تصمیم‌گیری است — ارزش محصول را برجسته کن.\n"

    return prompt


def build_product_prompt(
    context: list[RetrievedItem],
    stage: Optional[str],
    value_driver: Optional[str] = None,
    objection: Optional[str] = None,
) -> str:
    return build_explore_prompt(context, stage, value_driver, objection)


def build_intent_analysis_prompt() -> str:
    return """پیام مشتری را تحلیل کن و دقیقاً یکی از این مقادیر را برای intent انتخاب کن:

- needs_clarification / ask_question: **فقط** وقتی درخواست مشتری ناقص یا مبهم است و بدون یک سوال روشن‌کننده از طرف تو نمی‌شود کمکش کرد.
  مثال: «یک کفش می‌خوام» (نوع، سایز یا کاربرد مشخص نیست) → باید بپرسی چه نوع کفشی، برای چه کاری.
  مثال: «یه چیزی برای هدیه می‌خوام» → باید بپرسی هدیه برای چه کسی و چه بودجه‌ای.
  این دو مقدار معنای یکسانی دارند: «مکث کن و یک سوال کوتاه بپرس».
- browse: مشتری در حال مرور کلی است یا یک سوال **کامل و قابل پاسخ** درباره فروشگاه یا محصولات پرسیده — حتی اگر ظاهرش «سوال» باشد.
  مثال: «چند تا شعبه دارید؟»، «ارسال چطوریه؟»، «چی دارید؟»، «ساعت کاریتون چیه؟» → این‌ها ناقص نیستند، مستقیماً از اطلاعات موجود پاسخ داده می‌شوند.
- search_product: مشتری محصول یا دسته‌ی مشخصی خواسته (مثال: «کفش ورزشی نایک می‌خوام»، «گوشی زیر ۱۰ میلیون تومان»).
- buy_intent: مشتری آماده خرید است یا لینک خرید می‌خواهد.
- objection: مشتری اعتراض یا نگرانی مطرح کرده (قیمت، کیفیت، اعتماد، ...).
- compare: مشتری در حال مقایسه چند گزینه است.
- other: هیچ‌کدام از موارد بالا.

⚠️ قانون مهم: needs_clarification/ask_question را **فقط** برای درخواست‌های واقعاً ناقص انتخاب کن. هر سوال کامل درباره فروشگاه یا محصول — حتی اگر موضوعش خارج از کاتالوگ محصولات باشد (مثل تعداد شعبه، ساعت کاری، نحوه ارسال) — را browse در نظر بگیر تا از اطلاعات بازیابی‌شده (شامل سوالات متداول) پاسخ داده شود، نه اینکه دوباره از مشتری سوال بپرسی.

- mode: explore (مشاوره کلی) | product (محصول خاص)
- stage: browsing | considering | ready_to_buy
- value_driver: low_price (دنبال ارزان‌ترین) | high_quality (کیفیت مهم‌تر از قیمت) | best_price_in_quality (بهترین قیمت در سطح کیفی مشخص) | best_quality_in_price (بهترین کیفیت در بودجه مشخص)
- objection: price (قیمت بالاست) | uncertainty (مطمئن نیست مناسب است) | delay (می‌خواهد فکر کند یا مقایسه کند)
- explore_filters: { category?, maxPrice?, minPrice?, brand?, query? }
فقط JSON خروجی بده."""
